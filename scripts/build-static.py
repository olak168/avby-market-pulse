"""Build the static dashboard for GitHub Pages: ``py scripts/build-static.py``.

Copies ``app/static`` into ``docs/`` and drops the scraped dataset next to it,
so the page can run without FastAPI. ``app/static/app.js`` detects the mode by
probing ``/api/meta``: present -> API mode, missing -> static mode reading
``data/cars.json`` + ``data/meta.json``.

GitHub Pages serves ``docs/`` from the repository, and the daily workflow
re-runs this script after scraping.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "app" / "static"
DATASET = ROOT / "data" / "cars.json"
OUT_DIR = ROOT / "docs"

sys.path.insert(0, str(ROOT))

from app.versioning import stamp_assets  # noqa: E402  (needs ROOT on sys.path)

# Files that must never end up in the published site.
SKIP = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "Thumbs.db")


def _make_writable(root: Path) -> None:
    """Clear read-only bits copied from OneDrive/cloud placeholders.

    ``app/static`` and ``app/static/vendor`` are OneDrive reparse points that
    carry the read-only attribute; ``copytree`` copies those flags onto the
    published tree and Windows then refuses to delete or overwrite it.
    """
    for path in [root, *root.rglob("*")]:
        try:
            mode = path.stat().st_mode
            if not mode & stat.S_IWUSR:
                os.chmod(path, mode | stat.S_IWUSR)
        except OSError:
            pass


def _remove_tree(path: Path) -> None:
    """Remove a generated tree, tolerating Windows file locks."""
    _make_writable(path)
    for attempt in range(3):
        try:
            shutil.rmtree(path)
            return
        except PermissionError:
            if attempt == 2:
                raise
            time.sleep(0.2)
            _make_writable(path)


def _meta(dataset: dict) -> dict:
    return {
        "source": dataset.get("source"),
        "scraped_at": dataset.get("scraped_at"),
        "count": dataset.get("count", len(dataset.get("cars", []))),
        "pages": dataset.get("pages"),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def build_static(dataset_path: Path = DATASET, out_dir: Path = OUT_DIR, force: bool = False) -> dict:
    """Rebuild ``out_dir`` from the static assets plus ``dataset_path``."""
    if not dataset_path.is_file():
        raise FileNotFoundError(
            f"{dataset_path} not found - run `py -m scraper.cli --pages 50` first"
        )

    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not dataset.get("cars"):
        raise ValueError(f"{dataset_path} contains no cars")

    # Rebuild from scratch so deleted assets don't linger, but only wipe a
    # directory this script produced (or an empty one) unless forced.
    if out_dir.exists():
        produced = (out_dir / ".nojekyll").exists()
        if out_dir.is_dir() and (produced or not any(out_dir.iterdir()) or force):
            _remove_tree(out_dir)
        else:
            raise RuntimeError(
                f"{out_dir} exists and was not built by this script - pass --force to overwrite"
            )
    out_dir.mkdir(parents=True, exist_ok=True)

    shutil.copytree(STATIC_DIR, out_dir, dirs_exist_ok=True, ignore=SKIP)
    _make_writable(out_dir)

    # Tell app.js to read data/*.json instead of probing /api/meta. Without the
    # marker the probe 404s on Pages, which looks like a broken page in devtools.
    index = out_dir / "index.html"
    html = index.read_text(encoding="utf-8")
    if "data-mode=\"static\"" not in html:
        marker = '<html lang="ru">'
        if marker not in html:
            raise RuntimeError(f'{index}: <html lang="ru"> not found - cannot mark the static build')
        html = html.replace(marker, '<html lang="ru" data-mode="static">', 1)
    # Pages caches assets for ~10 minutes, so a rebuilt app.js would otherwise
    # keep rendering the previous UI; the content hash makes the URL change.
    index.write_text(stamp_assets(html, out_dir), encoding="utf-8")

    data_dir = out_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(dataset_path, data_dir / "cars.json")
    meta = _meta(dataset)
    (data_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # GitHub Pages would otherwise run Jekyll over the build output.
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    return meta


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Build the static dashboard into docs/")
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--force", action="store_true", help="overwrite a directory not built by this script")
    args = parser.parse_args(argv)

    try:
        meta = build_static(args.dataset, args.out, force=args.force)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Build failed: {error}", file=sys.stderr)
        return 1

    size = (args.out / "data" / "cars.json").stat().st_size
    print(f"Built static dashboard -> {args.out}")
    print(f"  cars: {meta['count']} | scraped_at: {meta['scraped_at']} | dataset: {size / 1024:.0f} KB")
    print(f"  open locally: py -m http.server 8001 --directory {args.out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
