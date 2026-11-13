from __future__ import annotations
from datetime import datetime, timezone
from .errors import APIError, invalid_coords
from .stats import analyze, InsufficientData, FILL
from .summary import build_summary

LAT_STEP, LON_STEP = 0.5, 0.625        # MERRA-2 grid spacing


def snap(lat: float, lon: float) -> tuple[float, float]:
    return round(round(lat / LAT_STEP) * LAT_STEP, 3), round(round(lon / LON_STEP) * LON_STEP, 3)


def validate(lat: float, lon: float):
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or lat != lat or lon != lon:
        raise invalid_coords()


def _has_any_valid(monthly: dict) -> bool:
    return any(v is not None and float(v) != FILL for v in monthly.values())


async def analyze_location(lat: float, lon: float, fetch, cache, last_full_year: int) -> dict:
    validate(lat, lon)
    cell_lat, cell_lon = snap(lat, lon)
    key = f"{cell_lat:.3f},{cell_lon:.3f}:{last_full_year}"

    if (hit := await cache.get(key)) is not None:
        return {**hit, "location": {"lat": lat, "lon": lon}, "cached": True}

    t_m, p_m = await fetch(cell_lat, cell_lon, last_full_year)
    if not (_has_any_valid(t_m) and _has_any_valid(p_m)):
        raise APIError("POWER_EMPTY", "NASA returned no valid data for this location.", 404)
    try:
        result = analyze(t_m, p_m, last_full_year)
    except InsufficientData as e:
        raise APIError("INSUFFICIENT_DATA", str(e), 422)

    payload = {
        "location": {"lat": lat, "lon": lon},
        "grid": {"approx_size_km": "50-60",
                 "note": "MERRA-2 grid cell average, not a point measurement",
                 "cell_lat": cell_lat, "cell_lon": cell_lon},
        "cached": False,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **result,
        "summary": build_summary(result),
    }
    await cache.set(key, payload)
    return payload
