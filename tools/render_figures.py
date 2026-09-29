"""Render docs/figures/*.svg from examples/output. Usage: python tools/render_figures.py"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from sec_business_evidence.errors import ConfigurationError  # noqa: E402
from sec_business_evidence.figures import render_all  # noqa: E402


def main() -> int:
    try:
        written = render_all(ROOT / "examples" / "output", ROOT / "docs" / "figures")
    except ConfigurationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for p in written:
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
