"""Cache-busting for the dashboard's static assets.

A browser will happily reuse a cached ``app.js``/``styles.css`` after a rebuild,
which made the page render the *previous* UI (a missing column, an absent sort
option) until the visitor forced a hard reload. Stamping every asset URL with a
short content hash gives a rebuilt file a new URL, so a normal reload always
picks up the new code.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# Asset references as they appear in index.html, in document order.
ASSETS = ("styles.css", "analytics.js", "app.js", "vendor/echarts.min.js")


def asset_version(path: Path) -> str:
    """Short, stable fingerprint of one asset's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:10]


def stamp_assets(html: str, static_dir: Path) -> str:
    """Rewrite ``"app.js"`` -> ``"app.js?v=<hash>"`` for every known asset."""
    for name in ASSETS:
        target = static_dir / name
        if not target.is_file():
            continue
        html = html.replace(f'"{name}"', f'"{name}?v={asset_version(target)}"')
    return html
