"""NASA POWER monthly point client. Real data only; never fabricates values."""
from __future__ import annotations
import asyncio
import httpx
from .errors import APIError

BASE = "https://power.larc.nasa.gov/api/temporal/monthly/point"
START_YEAR = 1981
_sem = asyncio.Semaphore(2)          # be polite to the POWER API


async def fetch_monthly(lat: float, lon: float, end_year: int,
                        client: httpx.AsyncClient | None = None) -> tuple[dict, dict]:
    params = {
        "parameters": "T2M,PRECTOTCORR", "community": "AG",
        "latitude": lat, "longitude": lon,
        "start": START_YEAR, "end": end_year, "format": "JSON",
    }
    own = client is None
    client = client or httpx.AsyncClient(timeout=20.0)
    try:
        last_err: APIError | None = None
        for attempt in range(2):
            try:
                async with _sem:
                    r = await client.get(BASE, params=params)
            except (httpx.TimeoutException, httpx.TransportError):
                last_err = APIError("POWER_UNAVAILABLE",
                                    "NASA's data service did not respond.", 502)
            else:
                if r.status_code == 429:
                    raise APIError("RATE_LIMITED",
                                   "NASA POWER is rate-limiting requests. Try again shortly.", 429)
                if r.status_code >= 500:
                    last_err = APIError("POWER_UNAVAILABLE",
                                        "NASA's data service returned an error.", 502)
                elif r.status_code != 200:
                    raise APIError("POWER_UNAVAILABLE",
                                   f"NASA POWER rejected the request (HTTP {r.status_code}).", 502)
                else:
                    return _parse(r)
            if attempt == 0:
                await asyncio.sleep(1.0)
        raise last_err  # type: ignore[misc]
    finally:
        if own:
            await client.aclose()


def _parse(r: httpx.Response) -> tuple[dict, dict]:
    try:
        par = r.json()["properties"]["parameter"]
        return par["T2M"], par["PRECTOTCORR"]
    except (ValueError, KeyError, TypeError):
        raise APIError("POWER_UNAVAILABLE",
                       "NASA POWER returned an unexpected response format.", 502)
