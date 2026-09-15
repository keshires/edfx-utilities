# Monthly Stale Non-Public Entity Refresh — Runbook

Repeatable monthly process to find and refresh stale **custom** and **private** entities
by their **PD date**. Run from the `edfx/` folder in PowerShell with `.env` populated.
The same commands work every month unchanged — `--date-filter` defaults to the **1st of the
current month**, so running them in August automatically targets `2026-08-01`.

## Why these specific flags (hard-won)

- **Measure staleness by `pd_last_known_date`, NOT `updated_date`.** A refresh bumps
  `updated_date` even when the PD does not advance, so an `updated_date` filter makes the queue
  look "caught up" when it isn't. `pd_last_known_date` is the true signal.
- **Two-phase tenant exclusion — clients first, then Moodys tenant.**
  - **Phase 1** (initial run): set `STALE_REFRESH_EXCLUDED_TENANTS=001aJ00000Cwqc2QAB,0014000000NXtS8`
    to prioritise client entities.
  - **Phase 2** (follow-up run): set `STALE_REFRESH_EXCLUDED_TENANTS=001aJ00000Cwqc2QAB` to pick
    up Moodys tenant `0014000000NXtS8`. The deprecated tenant `001aJ00000Cwqc2QAB` is always excluded.
- **Batch posting is the default — do NOT use `--one-per-request`.** The "Multiple Overlay Process
  Ids" bug that previously required one-per-request was fixed by PR #2564 / EDFX-28971 and deployed
  2026-07-24. Batching is ~100× fewer HTTP calls (197k → ~2k requests for a 200k custom run).
- **Keep `--workers 3` when batching.** `--workers 20` with batched payloads caused sustained HTTP
  502 gateway errors on 2026-07-24. Low workers + batching is the safe shape. (`--one-per-request`
  tolerates 20 workers because payloads are tiny — but don't use it; it's ~10 hrs vs ~6 min.)
- **Residual iterations use precheck → extract → repost, not a full re-refresh.** After the first
  pass, run `validate_pd_precheck.py` to classify the residual into `refreshable` vs `mapped_no_pd`
  vs `orphaned`. Only post the `refreshable` subset via `--allow-ids-file` — avoids futile posts
  and catches orphans before they're mistaken for delete-candidates (see mapping note below).
- **Custom entities need `x-tenant-id` on the mapping fallback call.** The `/entity/v1/mapping`
  endpoint returns empty results for custom external_ids without the `x-tenant-id` header — they
  look orphaned but aren't. Fixed in `validate_pd_precheck.py` (2026-09-09); always use the
  updated script.

## How `refreshEntities` actually works (verified from edfx-tessera-service source)

- **It enqueues, it does not refresh synchronously.** `POST /tesseraui/v1/refreshEntities` returns
  `"Submitted"` (HTTP 200) after putting an SQS message on the refresh queue. The real recompute +
  persist happens **downstream in the SQS consumer** (`EntityRefreshService`). So **a 200 ≠ the PD
  moved.**
- **Therefore re-validate only after the refresh queue drains** — not merely when Postgres "looks
  settled." Low yield seen minutes/hours after posting is usually the async consumer still working
  (or entities that genuinely can't advance), not failed posts.
- The service internally chunks at **5 public / 10 private / 100 custom-financials** per message —
  so a large client `--batch-size` (default 15k) just means fewer HTTP posts with the same downstream throughput.
- `force: true` (which the script sends) bypasses the service's staleness threshold and refreshes
  the named entities regardless of recency.

## PD-date rule per entity type

| Type | PD lands on | "Fresh" means | Stale (in scope) |
|------|-------------|---------------|------------------|
| **Custom** | 1st of the month (always) | `pd_last_known_date` == 1st of current month | `< 1st-of-month` or null |
| **Private** | any day in current month (vendor) | `pd_last_known_date` anywhere in current month | `< 1st-of-month` or null |

Both use the same stale cutoff (`pd_last_known_date < 1st-of-month`); only `--entity-type` differs.

## One-time setup

Add to `.env`:
```
STALE_REFRESH_EXCLUDED_TENANTS=001aJ00000Cwqc2QAB
```
Ensure `.env` also has `TESSERA_POSTGRES_*` (validate) and `MOODYS_SSO_USERNAME` /
`MOODYS_SSO_PASSWORD` / `TESSERA_BASE_URL` (refresh).

## The monthly steps

### 1. Look for stale entities (read-only)
```
.\.venv\Scripts\python validate_stale_entities.py --entity-type custom --stale-date-column pd_last_known_date
```
```
.\.venv\Scripts\python validate_stale_entities.py --entity-type private --stale-date-column pd_last_known_date
```
Writes a CSV under `output\validate_stale_entities\` + a `.summary.json` (with the count) under
`logs\validate_stale_entities\`. Restrict to one tenant with `--tenant-id <id>`.

### 1b. (Optional) PD pre-check report — see what's worth refreshing / what's orphaned
```
.\.venv\Scripts\python validate_pd_precheck.py --entity-type custom   # or private / public
```
Classifies the stale set using the authoritative PD check:
- **private/custom** → `/edfx/v1/entities/pds` (custom uses `externalId-financialsProcessId`);
  if pds has no data → `/entity/v1/mapping`; empty ⇒ **orphaned** (written to a separate
  `.orphaned.csv` delete-candidate list). Buckets: `refreshable`/`current_pd` (POST),
  `no_pd`/`source_stale`/`mapped_no_pd`/`orphaned` (SKIP).
- **public** → DB-only, report-only: `public_fresh` (current-month PD + Active/null status)
  vs `public_stale`.
Needs SSO env (private/custom). Add `--limit N` to sample. Read-only — never posts.

### 2. Dry-run the refresh (no posting; confirms the count)
```
.\.venv\Scripts\python refresh_stale_non_public_entities.py --entity-type custom --stale-date-column pd_last_known_date --dry-run
```

### 3. Live refresh (posts to queue, batched)
```
.\.venv\Scripts\python refresh_stale_non_public_entities.py --entity-type custom --stale-date-column pd_last_known_date --workers 3
```
Repeat steps 2–3 with `--entity-type private`.

### 3b. Check entity_refresh_status for downstream failures and resubmit

After posting the live refresh, check the `entity_refresh_status` table for entities that
failed during downstream processing (the SQS consumer, not the HTTP submission itself).
These failures are independent of the stale-date filter — an entity may have received a 200
from `refreshEntities` but still failed inside `EntityRefreshService`.

```powershell
# Report only — see what failed since the start of the month
.\.venv\Scripts\python monitor_entity_refresh_status.py --source Scoring --since 2026-08-01

# Resubmit failures (dry-run first)
.\.venv\Scripts\python monitor_entity_refresh_status.py --source Scoring --since 2026-08-01 --resubmit --dry-run

# Resubmit failures (live)
.\.venv\Scripts\python monitor_entity_refresh_status.py --source Scoring --since 2026-08-01 --resubmit --workers 3
```

Tip: use `--since` matching the current month's 1st (same date as `--date-filter` in the refresh
run). Use `--correlation-id <id>` to scope to a specific batch from the refresh log.
The CSV output shows `entity_type_resolved` (custom/private/not_found) and the action taken.

### 4. Re-validate & iterate (precheck → extract → repost)

After the queue settles (allow ≥24 hrs — the consumer is async), run the PD pre-check on the
residual instead of blindly re-posting everything. This avoids futile posts for `mapped_no_pd`
and `orphaned` entities and catches orphans before they get posted again.

**a. Run the pre-check**
```powershell
.\.venv\Scripts\python validate_pd_precheck.py --entity-type custom   # or private
```
Output: a CSV at `output\validate_pd_precheck\pd_precheck_custom_<ts>.csv` with columns
`external_id, tenant_id, category, action, reason`.

**b. Extract only the refreshable IDs** (action == 'POST')
```python
import csv, pathlib
src = pathlib.Path(r"output\validate_pd_precheck\pd_precheck_custom_<ts>.csv")
ids = [r["external_id"] for r in csv.DictReader(src.open()) if r["action"] == "POST"]
out = src.with_name(src.stem + "_refreshable_ids.txt")
out.write_text("\n".join(ids))
print(f"{len(ids)} refreshable → {out}")
```
Or run it as a one-liner inline with python:
```powershell
.\.venv\Scripts\python -c "
import csv, pathlib
src = pathlib.Path(r'output/validate_pd_precheck/pd_precheck_custom_<ts>.csv')
ids = [r['external_id'] for r in csv.DictReader(src.open()) if r['action'] == 'POST']
out = src.with_name(src.stem + '_refreshable_ids.txt')
out.write_text('\n'.join(ids))
print(len(ids), 'refreshable ->', out)
"
```

**c. Repost only the refreshable subset**
```powershell
.\.venv\Scripts\python refresh_stale_non_public_entities.py `
    --entity-type custom --stale-date-column pd_last_known_date `
    --workers 3 --allow-ids-file "output\validate_pd_precheck\pd_precheck_custom_<ts>_refreshable_ids.txt"
```

Repeat steps a–c until the pre-check shows zero `action == 'POST'` entities. Also run step 3b
on each repost.

**Categories to skip (do NOT repost):**
- `mapped_no_pd` — entity exists in mapping but has no PD source data yet; posting it again
  won't advance the PD until the source data arrives.
- `orphaned` — not in mapping; candidate for deletion, not refresh.
- `source_stale` — PD source data is too old (>3 yrs); posting won't help.
- `current_pd` — PD is already current-month; skip.

**Note:** Run `monitor_entity_refresh_status.py` (step 3b) after each repost to catch
downstream consumer failures independent of the HTTP 200 submission response.

### 5. Spot-verify (optional)
```
.\.venv\Scripts\python test_single_entity_refresh.py --entity-type custom --count 10
```
Submits a few individually and polls until `pd_last_known_date` advances.

## Explicit month override (optional)
`--date-filter` defaults to the 1st of the current month. To target a specific month:
```
... --date-filter 2026-08-01
```

## Not yet automated
- **Public** entities (report-only, vendor-driven) and the **peer-group-aware pre-check**
  (skip entities whose peer group already has the PD; don't post futile ones) are a planned
  feature, not in these commands yet.
