from app import analytics


def car(**overrides):
    base = {
        "id": 1,
        "brand": "BMW",
        "model": "iX",
        "year": 2020,
        "price_usd": 30000,
        "price_byn": 90000,
        "mileage_km": 100000,
        "engine_type": "бензин",
        "body_type": "седан",
        "location": "Минск",
        "days_on_sale": 10,
        "url": "https://cars.av.by/x",
        "photo": None,
    }
    base.update(overrides)
    return base


def sample():
    return [
        car(id=1, brand="BMW", price_usd=20000, year=2018, mileage_km=120000),
        car(id=2, brand="BMW", price_usd=30000, year=2020, mileage_km=100000),
        car(id=3, brand="BMW", price_usd=40000, year=2022, mileage_km=80000),
        car(id=4, brand="Audi", price_usd=25000, year=2019, mileage_km=150000, engine_type="дизель"),
        car(id=5, brand="Audi", price_usd=35000, year=2021, mileage_km=90000, engine_type="дизель"),
        car(id=6, brand="Tesla", price_usd=45000, year=2023, mileage_km=40000, engine_type="электро"),
        car(id=7, brand="BMW", price_usd=20000, year=2018, mileage_km=120000),
        car(id=8, brand="BMW", price_usd=21000, year=2018, mileage_km=110000),
    ]


def test_summary():
    s = analytics.summary(sample())
    assert s["total"] == 8
    assert s["avg_price_usd"] == 29500.0
    assert s["median_price_usd"] == 27500.0
    assert s["top_brand"] == "BMW"
    assert s["electric_share"] == 12.5


def test_filter_cars_by_brand_and_sort():
    result = analytics.filter_cars(sample(), brand="Audi", sort="price_desc")
    assert [c["id"] for c in result] == [5, 4]


def test_filter_cars_by_price_and_mileage():
    result = analytics.filter_cars(sample(), price_min=20000, price_max=30000, mileage_max=100000)
    assert {c["id"] for c in result} == {2}


def test_filter_cars_query_matches_brand_or_model():
    assert {c["id"] for c in analytics.filter_cars(sample(), q="bmw")} == {1, 2, 3, 7, 8}
    assert {c["id"] for c in analytics.filter_cars(sample(), q="ix")} == {1, 2, 3, 4, 5, 6, 7, 8}


def test_paginate():
    page = analytics.paginate(sample(), page=2, page_size=3)
    assert page["total"] == 8
    assert page["pages"] == 3
    assert [c["id"] for c in page["items"]] == [4, 5, 6]


def test_price_histogram_uses_fixed_buckets():
    hist = analytics.price_histogram(sample())
    assert len(hist["labels"]) == len(analytics.PRICE_BUCKETS)
    assert sum(hist["values"]) == 8
    assert hist["labels"][0] == "до $3k"


def test_by_brand_filters_small_groups():
    rows = analytics.by_brand(sample(), min_count=3)
    assert [r["brand"] for r in rows] == ["BMW"]
    assert rows[0]["count"] == 5


def test_best_deals_flags_below_median():
    deals = analytics.best_deals(sample(), min_brand_count=3)
    assert deals
    assert deals[0]["discount_pct"] > 0
    assert deals[0]["brand"] == "BMW"


def test_below_brand_median_returns_every_match():
    deals = analytics.below_brand_median(sample(), min_brand_count=3)
    # BMW median is 21 000, so both 20 000 cars qualify; Audi/Tesla are too small.
    assert {d["id"] for d in deals} == {1, 7}
    assert all(d["brand"] == "BMW" for d in deals)
    assert deals[0]["brand_median_usd"] == 21000.0


def test_build_deals_paginates_all_matches():
    first = analytics.build_deals(sample(), page=1, page_size=1, min_brand_count=3)
    assert first["total"] == 2
    assert first["pages"] == 2
    assert len(first["items"]) == 1
    second = analytics.build_deals(sample(), page=2, page_size=1, min_brand_count=3)
    assert len(second["items"]) == 1
    assert {first["items"][0]["id"], second["items"][0]["id"]} == {1, 7}


def test_below_median_follows_the_chosen_sort():
    cars = [
        car(id=1, brand="BMW", price_usd=10000),
        car(id=2, brand="BMW", price_usd=20000),
        car(id=3, brand="BMW", price_usd=25000),
        car(id=4, brand="BMW", price_usd=26000),
        car(id=5, brand="BMW", price_usd=30000),
    ]
    # Default: biggest gap to the brand median first (10k is 60% below 25k).
    assert [d["id"] for d in analytics.below_brand_median(cars)] == [1, 2]
    # The listings-table sort applies to the deals block as well.
    assert [d["id"] for d in analytics.below_brand_median(cars, sort="price_desc")] == [2, 1]
    assert [d["id"] for d in analytics.below_brand_median(cars, sort="price_asc")] == [1, 2]

    deals = analytics.build_deals(cars, sort="price_desc")
    prices = [d["price_usd"] for d in deals["items"]]
    assert prices == sorted(prices, reverse=True)
    assert prices[0] == 20000


def test_build_dashboard_shape():
    data = analytics.build_dashboard(sample(), page=1, page_size=4)
    assert data["summary"]["total"] == 8
    assert data["cars"]["page_size"] == 4
    assert set(data["charts"]) == {
        "price_histogram",
        "by_brand",
        "by_body",
        "by_fuel",
        "by_year",
        "price_segments",
        "days_on_sale",
        "price_vs_mileage",
        "by_location",
    }
