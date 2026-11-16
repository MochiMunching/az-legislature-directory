"""
Scrape the Arizona Legislature member roster into data/legislators.json.

Source: https://www.azleg.gov/memberroster/  (both chambers on one page)

    pip install requests beautifulsoup4
    python scraper/scrape_roster.py                 # roster only
    python scraper/scrape_roster.py --committees     # also visit each member page

The legislature number and session id are read from the member links, so when
azleg.gov switches to the 58th Legislature in January this picks it up without
code changes.
"""
import argparse
import json
import re
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
import roster_changes  # noqa: E402

ROSTER_URL = "https://www.azleg.gov/memberroster/"
# azleg.gov sits behind the Sucuri firewall, which can block or challenge scripts
# that send an unusual User-Agent. Send ordinary browser headers; requests stay slow.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/130.0 Safari/537.36 (AZ SBDC legislative research)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
FIREWALL_MARKERS = ("sucuri", "cloudproxy", "access denied", "attention required", "cf-chl", "just a moment")
OUT = Path(__file__).resolve().parent.parent / "data" / "legislators.json"


def get(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
    except requests.RequestException as e:
        sys.exit(f"Couldn't reach {url}: {e}")
    blocked = r.status_code in (403, 429, 503) or (
        "<table" not in r.text.lower() and any(k in r.text.lower() for k in FIREWALL_MARKERS))
    if blocked:
        sys.exit(f"{url} returned HTTP {r.status_code} and looks like a firewall page, not the roster.\n"
                 f"The site may be blocking this network or script. First 300 characters:\n{r.text[:300]}")
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def parse_row(tr):
    tds = tr.find_all("td")
    if len(tds) < 6:
        return None
    link = tds[0].find("a", href=re.compile(r"-member/"))
    if not link:
        return None

    href = urljoin(ROSTER_URL, link["href"])
    qs = parse_qs(urlparse(href).query)
    chamber = "S" if "/Senate/" in href else "H"

    # Name text looks like "Steve Montenegro -- Speaker"
    raw_name = clean(link.get_text(" "))
    name, _, title = raw_name.partition(" -- ")

    email_cell = tds[3]
    email_link = email_cell.find("a")
    handle = None
    note = None
    if email_link:
        handle = clean(email_link.get_text()).replace("Email:", "").strip()
    else:
        note = clean(email_cell.get_text()) or None

    room = clean(tds[4].get_text()) or None
    phone = clean(tds[5].get_text()) or None

    return {
        "id": int(qs["legislator"][0]),
        "name": clean(name),
        "chamber": chamber,
        "chamber_name": "Senate" if chamber == "S" else "House",
        "district": int(re.search(r"\d+", tds[1].get_text()).group()),
        "party": clean(tds[2].get_text()),
        "leadership_title": clean(title) or None,
        "email": f"{handle.lower()}@azleg.gov" if handle else None,
        "room": room,
        "phone": phone,
        "status": "active" if handle else "resigned",
        "status_note": note,
        "committees": [],
        "profile_url": href,
        "source": "azleg.gov/memberroster",
        "_legislature": int(qs.get("legislature", [0])[0]),
        "_session": int(qs.get("session", [0])[0]),
    }


def parse_committees(profile_url):
    """Committee assignments sit in the top-right block of each member page.
    The markup varies a little between chambers, so look for list items that
    mention a committee and an optional role."""
    soup = get(profile_url)
    committees = []
    for li in soup.select("li"):
        text = clean(li.get_text(" "))
        if not text or len(text) > 120:
            continue
        a = li.find("a", href=re.compile(r"Committee", re.I))
        if not a:
            continue
        cname = clean(a.get_text())
        role = None
        m = re.search(r"\b(Chair(?:man)?|Vice[- ]Chair(?:man)?|Ex[- ]Officio)\b", text, re.I)
        if m:
            role = m.group(1).title().replace("Chairman", "Chair")
        committees.append({"name": cname, "role": role})
    # de-duplicate, keep order
    seen, out = set(), []
    for c in committees:
        if c["name"] not in seen:
            seen.add(c["name"])
            out.append(c)
    return out


def validate(members):
    active = [m for m in members if m["status"] == "active"]
    problems = []
    for d in range(1, 31):
        s = sum(1 for m in active if m["district"] == d and m["chamber"] == "S")
        h = sum(1 for m in active if m["district"] == d and m["chamber"] == "H")
        if s != 1 or h != 2:
            problems.append(f"LD{d}: {s} senator(s), {h} representative(s)")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--committees", action="store_true", help="visit each member page for committee assignments")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between member-page requests")
    args = ap.parse_args()

    soup = get(ROSTER_URL)
    members = [m for m in (parse_row(tr) for tr in soup.select("table tr")) if m]
    if not members:
        title = clean(soup.title.get_text()) if soup.title else "(no title)"
        sys.exit(f"No rows parsed (page title: {title}). The roster page layout may have changed.")

    legislature = max(m["_legislature"] for m in members)
    session = max(m["_session"] for m in members)
    session_label = clean(soup.select_one("select option[selected]").get_text()) if soup.select_one("select option[selected]") else ""

    if args.committees:
        for i, m in enumerate(members, 1):
            if m["status"] != "active":
                continue
            try:
                m["committees"] = parse_committees(m["profile_url"])
            except requests.RequestException as e:
                print(f"  ! {m['name']}: {e}", file=sys.stderr)
            print(f"  [{i}/{len(members)}] {m['name']}: {len(m['committees'])} committees")
            time.sleep(args.delay)

    for m in members:
        m.pop("_legislature", None)
        m.pop("_session", None)

    payload = {
        "legislature": legislature,
        "session_id": session,
        "session_label": session_label,
        "retrieved": date.today().isoformat(),
        "source_url": ROSTER_URL,
        "members": members,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        previous = json.loads(OUT.read_text(encoding="utf-8"))
        # Without --committees, keep last known committee data rather than recording removals
        if not args.committees:
            prev_by_id = {m["id"]: m for m in previous.get("members", [])}
            for m in members:
                m["committees"] = prev_by_id.get(m["id"], {}).get("committees", [])
            payload["committee_sources"] = previous.get("committee_sources")
        recorded = roster_changes.append(roster_changes.diff(previous, payload))
        print(f"{len(recorded)} roster change(s) recorded in data/changes.json")
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    active = [m for m in members if m["status"] == "active"]
    print(f"Wrote {OUT}: {len(active)} active members "
          f"({sum(m['chamber']=='S' for m in active)} Senate, {sum(m['chamber']=='H' for m in active)} House), "
          f"legislature {legislature}")
    problems = validate(members)
    if problems:
        print("Check these districts (vacancy or new appointment?):", *problems, sep="\n  ")


if __name__ == "__main__":
    main()
