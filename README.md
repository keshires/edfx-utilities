# edfx-utilities

Shared repository for support and day-to-day operational utilities across EDFX, Credit Edge, and RiskCalc.

New here? See [GETTING_STARTED.md](GETTING_STARTED.md) for setup and operations by app.

## Repo Structure

```
edfx-utilities/
│
├── edfx/               ← EDFX scripts, runbooks, utilities
├── credit-edge/        ← Credit Edge scripts, runbooks
├── riskcalc/           ← RiskCalc scripts, runbooks
│
├── docuproj/           ← Cross-repo flow analyzer (standalone project)
│
├── shared/             ← Code shared across all three apps
│   ├── REPOS.md        ← Fleet repo registry (DocuProj reads from here)
│   └── project_paths.py
│
├── docs/
│   ├── architecture.md ← How this repo is organized (the map for new devs)
│   └── contributing.md ← How to add a new script or runbook
│
└── README.md           ← Repo index — what each folder is, quick-start per app
```

## Projects

| Folder | Purpose |
|--------|---------|
| [**edfx/**](edfx/) | Python scripts and runbooks for EDFX — Postgres KPIs, stale-entity refresh, OpenSearch queries, Financials API, DynamoDB batch ops. |
| [**credit-edge/**](credit-edge/) | Scripts and runbooks for Credit Edge support operations. |
| [**riskcalc/**](riskcalc/) | Scripts and runbooks for RiskCalc — SecurityService, LC processing. |
| [**docuproj/**](docuproj/) | Static analyzer for cross-repo flows across the EDFX fleet — traces who calls an endpoint and where it gets its data, with a swimlane dashboard. See [docuproj/README.md](docuproj/README.md). |
| [**shared/**](shared/) | Utilities and config shared across apps — `project_paths.py`, `REPOS.md` fleet registry. |

## Quick Start — pick your app

Each app folder is self-contained: its own `README.md`, `.env.example`, and `requirements.txt`.

```powershell
# Example: EDFX
cd edfx
copy .env.example .env          # fill in your credentials
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

See each app's `README.md` for the full setup and script catalog.