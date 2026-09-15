---
name: stale-entity-refresh
description: Use when refreshing or reconciling stale non-public (private/custom) entities, or running the monthly stale-entity refresh — finding which external ids are stale by pd_last_known_date, exporting them, submitting refreshes via the Tessera refreshEntities API, or verifying a refresh actually advanced the PD.
---

# Stale Entity Refresh

Tools live in `edfx/scripts/`. Run everything from `edfx/` with its venv
(`.\.venv\Scripts\python`), with `.env` populated at `edfx/.env`. Canonical args/env for every
command are in `edfx/utilities.yaml` (browse via the dashboard). Full monthly procedure:
`edfx/runbooks/monthly-stale-refresh-runbook.md`.

## Three corrections that matter (get these wrong and the run is invalid)

- **Measure staleness by `--stale-date-column pd_last_known_date`, NOT the default `updated_date`.**
  A refresh bumps `updated_date` even when the PD doesn't advance, so `updated_date` makes the queue
  look caught up when it isn't. `pd_last_known_date` is the true signal.
- **Two-phase tenant exclusion — clients first, then Moodys tenant.**
  - **Phase 1** (initial/overnight): set `STALE_REFRESH_EXCLUDED_TENANTS=001aJ00000Cwqc2QAB,0014000000NXtS8`
    to prioritise client entities first.
  - **Phase 2** (follow-up): set `STALE_REFRESH_EXCLUDED_TENANTS=001aJ00000Cwqc2QAB` to pick up
    Moodys tenant `0014000000NXtS8`. The deprecated giant `001aJ00000Cwqc2QAB` is **always excluded**.
- **Batch posting is the default — do NOT use `--one-per-request` unless explicitly asked.** The
  "Multiple Overlay Process Ids found" failure on large mixed-overlay batches was fixed by
  [edfx-tessera-service PR #2564 / EDFX-28971](https://github.com/moodysanalytics/edfx-tessera-service/pull/2564)
  (each batch is grouped by its `(qualitative-overlay, parent-group-support)` process-id pair and
  fanned out into one PD request per group, then merged — instead of raising) — **deployed to prod
  2026-07-24**. The service also re-chunks internally (5 public / 10 private / 100 custom-financials
  per SQS message), so a larger client `--batch-size` (default 15000) just means fewer HTTP posts.
  **Keep `--workers` LOW when batching** (~3, with `--batch-size` ~100): ~20 workers × 100-entity
  payloads overwhelmed the API gateway with sustained **HTTP 502** on 2026-07-24, while 3 concurrent
  was clean. (Batch-size-1 tolerates ~20 workers because those payloads are tiny.) So: batch → few
  workers; one-per-request → many workers.
  `refreshEntities` still **enqueues asynchronously** — a 200 means "Submitted", NOT that the PD
  moved; the SQS consumer recomputes downstream. **Re-validate only after the refresh queue drains**,
  not just when Postgres looks settled (low mid-processing yield is expected, not failure). Iterate on
  the residual until it plateaus. (Verified from source — see memory `edfx-refresh-mechanics`.)

## Monthly run (custom + private, by PD date)

Same commands every month — `--date-filter` defaults to the 1st of the current month (August
auto-targets `2026-08-01`; override with `--date-filter YYYY-MM-01`).

1. **Find stale (read-only)** — per type, writes CSV + `.summary.json`:
   `python validate_stale_entities.py --entity-type custom --stale-date-column pd_last_known_date`
   (repeat with `--entity-type private`; one tenant only: add `--tenant-id <id>`).
2. **Dry-run** (no posting, confirm count):
   `python refresh_stale_non_public_entities.py --entity-type custom --stale-date-column pd_last_known_date --dry-run`
3. **Live refresh** (posts to prod queue, batched):
   `python refresh_stale_non_public_entities.py --entity-type custom --stale-date-column pd_last_known_date --workers 3`
   (repeat with `--entity-type private`; add `--one-per-request` only if explicitly instructed — see the batch note above; one-per-request tolerates `--workers 20` but is ~100× slower).
3b. **Check entity_refresh_status for downstream failures** — entities that received a 200 from
   `refreshEntities` but failed inside the SQS consumer (`EntityRefreshService`) need to be
   resubmitted. This is independent of the stale-date check:
   ```
   python monitor_entity_refresh_status.py --source Scoring --since 2026-08-01
   python monitor_entity_refresh_status.py --source Scoring --since 2026-08-01 --resubmit --dry-run
   python monitor_entity_refresh_status.py --source Scoring --since 2026-08-01 --resubmit --workers 3
   ```
   Resolves `custom_id` via JOIN with `public.entity` to pick the right `payload_type`. Entities not
   found in `public.entity` are logged as `not_found` and skipped. Add `--correlation-id <id>` to
   scope to a specific batch. Read-only without `--resubmit`.
4. **Re-validate & iterate using precheck → extract → repost** (allow ≥24 hrs for the async queue):
   - Run precheck: `python validate_pd_precheck.py --entity-type custom`
   - Extract refreshable IDs (action == 'POST') from the output CSV into a `.txt` file
   - Repost only those: `python refresh_stale_non_public_entities.py --entity-type custom --stale-date-column pd_last_known_date --workers 3 --allow-ids-file <path>`
   - Skip `mapped_no_pd`, `orphaned`, `source_stale`, `current_pd` — reposting them won't advance the PD.
   - Run step 3b after each repost. Repeat until precheck shows zero `action == 'POST'`.
5. **Spot-verify (optional):** `python test_single_entity_refresh.py --entity-type custom --count 10`
   — submits a few individually and polls until `pd_last_known_date` advances.

## PD eligibility validation report (`validate_pd_precheck.py`) — team command

**Command** (run from `edfx/`, read-only, never posts):
```powershell
.\.venv\Scripts\python validate_pd_precheck.py --entity-type custom    # or: private | public
#   --date-filter YYYY-MM-01   (default: 1st of the current month)
#   --limit N                  (sample a subset for a quick look)
```

**Purpose:** before posting anything to `refreshEntities`, determine which stale entities are
actually *eligible / worth* refreshing — so the team avoids futile queue posts and gets an
actionable data-quality view (orphans to clean up; custom financials not completed).

**What it does:** finds stale entities (`pd_last_known_date < 1st-of-month`, with `financialStmtDate ≤3y`), then:
- **private / custom** — authoritative PD check via `/edfx/v1/entities/pds` (custom id =
  `externalId-financialsProcessId`); if pds has no data → `/entity/v1/mapping`; in **neither ⇒ orphaned**.
- **public** — DB-only, report-only (`public_fresh` = current-month PD + Active/null status, else `public_stale`).

**Buckets:** `current_pd`/`refreshable` → POST (worth refreshing) · `no_pd`/`source_stale`/`mapped_no_pd` → SKIP (futile) · `orphaned` → SKIP + delete-candidate.

**Custom entity mapping fix (2026-09-09):** `/entity/v1/mapping` requires `x-tenant-id` header
for custom entities — without it, tenant-scoped external_ids return empty and entities are
falsely classified as orphaned. Fixed in `validate_pd_precheck.py`; always use the updated script.

**Outputs** (`output/validate_pd_precheck/` + `.summary.json` in `logs/validate_pd_precheck/`):
- `pd_precheck_<type>_<ts>.csv` — every stale entity + category/action/reason (+ `financials_process_status` for custom).
- `…orphaned.csv` — delete-candidates.
- `…financials_not_completed.csv` (**custom only**) — entities whose `financials_process_status <> Completed`.

**Prereqs:** `.env` needs `TESSERA_POSTGRES_*` (all) + `MOODYS_SSO_*` / `TESSERA_BASE_URL` (private/custom) + `STALE_REFRESH_EXCLUDED_TENANTS=001aJ00000Cwqc2QAB`.
Design: `docs/superpowers/specs/2026-07-15-pd-aware-presubmission-validation-design.md`.
(The refresh's `--pd-precheck` flag uses the older DB-max peer heuristic; this report is the authoritative pds path.)

Outputs: `output/<script>/…` (CSVs, snapshots) and `logs/<script>/…` (run log + `.summary.json`).

## PD-date rule per type
- **Custom:** PD lands on the **1st** of the month (fresh = pd_last_known_date == 1st).
- **Private:** PD lands **any day** in the current month (vendor-dependent).
- Both share the stale cutoff `pd_last_known_date < 1st-of-month`; only `--entity-type` differs.
- **Public** entities are vendor-driven (refreshed by the separate daily `edfx-portfolio-refresh-batch`) — not refreshable here; report-only via the validation report.

## Safety
- `refresh_*` and `test_single_*` **write to prod** via Tessera. Dry-run, small `--limit`/`--count`, verify, then scale.
- `validate_*` / `export_*` are read-only Postgres queries.

## Prereqs
`.env` must have `MOODYS_SSO_USERNAME`, `MOODYS_SSO_PASSWORD`, `TESSERA_BASE_URL`, the
`TESSERA_POSTGRES_*` group, and `STALE_REFRESH_EXCLUDED_TENANTS=001aJ00000Cwqc2QAB`.

## Dashboard
```powershell
cd edfx
.\.venv\Scripts\python -m uvicorn dashboard.serve:app --host 127.0.0.1 --port 8021
# http://127.0.0.1:8021/app/ — cards, copy-ready commands, recent run history.
```
