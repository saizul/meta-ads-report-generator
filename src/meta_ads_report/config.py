"""YAML configuration: report options, KPI targets and insight thresholds.

Example::

    brand: Acme Studio
    currency: BDT
    theme: ocean
    targets:
      ctr_min: 1.2
      cpa_max: 250
      roas_min: 3
      frequency_max: 2.5
    thresholds:
      frequency_warn: 3
      ctr_warn: 1
    disable_rules: [spend_concentration]
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml

from .metrics import Stats

#: target key -> (metric attribute, comparison, label)
TARGET_DEFS: Dict[str, tuple] = {
    "ctr_min": ("ctr", ">=", "CTR"),
    "cpc_max": ("cpc", "<=", "CPC"),
    "cpm_max": ("cpm", "<=", "CPM"),
    "cpa_max": ("cpa", "<=", "Cost per result"),
    "roas_min": ("roas", ">=", "ROAS"),
    "frequency_max": ("frequency", "<=", "Frequency"),
}

DEFAULT_THRESHOLDS: Dict[str, float] = {
    "frequency_warn": 3.0,
    "ctr_warn": 1.0,
    "ctr_good": 2.0,
    "roas_good": 3.0,
    "cpa_multiple": 2.0,
    "min_impressions": 1000,
    "min_spend_share": 0.05,
    "concentration_share": 0.6,
    "wow_drop_pct": 20.0,
}

THEMES = ("light", "dark", "ocean")


@dataclass
class Config:
    brand: str = ""
    logo_text: str = ""
    title: str = "Meta Ads Performance Report"
    currency: Optional[str] = None
    theme: str = "light"
    targets: Dict[str, float] = field(default_factory=dict)
    thresholds: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_THRESHOLDS))
    disable_rules: List[str] = field(default_factory=list)
    top_n: int = 3


class ConfigError(ValueError):
    """Raised for invalid configuration files."""


def load_config(path: Optional[str]) -> Config:
    """Load a YAML config file (None gives defaults). Unknown keys are rejected."""
    cfg = Config()
    if not path:
        return cfg
    with open(path, encoding="utf-8") as fh:
        data: Any = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ConfigError("config root must be a mapping")
    known = {"brand", "logo_text", "title", "currency", "theme", "targets", "thresholds", "disable_rules", "top_n"}
    unknown = set(data) - known
    if unknown:
        raise ConfigError(f"unknown config keys: {', '.join(sorted(unknown))}")
    for key in ("brand", "logo_text", "title", "currency", "theme", "top_n"):
        if key in data and data[key] is not None:
            setattr(cfg, key, data[key])
    if cfg.theme not in THEMES:
        raise ConfigError(f"theme must be one of {', '.join(THEMES)}")
    targets = data.get("targets") or {}
    bad = set(targets) - set(TARGET_DEFS)
    if bad:
        raise ConfigError(f"unknown target(s): {', '.join(sorted(bad))}; valid: {', '.join(TARGET_DEFS)}")
    cfg.targets = {k: float(v) for k, v in targets.items()}
    thr = data.get("thresholds") or {}
    bad = set(thr) - set(DEFAULT_THRESHOLDS)
    if bad:
        raise ConfigError(f"unknown threshold(s): {', '.join(sorted(bad))}")
    cfg.thresholds.update({k: float(v) for k, v in thr.items()})
    cfg.disable_rules = list(data.get("disable_rules") or [])
    return cfg


def evaluate_target(stats: Stats, key: str, target: float) -> Dict[str, Any]:
    """Return ``{'label','actual','target','op','passed'}``; passed is None when
    the metric cannot be computed."""
    attr, op, label = TARGET_DEFS[key]
    actual = stats.metric(attr)
    passed: Optional[bool]
    if actual is None:
        passed = None
    else:
        passed = actual >= target if op == ">=" else actual <= target
    return {"key": key, "metric": attr, "label": label, "actual": actual, "target": target, "op": op, "passed": passed}


def evaluate_targets(stats: Stats, targets: Dict[str, float]) -> List[Dict[str, Any]]:
    return [evaluate_target(stats, k, v) for k, v in targets.items()]
