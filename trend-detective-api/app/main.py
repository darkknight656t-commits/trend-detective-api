from __future__ import annotations
import os
from datetime import datetime, timezone
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .cache import make_cache
from .errors import APIError, invalid_coords
from .power import fetch_monthly
from .service import analyze_location


def create_app(fetch=None, cache=None, last_full_year: int | None = None) -> FastAPI:
    app = FastAPI(title="Trend Detective API")
    origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",")]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET"], allow_headers=["*"])
    fetch = fetch or fetch_monthly
    cache = cache or make_cache()

    def _err(e: APIError):
        return JSONResponse({"error": {"code": e.code, "message": e.message}}, status_code=e.status)

    @app.exception_handler(APIError)
    async def _api_err(_: Request, e: APIError):
        return _err(e)

    @app.exception_handler(RequestValidationError)
    async def _val_err(_: Request, __):
        return _err(invalid_coords("lat and lon must be numbers."))

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/analyze")
    async def analyze_endpoint(lat: float = Query(...), lon: float = Query(...)):
        year = last_full_year or datetime.now(timezone.utc).year - 1
        return await analyze_location(lat, lon, fetch, cache, year)

    return app


app = create_app()
