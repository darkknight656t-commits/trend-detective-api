import numpy as np
from app.stats import annual_means, pettitt, analyze_series, analyze

rng = np.random.default_rng(42)
YEARS = np.arange(1981, 2026)
N = len(YEARS)


def monthly_from_annual(vals, fill_some=False):
    d = {}
    for y, v in zip(YEARS, vals):
        for m in range(1, 13):
            d[f"{y}{m:02d}"] = float(v)
        d[f"{y}13"] = float(v)
    if fill_some:
        d["198505"] = -999.0
    return d


def test_known_trend_recovered():
    x = 20 + 0.03 * np.arange(N) + rng.normal(0, 0.3, N)   # 0.30 per decade
    r = analyze_series(YEARS, x)
    assert r["trend_direction"] == "increasing"
    assert abs(r["sen_slope_per_decade"] - 0.30) < 0.08


def test_pure_noise_not_significant():
    x = rng.normal(5, 1, N)
    assert analyze_series(YEARS, x)["p_raw"] > 0.05


def test_pettitt_finds_known_shift():
    x = np.r_[rng.normal(10, 0.3, 20), rng.normal(11, 0.3, N - 20)]
    r = analyze_series(YEARS, x)
    assert abs(r["pettitt_year"] - YEARS[20]) <= 1
    assert r["pettitt_p_raw"] < 0.01


def test_fill_value_drops_incomplete_year():
    d = monthly_from_annual(np.arange(N, dtype=float), fill_some=True)
    yrs, _ = annual_means(d, 2025)
    assert 1985 not in yrs and len(yrs) == N - 1


def test_current_year_dropped():
    d = monthly_from_annual(np.arange(N, dtype=float))
    yrs, _ = annual_means(d, 2024)
    assert yrs.max() == 2024


def test_spurious_correlation_removed_by_detrending():
    # two independent series that both trend upward -> raw rho high, detrended ~0
    t = 0.05 * np.arange(N) + rng.normal(0, 0.2, N)
    p = 0.02 * np.arange(N) + rng.normal(0, 0.1, N)
    out = analyze(monthly_from_annual(t), monthly_from_annual(p), 2025)
    c = out["correlation"]
    assert c["spearman_raw"] > 0.6
    assert abs(c["spearman_detrended"]) < 0.4
