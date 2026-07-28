from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .apple import _fetch_html, listing_from_summary, parse_catalog
from .config import ConfigError
from .models import Listing, ProductCategory, Region, WatchRule
from .setup_config import add_rule, make_rule, read_watch_config
from .storefronts import storefront

Input = Callable[[str], str]
Output = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class RuleOptions:
    listings: tuple[Listing, ...]

    @property
    def models(self) -> tuple[str, ...]:
        return tuple(sorted({value.product for value in self.listings if value.product}))

    def values(self, model: str, field: str) -> tuple[object, ...]:
        return tuple(
            sorted(
                {
                    value
                    for listing in self.listings
                    if listing.product == model
                    if (value := getattr(listing, field)) is not None
                },
                key=str,
            )
        )


def discover_rule_options(
    region: Region,
    category: ProductCategory,
    *,
    fetcher: Callable[[str], str] | None = None,
) -> RuleOptions:
    store = storefront(region)
    get = fetcher or (
        lambda url: _fetch_html(url, store.locale, 20)
    )
    summaries = parse_catalog(
        get(store.catalog_url(category)),
        category=category,
        base_url=store.base_url,
        currency=store.currency,
    )
    listings = tuple(
        listing
        for summary in summaries
        if (listing := listing_from_summary(summary)).product is not None
    )
    return RuleOptions(listings)


def _choose[T](
    prompt: str,
    values: tuple[T, ...],
    *,
    input_fn: Input,
    output: Output,
    allow_any: bool = False,
    allow_manual: bool = False,
) -> T | str | None:
    choices: list[tuple[str, T | str | None]] = []
    if allow_any:
        choices.append(("Any", None))
    choices.extend((str(value), value) for value in values)
    if allow_manual:
        choices.append(("Enter manually", "__manual__"))
    for index, (label, _value) in enumerate(choices, 1):
        output(f"  {index}. {label}")
    while True:
        answer = input_fn(f"{prompt} [1-{len(choices)}]: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(choices):
            return choices[int(answer) - 1][1]
        output("Please enter one of the displayed numbers.")


def _manual(prompt: str, input_fn: Input) -> str:
    while True:
        value = input_fn(f"{prompt}: ").strip()
        if value:
            return value


def _manual_criterion(field: str, input_fn: Input, output: Output) -> object | None:
    numeric = {
        "display_size_inches",
        "cpu_cores",
        "gpu_cores",
        "memory_gb",
    }
    while True:
        value = input_fn(
            f"{field.replace('_', ' ').title()} "
            "(leave blank for Any): "
        ).strip()
        if not value:
            return None
        if field not in numeric:
            return value
        if value.isdigit() and int(value) > 0:
            return int(value)
        output("Please enter a positive whole number, or leave blank for Any.")


def _region_for(path: Path, input_fn: Input, output: Output) -> Region:
    if path.exists():
        region, _rules = read_watch_config(path)
        output(f"Using installation region: {region.value}")
        return region
    selected = _choose(
        "Choose an Apple Store region",
        tuple(Region),
        input_fn=input_fn,
        output=output,
    )
    return Region(selected)


def interactive_add_rule(
    path: Path,
    *,
    input_fn: Input = input,
    output: Output = print,
    fetcher: Callable[[str], str] | None = None,
    region_override: Region | None = None,
    save: bool = True,
) -> WatchRule:
    region = region_override or _region_for(path, input_fn, output)
    category = ProductCategory(
        _choose(
            "Choose a product category",
            tuple(ProductCategory),
            input_fn=input_fn,
            output=output,
        )
    )
    options: RuleOptions | None
    try:
        output("Loading current options from Apple...")
        options = discover_rule_options(region, category, fetcher=fetcher)
        if not options.models:
            raise ConfigError("Apple returned no supported models")
    except Exception as exc:
        output(f"Could not load live options ({exc}). Continuing with manual entry.")
        options = None

    if options:
        model = _choose(
            "Choose a model",
            options.models,
            input_fn=input_fn,
            output=output,
            allow_manual=True,
        )
        if model == "__manual__":
            model = _manual("Exact model name", input_fn)
    else:
        model = _manual("Exact model name", input_fn)
    assert isinstance(model, str)

    fields = {
        ProductCategory.MAC: (
            "display_size_inches",
            "chip",
            "cpu_cores",
            "gpu_cores",
            "memory_gb",
            "storage",
            "color",
        ),
        ProductCategory.IPHONE: ("storage", "color"),
        ProductCategory.IPAD: (
            "display_size_inches",
            "storage",
            "color",
            "connectivity",
        ),
    }[category]
    criteria: dict[str, object | None] = {}
    for field in fields:
        values = options.values(model, field) if options else ()
        if not values:
            criteria[field] = _manual_criterion(field, input_fn, output)
            continue
        selected = _choose(
            f"Choose {field.replace('_', ' ')}",
            values,
            input_fn=input_fn,
            output=output,
            allow_any=True,
            allow_manual=True,
        )
        criteria[field] = (
            _manual_criterion(field, input_fn, output)
            if selected == "__manual__"
            else selected
        )
    rule_id = _manual("Rule ID (for example: work-mac)", input_fn)
    rule = make_rule(
        rule_id=rule_id,
        category=category.value,
        model=model,
        **criteria,
    )
    if save:
        add_rule(path, region, rule)
        output(f"Added rule {rule.id}. Current matching stock will notify immediately.")
    return rule
