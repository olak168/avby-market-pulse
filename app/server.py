"""FastAPI application serving the dashboard API and static frontend."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from . import analytics
from .store import get_cars, get_filter_options, get_meta
from .versioning import stamp_assets

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="AV.BY Market Pulse",
    description="Analytics dashboard for the Belarusian used-car market (cars.av.by).",
    version="1.0.0",
)


@app.middleware("http")
async def _revalidate_static(request: Request, call_next):
    """Stop browsers from reusing a stale dashboard after a rebuild.

    ``StaticFiles`` only sends ETag/Last-Modified, so a browser may keep an old
    ``index.html``/``app.js``/``styles.css`` in memory and silently render the
    previous UI (a missing column, an absent sort option) until a hard reload.
    """
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".html", ".js", ".css", ".json")):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


def _cars() -> list[dict[str, Any]]:
    try:
        return get_cars()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _filters(
    brand: str | None,
    model: str | None,
    body: str | None,
    fuel: str | None,
    year_min: int | None,
    year_max: int | None,
    price_min: int | None,
    price_max: int | None,
    mileage_max: int | None,
    q: str | None,
    sort: str,
) -> dict[str, Any]:
    return {
        "brand": brand,
        "model": model,
        "body": body,
        "fuel": fuel,
        "year_min": year_min,
        "year_max": year_max,
        "price_min": price_min,
        "price_max": price_max,
        "mileage_max": mileage_max,
        "q": q,
        "sort": sort,
    }


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "cars": len(_cars())}


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    try:
        return get_meta()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/filters")
def filters() -> dict[str, Any]:
    return get_filter_options(_cars())


@app.get("/api/dashboard")
def dashboard(
    brand: str | None = None,
    model: str | None = None,
    body: str | None = None,
    fuel: str | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    price_min: int | None = None,
    price_max: int | None = None,
    mileage_max: int | None = None,
    q: str | None = None,
    sort: str = "relevance",
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=100),
) -> dict[str, Any]:
    cars = _cars()
    result = analytics.build_dashboard(
        cars,
        page=page,
        page_size=page_size,
        **_filters(
            brand, model, body, fuel, year_min, year_max, price_min, price_max,
            mileage_max, q, sort,
        ),
    )
    result["meta"] = get_meta()
    result["sort_options"] = [
        {"id": key, "label": label}
        for key, (label, _) in analytics.SORT_OPTIONS.items()
    ]
    return result


@app.get("/api/deals")
def deals(
    brand: str | None = None,
    model: str | None = None,
    body: str | None = None,
    fuel: str | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    price_min: int | None = None,
    price_max: int | None = None,
    mileage_max: int | None = None,
    q: str | None = None,
    sort: str = "relevance",
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=100),
) -> dict[str, Any]:
    """All cars priced below the median of their brand (or brand+model), paginated."""
    return analytics.build_deals(
        _cars(),
        page=page,
        page_size=page_size,
        **_filters(
            brand, model, body, fuel, year_min, year_max, price_min, price_max,
            mileage_max, q, sort,
        ),
    )


DEAL_CSV_COLUMNS = [
    ("id", "ID"),
    ("brand", "Марка"),
    ("model", "Модель"),
    ("year", "Год"),
    ("score", "Балл"),
    ("price_usd", "Цена, USD"),
    ("brand_median_usd", "Медиана, USD"),
    ("discount_pct", "Ниже медианы, %"),
    ("mileage_km", "Пробег, км"),
    ("engine_type", "Двигатель"),
    ("body_type", "Кузов"),
    ("location", "Город"),
    ("url", "Ссылка"),
]


@app.get("/api/deals.csv")
def export_deals_csv(
    brand: str | None = None,
    model: str | None = None,
    body: str | None = None,
    fuel: str | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    price_min: int | None = None,
    price_max: int | None = None,
    mileage_max: int | None = None,
    q: str | None = None,
    sort: str = "relevance",
) -> Response:
    """CSV with every below-median car in the current selection (not just one page)."""
    filters = _filters(
        brand, model, body, fuel, year_min, year_max, price_min, price_max,
        mileage_max, q, sort,
    )
    cars = analytics.filter_cars(_cars(), **filters)
    deals = analytics.below_brand_median(
        cars,
        sort=filters["sort"],
        reference=_cars(),
        model=filters.get("model") or None,
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow([label for _, label in DEAL_CSV_COLUMNS])
    for deal in deals:
        writer.writerow([deal.get(key, "") for key, _ in DEAL_CSV_COLUMNS])

    return Response(
        content="\ufeff" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="avby-below-median.csv"'},
    )


CSV_COLUMNS = [
    ("id", "ID"),
    ("brand", "Марка"),
    ("model", "Модель"),
    ("year", "Год"),
    ("score", "Балл"),
    ("price_usd", "Цена, USD"),
    ("price_byn", "Цена, BYN"),
    ("mileage_km", "Пробег, км"),
    ("engine_type", "Двигатель"),
    ("engine_capacity", "Объём, л"),
    ("engine_power", "Мощность, л.с."),
    ("transmission", "КПП"),
    ("body_type", "Кузов"),
    ("drive_type", "Привод"),
    ("color", "Цвет"),
    ("condition", "Состояние"),
    ("location", "Город"),
    ("seller", "Продавец"),
    ("days_on_sale", "Дней в продаже"),
    ("url", "Ссылка"),
]


@app.get("/api/export.csv")
def export_csv(
    brand: str | None = None,
    model: str | None = None,
    body: str | None = None,
    fuel: str | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    price_min: int | None = None,
    price_max: int | None = None,
    mileage_max: int | None = None,
    q: str | None = None,
    sort: str = "relevance",
) -> Response:
    cars = analytics.filter_cars(
        _cars(),
        **_filters(
            brand, model, body, fuel, year_min, year_max, price_min, price_max,
            mileage_max, q, sort,
        ),
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow([label for _, label in CSV_COLUMNS])
    for car in cars:
        writer.writerow([car.get(key, "") for key, _ in CSV_COLUMNS])

    return Response(
        content="\ufeff" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="avby-cars.csv"'},
    )


@app.get("/")
def index() -> HTMLResponse:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(stamp_assets(html, STATIC_DIR))


# Mounted last so /api/* routes win. The dashboard uses relative asset paths,
# so the same files work here and on GitHub Pages.
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
