"""Hand-written SVG figures from committed demo output. No plotting library needed."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import ConfigurationError

WIDTH, HEIGHT = 720, 360
MARGIN = {"left": 70, "right": 20, "top": 40, "bottom": 50}
PALETTE = ("#1f5f8b", "#d97b29", "#3a8f5a")
FONT = "font-family='Helvetica, Arial, sans-serif' font-size='12'"


def _load_evidence(output_dir: Path) -> list[dict[str, Any]]:
    docs = []
    for p in sorted(output_dir.glob("*/evidence.json")):
        with p.open("r", encoding="utf-8") as fh:
            docs.append(json.load(fh))
    if not docs:
        raise ConfigurationError(f"no evidence.json under {output_dir}; run 'python -m sec_business_evidence demo' first")
    return docs


def _ratio_series(doc: dict[str, Any], ratio: str) -> list[tuple[int, float]]:
    out = []
    for fy in doc["fiscal_years"]:
        for r in fy["ratios"]:
            if r["name"] == ratio and r["value"] is not None:
                out.append((fy["fy"], float(r["value"])))
    return out


def _revenue_series(doc: dict[str, Any]) -> list[tuple[int, int]]:
    """Revenue per fiscal year from the evidence entries cited by receivables_to_revenue."""
    out: dict[int, int] = {}
    cite = {e["id"]: e for e in doc["evidence"]}
    for fy in doc["fiscal_years"]:
        for r in fy["ratios"]:
            if r["name"] == "receivables_to_revenue":
                for cid in r["citation_ids"]:
                    e = cite[cid]
                    if e["tag"] in ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"):
                        out[fy["fy"]] = int(e["value"])
    return sorted(out.items())


def _frame(title: str, subtitle: str) -> list[str]:
    return [
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{WIDTH}' height='{HEIGHT}' viewBox='0 0 {WIDTH} {HEIGHT}'>",
        f"<rect width='{WIDTH}' height='{HEIGHT}' fill='white'/>",
        f"<text x='{MARGIN['left']}' y='20' {FONT} font-size='15' font-weight='bold'>{title}</text>",
        f"<text x='{MARGIN['left']}' y='{HEIGHT - 12}' {FONT} fill='#555'>{subtitle}</text>",
    ]


def _scale(vmin: float, vmax: float, pixels: tuple[float, float]):
    span = (vmax - vmin) or 1.0
    lo, hi = pixels
    return lambda v: lo + (v - vmin) / span * (hi - lo)


def grouped_bars(docs: list[dict[str, Any]]) -> str:
    series = [(d["issuer"]["name"], _revenue_series(d)) for d in docs]
    years = sorted({fy for _, s in series for fy, _ in s})
    vmax = max((v for _, s in series for _, v in s), default=1)
    x0, x1 = MARGIN["left"], WIDTH - MARGIN["right"]
    y0, y1 = HEIGHT - MARGIN["bottom"], MARGIN["top"]
    ys = _scale(0, vmax * 1.1, (y0, y1))
    group_w = (x1 - x0) / max(len(years), 1)
    bar_w = group_w / (len(series) + 1)
    parts = _frame("Revenue by fiscal year (USD, synthetic fixture v1)",
                   "Computed by make demo on synthetic fixture v1, seed 42. Fictional issuers; not a benchmark result.")
    parts.append(f"<line x1='{x0}' y1='{y0}' x2='{x1}' y2='{y0}' stroke='#333'/>")
    for k in range(5):
        v = vmax * 1.1 * k / 4
        y = ys(v)
        parts.append(f"<line x1='{x0 - 4}' y1='{y:.1f}' x2='{x0}' y2='{y:.1f}' stroke='#333'/>")
        parts.append(f"<text x='{x0 - 8}' y='{y + 4:.1f}' {FONT} text-anchor='end'>{v / 1e9:.1f}B</text>")
    for gi, fy in enumerate(years):
        gx = x0 + gi * group_w
        parts.append(f"<text x='{gx + group_w / 2:.1f}' y='{y0 + 16}' {FONT} text-anchor='middle'>FY{fy}</text>")
        for si, (_, s) in enumerate(series):
            val = dict(s).get(fy)
            if val is None:
                continue
            bx = gx + bar_w * (si + 0.5)
            by = ys(val)
            parts.append(f"<rect x='{bx:.1f}' y='{by:.1f}' width='{bar_w * 0.9:.1f}' height='{y0 - by:.1f}' fill='{PALETTE[si % 3]}'/>")
    for si, (name, _) in enumerate(series):
        lx = x0 + si * 220
        parts.append(f"<rect x='{lx}' y='{MARGIN['top'] - 14}' width='10' height='10' fill='{PALETTE[si % 3]}'/>")
        parts.append(f"<text x='{lx + 14}' y='{MARGIN['top'] - 5}' {FONT}>{name}</text>")
    parts.append("</svg>")
    return "\n".join(parts)


def line_chart(docs: list[dict[str, Any]], ratio: str, title: str, fmt: str) -> str:
    series = [(d["issuer"]["name"], _ratio_series(d, ratio)) for d in docs]
    points = [(fy, v) for _, s in series for fy, v in s]
    if not points:
        raise ConfigurationError(f"no values for ratio {ratio}")
    years = sorted({fy for fy, _ in points})
    vmin, vmax = min(v for _, v in points), max(v for _, v in points)
    pad = (vmax - vmin) * 0.15 or 1.0
    x0, x1 = MARGIN["left"], WIDTH - MARGIN["right"]
    y0, y1 = HEIGHT - MARGIN["bottom"], MARGIN["top"]
    xs = _scale(years[0], years[-1] if len(years) > 1 else years[0] + 1, (x0 + 30, x1 - 30))
    ys = _scale(vmin - pad, vmax + pad, (y0, y1))
    parts = _frame(title, "Computed by make demo on synthetic fixture v1, seed 42. Fictional issuers; not a benchmark result.")
    parts.append(f"<line x1='{x0}' y1='{y0}' x2='{x1}' y2='{y0}' stroke='#333'/>")
    parts.append(f"<line x1='{x0}' y1='{y0}' x2='{x0}' y2='{y1}' stroke='#333'/>")
    for k in range(5):
        v = (vmin - pad) + (vmax - vmin + 2 * pad) * k / 4
        y = ys(v)
        parts.append(f"<text x='{x0 - 8}' y='{y + 4:.1f}' {FONT} text-anchor='end'>{fmt.format(v)}</text>")
        parts.append(f"<line x1='{x0}' y1='{y:.1f}' x2='{x1}' y2='{y:.1f}' stroke='#eee'/>")
    for fy in years:
        parts.append(f"<text x='{xs(fy):.1f}' y='{y0 + 16}' {FONT} text-anchor='middle'>FY{fy}</text>")
    for si, (name, s) in enumerate(series):
        if not s:
            continue
        path = " ".join(f"{'M' if i == 0 else 'L'}{xs(fy):.1f},{ys(v):.1f}" for i, (fy, v) in enumerate(s))
        parts.append(f"<path d='{path}' fill='none' stroke='{PALETTE[si % 3]}' stroke-width='2'/>")
        for fy, v in s:
            parts.append(f"<circle cx='{xs(fy):.1f}' cy='{ys(v):.1f}' r='3.5' fill='{PALETTE[si % 3]}'/>")
        lx = x0 + si * 220
        parts.append(f"<rect x='{lx}' y='{MARGIN['top'] - 14}' width='10' height='10' fill='{PALETTE[si % 3]}'/>")
        parts.append(f"<text x='{lx + 14}' y='{MARGIN['top'] - 5}' {FONT}>{name}</text>")
    parts.append("</svg>")
    return "\n".join(parts)


def pipeline_diagram() -> str:
    steps = ["companyfacts JSON", "point in time (filed <= D)", "amendment versioning",
             "deduplicate", "annual / quarterly split", "ratios + citations", "review flags"]
    w, h = 96, 44
    parts = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{WIDTH}' height='120' viewBox='0 0 {WIDTH} 120'>",
             f"<rect width='{WIDTH}' height='120' fill='white'/>"]
    for i, label in enumerate(steps):
        x = 8 + i * (w + 6)
        parts.append(f"<rect x='{x}' y='30' width='{w}' height='{h}' rx='6' fill='#eef3f8' stroke='#1f5f8b'/>")
        words = label.split(" ")
        half = (len(words) + 1) // 2
        for li, line in enumerate((" ".join(words[:half]), " ".join(words[half:]))):
            parts.append(f"<text x='{x + w / 2:.1f}' y='{48 + li * 14}' {FONT} font-size='10' text-anchor='middle'>{line}</text>")
        if i < len(steps) - 1:
            parts.append(f"<line x1='{x + w}' y1='52' x2='{x + w + 6}' y2='52' stroke='#333'/>")
    parts.append(f"<text x='8' y='100' {FONT} fill='#555'>Selection order used by sec_business_evidence.pipeline.analyze. Output: evidence.json, flow.json, summary.md.</text>")
    parts.append("</svg>")
    return "\n".join(parts)


def render_all(output_dir: str | Path, figures_dir: str | Path) -> list[Path]:
    docs = _load_evidence(Path(output_dir))
    fig = Path(figures_dir)
    fig.mkdir(parents=True, exist_ok=True)
    written = []
    for name, svg in (
        ("revenue_by_year.svg", grouped_bars(docs)),
        ("dso_by_year.svg", line_chart(docs, "dso", "Days sales outstanding by fiscal year", "{:.0f}")),
        ("ocf_to_net_income.svg", line_chart(docs, "ocf_to_net_income", "Operating cash flow to net income", "{:.2f}")),
        ("pipeline.svg", pipeline_diagram()),
    ):
        p = fig / name
        p.write_text(svg + "\n", encoding="utf-8")
        written.append(p)
    return written
