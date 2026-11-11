"""Command line entry point: ``py -m scraper.cli --pages 50``."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .avby import BASE_URL, FILTER_URL, dump_cars, scrape

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "data" / "cars.json"


def _progress(page: int, fresh: int, unique: int, pagination: dict) -> None:
    total = pagination.get("total")
    page_count = pagination.get("page_count")
    print(
        f"page {page:>4} | +{fresh:>3} new | unique={unique:>5}"
        f" | site total={total} | pages={page_count}",
        flush=True,
    )


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Scrape car listings from cars.av.by")
    parser.add_argument("--pages", type=int, default=50, help="number of pages (25 cars each)")
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--delay", type=float, default=0.4, help="seconds between requests")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    if args.pages < 1:
        parser.error("--pages must be >= 1")

    print(f"Scraping {args.pages} page(s) from {BASE_URL} ...", flush=True)
    cars = scrape(
        pages=args.pages,
        delay=args.delay,
        start_page=args.start_page,
        on_page=_progress,
    )
    if not cars:
        print("No cars parsed - aborting.", file=sys.stderr)
        return 1

    dataset = {
        "source": FILTER_URL.format(page=args.start_page),
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pages": args.pages,
        "count": len(cars),
        "cars": dump_cars(cars),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_name(args.out.name + ".tmp")
    tmp.write_text(
        json.dumps(dataset, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(tmp, args.out)  # atomic on Windows: never leaves a half-written dataset
    print(f"Saved {len(cars)} unique cars -> {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
