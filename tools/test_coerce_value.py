"""Quick checks for PLC Int64 -> local Double conversion."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from asyncua import ua  # noqa: E402
from gateway import coerce_value, get_variant_type  # noqa: E402


def main() -> None:
    assert coerce_value(47, get_variant_type("Double")) == 47.0
    assert coerce_value(2027, get_variant_type("Double")) == 2027.0
    assert coerce_value(False, get_variant_type("Double")) == 0.0
    assert coerce_value(True, get_variant_type("Boolean")) is True
    assert coerce_value(16, get_variant_type("Int64")) == 16
    print("coerce_value: OK")


if __name__ == "__main__":
    main()
