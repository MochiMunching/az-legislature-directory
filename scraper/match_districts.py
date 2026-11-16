"""
Match AZ SBDC centers to Arizona districts, legislative (30) or congressional (9).

Two outputs per level:
  1. Which districts each center serves, from county overlap: a district counts
     for a center when at least --min-share of the district's area lies in one
     of the center's counties.
  2. Which district each center's office sits in, by geocoding its street
     address with the free Census geocoder.

Boundaries default to Census TIGER/Line 2022 (Arizona state senate districts,
which are the IRC 2022 legislative districts; or 118th Congress districts).
You can pass the IRC's own maps instead, including the KMZ downloads:

    pip install geopandas requests
    python scraper/match_districts.py                                        # legislative, TIGER
    python scraper/match_districts.py --districts-file Approved_Official_Legislative_Map.kmz
    python scraper/match_districts.py --level congressional --districts-file Approved_Official_Congressional_Map.kmz

Legislative results go to data/centers.json (legislative_districts, home_district)
and data/district_centers.json. Congressional results go to data/centers.json
(congressional_districts, home_congressional_district) and data/congressional_centers.json.
"""
import argparse
import json
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
import requests
from shapely.geometry import Point
from shapely.validation import make_valid

ROOT = Path(__file__).resolve().parent.parent
TIGER = {
    "legislative": "https://www2.census.gov/geo/tiger/TIGER2022/SLDU/tl_2022_04_sldu.zip",
    "congressional": "https://www2.census.gov/geo/tiger/TIGER2022/CD/tl_2022_04_cd118.zip",
}
TIGER_COUNTY = "https://www2.census.gov/geo/tiger/TIGER2022/COUNTY/tl_2022_us_county.zip"
GEOCODER = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
EQUAL_AREA = "EPSG:26912"  # NAD83 / UTM 12N, good for area across Arizona
LEVELS = {
    "legislative": {"count": 30, "served": "legislative_districts", "home": "home_district", "out": "district_centers.json"},
    "congressional": {"count": 9, "served": "congressional_districts", "home": "home_congressional_district", "out": "congressional_centers.json"},
}
BOUNDARIES = ROOT / "data" / "boundaries"
LOCAL = {
    "legislative": BOUNDARIES / "Approved_Official_Legislative_Map.kmz",
    "congressional": BOUNDARIES / "Approved_Official_Congressional_Map.kmz",
    "county": BOUNDARIES / "az_counties.geojson",
}
FIELD_GUESSES =["SLDUST", "CD118FP", "CD116FP", "DISTRICT", "District", "Name", "NAME"]


def read_any(path):
    """Read shapefile/GeoJSON/zip/KML, plus KMZ (a zipped KML)."""
    p = str(path)
    if p.lower().endswith(".kmz"):
        tmp = Path(tempfile.mkdtemp())
        with zipfile.ZipFile(p) as z:
            z.extractall(tmp)
        kmls = sorted(tmp.rglob("*.kml"))
        if not kmls:
            raise SystemExit(f"No .kml inside {p}")
        p = str(kmls[0])
    return gpd.read_file(p)


def polygons_only(geom):
    """KML exports often wrap polygons in GeometryCollections; keep the area parts."""
    geom = make_valid(geom)
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom
    parts = [g for g in getattr(geom, "geoms", []) if g.geom_type in ("Polygon", "MultiPolygon")]
    if not parts:
        return None
    from shapely.ops import unary_union
    return unary_union(parts)


def load_districts(path, field, level):
    gdf = read_any(path or (LOCAL[level] if LOCAL[level].exists() else TIGER[level]))
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    field = field or next((f for f in FIELD_GUESSES if f in gdf.columns), None)
    if not field:
        raise SystemExit(f"Pass --field; columns are {list(gdf.columns)}")
    gdf = gdf[[field, "geometry"]].rename(columns={field: "district"})
    gdf["district"] = gdf["district"].astype(str).str.extract(r"(\d+)")[0].astype(int)
    gdf["geometry"] = gdf.geometry.apply(polygons_only)
    gdf = gdf[gdf.geometry.notna() & gdf["district"].between(1, LEVELS[level]["count"])]
    # One row per district (KML can split a district across placemarks)
    gdf = gdf.dissolve(by="district", as_index=False)
    found = sorted(gdf["district"])
    expected = list(range(1, LEVELS[level]["count"] + 1))
    if found != expected:
        raise SystemExit(f"Expected {level} districts {expected[0]}-{expected[-1]}, found {found}. "
                         f"Is this the right map for --level {level}?")
    return gdf.to_crs(EQUAL_AREA)


def load_counties(path):
    gdf = read_any(path or (LOCAL["county"] if LOCAL["county"].exists() else TIGER_COUNTY))
    if "STATEFP" in gdf.columns:
        gdf = gdf[gdf["STATEFP"] == "04"]
    name = "NAME" if "NAME" in gdf.columns else "name"
    return gdf[[name, "geometry"]].rename(columns={name: "county"}).to_crs(EQUAL_AREA)


def county_overlap(districts, counties):
    """Share of each district's area in each county, and share of each county in each district."""
    d = districts.copy()
    d["d_area"] = d.area
    c = counties.copy()
    c["c_area"] = c.area
    pieces = gpd.overlay(d, c, how="intersection", keep_geom_type=True)
    pieces["share"] = pieces.area / pieces["d_area"]
    pieces["county_share"] = pieces.area / pieces["c_area"]
    return pieces[["district", "county", "share", "county_share"]]


def geocode(address):
    r = requests.get(GEOCODER, params={"address": address, "benchmark": "Public_AR_Current", "format": "json"}, timeout=30)
    r.raise_for_status()
    matches = r.json()["result"]["addressMatches"]
    if not matches:
        return None
    c = matches[0]["coordinates"]
    return Point(c["x"], c["y"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", choices=LEVELS, default="legislative")
    ap.add_argument("--districts-file", "--ld-file", dest="districts_file",
                    help="district boundaries: shapefile, GeoJSON, zip, KML or KMZ")
    ap.add_argument("--field", "--ld-field", dest="field", help="column holding the district number")
    ap.add_argument("--county-file", help="county boundaries; defaults to TIGER 2022")
    ap.add_argument("--min-share", type=float, default=0.01, help="count a district when this share of its area is in a served county (default 0.01)")
    ap.add_argument("--min-county-share", type=float, default=0.02,
                    help="also count it when it covers this share of a served county's area (default 0.02); "
                         "catches large rural districts that reach into a county")
    ap.add_argument("--no-geocode", action="store_true", help="skip locating each office's home district")
    args = ap.parse_args()
    cfg = LEVELS[args.level]

    centers_path = ROOT / "data" / "centers.json"
    centers_doc = json.loads(centers_path.read_text(encoding="utf-8"))
    centers = centers_doc["centers"]

    districts = load_districts(args.districts_file, args.field, args.level)
    counties = load_counties(args.county_file)
    overlap = county_overlap(districts, counties)
    overlap = overlap[(overlap["share"] >= args.min_share) | (overlap["county_share"] >= args.min_county_share)]

    by_district = {d: [] for d in range(1, cfg["count"] + 1)}
    for c in centers:
        shares = overlap[overlap["county"].isin(c["counties"])].groupby("district")["share"].sum()
        c[cfg["served"]] = sorted(int(d) for d in shares.index)
        for d, s in shares.items():
            by_district[int(d)].append({"center": c["id"], "share_of_district": round(float(s), 3)})

        if not args.no_geocode:
            try:
                pt = geocode(f"{c['address']}, {c['city']}, AZ {c['zip']}")
            except requests.RequestException as e:
                print(f"  ! geocode failed for {c['name']}: {e}")
                pt = None
            home = None
            if pt is not None:
                c["lat"], c["lon"] = round(pt.y, 5), round(pt.x, 5)
                p = gpd.GeoSeries([pt], crs="EPSG:4326").to_crs(EQUAL_AREA).iloc[0]
                hit = districts[districts.contains(p)]
                home = int(hit["district"].iloc[0]) if len(hit) else None
            c[cfg["home"]] = home

    for d in by_district:
        by_district[d].sort(key=lambda x: -x["share_of_district"])

    if args.districts_file:
        source = Path(args.districts_file).name
    elif LOCAL[args.level].exists():
        source = f"the IRC {LOCAL[args.level].stem.replace('_', ' ')}"
    else:
        source = f"TIGER/Line 2022 {args.level} districts"
    method = (f"County overlap with {source}; a district counts when at least {args.min_share:.0%} of its area "
              f"is in a served county, or it covers at least {args.min_county_share:.0%} of a served county.")
    centers_doc.setdefault("district_methods", {})[args.level] = method
    if args.level == "legislative":
        centers_doc["district_method"] = method
    centers_path.write_text(json.dumps(centers_doc, indent=2, ensure_ascii=False), encoding="utf-8")
    (ROOT / "data" / cfg["out"]).write_text(
        json.dumps({"level": args.level, "method": method, "districts": by_district}, indent=2), encoding="utf-8")

    label = "LD" if args.level == "legislative" else "CD"
    for c in centers:
        print(f"{c['name']:<34} office {label} {c.get(cfg['home'])!s:<5} serves {label}s {c[cfg['served']]}")
    unserved = [d for d, v in by_district.items() if not v]
    print("districts with no center match:", unserved or "none")


if __name__ == "__main__":
    main()
