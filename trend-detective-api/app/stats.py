"""
Trend Detective stats engine.
Input: monthly NASA POWER values (dict like {"198101": 12.3, ..., "198113": annual}).
Output: plain dict, every number computed from the real series.
"""
from __future__ import annotations
import numpy as np
import pymannkendall as mk
from scipy.stats import spearmanr, false_discovery_control

FILL = -999.0
MIN_YEARS = 20          # refuse to test shorter series
ALPHA = 0.05


class InsufficientData(Exception):
    pass


def annual_means(monthly: dict, last_full_year: int) -> tuple[np.ndarray, np.ndarray]:
    """Monthly -> annual means. A year counts only if all 12 months are valid
    (-999 treated as missing). Incomplete current year is dropped.
    The 'YYYY13' annual key from POWER is ignored on purpose."""
    years, vals = [], []
    by_year: dict[int, list[float]] = {}
    for key, v in monthly.items():
        y, m = int(key[:4]), int(key[4:])
        if m == 13 or y > last_full_year:
            continue
        if v is None or float(v) == FILL:
            continue
        by_year.setdefault(y, []).append(float(v))
    for y in sorted(by_year):
        if len(by_year[y]) == 12:
            years.append(y)
            vals.append(float(np.mean(by_year[y])))
    return np.array(years), np.array(vals)


def pettitt(x: np.ndarray) -> dict:
    """Pettitt (1979) change-point test. Returns index of last point of the
    first segment, and approximate p-value."""
    n = len(x)
    ranks = np.argsort(np.argsort(x)) + 1.0
    # U_t = 2 * sum(rank_1..t) - t(n+1)
    t = np.arange(1, n)
    u = 2 * np.cumsum(ranks)[:-1] - t * (n + 1)
    k = np.max(np.abs(u))
    idx = int(np.argmax(np.abs(u)))          # change after element idx
    p = min(1.0, 2.0 * np.exp(-6.0 * k**2 / (n**3 + n**2)))
    return {"index": idx, "p": float(p), "K": float(k)}


def _detrend(years: np.ndarray, x: np.ndarray, slope: float, intercept: float) -> np.ndarray:
    # pymannkendall intercept is relative to index 0..n-1
    return x - (intercept + slope * np.arange(len(x)))


def analyze_series(years: np.ndarray, x: np.ndarray) -> dict:
    """Trend + change point for ONE variable."""
    if len(x) < MIN_YEARS:
        raise InsufficientData(f"Only {len(x)} complete years; need {MIN_YEARS}.")
    t = mk.hamed_rao_modification_test(x)     # autocorrelation-corrected
    pt = pettitt(x)
    return {
        "n_years": int(len(x)),
        "first_year": int(years[0]),
        "last_year": int(years[-1]),
        "trend_direction": t.trend,           # increasing / decreasing / no trend
        "p_raw": float(t.p),
        "sen_slope_per_year": float(t.slope),
        "sen_slope_per_decade": float(t.slope * 10),
        "intercept": float(t.intercept),
        "pettitt_year": int(years[pt["index"] + 1]),   # first year of the new regime
        "pettitt_p_raw": pt["p"],
        "mean_before": float(np.mean(x[: pt["index"] + 1])),
        "mean_after": float(np.mean(x[pt["index"] + 1:])),
    }


def confidence_label(p_adj: float) -> str:
    if p_adj < 0.01:
        return "Strong"
    if p_adj < ALPHA:
        return "Weak"
    return "No significant trend"


def analyze(temp_monthly: dict, precip_monthly: dict, last_full_year: int) -> dict:
    ty, tx = annual_means(temp_monthly, last_full_year)
    py, px = annual_means(precip_monthly, last_full_year)
    common, ti, pi = np.intersect1d(ty, py, return_indices=True)
    tx, px, years = tx[ti], px[pi], common

    T = analyze_series(years, tx)
    P = analyze_series(years, px)

    rho_raw, p_raw_corr = spearmanr(tx, px)
    t_dt = _detrend(years, tx, T["sen_slope_per_year"], T["intercept"])
    p_dt = _detrend(years, px, P["sen_slope_per_year"], P["intercept"])
    rho_dt, p_dt_corr = spearmanr(t_dt, p_dt)

    # One family of 5 tests per click -> Benjamini-Hochberg FDR
    raw_ps = np.array([T["p_raw"], P["p_raw"], T["pettitt_p_raw"],
                       P["pettitt_p_raw"], p_dt_corr])
    adj = false_discovery_control(raw_ps, method="bh")
    T["p_adj"], P["p_adj"] = float(adj[0]), float(adj[1])
    T["pettitt_p_adj"], P["pettitt_p_adj"] = float(adj[2]), float(adj[3])

    for S in (T, P):
        S["confidence"] = confidence_label(S["p_adj"])
        # Only report a change point if it survives correction
        S["change_point_significant"] = S["pettitt_p_adj"] < ALPHA
    return {
        "years": years.tolist(),
        "temperature": {**T, "values": tx.tolist(), "unit": "°C"},
        "precipitation": {**P, "values": px.tolist(), "unit": "mm/day"},
        "correlation": {
            "spearman_raw": float(rho_raw), "p_raw": float(p_raw_corr),
            "spearman_detrended": float(rho_dt),
            "p_detrended_raw": float(p_dt_corr), "p_detrended_adj": float(adj[4]),
        },
        "meta": {"alpha": ALPHA, "fdr": "Benjamini-Hochberg over 5 tests",
                 "trend_test": "Mann-Kendall, Hamed-Rao modification",
                 "source": "NASA POWER (MERRA-2)"},
    }
