import json
import numpy as np
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.cache import MemoryCache
from app.errors import APIError
from app.power import fetch_monthly

rng = np.random.default_rng(7)
LAST = 2025


def fake_monthly(start=1981, trend=0.03, base=20.0, noise=0.4):
    d = {}
    for i, y in enumerate(range(start, LAST + 1)):
        for m in range(1, 13):
            seas = 8 * np.sin((m - 4) / 12 * 2 * np.pi)
            d[f"{y}{m:02d}"] = float(base + trend * i + seas + rng.normal(0, noise))
        d[f"{y}13"] = base
    return d


def make_client(fetch=None):
    calls = {"n": 0}

    async def default_fetch(lat, lon, end):
        calls["n"] += 1
        return fake_monthly(), fake_monthly(trend=0.0, base=2.0, noise=0.3)

    app = create_app(fetch=fetch or default_fetch, cache=MemoryCache(), last_full_year=LAST)
    return TestClient(app), calls


def test_contract_and_cache():
    c, calls = make_client()
    r = c.get("/analyze", params={"lat": 31.55, "lon": 74.34})
    assert r.status_code == 200
    j = r.json()
    for k in ["location", "grid", "cached", "fetched_at", "years", "temperature",
              "precipitation", "correlation", "summary", "meta"]:
        assert k in j
    assert j["cached"] is False
    assert j["temperature"]["confidence"] == "Strong"
    assert abs(j["temperature"]["sen_slope_per_decade"] - 0.30) < 0.1
    assert j["precipitation"]["confidence"] == "No significant trend"
    assert j["meta"]["source"] == "NASA POWER (MERRA-2)"
    assert 2 <= len(j["summary"]) <= 3
    # a nearby click in the same grid cell hits the cache, and fetch ran once
    r2 = c.get("/analyze", params={"lat": 31.60, "lon": 74.40}).json()
    assert r2["cached"] is True and calls["n"] == 1
    assert r2["location"] == {"lat": 31.60, "lon": 74.40}


def test_summary_is_template_only_and_non_causal():
    c, _ = make_client()
    text = " ".join(c.get("/analyze", params={"lat": 10, "lon": 10}).json()["summary"]).lower()
    for bad in ["because", "due to", "will ", "forecast", "predict", "caused by", "proves"]:
        assert bad not in text


def test_all_fill_values_is_power_empty():
    async def empty(lat, lon, end):
        d = {f"{y}{m:02d}": -999.0 for y in range(1981, LAST + 1) for m in range(1, 13)}
        return d, d
    c, _ = make_client(empty)
    r = c.get("/analyze", params={"lat": 0, "lon": -30})
    assert r.status_code == 404 and r.json()["error"]["code"] == "POWER_EMPTY"


def test_short_series_is_insufficient_data():
    async def short(lat, lon, end):
        d = fake_monthly(start=2012)
        return d, d
    c, _ = make_client(short)
    r = c.get("/analyze", params={"lat": 5, "lon": 5})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INSUFFICIENT_DATA"


@pytest.mark.parametrize("q", [{"lat": 95, "lon": 0}, {"lat": 0, "lon": 200}, {"lat": "abc", "lon": 0}, {"lat": 1}])
def test_invalid_coordinates(q):
    c, _ = make_client()
    r = c.get("/analyze", params=q)
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_COORDINATES"


def test_power_down_returns_honest_error_not_numbers():
    async def down(lat, lon, end):
        raise APIError("POWER_UNAVAILABLE", "NASA's data service did not respond.", 502)
    c, _ = make_client(down)
    r = c.get("/analyze", params={"lat": 31, "lon": 74})
    assert r.status_code == 502
    assert set(r.json()) == {"error"} and r.json()["error"]["code"] == "POWER_UNAVAILABLE"


# ---- power.py parsing / status handling against a mocked NASA response shape ----
def _client_returning(status, body):
    return httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(status, json=body)))


@pytest.mark.asyncio
async def test_power_parse_ok():
    body = {"properties": {"parameter": {"T2M": {"198101": 10.0}, "PRECTOTCORR": {"198101": 1.0}}}}
    async with _client_returning(200, body) as cl:
        t, p = await fetch_monthly(31.5, 74.375, 2025, client=cl)
    assert t == {"198101": 10.0} and p == {"198101": 1.0}


@pytest.mark.asyncio
async def test_power_429_and_bad_shape():
    async with _client_returning(429, {}) as cl:
        with pytest.raises(APIError) as e:
            await fetch_monthly(1, 1, 2025, client=cl)
    assert e.value.code == "RATE_LIMITED"
    async with _client_returning(200, {"oops": 1}) as cl:
        with pytest.raises(APIError) as e:
            await fetch_monthly(1, 1, 2025, client=cl)
    assert e.value.code == "POWER_UNAVAILABLE"
