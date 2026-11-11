"""The GitHub Pages build must stay self-contained and offline."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "data" / "cars.json"


@pytest.fixture(scope="module")
def builder():
    spec = importlib.util.spec_from_file_location("build_static", ROOT / "scripts" / "build-static.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_static_produces_self_contained_site(builder, tmp_path):
    out = tmp_path / "docs"
    meta = builder.build_static(DATASET, out)

    dataset = json.loads(DATASET.read_text(encoding="utf-8"))

    assert (out / "index.html").is_file()
    assert (out / "styles.css").is_file()
    assert (out / "app.js").is_file()
    assert (out / "analytics.js").is_file()
    assert (out / "vendor" / "echarts.min.js").is_file()
    assert (out / ".nojekyll").is_file()
    assert 'data-mode="static"' in (out / "index.html").read_text(encoding="utf-8")

    published = json.loads((out / "data" / "cars.json").read_text(encoding="utf-8"))
    assert published["count"] == dataset["count"]
    assert published["scraped_at"] == dataset["scraped_at"]
    assert len(published["cars"]) == len(dataset["cars"])

    published_meta = json.loads((out / "data" / "meta.json").read_text(encoding="utf-8"))
    assert published_meta["count"] == dataset["count"]
    assert published_meta["scraped_at"] == dataset["scraped_at"]
    assert published_meta["source"] == dataset["source"]
    assert meta["built_at"]


def test_build_static_rebuilds_cleanly(builder, tmp_path):
    out = tmp_path / "docs"
    builder.build_static(DATASET, out)
    stale = out / "stale.html"
    stale.write_text("old build", encoding="utf-8")

    builder.build_static(DATASET, out)

    assert not stale.exists(), "a rebuild must not leave files from the previous build"


def test_build_static_refuses_foreign_directory(builder, tmp_path):
    out = tmp_path / "docs"
    out.mkdir()
    (out / "keep-me.txt").write_text("user file", encoding="utf-8")

    with pytest.raises(RuntimeError):
        builder.build_static(DATASET, out)

    assert (out / "keep-me.txt").is_file()


def test_build_static_requires_dataset(builder, tmp_path):
    with pytest.raises(FileNotFoundError):
        builder.build_static(tmp_path / "missing.json", tmp_path / "docs")
