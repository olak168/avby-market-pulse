"""Pure-Python aggregations used by the dashboard API.

Keeping this module framework-free makes it trivial to unit test and to reuse
from notebooks. Every function accepts a list of plain ``dict`` car records.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean, median
from typing import Any, Iterable

Car = dict[str, Any]

SORT_OPTIONS = {
    "relevance": ("По релевантности", None),
    "price_asc": ("Цена: по возрастанию", lambda c: c.get("price_usd") or 0),
    "price_desc": ("Цена: по убыванию", lambda c: -(c.get("price_usd") or 0)),
    "year_desc": ("Год: новее", lambda c: -(c.get("year") or 0)),
    "year_asc": ("Год: старше", lambda c: c.get("year") or 0),
    "mileage_asc": ("Пробег: меньше", lambda c: c.get("mileage_km") or 0),
    "mileage_desc": ("Пробег: больше", lambda c: -(c.get("mileage_km") or 0)),
    "fresh": ("Дольше всего в продаже", lambda c: -(c.get("days_on_sale") or 0)),
}


def _avg(values: Iterable[float]) -> float | None:
    values = [v for v in values if v is not None]
    return round(mean(values), 1) if values else None


def _median(values: Iterable[float]) -> float | None:
    values = [v for v in values if v is not None]
    return round(median(values), 1) if values else None


def filter_cars(
    cars: list[Car],
    brand: str | None = None,
    body: str | None = None,
    fuel: str | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    price_min: int | None = None,
    price_max: int | None = None,
    mileage_max: int | None = None,
    q: str | None = None,
    sort: str = "relevance",
) -> list[Car]:
    """Apply the dashboard filters and ordering."""
    result = cars
    if brand:
        result = [c for c in result if c.get("brand") == brand]
    if body:
        result = [c for c in result if c.get("body_type") == body]
    if fuel:
        result = [c for c in result if c.get("engine_type") == fuel]
    if year_min is not None:
        result = [c for c in result if (c.get("year") or 0) >= year_min]
    if year_max is not None:
        result = [c for c in result if (c.get("year") or 0) <= year_max]
    if price_min is not None:
        result = [c for c in result if (c.get("price_usd") or 0) >= price_min]
    if price_max is not None:
        result = [c for c in result if (c.get("price_usd") or 0) <= price_max]
    if mileage_max is not None:
        result = [c for c in result if (c.get("mileage_km") or 0) <= mileage_max]
    if q:
        needle = q.strip().lower()
        if needle:
            result = [
                c
                for c in result
                if needle in f"{c.get('brand')} {c.get('model')}".lower()
            ]

    key = SORT_OPTIONS.get(sort, (None, None))[1]
    if key is not None:
        result = sorted(result, key=key)
    return result


def summary(cars: list[Car]) -> dict[str, Any]:
    prices = [c["price_usd"] for c in cars if c.get("price_usd")]
    years = [c["year"] for c in cars if c.get("year")]
    mileage = [c["mileage_km"] for c in cars if c.get("mileage_km")]
    brands = Counter(c["brand"] for c in cars if c.get("brand"))
    electric = sum(1 for c in cars if c.get("engine_type") == "электро")
    return {
        "total": len(cars),
        "avg_price_usd": _avg(prices),
        "median_price_usd": _median(prices),
        "min_price_usd": min(prices) if prices else None,
        "max_price_usd": max(prices) if prices else None,
        "avg_year": _avg(years),
        "avg_mileage_km": _avg(mileage),
        "electric_share": round(electric / len(cars) * 100, 1) if cars else 0.0,
        "top_brand": brands.most_common(1)[0][0] if brands else None,
        "brands_count": len(brands),
    }


PRICE_BUCKETS = [
    (0, 3_000, "до $3k"),
    (3_000, 6_000, "$3–6k"),
    (6_000, 10_000, "$6–10k"),
    (10_000, 15_000, "$10–15k"),
    (15_000, 20_000, "$15–20k"),
    (20_000, 30_000, "$20–30k"),
    (30_000, 40_000, "$30–40k"),
    (40_000, 60_000, "$40–60k"),
    (60_000, 80_000, "$60–80k"),
    (80_000, 10**12, "$80k+"),
]


def price_histogram(cars: list[Car]) -> dict[str, Any]:
    """Fixed USD buckets keep the skewed used-car distribution readable."""
    counts = [0] * len(PRICE_BUCKETS)
    for car in cars:
        price = car.get("price_usd")
        if not price:
            continue
        for i, (lo, hi, _) in enumerate(PRICE_BUCKETS):
            if lo <= price < hi:
                counts[i] += 1
                break
    return {
        "labels": [label for _, _, label in PRICE_BUCKETS],
        "values": counts,
    }


def by_brand(cars: list[Car], limit: int = 12, min_count: int = 2) -> list[dict[str, Any]]:
    groups: dict[str, list[Car]] = defaultdict(list)
    for car in cars:
        if car.get("brand"):
            groups[car["brand"]].append(car)
    rows = []
    for brand, items in groups.items():
        if len(items) < min_count:
            continue
        prices = [c["price_usd"] for c in items if c.get("price_usd")]
        rows.append(
            {
                "brand": brand,
                "count": len(items),
                "avg_price_usd": _avg(prices),
                "median_price_usd": _median(prices),
            }
        )
    rows.sort(key=lambda r: r["count"], reverse=True)
    return rows[:limit]


def by_category(cars: list[Car], field: str, limit: int = 10) -> list[dict[str, Any]]:
    counter = Counter(c.get(field) for c in cars if c.get(field))
    total = sum(counter.values()) or 1
    return [
        {
            "name": name,
            "count": count,
            "share": round(count / total * 100, 1),
        }
        for name, count in counter.most_common(limit)
    ]


def by_fuel(cars: list[Car]) -> list[dict[str, Any]]:
    groups: dict[str, list[Car]] = defaultdict(list)
    for car in cars:
        if car.get("engine_type"):
            groups[car["engine_type"]].append(car)
    rows = []
    for name, items in groups.items():
        prices = [c["price_usd"] for c in items if c.get("price_usd")]
        rows.append(
            {
                "name": name,
                "count": len(items),
                "avg_price_usd": _avg(prices),
            }
        )
    rows.sort(key=lambda r: r["count"], reverse=True)
    return rows


def by_year(cars: list[Car], min_year: int = 1990, min_count: int = 2) -> list[dict[str, Any]]:
    groups: dict[int, list[Car]] = defaultdict(list)
    for car in cars:
        year = car.get("year")
        if year and year >= min_year:
            groups[year].append(car)
    rows = []
    for year in sorted(groups):
        items = groups[year]
        if len(items) < min_count:
            continue
        prices = [c["price_usd"] for c in items if c.get("price_usd")]
        rows.append(
            {
                "year": year,
                "count": len(items),
                "avg_price_usd": _avg(prices),
            }
        )
    return rows


def price_segments(cars: list[Car]) -> list[dict[str, Any]]:
    edges = [0, 5_000, 10_000, 20_000, 40_000, 10**12]
    labels = ["до $5k", "$5–10k", "$10–20k", "$20–40k", "$40k+"]
    counts = [0] * len(labels)
    for car in cars:
        price = car.get("price_usd")
        if not price:
            continue
        for i in range(len(labels)):
            if edges[i] <= price < edges[i + 1]:
                counts[i] += 1
                break
    return [{"name": label, "count": count} for label, count in zip(labels, counts)]


def days_on_sale_histogram(cars: list[Car]) -> list[dict[str, Any]]:
    buckets = [("0–7 дней", 0, 7), ("8–30 дней", 8, 30), ("31–90 дней", 31, 90), ("90+ дней", 91, 10**9)]
    counts = [0] * len(buckets)
    for car in cars:
        days = car.get("days_on_sale")
        if days is None:
            continue
        for i, (_, lo, hi) in enumerate(buckets):
            if lo <= days <= hi:
                counts[i] += 1
                break
    return [{"name": name, "count": count} for (name, _, _), count in zip(buckets, counts)]


def price_vs_mileage(cars: list[Car], limit: int = 700) -> list[dict[str, Any]]:
    points = [
        {
            "x": c["mileage_km"],
            "y": c["price_usd"],
            "brand": c.get("brand"),
            "fuel": c.get("engine_type"),
            "url": c.get("url"),
        }
        for c in cars
        if c.get("mileage_km") and c.get("price_usd")
    ]
    if len(points) > limit:
        step = len(points) / limit
        points = [points[int(i * step)] for i in range(limit)]
    return points


def below_brand_median(
    cars: list[Car], min_brand_count: int = 5
) -> list[dict[str, Any]]:
    """Every car priced below the median for its own brand, biggest gap first.

    This is a transparent heuristic, not a valuation model: brands with fewer
    than ``min_brand_count`` cars in the current selection are skipped, so a
    single cheap outlier cannot define its own median.
    """
    groups: dict[str, list[Car]] = defaultdict(list)
    for car in cars:
        if car.get("brand") and car.get("price_usd"):
            groups[car["brand"]].append(car)

    medians = {
        brand: median([c["price_usd"] for c in items])
        for brand, items in groups.items()
        if len(items) >= min_brand_count
    }

    scored = []
    for car in cars:
        brand = car.get("brand")
        price = car.get("price_usd")
        if brand in medians and price:
            discount = (medians[brand] - price) / medians[brand] * 100
            if discount > 0:
                scored.append(
                    {
                        "id": car["id"],
                        "brand": brand,
                        "model": car.get("model"),
                        "year": car.get("year"),
                        "mileage_km": car.get("mileage_km"),
                        "price_usd": price,
                        "price_byn": car.get("price_byn"),
                        "discount_pct": round(discount, 1),
                        "brand_median_usd": round(medians[brand], 1),
                        "photo": car.get("photo"),
                        "url": car.get("url"),
                        "location": car.get("location"),
                    }
                )
    scored.sort(key=lambda r: r["discount_pct"], reverse=True)
    return scored


def best_deals(cars: list[Car], limit: int = 8, min_brand_count: int = 5) -> list[dict[str, Any]]:
    """Top ``limit`` entries of :func:`below_brand_median`."""
    return below_brand_median(cars, min_brand_count=min_brand_count)[:limit]


def paginate(cars: list[Car], page: int = 1, page_size: int = 20) -> dict[str, Any]:
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    total = len(cars)
    pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, pages)
    start = (page - 1) * page_size
    return {
        "items": cars[start : start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }


def build_dashboard(
    cars: list[Car],
    page: int = 1,
    page_size: int = 12,
    deals_page_size: int = 12,
    **filters: Any,
) -> dict[str, Any]:
    filtered = filter_cars(cars, **filters)
    deals = below_brand_median(filtered)
    return {
        "summary": summary(filtered),
        "charts": {
            "price_histogram": price_histogram(filtered),
            "by_brand": by_brand(filtered),
            "by_body": by_category(filtered, "body_type", limit=8),
            "by_fuel": by_fuel(filtered),
            "by_year": by_year(filtered),
            "price_segments": price_segments(filtered),
            "days_on_sale": days_on_sale_histogram(filtered),
            "price_vs_mileage": price_vs_mileage(filtered),
            "by_location": by_category(filtered, "location", limit=10),
        },
        "deals": paginate(deals, page=1, page_size=deals_page_size),
        "best_deals": deals[:8],
        "cars": paginate(filtered, page=page, page_size=page_size),
    }


def build_deals(
    cars: list[Car],
    page: int = 1,
    page_size: int = 12,
    min_brand_count: int = 5,
    **filters: Any,
) -> dict[str, Any]:
    """Paginated view over *all* cars below their brand median."""
    filtered = filter_cars(cars, **filters)
    return paginate(
        below_brand_median(filtered, min_brand_count=min_brand_count),
        page=page,
        page_size=page_size,
    )
