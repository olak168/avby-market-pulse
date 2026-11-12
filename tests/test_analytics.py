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


def test_filter_cannot_raise_the_brand_median():
    # Filtering to newer cars used to recompute the brand median from the
    # selection, so a 40k car looked cheap next to a 45k filtered median even
    # though the brand's real median is 30k. The full dataset is the reference.
    cars = [
        car(id=1, brand="A", price_usd=10000, year=2010),
        car(id=2, brand="A", price_usd=20000, year=2012),
        car(id=3, brand="A", price_usd=30000, year=2014),
        car(id=4, brand="A", price_usd=40000, year=2020),
        car(id=5, brand="A", price_usd=50000, year=2022),
    ]
    deals = analytics.build_deals(cars, year_min=2020)
    assert deals["total"] == 0
    assert deals["items"] == []

    dashboard = analytics.build_dashboard(cars, year_min=2020)
    assert dashboard["deals"]["total"] == 0
    assert dashboard["best_deals"] == []
    # The full view still finds the two cars below the 30k median.
    assert [d["id"] for d in analytics.below_brand_median(cars)] == [1, 2]
    assert analytics.below_brand_median(cars)[0]["brand_median_usd"] == 30000


def test_every_deal_stays_below_the_full_brand_median():
    # Mixed brands and years: no active filter may let a car in that is not
    # cheaper than the median its brand has across the whole dataset.
    cars = [
        car(id=1, brand="A", price_usd=10000, year=2011),
        car(id=2, brand="A", price_usd=20000, year=2013),
        car(id=3, brand="A", price_usd=30000, year=2015),
        car(id=4, brand="A", price_usd=40000, year=2019),
        car(id=5, brand="A", price_usd=50000, year=2021),
        car(id=6, brand="B", price_usd=12000, year=2010),
        car(id=7, brand="B", price_usd=16000, year=2012),
        car(id=8, brand="B", price_usd=20000, year=2014),
        car(id=9, brand="B", price_usd=24000, year=2018),
        car(id=10, brand="B", price_usd=28000, year=2020),
    ]
    medians = {"A": 30000, "B": 20000}
    for filters in (
        {},
        {"year_min": 2018},
        {"year_min": 2014, "price_max": 30000},
        {"brand": "A", "year_min": 2015},
    ):
        for sort in analytics.SORT_OPTIONS:
            items = analytics.below_brand_median(
                analytics.filter_cars(cars, **filters), sort=sort, reference=cars
            )
            for deal in items:
                assert deal["price_usd"] < medians[deal["brand"]]
                assert deal["brand_median_usd"] == medians[deal["brand"]]


def test_model_filter_narrows_the_selection():
    rows = analytics.filter_cars(sample(), model="iX")
    assert rows
    assert all(c["model"] == "iX" for c in rows)


def test_model_filter_switches_the_deals_scope():
    cars = [
        car(id=1, brand="A", model="M1", price_usd=10000, year=2010),
        car(id=2, brand="A", model="M1", price_usd=20000, year=2012),
        car(id=3, brand="A", model="M1", price_usd=30000, year=2014),
        car(id=4, brand="A", model="M1", price_usd=40000, year=2016),
        car(id=5, brand="A", model="M1", price_usd=50000, year=2018),
        car(id=6, brand="A", model="M2", price_usd=60000, year=2020),
        car(id=7, brand="A", model="M2", price_usd=70000, year=2021),
        car(id=8, brand="A", model="M2", price_usd=80000, year=2022),
    ]
    # Brand scope: the median of all eight cars is 45k, so 10k..40k qualify.
    brand_deals = analytics.build_deals(cars)
    assert [d["id"] for d in brand_deals["items"]] == [1, 2, 3, 4]
    assert brand_deals["scope"]["scope"] == "brand"
    assert brand_deals["scope"]["group_count"] is None  # no brand filter → no group
    assert all(d["median_scope"] == "brand" for d in brand_deals["items"])
    assert brand_deals["items"][0]["brand_median_usd"] == 45000

    # Model scope: the M1 median is 30k, so 40k drops out even though it is
    # below the brand median.
    model_deals = analytics.build_deals(cars, brand="A", model="M1")
    assert [d["id"] for d in model_deals["items"]] == [1, 2]
    assert model_deals["scope"] == {
        "scope": "model",
        "brand": "A",
        "model": "M1",
        "min_count": 3,
        "group_count": 5,
    }
    assert all(d["median_scope"] == "model" for d in model_deals["items"])
    assert model_deals["items"][0]["brand_median_usd"] == 30000

    dashboard = analytics.build_dashboard(cars, brand="A", model="M1")
    assert dashboard["deals"]["scope"]["scope"] == "model"
    assert [d["id"] for d in dashboard["best_deals"]] == [1, 2]
    assert [d["id"] for d in dashboard["deals"]["items"]] == [1, 2]


def test_model_scope_needs_enough_listings_for_a_median():
    cars = [
        car(id=1, brand="A", model="M3", price_usd=1000, year=2020),
        car(id=2, brand="A", model="M3", price_usd=2000, year=2021),
        car(id=3, brand="A", model="M3", price_usd=3000, year=2022),
        car(id=4, brand="A", model="M3", price_usd=4000, year=2023),
    ]
    enough = analytics.build_deals(cars, brand="A", model="M3")
    assert enough["total"] == 2  # 1000 and 2000 are below the 2500 median
    assert enough["scope"]["min_count"] == 3
    assert enough["scope"]["group_count"] == 4

    thin = analytics.build_deals(cars[:2], brand="A", model="M3")
    assert thin["total"] == 0
    assert thin["scope"]["group_count"] == 2
    assert thin["scope"]["min_count"] == 3


def test_score_is_five_for_year_plus_five_for_mileage():
    cars = [
        car(id=1, brand="A", year=2000, mileage_km=300000),
        car(id=2, brand="A", year=2010, mileage_km=150000),
        car(id=3, brand="A", year=2020, mileage_km=1000),
    ]
    scored = {c["id"]: c for c in analytics.with_score(cars)}
    # Newest + lowest mileage = the full 10, oldest + highest = 0.
    assert scored[3]["score_year"] == 5.0
    assert scored[3]["score_mileage"] == 5.0
    assert scored[3]["score"] == 10.0
    assert scored[1]["score_year"] == 0.0
    assert scored[1]["score_mileage"] == 0.0
    assert scored[1]["score"] == 0.0
    assert all(0 <= c["score"] <= 10 for c in scored.values())


def test_score_is_stable_when_filters_change():
    full = {c["id"]: c for c in analytics.filter_cars(sample())}
    bmw = {c["id"]: c for c in analytics.filter_cars(sample(), brand="BMW")}
    assert bmw[1]["score"] == full[1]["score"]


def test_sort_by_score_desc_orders_both_blocks():
    cars = [
        car(id=1, brand="BMW", year=1998, mileage_km=400000, price_usd=20000),
        car(id=2, brand="BMW", year=2019, mileage_km=90000, price_usd=30000),
        car(id=3, brand="BMW", year=2022, mileage_km=20000, price_usd=40000),
        car(id=4, brand="BMW", year=2001, mileage_km=350000, price_usd=15000),
        car(id=5, brand="BMW", year=2015, mileage_km=180000, price_usd=25000),
    ]
    table = analytics.filter_cars(cars, sort="score_desc")
    scores = [c["score"] for c in table]
    assert scores == sorted(scores, reverse=True)
    assert table[0]["id"] == 3

    deals = analytics.build_deals(cars, page=1, page_size=10, sort="score_desc")
    deal_scores = [d["score"] for d in deals["items"]]
    assert deal_scores == sorted(deal_scores, reverse=True)
    assert all(d["score"] is not None for d in deals["items"])


def test_sort_by_score_then_price_asc():
    # Score comes first: a cheap high-score listing must beat an expensive
    # low-score one. Price only breaks ties inside the same score.
    cars = [
        car(id=1, brand="BMW", price_usd=10000, year=2020, mileage_km=30000),
        car(id=2, brand="BMW", price_usd=50000, year=2005, mileage_km=400000),
        car(id=3, brand="BMW", price_usd=30000, year=2019, mileage_km=40000),
        car(id=4, brand="BMW", price_usd=20000, year=2018, mileage_km=60000),
        car(id=5, brand="BMW", price_usd=20000, year=2010, mileage_km=200000),
    ]
    table = analytics.filter_cars(cars, sort="score_price_asc")
    assert table[0]["id"] == 1
    assert table[-1]["id"] == 2

    scores = [c["score"] for c in table]
    assert scores == sorted(scores, reverse=True)
    prices = [c["price_usd"] for c in table]
    assert prices != sorted(prices), "score must dominate price"
    for left, right in zip(table, table[1:]):
        if left["score"] == right["score"]:
            assert left["price_usd"] <= right["price_usd"]

    # Below-median deals must follow the same rule: score first, price second.
    deals_cars = [
        car(id=11, brand="A", price_usd=10000, year=2000, mileage_km=400000),
        car(id=12, brand="A", price_usd=10000, year=2020, mileage_km=20000),
        car(id=13, brand="A", price_usd=15000, year=2010, mileage_km=200000),
        car(id=14, brand="A", price_usd=30000, year=2016, mileage_km=90000),
        car(id=15, brand="A", price_usd=40000, year=2017, mileage_km=80000),
        car(id=16, brand="A", price_usd=50000, year=2022, mileage_km=10000),
    ]
    deals = analytics.build_deals(deals_cars, page=1, page_size=10, sort="score_price_asc")
    assert [d["id"] for d in deals["items"]] == [12, 13, 11]


def test_score_price_sort_is_offered():
    labels = [label for label, _ in analytics.SORT_OPTIONS.values()]
    assert "В порядке убывания скорингового балла и возрастания цены" in labels


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
