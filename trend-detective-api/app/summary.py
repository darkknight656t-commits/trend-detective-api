"""Template summary. Every number is read from the analysis dict. No free text, no causal or forecast wording."""
from __future__ import annotations


def fmt_p(p: float) -> str:
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}"


def corr_label(r: float) -> str:
    a = abs(r)
    return "negligible" if a < 0.2 else "weak" if a < 0.4 else "moderate" if a < 0.6 else "strong"


def _trend_sentence(name: str, s: dict, unit: str, decimals: int, up: str, down: str) -> str:
    span = f"{s['first_year']} to {s['last_year']}"
    if s["confidence"] == "No significant trend":
        return (f"No statistically significant trend in {name} was detected from {span} "
                f"(adjusted {fmt_p(s['p_adj'])}).")
    word = up if s["trend_direction"] == "increasing" else down
    support = "strong" if s["confidence"] == "Strong" else "weak"
    return (f"From {span}, {name} in this grid cell shows a {word} trend of "
            f"{s['sen_slope_per_decade']:+.{decimals}f} {unit} per decade, with {support} "
            f"statistical support (adjusted {fmt_p(s['p_adj'])}).")


def build_summary(result: dict) -> list[str]:
    t, p, c = result["temperature"], result["precipitation"], result["correlation"]
    out = [
        _trend_sentence("average air temperature at 2 m", t, "°C", 2, "warming", "cooling"),
        _trend_sentence("average precipitation", p, "mm/day", 3, "increasing", "decreasing"),
    ]
    sig = "" if c["p_detrended_adj"] < 0.05 else ", not statistically significant"
    r = c["spearman_detrended"]
    label = corr_label(r)
    kind = label if label == "negligible" else f"{label} {'negative' if r < 0 else 'positive'}"
    out.append(
        f"After removing each series' own trend, temperature and precipitation show a "
        f"{kind} correlation (Spearman ρ = {r:+.2f}{sig}); this describes association only."
    )
    return out
