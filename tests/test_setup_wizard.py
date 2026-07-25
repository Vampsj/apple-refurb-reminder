import json
from pathlib import Path

from apple_refurb_reminder.models import ProductCategory, Region
from apple_refurb_reminder.setup_config import read_watch_config
from apple_refurb_reminder.setup_wizard import (
    discover_rule_options,
    interactive_add_rule,
)


def catalog() -> str:
    payload = {
        "tiles": [
            {
                "title": "Refurbished iPhone 16 Pro 256GB - Black Titanium",
                "partNumber": "ONE",
                "productDetailsUrl": "/shop/product/one",
                "price": {"currentPrice": {"raw_amount": "799"}},
                "filters": {
                    "dimensions": {
                        "dimensionCapacity": "256gb",
                        "dimensionColor": "blacktitanium",
                    }
                },
            },
            {
                "title": "Refurbished iPhone 16 Pro 512GB - White Titanium",
                "partNumber": "TWO",
                "productDetailsUrl": "/shop/product/two",
                "price": {"currentPrice": {"raw_amount": "999"}},
                "filters": {
                    "dimensions": {
                        "dimensionCapacity": "512gb",
                        "dimensionColor": "whitetitanium",
                    }
                },
            },
        ]
    }
    return f"<script>window.REFURB_GRID_BOOTSTRAP = {json.dumps(payload)};</script>"


def test_discovers_model_specific_options() -> None:
    options = discover_rule_options(
        Region.US,
        ProductCategory.IPHONE,
        fetcher=lambda _url: catalog(),
    )
    assert options.models == ("iPhone 16 Pro",)
    assert options.values("iPhone 16 Pro", "storage") == ("256GB", "512GB")


def test_interactive_setup_creates_rule_from_live_options(tmp_path: Path) -> None:
    answers = iter(
        [
            "2",  # US
            "2",  # iphone
            "1",  # iPhone 16 Pro
            "2",  # 256GB (Any is option 1)
            "1",  # Any color
            "phone",
        ]
    )
    messages: list[str] = []
    path = tmp_path / "watch.yaml"
    interactive_add_rule(
        path,
        input_fn=lambda _prompt: next(answers),
        output=messages.append,
        fetcher=lambda _url: catalog(),
    )
    region, rules = read_watch_config(path)
    assert region == Region.US
    assert rules[0].model == "iPhone 16 Pro"
    assert rules[0].storage == "256GB"
    assert rules[0].color is None


def test_interactive_setup_falls_back_to_manual_model(tmp_path: Path) -> None:
    answers = iter(["1", "1", "Mac Pro", "desktop"])
    path = tmp_path / "watch.yaml"
    rule = interactive_add_rule(
        path,
        input_fn=lambda _prompt: next(answers),
        output=lambda _message: None,
        fetcher=lambda _url: (_ for _ in ()).throw(TimeoutError()),
    )
    assert rule.model == "Mac Pro"
    assert rule.storage is None
