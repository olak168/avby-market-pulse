"""Dataset loading and filter-option derivation."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from threading import Lock
from typing import Any

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "cars.json"

_lock = Lock()
_cache: dict[str, Any] = {"mtime": None, "dataset": None}


def dataset_exists() -> bool:
    return DATA_FILE.exists()


def load_dataset() -> dict[str, Any]:
    """Load ``data/cars.json`` and reload it automatically when it changes."""
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"{DATA_FILE} is missing. Run: py -m scraper.cli --pages 50"
        )
    mtime = DATA_FILE.stat().st_mtime
    if _cache["mtime"] != mtime:
        with _lock:
            if _cache["mtime"] != mtime:
                _cache["dataset"] = json.loads(DATA_FILE.read_text(encoding="utf-8"))
                _cache["mtime"] = mtime
    return _cache["dataset"]


def get_cars() -> list[dict[str, Any]]:
    return load_dataset()["cars"]


def get_meta() -> dict[str, Any]:
    data = load_dataset()
    return {
        "source": data.get("source"),
        "scraped_at": data.get("scraped_at"),
        "count": data.get("count", len(data.get("cars", []))),
        "pages": data.get("pages"),
    }


def get_filter_options(cars: list[dict[str, Any]]) -> dict[str, Any]:
    brands = Counter(c["brand"] for c in cars if c.get("brand"))
    bodies = Counter(c["body_type"] for c in cars if c.get("body_type"))
    fuels = Counter(c["engine_type"] for c in cars if c.get("engine_type"))
    years = [c["year"] for c in cars if c.get("year")]
    prices = [c["price_usd"] for c in cars if c.get("price_usd")]
    return {
        "brands": [{"name": name, "count": n} for name, n in brands.most_common()],
        "bodies": [{"name": name, "count": n} for name, n in bodies.most_common()],
        "fuels": [{"name": name, "count": n} for name, n in fuels.most_common()],
        "year_min": min(years) if years else None,
        "year_max": max(years) if years else None,
        "price_min": min(prices) if prices else None,
        "price_max": max(prices) if prices else None,
    }
