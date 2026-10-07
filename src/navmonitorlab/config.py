"""Load the YAML configs. One directory, five files; see configs/."""
from __future__ import annotations

from pathlib import Path

import yaml

FILES = {"vehicle": "vehicle_nbpe.yaml", "track": "track_record_calpers.yaml", "gp_map": "gp_map.yaml",
         "market": "market.yaml", "facility": "facility.yaml"}


def load(config_dir: Path, vehicle_file: str | None = None) -> dict:
    config_dir = Path(config_dir)
    names = dict(FILES)
    if vehicle_file:
        names["vehicle"] = vehicle_file
    cfg = {}
    for key, name in names.items():
        path = config_dir / name
        if not path.exists():
            raise FileNotFoundError(f"missing config file: {path}")
        with open(path, encoding="utf-8") as fh:
            cfg[key] = yaml.safe_load(fh) or {}
    cfg["_dir"] = str(config_dir)
    return cfg
