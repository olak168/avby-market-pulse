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


def test_index_is_served():
    response = client.get("/")
    assert response.status_code == 200
    assert "Market Pulse" in response.text
