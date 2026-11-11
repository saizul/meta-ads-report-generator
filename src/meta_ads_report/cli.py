"""Command line interface: ``meta-ads-report export.csv -o report.html``."""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from . import __version__
from .config import THEMES, ConfigError, load_config
from .exporters import METRICS_LEVELS, ExportUnavailable, write_metrics_csv, write_pdf, write_xlsx
from .insights import load_rule_module
from .metrics import build_report
from .render import build_context, render_html
from .summary import write_summary_json


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="meta-ads-report",
        description="Turn Meta Ads Manager CSV exports into a client-ready HTML report.",
    )
    p.add_argument("csv", nargs="+", help="one or more Ads Manager CSV exports (merged; overlaps are de-duplicated)")
    p.add_argument("-o", "--output", default="report.html", help="HTML output path (default: report.html)")
    p.add_argument("--previous", nargs="+", metavar="CSV", help="CSV export(s) for the previous period (enables comparison)")
    p.add_argument("-c", "--config", help="YAML config with brand, targets, thresholds")
    p.add_argument("--currency", help="currency label, e.g. BDT or USD (default: detected from the spend column)")
    p.add_argument("--brand", help="brand / agency name shown in the header")
    p.add_argument("--logo-text", help="short text shown in the logo badge (default: brand initials)")
    p.add_argument("--title", help="report title")
    p.add_argument("--theme", choices=THEMES, help="colour theme")
    p.add_argument("--pdf", metavar="FILE", help="also write a PDF (needs weasyprint)")
    p.add_argument("--xlsx", metavar="FILE", help="also write an Excel workbook (needs openpyxl)")
    p.add_argument("--metrics-csv", metavar="FILE", help="also write the computed metrics (CTR, CPC, CPM, CPA, ROAS ...) to a CSV file")
    p.add_argument("--metrics-level", choices=METRICS_LEVELS, default="campaign",
                   help="row level for --metrics-csv (default: campaign)")
    p.add_argument("--json", metavar="FILE", dest="json_path",
                   help="also write a machine-readable JSON summary (totals, targets, insights, tables)")
    p.add_argument("--rules", action="append", default=[], metavar="PY", help="Python file registering extra insight rules")
    p.add_argument("--no-dedupe", action="store_true", help="do not drop rows repeated across files")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = load_config(args.config)
        for key in ("brand", "logo_text", "title", "theme"):
            val = getattr(args, key)
            if val:
                setattr(cfg, key, val)
        if args.currency:
            cfg.currency = args.currency
        for path in args.rules:
            load_rule_module(path)
        rep = build_report(args.csv, cfg.currency, args.previous, dedupe=not args.no_dedupe)
    except (OSError, ValueError, ConfigError, ImportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not cfg.logo_text and cfg.brand:
        cfg.logo_text = "".join(w[0] for w in cfg.brand.split()[:3]).upper()
    html = render_html(rep, cfg)
    with open(args.output, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"wrote {args.output}")

    status = 0
    if args.metrics_csv:
        try:
            count = write_metrics_csv(rep, args.metrics_csv, args.metrics_level)
        except OSError as exc:
            print(f"error: cannot write {args.metrics_csv}: {exc.strerror}", file=sys.stderr)
            return 2
        print(f"wrote {args.metrics_csv} ({count} {args.metrics_level} rows)")
    if args.json_path:
        try:
            summary = write_summary_json(rep, cfg, args.json_path)
        except OSError as exc:
            print(f"error: cannot write {args.json_path}: {exc.strerror}", file=sys.stderr)
            return 2
        ts = summary["targets_summary"]
        note = f" ({ts['passed']} of {len(summary['targets'])} KPI targets passed)" if summary["targets"] else ""
        print(f"wrote {args.json_path}{note}")
    if args.xlsx:
        try:
            write_xlsx(build_context(rep, cfg), args.xlsx)
            print(f"wrote {args.xlsx}")
        except ExportUnavailable as exc:
            print(f"warning: {exc}; skipped", file=sys.stderr)
            status = 1
    if args.pdf:
        try:
            write_pdf(html, args.pdf)
            print(f"wrote {args.pdf}")
        except ExportUnavailable as exc:
            print(f"warning: {exc}; HTML report was still written", file=sys.stderr)
            status = 1
    return status


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
