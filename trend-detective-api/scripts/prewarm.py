"""Run once after deploy so the 3 story locations are cached (instant demo).
Usage: python scripts/prewarm.py https://your-backend.onrender.com"""
import sys, httpx
base = sys.argv[1].rstrip("/")
for name, lat, lon in [("Arctic", 78.2, 15.6), ("Sahel", 13.5, 2.1), ("Amazon", -3.1, -60.0)]:
    r = httpx.get(f"{base}/analyze", params={"lat": lat, "lon": lon}, timeout=60)
    print(name, r.status_code, r.json().get("cached", r.json().get("error")))
