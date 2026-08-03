# Setup

From a fresh clone to a working demo. Roughly ten minutes, most of it
`npm install`.

---

## Prerequisites

| | Version | Check |
|---|---|---|
| Python | 3.10+ | `python --version` |
| Node.js | 18+ | `node --version` |
| Docker | any recent | `docker --version` |

Docker is only used for Postgres. If you'd rather not install it, see
[Running without Docker](#running-without-docker) below — the app has a SQLite
fallback and will still work.

---

## Step 1 — Get a Groq API key

1. Sign up at <https://console.groq.com>
2. Go to **API Keys** → **Create API Key**
3. Copy it immediately — Groq shows it once

The free tier is generous enough for the whole demo. You'll use maybe 200
requests testing and recording.

---

## Step 2 — Start Postgres

```bash
cd aivoa-cms
docker compose up -d db
```

Confirm it's healthy:

```bash
docker compose ps
# STATUS should read "healthy" after ~10 seconds
```

Credentials are baked into `docker-compose.yml` (`aivoa` / `aivoa` /
`aivoa_cms`) and match the default `DATABASE_URL`. Nothing to configure.

---

## Step 3 — Backend

```bash
cd backend

# Virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

Create your `.env`:

```bash
cp .env.example .env              # Windows: copy .env.example .env
```

Open `backend/.env` and paste your key:

```ini
GROQ_API_KEY=gsk_your_actual_key_here
DATABASE_URL=postgresql+psycopg://aivoa:aivoa@localhost:5432/aivoa_cms
LOG_LEVEL=INFO
```

Generate the demo documents:

```bash
python scripts/generate_sample_docs.py
```

```
  ✓ sample_documents/complaint_metformin_api.pdf
  ✓ sample_documents/complaint_amoxicillin_fdf.pdf
  ✓ sample_documents/complaint_cetirizine_email.eml
```

Start the server:

```bash
uvicorn app.main:app --reload
```

You should see:

```
INFO  app.main      Starting AIVOA Complaint Management System
INFO  app.database  Connected to database: localhost:5432/aivoa_cms
INFO  app.database  Schema ready
WARN  app.llm       gemma2-9b-it (named in the assignment) is not available on
                    this Groq account. Falling back to extraction=llama-3.1-8b-instant,
                    reasoning=llama-3.3-70b-versatile. See docs/MODEL_NOTES.md.
INFO  app.llm       Model resolution complete: reasoning=llama-3.3-70b-versatile
                    extraction=llama-3.1-8b-instant (18 live models)
INFO  app.graph     LangGraph compiled with 13 nodes
```

That warning is expected and correct — see `docs/MODEL_NOTES.md`. Tables are
created automatically on first start; there's no migration step.

Verify:

```bash
curl localhost:8000/api/health
```

---

## Step 4 — Frontend

New terminal:

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>

No `.env` needed. Vite proxies `/api` to `localhost:8000`, so the browser sees
one origin and CORS never comes up.

---

## Step 5 — Verify it works

Type into the assistant on the right:

```
Apollo Pharmacy reported discoloured capsules in Amoxicillin Capsules 500 mg
```

Within a few seconds the left form should populate — product name, strength,
customer, complaint type, description — with each written field flashing blue,
and the risk assessment should appear below the chat.

Then send:

```
sorry, the batch number is BMX24602 and the affected quantity is 48 capsules
```

**Only those two fields should flash.** Everything from the first message stays
put. That's the behaviour to show on camera.

Then drag `backend/sample_documents/complaint_metformin_api.pdf` onto the drop
zone.

---

## Running without Docker

The app falls back to SQLite automatically if Postgres is unreachable. Leave
`DATABASE_URL` as-is and start the backend — you'll see:

```
WARN  Could not connect to localhost:5432/aivoa_cms. Falling back to SQLite...
```

Everything works, including duplicate detection. The fallback exists so a
laptop with no Docker can still record a demo, but Postgres is the intended
target and worth using for the submission.

**Local Postgres instead of Docker:**

```sql
CREATE DATABASE aivoa_cms;
CREATE USER aivoa WITH PASSWORD 'aivoa';
GRANT ALL PRIVILEGES ON DATABASE aivoa_cms TO aivoa;
```

Then point `DATABASE_URL` at it.

**MySQL instead of Postgres** — the brief allows either:

```bash
pip install pymysql
```

```ini
DATABASE_URL=mysql+pymysql://aivoa:aivoa@localhost:3306/aivoa_cms
```

The ORM layer is unchanged. Note that `JSON` columns behave slightly
differently on MySQL 5.7; 8.0+ is fine.

---

## Tests

```bash
cd backend
pytest -v
```

Nine tests, no API key and no database required.

---

## Troubleshooting

**`GROQ_API_KEY is not set`**
`.env` must be in `backend/`, not the repo root. Restart uvicorn after editing
it — `--reload` watches `.py` files, not `.env`.

**Frontend loads but shows "Could not reach the backend"**
Backend isn't running, or isn't on port 8000. Check `curl localhost:8000/api/health`.

**`ModuleNotFoundError: No module named 'app'`**
Run uvicorn from `backend/`, not the repo root.

**Postgres connection refused**
`docker compose ps` — if the container is starting, wait for `healthy`. If port
5432 is taken by a local Postgres, either stop it or change the host port in
`docker-compose.yml` and match it in `DATABASE_URL`.

**Rate limited by Groq**
Free tier limits requests per minute. Each turn makes 2–4 LLM calls. Wait a
minute, or set both preferences to `llama-3.1-8b-instant` in `config.py` for a
higher limit.

**Extraction returns empty fields from a PDF**
The PDF has no text layer (it's a scan). Production OCR is out of scope per the
brief — use the "Paste Complaint Text / Email" button instead. The generated
sample PDFs all have proper text layers.

**`npm install` fails on Node 16**
Vite 6 needs Node 18+.

---

## Resetting

```bash
# Wipe the database
docker compose down -v && docker compose up -d db

# Or for the SQLite fallback
rm backend/aivoa_cms.db
```

Tables are recreated on next start. Useful before recording so complaint
numbers begin at `CC-2026-0001`.

Note that duplicate detection needs prior complaints in the table to have
anything to match against — log one complaint, then log a second on the same
batch to demonstrate it.
