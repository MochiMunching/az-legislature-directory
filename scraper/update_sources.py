"""
Write data/sources.json: when each public data source was last refreshed.
Runs at the end of every scheduled refresh; the site shows it on the Updates tab.
Also collects bill fact sheets (scraper/bill_docs.py) and rebuilds data/updates_feed.json (scraper/capitol_updates.py) for the
"Latest from the Capitol" section, so the workflow file doesn't need a new step.

    python scraper/update_sources.py
"""
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
DATA = ROOT / "data"


def load(name):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def refresh_bill_docs():
    """Collect official fact sheets for tracked bills (data/bill_docs.json). Never stops the refresh."""
    try:
        import bill_docs
        bill_docs.main()
    except Exception as e:
        print(f"Bill fact sheets skipped: {type(e).__name__}: {e}")


def refresh_updates_feed():
    """Rebuild data/updates_feed.json. Never stops the rest of the refresh."""
    try:
        import capitol_updates
        capitol_updates.main()
    except Exception as e:  # one bad source can't break the site build
        print(f"Capitol updates feed skipped: {type(e).__name__}: {e}")


def main():
    refresh_bill_docs()
    try:
        import bill_summaries
        bill_summaries.main()
    except Exception as e:
        print(f"Bill summaries skipped: {type(e).__name__}: {e}")
    refresh_updates_feed()
    feed = load("updates_feed.json")
    leg, sch, cen, chg = load("legislators.json"), load("schedule.json"), load("centers.json"), load("changes.json")
    bills, esop, elect, impact = load("bills.json"), load("esop_watch.json"), load("members_elect.json"), load("district_impact.json")
    src = [
        {"source": "Member roster", "what": "Names, districts, contact details, leadership", "as_of": leg and leg.get("retrieved"),
         "refresh": "Automatic: weekdays January–June, Mondays otherwise", "url": "https://www.azleg.gov/memberroster/"},
        {"source": "Committee assignments", "what": "Standing committees, JLBC, chairs", "as_of": "2026-03-20",
         "refresh": "Manual when new lists are published (usually December or January)", "url": "https://www.azsenate.gov/arizona-state-senate-legislative-lists/"},
        {"source": "Committee schedule", "what": "Weekly meeting days, times and rooms",
         "as_of": sch and max(v["revised"] for v in sch["sources"].values()),
         "refresh": "Manual each session", "url": "https://azhouse.gov/legislative-lists/"},
        {"source": "Roster changes", "what": "Joins, departures, office and committee changes",
         "as_of": chg and max((c["date"] for c in chg["changes"] if c.get("date")), default=None),
         "refresh": "Automatic with each roster refresh", "url": None},
        {"source": "Members-elect", "what": "November 3 winners, new or returning", "as_of": elect and elect.get("updated") if elect and elect.get("members_elect") else None,
         "refresh": "Manual from certified results", "url": None},
        {"source": "Bills and votes", "what": "Tracked bills, sponsors, roll calls", "as_of": bills and bills.get("retrieved"),
         "refresh": "Automatic when an Open States key is set", "url": "https://open.pluralpolicy.com"},
        {"source": "ESOP watch", "what": "Bills mentioning employee ownership", "as_of": esop and esop.get("retrieved"),
         "refresh": "Automatic when an Open States key is set", "url": None},
        {"source": "Capitol updates feed", "what": "Governor bill actions, budget reports, Capitol news, tracked bill actions",
         "as_of": feed and feed.get("updated"), "refresh": "Automatic with each scheduled refresh", "url": None},
        {"source": "SBDC centers", "what": "Locations, counties served, district matches", "as_of": cen and cen.get("retrieved"),
         "refresh": "Manual if centers change", "url": "https://www.arizonasbdc.com/locations/"},
        {"source": "District boundaries", "what": "Official 2022 legislative map and 2020 population", "as_of": "2022 maps",
         "refresh": "Fixed until the next redistricting", "url": "https://redistricting-irc-az.hub.arcgis.com/pages/official-maps"},
        {"source": "SBDC district results", "what": "Clients and results per district", "as_of": impact and impact.get("updated"),
         "refresh": "Manual from SBDC's client export", "url": None},
    ]
    (DATA / "sources.json").write_text(json.dumps({"generated": date.today().isoformat(), "sources": src}, indent=2), encoding="utf-8")
    print("Wrote data/sources.json")


if __name__ == "__main__":
    main()
