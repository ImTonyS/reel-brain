"""Loads .env into os.environ. Import before anything that reads keys."""
import os
from pathlib import Path

_f = Path(__file__).parent / ".env"
for line in _f.read_text().splitlines() if _f.exists() else []:
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.split("=", 1)
        if v.strip():
            os.environ.setdefault(k.strip(), v.strip())
