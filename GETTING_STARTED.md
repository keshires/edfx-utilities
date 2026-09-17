# Getting Started with edfx-utilities

This repo is the shared operations toolkit for the **EDFX**, **Credit Edge**, and **RiskCalc**
teams — scripts, runbooks, and SQL for day-to-day support operations, all in one place.

---

## Repo Map

| Folder | App | What's inside |
|--------|-----|---------------|
| `edfx/` | EDFX | Scripts, runbooks, SQL for EDFX support operations |
| `credit-edge/` | Credit Edge | Scripts, runbooks, SQL for Credit Edge support operations |
| `riskcalc/` | RiskCalc | Scripts for RiskCalc SecurityService and LC file processing |
| `docuproj/` | All | Cross-repo flow analyzer — traces request paths across EDFX services |
| `shared/` | All | Shared Python helpers and the fleet repo registry (`REPOS.md`) |
| `docs/` | All | Architecture overview, contributing guide, design docs |

---

## Prerequisites

- **Python 3.12+** — EDFX scripts require 3.13; Credit Edge and RiskCalc work on 3.12
- **PowerShell** — all commands below use PowerShell syntax (Windows)
- **Each app has its own `.venv` and `.env`** — set up only the one you need

Optional:
- **`gh` CLI** — needed only if you use the DocuProj flow-tracing skill with Claude Code

---

## EDFX Operations

### Setup

```powershell
cd edfx
copy .env.example .env    # open .env and fill in all credentials
.\.venv\Scripts\Activate.ps1
```

The venv is pre-built. If you see import errors, run:

```powershell
.\.venv\Scripts\pip install -r requirements.txt
```

### Monthly Stale Entity Refresh

The most common EDFX operation. Finds non-public entities (private + custom) whose PD date
is older than the 1st of the current month and re-submits them for refresh.

**Full runbook:** [`edfx/runbooks/monthly-stale-refresh-runbook.md`](edfx/runbooks/monthly-stale-refresh-runbook.md)

Key things to know before you start:

- **Always use `--stale-date-column pd_last_known_date`.** The default (`updated_date`)
  under-counts by ~10× — it makes entities look "caught up" when they aren't.
- **Run in two phases** (clients first, then Moodys tenant):
  - Phase 1: set `STALE_REFRESH_EXCLUDED_TENANTS=001aJ00000Cwqc2QAB,0014000000NXtS8` in `.env`
  - Phase 2: set `STALE_REFRESH_EXCLUDED_TENANTS=001aJ00000Cwqc2QAB` in `.env`
- **Use batch posting** (the default). `--one-per-request` is no longer needed since
  EDFX-28971 (fixed 2026-07-24) and is ~100× slower.
- **Keep `--workers 3`** when batching. More workers cause sustained HTTP 502 errors.
- **It's iterative** — one run is never done. Refresh → validate → re-refresh until the
  stale count plateaus.

Follow the runbook step-by-step for exact commands.

**Claude Code skill:** `/stale-entity-refresh`

### Portfolio KPI Recalculation

**Runbook:** [`edfx/runbooks/run-portfolio-kpis-postgres.md`](edfx/runbooks/run-portfolio-kpis-postgres.md)

**Claude Code skill:** `/portfolio-kpi-ops`

### Other EDFX Tools

| Script | Purpose | Claude Code skill |
|--------|---------|-------------------|
| `scripts/financials_delete_custom_entity.py` | Delete a custom entity via the Financials API | `/edfx-entity-ops` |
| `scripts/EDFX_ProcessStatus.py` | Check EDFX process/job statuses and produce an error report | `/edfx-entity-ops` |
| `scripts/build_opensearch_entity_query_from_csv.py` | Build an OpenSearch `_search` query from a CSV of company IDs | `/edfx-entity-ops` |
| `scripts/DynamoDB_BatchUpdate_CreatedBy.py` | Batch-update a field across DynamoDB records | `/dynamo-batch-update` |
| `scripts/monitor_entity_refresh_status.py` | Poll real-time entity refresh queue status | — |

---

## Credit Edge Operations

### Setup

```powershell
cd credit-edge
copy .env.example .env    # fill in your credentials
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\Activate.ps1
```

### Slow Stored Procedure — `ce2_get_report_builder_pit_v7`

When this proc degrades from ~1 second to ~1 minute with no data growth, it is almost
always **lock contention** — not a query regression.

**Runbook:** [`credit-edge/runbooks/slow-sp-ce2-report-builder-pit.md`](credit-edge/runbooks/slow-sp-ce2-report-builder-pit.md)

**Diagnostic SQL:** [`credit-edge/sql/diagnose_slow_sp_blocking.sql`](credit-edge/sql/diagnose_slow_sp_blocking.sql)

Run the diagnostic SQL **while the slow query is in progress** and check for
`wait_type LIKE 'LCK_M_%'` with a set `blocking_session_id`. The runbook walks through
diagnosis and the structural fix (READ_COMMITTED_SNAPSHOT isolation).

---

## RiskCalc Operations

### Setup

```powershell
cd riskcalc
copy .env.example .env    # fill in your credentials
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\Activate.ps1
```

### SecurityService.py

Authenticates via the RiskCalc SOAP SecurityService and retrieves user information.

```powershell
python scripts/SecurityService.py
```

Reads `RISKCALC_WSSE_USERNAME`, `RISKCALC_WSSE_PASSWORD`, and related SOAP vars from `.env`
(see `.env.example` for the full list). Output is written to `output/riskcalc/`.

### LC_Process.py

Processes LC batch files from a UNC file share.

```powershell
python scripts/LC_Process.py
```

Reads `LC_BATCH_ROOT_FOLDER` (UNC path) from `.env`. Output and logs go to
`output/riskcalc/` and `logs/riskcalc/`.

---

## Claude Code Skills

If you use **Claude Code** (VS Code extension or CLI), this repo ships skills that let you
run operations by describing what you need in plain English. Skills live in `.claude/skills/`
and are invoked by typing `/skill-name` in Claude Code.

| Skill | Purpose | When to use |
|-------|---------|-------------|
| `/stale-entity-refresh` | Guides the full stale entity refresh workflow | Monthly refresh or ad-hoc private/custom entity refresh |
| `/portfolio-kpi-ops` | Portfolio KPI recalculation and log analysis | Running `calculate_portfolio_kpis` or reading the KPI update log |
| `/edfx-entity-ops` | Delete custom entities, check process statuses, build OpenSearch queries | Ad-hoc entity operations outside the refresh flow |
| `/dynamo-batch-update` | Batch-update a field across DynamoDB records | DynamoDB field migrations |
| `/troubleshooting-edfx-flows` | Trace a request path across EDFX services | Understanding which repos/databases an endpoint touches |
