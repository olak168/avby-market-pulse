from fastapi.testclient import TestClient

from app.server import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["cars"] > 0


def test_dashboard_returns_all_sections():
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["total"] > 0
    assert data["cars"]["items"]
    assert "price_histogram" in data["charts"]
    assert data["meta"]["count"] > 0
    assert any(o["id"] == "price_asc" for o in data["sort_options"])


def test_dashboard_brand_filter_narrows_results():
    response = client.get("/api/dashboard", params={"brand": "BMW", "page_size": 5})
    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["total"] > 0
    assert all(item["brand"] == "BMW" for item in data["cars"]["items"])


def test_dashboard_rejects_bad_pagination():
    assert client.get("/api/dashboard", params={"page_size": 500}).status_code == 422
    assert client.get("/api/dashboard", params={"page": 0}).status_code == 422


def test_export_csv_is_downloadable():
    response = client.get("/api/export.csv", params={"brand": "BMW"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert "Марка;Модель" in response.text


def test_deals_pagination_covers_every_match():
    first = client.get("/api/deals", params={"page_size": 5}).json()
    assert first["total"] > 0
    assert len(first["items"]) == 5
    assert first["pages"] == -(-first["total"] // 5)

    last = client.get("/api/deals", params={"page_size": 5, "page": first["pages"]}).json()
    seen = {d["id"] for d in first["items"]} | {d["id"] for d in last["items"]}
    assert len(seen) == len(first["items"]) + len(last["items"])

    dashboard = client.get("/api/dashboard").json()
    assert dashboard["deals"]["total"] == first["total"]


def test_deals_follow_the_filters():
    data = client.get("/api/deals", params={"brand": "BMW", "page_size": 100}).json()
    assert data["total"] > 0
    assert all(d["brand"] == "BMW" for d in data["items"])


def test_deals_csv_contains_all_rows():
    total = client.get("/api/deals").json()["total"]
    response = client.get("/api/deals.csv")
    assert response.status_code == 200
    assert "Ниже медианы, %" in response.text
    rows = [line for line in response.text.splitlines() if line.strip()]
    assert len(rows) == total + 1  # header + every match, not just one page


def test_filtered_deals_csv_stays_below_the_full_brand_median():
    # Medians must come from the whole dataset, not from the filtered slice:
    # the CSV export of a filtered view has to obey the same rule as the UI.
    import csv
    import io

    from app import analytics
    from app.store import get_cars

    cars = get_cars()
    prices = {}
    for car in cars:
        if car.get("brand") and car.get("price_usd"):
            prices.setdefault(car["brand"], []).append(car["price_usd"])
    medians = {b: analytics._median(p) for b, p in prices.items() if len(p) >= 5}

    response = client.get("/api/deals.csv", params={"year_min": 2024})
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.text.lstrip("\ufeff")), delimiter=";"))
    assert rows
    for row in rows:
        assert float(row["Цена, USD"]) < medians[row["Марка"]]
        assert float(row["Медиана, USD"]) == medians[row["Марка"]]


def test_deals_csv_uses_the_model_median_when_a_model_is_selected():
    # The CSV has to agree with the block: with a model filter it must compare
    # against the brand+model median, not the brand median.
    import csv
    import io

    from app import analytics
    from app.store import get_cars

    cars = get_cars()
    prices = [
        c["price_usd"]
        for c in cars
        if c.get("brand") == "BMW" and c.get("model") == "X3" and c.get("price_usd")
    ]
    model_median = analytics._median(prices)
    brand_median = analytics._median(
        [c["price_usd"] for c in cars if c.get("brand") == "BMW" and c.get("price_usd")]
    )
    assert model_median != brand_median

    response = client.get("/api/deals.csv", params={"brand": "BMW", "model": "X3"})
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.text.lstrip("\ufeff")), delimiter=";"))
    assert rows
    for row in rows:
        assert row["Марка"] == "BMW" and row["Модель"] == "X3"
        assert float(row["Медиана, USD"]) == model_median
        assert float(row["Цена, USD"]) < model_median

    # Same row count as the paginated block, which is the whole point.
    deals = client.get("/api/deals", params={"brand": "BMW", "model": "X3", "page_size": 100})
    assert len(rows) == deals.json()["total"]


def test_filters_offer_models_per_brand():
    data = client.get("/api/filters").json()
    assert data["models"]
    assert all({"brand", "name", "count"} <= set(m) for m in data["models"])
    bmw = [m for m in data["models"] if m["brand"] == "BMW"]
    assert any(m["name"] == "X3" for m in bmw)
    # A model name may repeat across brands, so the pair is the key.
    pairs = {(m["brand"], m["name"]) for m in data["models"]}
    assert len(pairs) == len(data["models"])


def test_model_filter_switches_deals_to_the_model_median():
    from app import analytics
    from app.store import get_cars

    cars = get_cars()
    x3_prices = [
        c["price_usd"] for c in cars if c.get("brand") == "BMW" and c.get("model") == "X3"
    ]
    model_median = analytics._median(x3_prices)
    brand_median = analytics._median(
        [c["price_usd"] for c in cars if c.get("brand") == "BMW"]
    )
    assert model_median != brand_median

    data = client.get(
        "/api/deals", params={"brand": "BMW", "model": "X3", "page_size": 100}
    ).json()
    assert data["scope"]["scope"] == "model"
    assert data["scope"]["model"] == "X3"
    assert data["scope"]["group_count"] == len(x3_prices)
    assert all(d["model"] == "X3" for d in data["items"])
    assert all(d["price_usd"] < model_median for d in data["items"])
    assert all(d["brand_median_usd"] == model_median for d in data["items"])
    assert all(d["median_scope"] == "model" for d in data["items"])

    dashboard = client.get("/api/dashboard", params={"brand": "BMW", "model": "X3"}).json()
    assert dashboard["deals"]["scope"]["scope"] == "model"
    assert dashboard["summary"]["total"] == len(x3_prices)

    exported = client.get("/api/export.csv", params={"brand": "BMW", "model": "X3"})
    rows = [line for line in exported.text.splitlines() if line.strip()]
    assert len(rows) == len(x3_prices) + 1


def test_index_is_served():
    response = client.get("/")
    assert response.status_code == 200
    assert "Market Pulse" in response.text


def test_static_assets_are_always_revalidated():
    # A cached app.js/styles.css made a rebuilt dashboard keep the old UI
    # (a missing column) until a hard reload, so the server forbids reuse.
    for path in ("/", "/app.js", "/styles.css", "/analytics.js"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers.get("cache-control") == "no-cache, must-revalidate", path


def test_index_fingerprints_every_asset():
    # A rebuild must produce new asset URLs, otherwise a browser keeps the old
    # app.js and the dashboard shows a stale UI after an update.
    from app.server import STATIC_DIR
    from app.versioning import asset_version

    html = client.get("/").text
    for name in ("styles.css", "analytics.js", "app.js", "vendor/echarts.min.js"):
        assert f'"{name}?v={asset_version(STATIC_DIR / name)}"' in html, name
    assert '"app.js"' not in html, "unfingerprinted app.js would be served from cache"


