"""Cache: in-memory by default, Supabase if configured. Failures never break a request."""
from __future__ import annotations
import logging, os, time
import httpx

log = logging.getLogger("cache")
TTL_SECONDS = 30 * 24 * 3600       # POWER monthly data changes at most monthly


class MemoryCache:
    def __init__(self):
        self._d: dict[str, tuple[float, dict]] = {}

    async def get(self, key: str):
        hit = self._d.get(key)
        if hit and time.time() - hit[0] < TTL_SECONDS:
            return hit[1]
        return None

    async def set(self, key: str, payload: dict):
        self._d[key] = (time.time(), payload)


class SupabaseCache:
    """Table: analysis_cache(key text primary key, payload jsonb, created_at timestamptz default now())."""
    def __init__(self, url: str, service_key: str):
        self.base = f"{url.rstrip('/')}/rest/v1/analysis_cache"
        self.h = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
        self.mem = MemoryCache()

    async def get(self, key: str):
        if (m := await self.mem.get(key)) is not None:
            return m
        try:
            async with httpx.AsyncClient(timeout=4.0) as c:
                r = await c.get(self.base, headers=self.h,
                                params={"key": f"eq.{key}", "select": "payload"})
            rows = r.json() if r.status_code == 200 else []
            if rows:
                await self.mem.set(key, rows[0]["payload"])
                return rows[0]["payload"]
        except Exception as e:                      # noqa: BLE001
            log.warning("supabase get failed: %s", e)
        return None

    async def set(self, key: str, payload: dict):
        await self.mem.set(key, payload)
        try:
            async with httpx.AsyncClient(timeout=4.0) as c:
                await c.post(self.base, json={"key": key, "payload": payload},
                             headers={**self.h, "Prefer": "resolution=merge-duplicates"})
        except Exception as e:                      # noqa: BLE001
            log.warning("supabase set failed: %s", e)


def make_cache():
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY")
    return SupabaseCache(url, key) if url and key else MemoryCache()
