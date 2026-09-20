import json
from pathlib import Path

import pytest

from feishu_label_printer.config import read_config

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def config():
    cfg = read_config(ROOT / "config.example.json")
    # Cross-platform tests use the bundled OFL font, not Windows-only fonts.
    cfg["fonts"]["text"] = cfg["fonts"]["dot"]
    cfg["fonts"]["mono"] = cfg["fonts"]["dot"]
    return cfg


@pytest.fixture
def prototype_row():
    return json.loads((ROOT / "examples/prototype.json").read_text(encoding="utf-8"))
