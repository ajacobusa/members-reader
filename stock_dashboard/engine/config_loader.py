from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml

REQUIRED_KEYS = [
    "universe", "quality_filter", "market_conditions", "catalysts",
    "technical_gates", "scoring", "signals", "api_keys", "email",
    "schedule", "output",
]


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


def load_config(path: Path) -> Config:
    data = yaml.safe_load(path.read_text())
    for key in REQUIRED_KEYS:
        if key not in data:
            raise KeyError(f"Missing required config key: {key}")
    return Config(**{k: data[k] for k in REQUIRED_KEYS})
