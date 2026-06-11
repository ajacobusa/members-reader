import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml


@dataclass
class Config:
    universe: dict[str, Any]
    quality_filter: dict[str, Any]
    market_conditions: dict[str, Any]
    catalysts: dict[str, Any]
    technical_gates: dict[str, Any]
    scoring: dict[str, Any]
    signals: dict[str, Any]
    api_keys: dict[str, str]
    email: dict[str, Any]
    schedule: dict[str, Any]
    output: dict[str, Any]
    factor_weights: dict[str, Any]
    statistics: dict[str, Any]
    enrichment: dict[str, Any]
    sizing: dict[str, Any]
    probability_filter: dict[str, Any]
    backtest: dict[str, Any]
    performance: dict[str, Any]
    health: dict[str, Any]
    ranking: dict[str, Any]
    # Optional blocks (default-provided): absent in older configs without breaking.
    rate_limit: dict[str, Any] = dataclasses.field(default_factory=dict)


# Required keys are the fields that have no default value.
REQUIRED_KEYS = [
    f.name for f in dataclasses.fields(Config)
    if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
]
OPTIONAL_KEYS = [
    f.name for f in dataclasses.fields(Config)
    if f.default is not dataclasses.MISSING or f.default_factory is not dataclasses.MISSING
]


def load_config(path: Path) -> Config:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a YAML mapping, got: {type(data).__name__}")
    for key in REQUIRED_KEYS:
        if key not in data:
            raise KeyError(f"Missing required config key: {key}")
    kwargs = {k: data[k] for k in REQUIRED_KEYS}
    for k in OPTIONAL_KEYS:
        if k in data:
            kwargs[k] = data[k]
    return Config(**kwargs)
