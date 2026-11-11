import json

import pytest

from scraper.avby import ScrapeError, parse_advert, parse_page


def _page(adverts, page=1, page_count=4202, total=105033):
    payload = {
        "props": {
            "initialState": {
                "filter": {
                    "main": {
                        "adverts": adverts,
                        "page": page,
                        "pageCount": page_count,
                        "count": total,
                    }
                }
            }
        }
    }
    return (
        '<html><body><script id="__NEXT_DATA__" type="application/json" '
        f'crossorigin="anonymous">{json.dumps(payload)}</script></body></html>'
    )


def _advert(**overrides):
    advert = {
        "id": 139092238,
        "publicUrl": "https://cars.av.by/bmw/ix/139092238",
        "price": {"usd": {"amount": 55000}, "byn": {"amount": 164868}},
        "shortLocationName": "Минск",
        "sellerName": "Иван",
        "publishedAt": "2026-09-07T12:40:26+0000",
        "originalDaysOnSale": 65,
        "top": True,
        "photos": [
            {"main": False, "medium": {"url": "https://avcdn.av.by/a.jpg"}},
            {"main": True, "medium": {"url": "https://avcdn.av.by/main.jpg"}},
        ],
        "properties": [
            {"name": "brand", "value": "BMW"},
            {"name": "model", "value": "iX"},
            {"name": "year", "value": "2023"},
            {"name": "mileage_km", "value": 87000},
            {"name": "engine_type", "value": "электро"},
            {"name": "engine_power", "value": 326},
            {"name": "engine_capacity", "value": "2,0"},
            {"name": "transmission_type", "value": "автомат"},
            {"name": "body_type", "value": "внедорожник 5 дв."},
            {"name": "drive_type", "value": "постоянный полный привод"},
            {"name": "color", "value": "красный"},
            {"name": "condition", "value": "с пробегом"},
        ],
    }
    advert.update(overrides)
    return advert


def test_parse_advert_flattens_properties():
    car = parse_advert(_advert())
    assert car.id == 139092238
    assert car.brand == "BMW"
    assert car.model == "iX"
    assert car.year == 2023
    assert car.price_usd == 55000
    assert car.price_byn == 164868
    assert car.mileage_km == 87000
    assert car.engine_power == 326
    assert car.engine_capacity == 2.0  # comma decimal is normalised
    assert car.body_type == "внедорожник 5 дв."
    assert car.location == "Минск"
    assert car.days_on_sale == 65
    assert car.is_top is True
    assert car.photo == "https://avcdn.av.by/main.jpg"


def test_parse_page_returns_pagination():
    cars, pagination = parse_page(_page([_advert(), _advert(id=2)]))
    assert len(cars) == 2
    assert pagination == {"page": 1, "page_count": 4202, "total": 105033}


def test_parse_page_missing_next_data_raises():
    with pytest.raises(ScrapeError):
        parse_page("<html>no data here</html>")


def test_parse_advert_tolerates_missing_fields():
    car = parse_advert({"id": 1, "properties": []})
    assert car.id == 1
    assert car.price_usd is None
    assert car.year is None
    assert car.photo is None
    assert car.url == ""
