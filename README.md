# LedgerIQ — Smart Expense & Financial Advisor

Personal-finance web app built from the project SRS (v1.0) and use-case diagram.
Track income and expenses, set budgets and savings goals, view dashboards/reports, get rule-based advice and
see future predictions (next-year budget, balance after one year, projections).

**Team:** Gungun Bhandari (EN24CS3010412) · Gitika Jain (EN24CS3010405)

## Features (use-case diagram → app)
| Use case | Where |
|---|---|
| Register / Login, Manage Profile | login screen, **Profile** |
| Manage Transactions, Search / Filter | **Transactions** (add/edit/delete, search, filters, CSV export) |
| Manage Budgets (+ threshold alerts) | **Budgets** |
| Set Savings Goals (+ monthly suggestion) | **Savings goals** |
| View Dashboard | **Dashboard** |
| View Reports → *extends* Future Prediction | **Reports** → **Future prediction** |
| Generate Next Year Budget / Forecast Balance (1 yr) / Financial Projections | **Future prediction** tabs |
| Get Financial Advice | **Financial advisor** |
| Manage Notifications | **Notifications** + preferences |

## Tech stack
Flask (Python 3.12) REST API · SQLite locally / **PostgreSQL** in production (same SQL, no ORM) ·
vanilla JS single-page UI with dependency-free SVG charts · strict CSP · unittest suite (23 tests).

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python seed_demo.py          # optional: demo data  (demo@ledgeriq.app / Demo@1234)
python wsgi.py               # http://localhost:5000
python -m unittest discover -s tests -v
```
With Docker + PostgreSQL: `docker compose up --build`.

## Configuration
| Variable | Purpose |
|---|---|
| `DATABASE_URL` | `postgresql://…` for PostgreSQL. If unset, a local SQLite file `instance/ledgeriq.db` is used. Tables are created automatically on start-up. |
| `SECRET_KEY` | **Required** when `APP_ENV=production` (signs session cookies). |
| `APP_ENV=production` | Enables Secure cookies + HSTS. |
| `TRUST_PROXY=1` | Behind a reverse proxy such as Render/Heroku. |

## Push to GitHub
```bash
git init -b main && git add . && git commit -m "LedgerIQ: Smart Expense & Financial Advisor"
# create an empty repo on github.com first (no README), then:
git remote add origin https://github.com/<your-username>/ledgeriq.git
git push -u origin main
```
(or with GitHub CLI: `gh repo create ledgeriq --public --source=. --push`)

## Deploy (Render + PostgreSQL, free tier)
1. Push to GitHub (above).
2. Render dashboard → **New → Blueprint** → select the repo. `render.yaml` provisions the web service **and** a PostgreSQL database, wires `DATABASE_URL`, and generates `SECRET_KEY`.
3. Open the service URL; `/api/health` should return `{"status":"ok"}`.

Other hosts work too: any platform that runs `gunicorn wsgi:app` and gives you a Postgres URL
(Railway, Fly.io, Koyeb, Azure, a VPS with `docker compose`). Free Postgres options: Neon, Supabase, Render.
> Free tiers sleep when idle and some free databases expire — check your provider's current terms before a final demo.

## Project layout
```
app/            Flask package: auth, finance, insights (API) · advisor, forecast (rule engines) · queries, notify · static/ (UI)
tests/          unit + API tests        docs/       user guide, requirements traceability
seed_demo.py    demo data               render.yaml / Dockerfile / docker-compose.yml / Procfile
```

## Notes & limitations
- Advice and forecasts are simple rule/average based estimates, labelled as such in the UI; not financial advice.
- Out of scope per SRS TBD list: receipt scanning, bank/UPI import, email notifications (in-app alerts only).
- Login throttling is in-memory per worker; use a shared store (e.g. Redis) if you scale out.
