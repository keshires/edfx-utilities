# edfx-utilities — Getting Started Doc + MyUtilities Rename Cleanup Design

**Date:** 2026-09-17
**Status:** Approved — ready for implementation
**Branch:** feat/add-credit-edge-repos

---

## Goals

1. **Rename cleanup** — remove all remaining `MyUtilities` references left over from the repo rename. Targets: `pyvenv.cfg` metadata files and stale allowed-commands in `.claude/settings.json`.
2. **Team onboarding doc** — add `GETTING_STARTED.md` at the repo root so any engineer on EDFX, Credit Edge, or RiskCalc can orient, set up, and run day-to-day operations without prior knowledge of this repo.

---

## Part 1 — MyUtilities Rename Cleanup

### Files to fix

| File | Change |
|------|--------|
| `edfx/.venv/pyvenv.cfg` | Update `executable` + `command` from `C:\Github\MyUtilities\Day2Day_Utillites\...` to `C:\Github\edfx-utilities\edfx\...` |
| `docuproj/.venv/pyvenv.cfg` | Update `command` from `C:\Github\MyUtilities\DocuProj\...` to `C:\Github\edfx-utilities\docuproj\...` |
| `.claude/settings.json` | Remove the two obsolete allowed commands: the `mv MyUtilities → edfx-utilities` and the `cp -r .claude/projects/c--Github-MyUtilities` entries |

### What does NOT need changing

- All `.py`, `.md`, `.yaml`, `.env`, `.toml` files are already clean.
- `shared/REPOS.md` — already correct.
- `~/.claude/skills/edfx-pr-review/SKILL.md` — fixed in the prior session (line 24).
- The `.claude/settings.json` entries are the only remaining live references outside `pyvenv.cfg`.

### Verification

After edits, run:
```powershell
grep -r "MyUtil" . --include="*.cfg" --include="*.json" --include="*.md" --include="*.py" --include="*.yaml"
```
Expected: zero hits outside `.git/`.

---

## Part 2 — GETTING_STARTED.md

### Location

`GETTING_STARTED.md` at the repo root — surfaced by GitHub alongside README, first thing a new team member sees.

### Audience

Cross-team engineers (EDFX, Credit Edge, RiskCalc) who are new to this repo. Assumes Python and PowerShell familiarity; does not assume knowledge of any specific app's internals.

### Structure

```
GETTING_STARTED.md
│
├── What is this repo?
├── Repo map
├── Prerequisites
│
├── EDFX Operations
│   ├── Setup
│   ├── Monthly stale entity refresh  (primary op — link to runbook + skill)
│   ├── Portfolio KPI recalculation   (reference — see skill)
│   └── Other EDFX tools             (entity ops, DynamoDB batch update — see skills)
│
├── Credit Edge Operations
│   ├── Setup
│   └── Slow stored-procedure runbook (link to runbook + SQL diagnostic)
│
├── RiskCalc Operations
│   ├── Setup
│   ├── SecurityService.py
│   └── LC_Process.py
│
└── Claude Code Skills (optional — for Claude Code users on the team)
```

### Section detail

**What is this repo?**
Two sentences: shared ops utilities for the EDFX, Credit Edge, and RiskCalc teams — scripts, runbooks, and SQL for day-to-day support operations, all in one place.

**Repo map**
Table with columns: Folder | App | What's inside. Rows: `edfx/`, `credit-edge/`, `riskcalc/`, `docuproj/`, `shared/`, `docs/`.

**Prerequisites**
- Python 3.12+ (EDFX uses 3.13; Credit Edge / RiskCalc use 3.12)
- PowerShell (Windows)
- Each app has its own `.venv` and `.env` — set up only the one you need
- `gh` CLI (optional, needed for DocuProj PR review skill)

**EDFX Operations — Setup**
```powershell
cd edfx
copy .env.example .env    # fill in credentials
.\.venv\Scripts\Activate.ps1
```
Note: venv is pre-built; no `pip install` needed unless packages changed.

**EDFX Operations — Monthly stale entity refresh**
The most common op. Key points (don't duplicate the full runbook, just orient):
- Full runbook: `edfx/runbooks/monthly-stale-refresh-runbook.md`
- Two-phase tenant strategy (clients first, then Moodys tenant)
- Always use `--stale-date-column pd_last_known_date`
- Batch posting is the default (one-per-request is NOT needed since EDFX-28971)
- It's iterative: refresh → validate → re-refresh until count plateaus
- Claude Code skill: `/stale-entity-refresh`

**EDFX Operations — Portfolio KPI recalculation**
Reference only: `edfx/runbooks/run-portfolio-kpis-postgres.md` and `/portfolio-kpi-ops` skill.

**EDFX Operations — Other EDFX tools**
Table listing scripts with one-line purpose and the corresponding skill (if any):
- `financials_delete_custom_entity.py` → `/edfx-entity-ops`
- `EDFX_ProcessStatus.py` → `/edfx-entity-ops`
- `build_opensearch_entity_query_from_csv.py` → `/edfx-entity-ops`
- `DynamoDB_BatchUpdate_CreatedBy.py` → `/dynamo-batch-update`
- `monitor_entity_refresh_status.py` → no skill; run directly

**Credit Edge Operations — Setup**
```powershell
cd credit-edge
copy .env.example .env
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

**Credit Edge Operations — Slow SP runbook**
When `ce2_get_report_builder_pit_v7` degrades from ~1s to ~1 min:
- Runbook: `credit-edge/runbooks/slow-sp-ce2-report-builder-pit.md`
- Diagnostic SQL: `credit-edge/sql/diagnose_slow_sp_blocking.sql`
- Root cause is almost always lock contention (SUSPENDED wait), not query regression.

**RiskCalc Operations — Setup**
```powershell
cd riskcalc
copy .env.example .env
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

**RiskCalc Operations — Scripts**
- `SecurityService.py` — authenticate via RiskCalc SOAP SecurityService; retrieve user info. Reads `RC_BASE_URL`, `RC_USERNAME`, `RC_PASSWORD` from `.env`.
- `LC_Process.py` — process LC batch files from a UNC file share. Reads file share path from `.env`.

**Claude Code Skills**
For team members using Claude Code (VS Code extension or CLI). Skills live in `.claude/skills/` and are invoked with `/skill-name`. Table: skill name | what it does | when to use.

### Writing style constraints

- Each section title maps 1:1 to the structure above — no invented sections.
- Runbook links use relative paths from repo root.
- Code blocks use `powershell` fence (Windows team).
- No duplication of runbook content — orient and link, do not copy.
- Imperative tone ("Run X", "Set Y") — not passive.

---

## Out of scope

- Modifying existing runbooks or scripts.
- Adding new scripts.
- Documenting DocuProj (it has its own README).
- Portfolio KPI recalculation as a detailed section (reference only per user preference).
