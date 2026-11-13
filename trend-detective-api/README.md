# Trend Detective backend

FastAPI + stats engine. Real NASA POWER (MERRA-2) monthly data only. Honest errors, never fake numbers.

## Run locally
```
pip install -r requirements.txt
python -m pytest -q                     # 17 tests, no network needed
uvicorn app.main:app --reload --port 8000
# open http://localhost:8000/analyze?lat=-3.1&lon=-60.0   (needs internet to reach NASA)
```

## First real-data check (do this before anything else)
Open the URL above. Confirm: HTTP 200, `years` starts at 1981, `temperature.values` look like plausible
annual means for the Amazon (roughly 25-28 C), `precipitation.unit` is mm/day. If NASA returns a different
JSON shape, only `app/power.py::_parse` needs changing.

## Supabase cache (optional; in-memory cache is used if unset)
Run in the Supabase SQL editor:
```sql
create table if not exists analysis_cache (
  key text primary key,
  payload jsonb not null,
  created_at timestamptz not null default now()
);
alter table analysis_cache enable row level security;  -- service key bypasses RLS; keep the table private
```
Set `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` (service role key, server-side only, never in the frontend).

## Deploy (Render)
New Web Service -> Docker -> point at this folder. Env vars: `CORS_ORIGINS=https://<your-vercel-app>.vercel.app`,
plus the two Supabase vars if used. Then set the frontend's `VITE_API_BASE_URL` to the Render URL.
After deploy: `python scripts/prewarm.py https://<your-render-url>` so the 3 story buttons are instant.
Free Render instances sleep when idle; open /health a minute before the demo.

## Behaviour notes
- Clicks are snapped to the MERRA-2 grid cell (0.5 deg lat x 0.625 deg lon); the cell centre is queried and
  returned in `grid.cell_lat/cell_lon`. Clicks inside one cell share a cache entry.
- Cache key includes the last full year, so it refreshes each January. TTL 30 days.
- Error codes: INVALID_COORDINATES 400, INSUFFICIENT_DATA 422, POWER_EMPTY 404, RATE_LIMITED 429, POWER_UNAVAILABLE 502.
