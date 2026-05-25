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


REQUIRED_KEYS = [f.name for f in dataclasses.fields(Config)]


def load_config(path: Path) -> Config:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a YAML mapping, got: {type(data).__name__}")
    for key in REQUIRED_KEYS:
        if key not in data:
            raise KeyError(f"Missing required config key: {key}")
    return Config(**{k: data[k] for k in REQUIRED_KEYS})
