"""Generate the synthetic example CSVs in this folder (no real data).

Run from the repository root:  python examples/generate_sample.py
"""
import csv
import datetime as dt
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))

# name, daily BDT spend, CPM (BDT), link CTR %, daily freq factor, conv rate on clicks, order value (BDT)
CAMPAIGNS = [
    ("Eid Sale - Prospecting", 2600, 190, 2.4, 1.15, 0.016, 1800),
    ("Retargeting - Cart Abandoners", 1100, 310, 3.1, 2.10, 0.034, 2200),
    ("Brand Awareness - Reels", 1500, 95, 0.7, 3.40, 0.003, 1500),
    ("Lookalike 1% - Buyers", 1900, 240, 1.6, 1.20, 0.013, 1900),
]
ADSETS = {"Eid Sale - Prospecting": ["Dhaka 18-34", "Chattogram 18-34"],
          "Retargeting - Cart Abandoners": ["Cart 7d", "Viewed 14d"],
          "Brand Awareness - Reels": ["Broad BD", "Interest - Fashion"],
          "Lookalike 1% - Buyers": ["LAL Purchasers", "LAL Top Spenders"]}
ADS = ["Video A", "Static B"]
AGES = ["18-24", "25-34", "35-44", "45-54"]
GENDERS = ["female", "male"]
PLACEMENTS = ["Facebook Feed", "Instagram Feed", "Instagram Stories", "Instagram Reels", "Audience Network"]
REGIONS = ["Dhaka", "Chattogram", "Sylhet", "Rajshahi"]


def metrics(rng, spend, cpm, ctr, freq, cvr, aov, days=1):
    impr = int(spend / cpm * 1000 * rng.uniform(0.92, 1.08))
    clicks = int(impr * ctr / 100 * rng.uniform(0.9, 1.1))
    results = round(clicks * cvr * rng.uniform(0.8, 1.2))
    reach = max(1, int(impr / (freq * rng.uniform(0.95, 1.05))))
    roas = round(results * aov / spend, 2) if results else 0
    return impr, reach, clicks, results, roas


def base_row(c, a, ad, day, m, spend):
    impr, reach, clicks, results, roas = m
    cpr = round(spend / results, 2) if results else ""
    return {
        "Day": day.isoformat(), "Campaign name": c, "Ad set name": a, "Ad name": ad,
        "Amount spent (BDT)": round(spend, 2), "Impressions": impr, "Reach": reach,
        "Link clicks": clicks, "Result type": "Purchases", "Results": results,
        "Cost per result": cpr, "Purchases": results, "Purchase ROAS (return on ad spend)": roas or "",
        "Reporting starts": day.isoformat(), "Reporting ends": day.isoformat(),
    }


def daily_file(path, start, days, seed, scale=1.0, fatigue=False):
    rng = random.Random(seed)
    rows = []
    for d in range(days):
        day = start + dt.timedelta(days=d)
        for c, spend, cpm, ctr, freq, cvr, aov in CAMPAIGNS:
            for a in ADSETS[c]:
                for k, ad in enumerate(ADS):
                    s = spend * scale / 4 * rng.uniform(0.85, 1.15) * (1.2 if k == 0 else 0.8)
                    f = freq * (1 + (0.04 * d if fatigue and c.startswith("Brand") else 0))
                    rows.append(base_row(c, a, ad, day, metrics(rng, s, cpm, ctr, f, cvr, aov), s))
    write(path, rows)


def breakdown_file(path, start, days, seed, dims):
    rng = random.Random(seed)
    rows = []
    for c, spend, cpm, ctr, freq, cvr, aov in CAMPAIGNS:
        for combo in dims:
            weight = rng.uniform(0.5, 1.5)
            s = spend * days * weight / (len(dims) * 1.0)
            m = metrics(rng, s, cpm * rng.uniform(0.8, 1.3), ctr * rng.uniform(0.7, 1.3), freq, cvr * rng.uniform(0.6, 1.4), aov)
            row = base_row(c, "", "", start, m, s)
            for k in ("Ad set name", "Ad name", "Day"):
                row.pop(k)
            row["Reporting starts"] = start.isoformat()
            row["Reporting ends"] = (start + dt.timedelta(days=days - 1)).isoformat()
            row.update(combo)
            rows.append(row)
    write(path, rows)


def write(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    cur = dt.date(2026, 3, 16)
    prev = dt.date(2026, 3, 2)
    daily_file(os.path.join(HERE, "sample-week1.csv"), cur, 7, 1, fatigue=True)
    daily_file(os.path.join(HERE, "sample-week2.csv"), cur + dt.timedelta(days=7), 7, 2, fatigue=True)
    daily_file(os.path.join(HERE, "sample-previous.csv"), prev, 14, 3, scale=0.9)
    breakdown_file(os.path.join(HERE, "sample-age-gender.csv"), cur, 14, 4,
                   [{"Age": a, "Gender": g} for a in AGES for g in GENDERS])
    breakdown_file(os.path.join(HERE, "sample-placement.csv"), cur, 14, 5,
                   [{"Placement": p} for p in PLACEMENTS])
    breakdown_file(os.path.join(HERE, "sample-region.csv"), cur, 14, 6,
                   [{"Region": r} for r in REGIONS])
