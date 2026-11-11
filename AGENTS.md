# AGENTS.md

Demo analytics app for the Belarusian used-car market: scraper for `cars.av.by` → FastAPI JSON API → static ECharts dashboard, published to GitHub Pages by a daily Actions workflow. No Node/npm, no build step, no database.

## Environment (verified on this machine)

- Only the `py` launcher exists. `python`, `node`, `npm`, and `git` are NOT on PATH.
- Use the project venv: `.venv\Scripts\python.exe` for FastAPI/uvicorn/pytest.
- `scraper/` is stdlib-only, so scraping also works with plain `py`.
- The console is cp1251: Cyrillic prints as mojibake. Files are valid UTF-8. Do not "fix" data based on console output; read files as UTF-8 (`Get-Content -Encoding UTF8` or the read tool).

## Commands

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# scrape -> data/cars.json (25 cars/page, ~0.35s delay)
.\.venv\Scripts\python.exe -m scraper.cli --pages 50

# dev server
.\.venv\Scripts\python.exe -m uvicorn app.server:app --reload --port 8000

# tests (never hit the network)
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest tests/test_api.py::test_dashboard_brand_filter_narrows_results

# daily 13:00 refresh (Windows Task Scheduler task "AVBY-MarketPulse-Daily")
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\register-schedule.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\update-dashboard.ps1   # run now
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\unregister-schedule.ps1

# static build for GitHub Pages -> docs/ (also what the Actions workflow runs)
.\.venv\Scripts\python.exe scripts\build-static.py
py -m http.server 8001 --directory docs      # preview the Pages build
```

`data/cars.json` is committed, so the app runs without scraping.

## Non-obvious facts

- Listings live on **cars.av.by**, not `av.by`. `av.by/automobiles`, `/cars`, and `/avtomobili` all return 404; the homepage only links out to `cars.av.by`.
- Listing pages are Next.js and server-render the payload in `<script id="__NEXT_DATA__">`. Extract `props.initialState.filter.main.adverts` (25 per page, `?page=N`). No browser/Playwright needed.
- Useful advert fields: `price.usd.amount`, `price.byn.amount`, `publicUrl` (absolute), `photos[].medium.url`, `properties[]` (name/value), `originalDaysOnSale`, `shortLocationName`; `metadata` also carries brand/model/year.
- `engine_capacity` uses a comma decimal (`"2,0"`); `_to_float` normalizes it.
- Promo/top ads repeat across pages → `scrape()` dedupes by `id`.
- `scraper/cli.py` writes atomically (`cars.json.tmp` → `os.replace`); keep it that way so a failed scheduled run can't truncate the dataset.
- The daily refresh is two independent halves: the Task Scheduler job re-scrapes the file, and the frontend polls `/api/meta` every 60 s (`REFRESH_MS`) and re-renders when `scraped_at` changes. Changing one without the other breaks the "updates itself" demo. In static mode the same poll reads `data/meta.json` and then re-fetches `data/cars.json`.
- The scheduled task uses `-LogonType Interactive`: it only fires while that user is logged on, and `-StartWhenAvailable` catches up after sleep. It does not start `uvicorn` — the server must already be running for the page to serve new data.
- Logs go to `logs\update-YYYY-MM-DD.log` (gitignored, last 30 kept). The console is cp1251, so read logs with `-Encoding UTF8`.
- The frontend has **two data sources**: `api` (FastAPI `/api/*`) and `static` (`data/cars.json` + `data/meta.json`). `app/static/app.js` picks one in `detectMode()`; `scripts/build-static.py` stamps `data-mode="static"` on `<html>` so Pages never probes `/api/meta` (that 404 showed up as a devtools error).
- `app/static/analytics.js` is a hand-maintained JS port of `app/analytics.py`. Any change to filters, aggregations, deals, or CSV columns must be made in **both** files, or API mode and Pages mode will disagree.
- `app/server.py` mounts `StaticFiles` at `/` (not `/static`) and does it **last**, after every `/api/*` route. Dashboard asset paths are relative so the same files work on Pages subpaths.
- `app/static/` and `app/static/vendor/` are OneDrive reparse points with the **read-only** attribute. `shutil.copytree` copies that flag, so `scripts/build-static.py` runs `_make_writable()` after copying and before deleting — without it the rebuild fails with `WinError 5`.
- GitHub Actions cron is `0 10 * * *` UTC = 13:00 Minsk (UTC+3, no DST). A failed scrape keeps the previous snapshot and still republishes `docs/`, so the site never goes dark.

## Architecture map

- `scraper/avby.py` — fetch (urllib + retries), parse, `Car` dataclass.
- `scraper/cli.py` — `--pages/--delay/--start-page/--out`; writes `{source, scraped_at, pages, count, cars}`.
- `app/analytics.py` — framework-free filtering and aggregations. Keep FastAPI out of this module; all chart data is computed here. `below_brand_median()` returns *every* below-median car (brands with <5 cars are skipped); `build_deals()` paginates it, `best_deals()` is just the first 8 for the dashboard payload.
- `app/store.py` — loads `data/cars.json` and reloads when its mtime changes. Missing file → endpoints return 503 with a scrape hint.
- `app/server.py` — `/api/dashboard`, `/api/deals`, `/api/deals.csv`, `/api/filters`, `/api/meta`, `/api/export.csv`, `/health`; serves `app/static` mounted at `/`.
- `app/static/` — no bundler: `index.html` + `styles.css` + `app.js` + `analytics.js`; ECharts is vendored at `vendor/echarts.min.js` so the demo works offline.
- `app/static/analytics.js` — `window.AvbyAnalytics`, the static-mode mirror of `app/analytics.py` (filters, summary, charts, below-median deals, pagination, CSV text).
- `scripts/build-static.py` — builds `docs/`: copies `app/static`, adds `data/cars.json` + `data/meta.json`, `.nojekyll`, and the `data-mode="static"` marker. Refuses to overwrite a directory it did not create unless `--force`.
- `scripts/update-dashboard.ps1` — scheduled wrapper: mutex, venv detection, logging, log rotation. `register-schedule.ps1` / `unregister-schedule.ps1` manage the 13:00 task.
- `.github/workflows/update-dashboard.yml` — cloud refresh: tests → scrape → `build-static.py` → commit `data/cars.json` + `docs/` (cron 13:00 Minsk, `workflow_dispatch`).

## Changing charts

Three manual steps: compute the series in `app/analytics.py` → expose it under `charts` in `build_dashboard()` → add a `renderX()` in `app/static/app.js` plus a container in `index.html`. Reuse `PALETTE` and the `TOOLTIP`/axis constants.

**Plus a fourth step now:** mirror the new series in `app/static/analytics.js` (`buildDashboard()`), otherwise the Pages build loses the chart. Then rebuild `docs/` with `scripts/build-static.py`.

## Constraints

- Do not add Node/npm/build tooling; the demo is intentionally Python + static files.
- Tests must stay offline: `tests/test_parse.py` builds a synthetic `__NEXT_DATA__`, `tests/test_api.py` uses the committed dataset via `TestClient`, `tests/test_static_build.py` builds into `tmp_path`.
- Keep scraping polite: preserve the delay, retries, and deduplication.
- `.venv/` and `__pycache__/` are gitignored; `data/cars.json`, `docs/`, and the vendored ECharts file are intentionally committed.
