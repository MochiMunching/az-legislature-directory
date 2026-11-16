"""
Match SBDC client records to Arizona legislative districts.

Input: a CSV exported from SBDC's client system. Any of these column sets works:
  - latitude, longitude                          (used as-is)
  - address, city, zip   (or street/city/state/zip) (geocoded with the free Census batch geocoder)
Optional numeric columns are summed per district when present:
  jobs_created, jobs_retained, capital_accessed, hours, sessions

    pip install geopandas requests
    python scraper/match_clients.py path/to/clients.csv
    python scraper/match_clients.py path/to/clients.csv --publish-aggregates

Writes (always, private):
  private/clients_with_districts.csv   each row plus its district (stays out of git)
  private/district_impact.json         full per-district totals
With --publish-aggregates, also writes data/district_impact.json for the public
site: counts and totals per district only, with small counts suppressed
(fewer than --min-count clients shows as "fewer than N").
"""
import argparse
import csv
import io
import json
from datetime import date
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = ROOT / "private"
KMZ = ROOT / "data" / "boundaries" / "Approved_Official_Legislative_Map.kmz"
GEOJSON = ROOT / "data" / "districts.geojson"
BATCH_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
SUM_FIELDS = ["jobs_created", "jobs_retained", "capital_accessed", "hours", "sessions"]


def load_districts():
    if KMZ.exists():
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import match_districts
        return match_districts.load_districts(KMZ, None, "legislative").to_crs("EPSG:4326")
    return gpd.read_file(GEOJSON)


def col(df, *names):
    for n in names:
        for c in df.columns:
            if c.strip().lower() == n:
                return c
    return None


def geocode_batch(df, street, city, state, zipc):
    """Census batch geocoder: up to 10,000 rows per request, no key."""
    lat = pd.Series(index=df.index, dtype=float)
    lon = pd.Series(index=df.index, dtype=float)
    for start in range(0, len(df), 9000):
        chunk = df.iloc[start:start + 9000]
        buf = io.StringIO()
        w = csv.writer(buf)
        for i, r in chunk.iterrows():
            w.writerow([i, r[street], r[city] if city else "", r[state] if state else "AZ", r[zipc] if zipc else ""])
        resp = requests.post(BATCH_URL, files={"addressFile": ("a.csv", buf.getvalue())},
                             data={"benchmark": "Public_AR_Current"}, timeout=600)
        resp.raise_for_status()
        for row in csv.reader(io.StringIO(resp.text)):
            if len(row) >= 6 and row[2] == "Match":
                x, y = row[5].split(",")
                lon[int(row[0])], lat[int(row[0])] = float(x), float(y)
        print(f"  geocoded rows {start + 1}-{start + len(chunk)}")
    return lat, lon


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--publish-aggregates", action="store_true")
    ap.add_argument("--min-count", type=int, default=5, help="suppress public counts below this (default 5)")
    args = ap.parse_args()

    df = pd.read_csv(args.csv, dtype=str).fillna("")
    lat_c, lon_c = col(df, "latitude", "lat"), col(df, "longitude", "lon", "lng")
    if lat_c and lon_c:
        lat = pd.to_numeric(df[lat_c], errors="coerce")
        lon = pd.to_numeric(df[lon_c], errors="coerce")
    else:
        street = col(df, "address", "street", "address1", "street_address")
        if not street:
            raise SystemExit(f"Need latitude/longitude or an address column. Columns: {list(df.columns)}")
        lat, lon = geocode_batch(df, street, col(df, "city"), col(df, "state"), col(df, "zip", "zipcode", "postal_code"))

    pts = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(lon, lat), crs="EPSG:4326")
    located = pts[lat.notna() & lon.notna()]
    joined = gpd.sjoin(located, load_districts()[["district", "geometry"]], how="left", predicate="within")
    df["district"] = joined["district"].reindex(df.index)

    PRIVATE.mkdir(exist_ok=True)
    df.drop(columns="geometry", errors="ignore").to_csv(PRIVATE / "clients_with_districts.csv", index=False)

    sums = [f for f in SUM_FIELDS if col(df, f)]
    for f in sums:
        df[col(df, f)] = pd.to_numeric(df[col(df, f)].str.replace(r"[$,]", "", regex=True), errors="coerce")
    per = {}
    for d in range(1, 31):
        rows = df[df["district"] == d]
        per[d] = {"clients": int(len(rows)), **{f: float(rows[col(df, f)].sum()) for f in sums}}

    unmatched = int(df["district"].isna().sum())
    meta = {"updated": date.today().isoformat(), "total_clients": int(len(df)), "unmatched": unmatched,
            "fields": ["clients"] + sums, "boundaries": "IRC Approved Official Legislative Map"}
    (PRIVATE / "district_impact.json").write_text(json.dumps({**meta, "districts": per}, indent=2), encoding="utf-8")

    if args.publish_aggregates:
        pub = {}
        for d, v in per.items():
            if v["clients"] < args.min_count:
                pub[d] = {"clients": None, "suppressed": f"fewer than {args.min_count}"}
            else:
                pub[d] = {k: (round(x) if isinstance(x, float) else x) for k, x in v.items()}
        (ROOT / "data" / "district_impact.json").write_text(
            json.dumps({**meta, "min_count": args.min_count, "districts": pub}, indent=2), encoding="utf-8")
        print("Wrote data/district_impact.json (public aggregates)")

    print(f"{len(df)} clients, {len(df) - unmatched} matched to a district, {unmatched} unmatched")
    print("Private detail: private/clients_with_districts.csv, private/district_impact.json")


if __name__ == "__main__":
    main()
