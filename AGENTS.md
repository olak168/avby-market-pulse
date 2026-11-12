# AGENTS.md

Demo analytics app for the Belarusian used-car market: scraper for `cars.av.by` → FastAPI JSON API → static ECharts dashboard, published to GitHub Pages by a manual/on-push Actions workflow. No Node/npm, no build step, no database.

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

# no terminal needed: double-click refresh-data.bat (scrape + rebuild docs/,
# then opens data/ so the snapshot can be dragged into GitHub). Optional arg = pages.
refresh-data.bat 80

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
- `cars.av.by` answers GitHub-runner IPs with a non-standard **HTTP 468** (bot filter), while the same request from a home connection returns 200. `fetch_page()` therefore retries through `curl` (different TLS/HTTP fingerprint) when urllib gets 403/468, and the workflow retries the whole scrape 3×. `scripts/probe-avby.py` prints both transports side by side for diagnosis.
- `scraper/cli.py` writes atomically (`cars.json.tmp` → `os.replace`); keep it that way so a failed scheduled run can't truncate the dataset.
- The refresh is manual by design: `cars.av.by` returns HTTP 468 to GitHub-runner IPs, so the cloud cannot scrape. The operator runs `scraper.cli`, then `build-static.py`, then uploads `data/cars.json` + `docs/` (web UI or git). The frontend polls `/api/meta` every 60 s (`REFRESH_MS`) and re-renders when `scraped_at` changes; in static mode the same poll reads `data/meta.json` and re-fetches `data/cars.json`. Keep the UI free of promises about automatic daily updates — the footer used to say "автообновление в 13:00" and that was removed.
- The scheduled task uses `-LogonType Interactive`: it only fires while that user is logged on, and `-StartWhenAvailable` catches up after sleep. It does not start `uvicorn` — the server must already be running for the page to serve new data.
- Logs go to `logs\update-YYYY-MM-DD.log` (gitignored, last 30 kept). The console is cp1251, so read logs with `-Encoding UTF8`.
- The frontend has **two data sources**: `api` (FastAPI `/api/*`) and `static` (`data/cars.json` + `data/meta.json`). `app/static/app.js` picks one in `detectMode()`; `scripts/build-static.py` stamps `data-mode="static"` on `<html>` so Pages never probes `/api/meta` (that 404 showed up as a devtools error).
- `app/static/analytics.js` is a hand-maintained JS port of `app/analytics.py`. Any change to filters, aggregations, deals, or CSV columns must be made in **both** files, or API mode and Pages mode will disagree.
- The «Модель» filter is a cascade: `/api/filters` (or `filterOptions()` in static mode) returns `models` as `{brand, name, count}` pairs because a model name is only unique inside a brand. The select stays disabled until a brand is chosen, and picking a model switches the deals block to the brand+model median (`median_scope: "model"`), including its heading and CSV export.
- The dashboard fingerprints its asset URLs (`app/versioning.py` → `app.js?v=<content hash>`). `app/server.py` stamps `index.html` on the fly and `scripts/build-static.py` stamps the Pages copy. Without it a browser happily reused the cached `app.js`/`styles.css` after a rebuild and rendered the *previous* UI (a missing column, an absent sort option) until a hard reload — that actually happened. Static responses also send `Cache-Control: no-cache, must-revalidate`.
- `app/server.py` mounts `StaticFiles` at `/` (not `/static`) and does it **last**, after every `/api/*` route. Dashboard asset paths are relative so the same files work on Pages subpaths.
- `app/static/` and `app/static/vendor/` are OneDrive reparse points with the **read-only** attribute. `shutil.copytree` copies that flag, so `scripts/build-static.py` runs `_make_writable()` after copying and before deleting — without it the rebuild fails with `WinError 5`.
- GitHub Actions has **no cron**: the workflow runs on `workflow_dispatch` and on pushes to `main` (paths-ignore `docs/**`, `data/**`). Scraping in the cloud is an opt-in input (`scrape: true`) because it normally fails with HTTP 468. A failed scrape keeps the previous snapshot and still republishes `docs/`, so the site never goes dark.

## Architecture map

- `scraper/avby.py` — fetch (urllib + retries), parse, `Car` dataclass.
- `scraper/cli.py` — `--pages/--delay/--start-page/--out`; writes `{source, scraped_at, pages, count, cars}`.
- `app/analytics.py` — framework-free filtering and aggregations. Keep FastAPI out of this module; all chart data is computed here. `filter_cars()` attaches the 0..10 score (`with_score()`: up to 5 for a newer year + up to 5 for lower mileage, linear over the **full** dataset so filtering never changes a score); `below_brand_median()` returns *every* below-median car (brands with <5 cars are skipped) ordered by the biggest discount unless a dashboard `sort` key is passed, in which case it mirrors the listings table. When the `model` filter is set it switches to the **brand+model** median (needs ≥3 listings) and tags each row with `median_scope`, which is how the block becomes «ниже медианы по марке и модели»; `deals_scope()` describes that choice (`scope`, `model`, `min_count`, `group_count`) for the UI. Medians always come from the full dataset via `reference=`, so filters cannot raise a median. `build_deals()` paginates it, `best_deals()` is just the first 8 for the dashboard payload.
- `app/store.py` — loads `data/cars.json` and reloads when its mtime changes. Missing file → endpoints return 503 with a scrape hint.
- `app/versioning.py` — content-hash cache busting for `index.html` asset URLs (used by both `app/server.py` and `scripts/build-static.py`).
- `app/server.py` — `/api/dashboard`, `/api/deals`, `/api/deals.csv`, `/api/filters`, `/api/meta`, `/api/export.csv`, `/health`; serves `app/static` mounted at `/`.
- `app/static/` — no bundler: `index.html` + `styles.css` + `app.js` + `analytics.js`; ECharts is vendored at `vendor/echarts.min.js` so the demo works offline.
- `app/static/analytics.js` — `window.AvbyAnalytics`, the static-mode mirror of `app/analytics.py` (filters, summary, charts, below-median deals, pagination, CSV text).
- `scripts/build-static.py` — builds `docs/`: copies `app/static`, adds `data/cars.json` + `data/meta.json`, `.nojekyll`, and the `data-mode="static"` marker. Refuses to overwrite a directory it did not create unless `--force`.
- `scripts/update-dashboard.ps1` — scheduled wrapper: mutex, venv detection, logging, log rotation. `register-schedule.ps1` / `unregister-schedule.ps1` manage the 13:00 task.
- `.github/workflows/update-dashboard.yml` — cloud rebuild: tests → `build-static.py` → commit `data/cars.json` + `docs/`. Triggers: `workflow_dispatch` and `push` to `main`; the scrape step is behind the `scrape` input (default false) because cloud IPs get HTTP 468. GITHUB_TOKEN pushes don't re-trigger, so no loop.

## Changing charts

Three manual steps: compute the series in `app/analytics.py` → expose it under `charts` in `build_dashboard()` → add a `renderX()` in `app/static/app.js` plus a container in `index.html`. Reuse `PALETTE` and the `TOOLTIP`/axis constants.

**Plus a fourth step now:** mirror the new series in `app/static/analytics.js` (`buildDashboard()`), otherwise the Pages build loses the chart. Then rebuild `docs/` with `scripts/build-static.py`.

## Constraints

- Do not add Node/npm/build tooling; the demo is intentionally Python + static files.
- Tests must stay offline: `tests/test_parse.py` builds a synthetic `__NEXT_DATA__`, `tests/test_api.py` uses the committed dataset via `TestClient`, `tests/test_static_build.py` builds into `tmp_path`.
- Keep scraping polite: preserve the delay, retries, and deduplication.
- `.venv/` and `__pycache__/` are gitignored; `data/cars.json`, `docs/`, and the vendored ECharts file are intentionally committed.
