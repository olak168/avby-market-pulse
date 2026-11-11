"""Scraper for cars.av.by (the classifieds section of av.by).

The site is a Next.js application. Every filter page server-renders the full
listing payload inside a ``<script id="__NEXT_DATA__">`` JSON blob, so no
headless browser is required. The data we care about lives at::

    props.initialState.filter.main.adverts

Each page contains 25 adverts. Pagination is ``?page=N``.
"""

from __future__ import annotations

import http.cookiejar
import json
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Iterable

BASE_URL = "https://cars.av.by"
FILTER_URL = BASE_URL + "/filter?page={page}"
NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}


class ScrapeError(RuntimeError):
    """Raised when a page cannot be fetched or parsed."""


@dataclass(slots=True)
class Car:
    id: int
    url: str
    brand: str
    model: str
    year: int | None
    price_usd: int | None
    price_byn: int | None
    mileage_km: int | None
    engine_type: str | None
    engine_power: int | None
    engine_capacity: float | None
    transmission: str | None
    body_type: str | None
    drive_type: str | None
    color: str | None
    condition: str | None
    location: str | None
    seller: str | None
    published_at: str | None
    days_on_sale: int | None
    photo: str | None
    is_top: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).replace(" ", "").replace("\u00a0", "")))
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(" ", "").replace("\u00a0", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def _first_photo(advert: dict[str, Any]) -> str | None:
    photos = advert.get("photos") or []
    if not photos:
        return None
    for photo in photos:
        if photo.get("main"):
            return (photo.get("medium") or photo.get("small") or {}).get("url")
    return (photos[0].get("medium") or photos[0].get("small") or {}).get("url")


def parse_advert(advert: dict[str, Any]) -> Car:
    """Convert one raw advert dict into a flat :class:`Car`."""
    props = {p.get("name"): p.get("value") for p in advert.get("properties") or []}
    price = advert.get("price") or {}
    usd = price.get("usd") or {}
    byn = price.get("byn") or {}

    return Car(
        id=int(advert["id"]),
        url=advert.get("publicUrl") or "",
        brand=str(props.get("brand") or ""),
        model=str(props.get("model") or ""),
        year=_to_int(props.get("year") or advert.get("year")),
        price_usd=_to_int(usd.get("amount")),
        price_byn=_to_int(byn.get("amount")),
        mileage_km=_to_int(props.get("mileage_km")),
        engine_type=props.get("engine_type"),
        engine_power=_to_int(props.get("engine_power")),
        engine_capacity=_to_float(props.get("engine_capacity")),
        transmission=props.get("transmission_type"),
        body_type=props.get("body_type"),
        drive_type=props.get("drive_type"),
        color=props.get("color"),
        condition=props.get("condition"),
        location=advert.get("shortLocationName") or advert.get("locationName"),
        seller=advert.get("sellerName"),
        published_at=advert.get("publishedAt"),
        days_on_sale=_to_int(advert.get("originalDaysOnSale")),
        photo=_first_photo(advert),
        is_top=bool(advert.get("top")),
    )


def parse_next_data(html: str) -> dict[str, Any]:
    match = NEXT_DATA_RE.search(html)
    if not match:
        raise ScrapeError("__NEXT_DATA__ payload not found in page")
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise ScrapeError(f"invalid __NEXT_DATA__ JSON: {exc}") from exc


def parse_page(html: str) -> tuple[list[Car], dict[str, Any]]:
    """Return ``(cars, pagination)`` for a single filter page."""
    data = parse_next_data(html)
    try:
        main = data["props"]["initialState"]["filter"]["main"]
    except KeyError as exc:  # pragma: no cover - defensive
        raise ScrapeError("unexpected page structure (filter.main missing)") from exc

    cars = [parse_advert(a) for a in main.get("adverts") or []]
    pagination = {
        "page": main.get("page"),
        "page_count": main.get("pageCount"),
        "total": main.get("count"),
    }
    return cars, pagination


_OPENER: urllib.request.OpenerDirector | None = None


def _opener() -> urllib.request.OpenerDirector:
    """Shared opener that keeps cookies between requests.

    cars.av.by is behind a bot filter that answers unfamiliar clients with a
    non-standard HTTP 468. It sets cookies on the first visit, so starting the
    session at the homepage makes the listing requests look like a browser.
    """
    global _OPENER
    if _OPENER is None:
        _OPENER = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )
    return _OPENER


def warm_up(timeout: float = 15.0) -> None:
    """Best-effort homepage visit so the cookie jar is primed before paging."""
    request = urllib.request.Request(BASE_URL + "/", headers=HEADERS)
    try:
        with _opener().open(request, timeout=timeout) as response:
            response.read(64)
    except (urllib.error.URLError, TimeoutError, OSError):
        pass  # the filter request below reports the real problem


def fetch_page(page: int, timeout: float = 25.0, retries: int = 3) -> str:
    """Fetch the raw HTML for one filter page, with retries."""
    url = FILTER_URL.format(page=page)
    last_error: Any = None
    for attempt in range(1, retries + 1):
        request = urllib.request.Request(url, headers=HEADERS)
        try:
            with _opener().open(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except urllib.error.HTTPError as exc:
            # The site's bot filter answers unfamiliar clients with a
            # non-standard 468 and a short HTML body; keep it for the log,
            # because "HTTP Error 468:" alone tells us nothing.
            try:
                snippet = exc.read(160).decode("utf-8", "replace")
                snippet = " ".join(snippet.split())
            except Exception:  # pragma: no cover - body already consumed
                snippet = ""
            last_error = f"HTTP {exc.code} {exc.reason}".strip()
            if snippet:
                last_error += f" - {snippet}"
            if exc.code not in (429, 468) and exc.code < 500:
                break  # a retry cannot fix 403/404
            if attempt < retries:
                time.sleep(2.0 * attempt + random.uniform(0, 1.0))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(1.5 * attempt + random.uniform(0, 1.0))
    raise ScrapeError(f"failed to fetch {url}: {last_error}")


def scrape(
    pages: int = 50,
    delay: float = 0.4,
    start_page: int = 1,
    on_page: Any = None,
) -> list[Car]:
    """Scrape ``pages`` filter pages and return deduplicated cars.

    ``on_page`` is an optional callback ``(page, new_cars, total_unique, pagination)``
    used by the CLI for progress reporting.
    """
    seen: dict[int, Car] = {}
    warm_up()
    for offset in range(pages):
        page = start_page + offset
        cars, pagination = parse_page(fetch_page(page))
        fresh = 0
        for car in cars:
            if car.id not in seen:
                seen[car.id] = car
                fresh += 1
        if on_page:
            on_page(page, fresh, len(seen), pagination)
        if pagination.get("page_count") and page >= pagination["page_count"]:
            break
        time.sleep(delay)
    return list(seen.values())


def dump_cars(cars: Iterable[Car]) -> list[dict[str, Any]]:
    return [car.to_dict() for car in cars]
