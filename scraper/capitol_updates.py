"""
Build data/updates_feed.json for the site's "Latest from the Capitol" section.

    python scraper/capitol_updates.py

Runs inside the scheduled refresh (called from update_sources.py). Every source is
optional: if one is down or blocks the request, the others still update and the
site shows which source didn't refresh. Only public information is collected.

Sources
  governor  Governor's news releases (azgovernor.gov/news-releases). "Legislative
            Action Update" releases are read for signed and vetoed bills and
            veto-letter links; bills SBDC tracks are flagged.
  news      Arizona Mirror and Chamber Business News RSS feeds, filtered to
            Legislature, budget, tax and business stories.
  budget    JLBC Monthly Fiscal Highlights (newest issue).
  bills     Latest actions on tracked bills, from data/bills.json (no extra fetch).
"""
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "updates_feed.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/130.0 Safari/537.36 (AZ SBDC legislative research)",
    "Accept": "text/html,application/xhtml+xml,application/xml,application/rss+xml;q=0.9,*/*;q=0.8",
}
KEEP_DAYS = 60          # news and Governor items older than this drop off
PER_SOURCE = 15         # newest items kept from each feed
BILL_RE = re.compile(r"\b([HS](?:B|CR|CM|JR|R|M))\s?(\d{4})\b")

# Stories worth surfacing for SBDC: Legislature, budget, taxes, business, regulation
RELEVANT = re.compile(
    r"legislat|lawmaker|azleg|capitol|\bbills?\b|\bveto|signs?\b|signed|budget|\btax|business|commerce|"
    r"econom|regulat|licens|workforce|minimum wage|employer|small business|session|ballot measure|proposition",
    re.I)
SKIP_CATEGORIES = {"DC Bureau", "Sponsored Commentary"}


def get(url, **kw):
    r = requests.get(url, headers=HEADERS, timeout=30, **kw)
    r.raise_for_status()
    return r


def iso(d):
    return d.isoformat() if d else None


def parse_date_text(text):
    """'November 16, 2026' anywhere in text -> date."""
    m = re.search(r"([A-Z][a-z]+) (\d{1,2}), (20\d\d)", text or "")
    if not m:
        return None
    try:
        return datetime.strptime(" ".join(m.groups()), "%B %d %Y").date()
    except ValueError:
        return None


def bill_ids(text):
    return sorted({f"{a} {b}" for a, b in BILL_RE.findall(text or "")})


# ---------------------------------------------------------------- Governor
GOV_BASE = "https://azgovernor.gov"


def governor_releases(html):
    """[(date, title, url)] from the news-releases listing page."""
    soup = BeautifulSoup(html, "html.parser")
    seen, out = set(), []
    for a in soup.find_all("a", href=True):
        href = urljoin(GOV_BASE, a["href"])
        title = " ".join(a.get_text(" ", strip=True).split())
        if "/news/20" not in href or not title or title.lower() in ("learn more", "read more") or href in seen:
            continue
        d, node = None, a
        for _ in range(5):  # the date sits in the surrounding card
            node = node.parent
            if node is None:
                break
            d = parse_date_text(node.get_text(" ", strip=True))
            if d:
                break
        seen.add(href)
        out.append((d, title, href))
    return out


def legislative_action(html, url):
    """Signed/vetoed bills and veto letters from a Legislative Action Update page."""
    soup = BeautifulSoup(html, "html.parser")
    body = soup.find("article") or soup.find("main") or soup
    signed, vetoed, section = [], [], None
    for line in body.get_text("\n", strip=True).split("\n"):
        word = line.strip().lower()
        if word in ("signed", "approved"):
            section = signed
            continue
        if word in ("vetoed", "veto"):
            section = vetoed
            continue
        if line.startswith("###"):
            break
        m = BILL_RE.match(line.strip())
        if m and section is not None:
            section.append({"bill": f"{m.group(1)} {m.group(2)}", "title": line.strip()[m.end():].strip(" ,;-")})
    letters = {}
    for a in body.find_all("a", href=True):
        if "veto" in a.get_text(" ", strip=True).lower():
            ids = bill_ids(a.get_text(" ", strip=True)) or bill_ids(a["href"].upper().replace("-", " "))
            for b in ids:
                letters[b] = urljoin(url, a["href"])
    for v in vetoed:
        v["veto_letter"] = letters.get(v["bill"])
    return signed, vetoed


def source_governor(tracked, since):
    items = []
    for d, title, url in governor_releases(get(f"{GOV_BASE}/news-releases").text):
        if d and d < since:
            continue
        item = {"source": "governor", "source_name": "Governor's Office", "date": iso(d), "title": title, "url": url}
        if re.search(r"legislative action", title, re.I):
            try:
                signed, vetoed = legislative_action(get(url).text, url)
            except requests.RequestException:
                signed, vetoed = [], []
            for b in signed + vetoed:
                b["tracked"] = b["bill"] in tracked
            item.update(signed=signed, vetoed=vetoed,
                        summary=f"Signed {len(signed)}, vetoed {len(vetoed)}" +
                                (f"; includes tracked {', '.join(b['bill'] for b in signed + vetoed if b['tracked'])}"
                                 if any(b["tracked"] for b in signed + vetoed) else ""))
        items.append(item)
    return items[:PER_SOURCE]


# ---------------------------------------------------------------- RSS news
def rss_items(xml_text):
    root = ET.fromstring(xml_text)
    for it in root.iter("item"):
        cats = [c.text or "" for c in it.findall("category")]
        try:
            d = parsedate_to_datetime(it.findtext("pubDate") or "").date()
        except (TypeError, ValueError):
            d = None
        desc = BeautifulSoup(it.findtext("description") or "", "html.parser").get_text(" ", strip=True)
        yield {"title": (it.findtext("title") or "").strip(), "url": (it.findtext("link") or "").strip(),
               "date": d, "categories": cats, "summary": " ".join(desc.split())[:240]}


def source_rss(source_id, name, url, since, tracked):
    items = []
    for it in rss_items(get(url).text):
        if it["date"] and it["date"] < since:
            continue
        if SKIP_CATEGORIES & set(it["categories"]):
            continue
        blob = " ".join([it["title"], it["summary"], " ".join(it["categories"])])
        if not RELEVANT.search(blob):
            continue
        bills = bill_ids(it["title"] + " " + it["summary"])
        items.append({"source": "news", "source_name": name, "feed": source_id, "date": iso(it["date"]),
                      "title": it["title"], "url": it["url"], "summary": it["summary"],
                      "bills": [{"bill": b, "tracked": b in tracked} for b in bills]})
    return items[:PER_SOURCE]


# ---------------------------------------------------------------- JLBC
MONTHS = ["jan", "feb", "mar", "apr", "may", "june", "july", "aug", "sep", "oct", "nov", "dec"]
MONTH_FULL = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
              "November", "December"]


def jlbc_candidates(today):
    """Newest-first URLs for the last four months. JLBC writes 'june'/'july' in full, and has
    used both 'jul' and 'july', so each month gets every spelling."""
    y, m = today.year, today.month
    for _ in range(4):
        spellings = {MONTHS[m - 1], MONTH_FULL[m - 1][:3].lower(), MONTH_FULL[m - 1].lower()}
        for s in sorted(spellings, key=len):
            yield date(y, m, 1), f"https://www.azjlbc.gov/mfh/mfh-{s}-{str(y)[2:]}.pdf"
        m -= 1
        if m == 0:
            y, m = y - 1, 12


def source_jlbc(today):
    for month, url in jlbc_candidates(today):
        try:
            r = requests.head(url, headers=HEADERS, timeout=20, allow_redirects=True)
            if r.status_code in (403, 405):
                r = requests.get(url, headers=HEADERS, timeout=20, stream=True)
                r.close()
        except requests.RequestException:
            continue
        if r.status_code == 200 and "pdf" in r.headers.get("content-type", "").lower():
            return [{"source": "budget", "source_name": "JLBC", "date": iso(month),
                     "title": f"Monthly Fiscal Highlights, {MONTH_FULL[month.month - 1]} {month.year}", "url": url,
                     "summary": "Nonpartisan budget staff report: state revenue against the budget forecast, plus agency reports."}]
    return []


# ---------------------------------------------------------------- tracked bills
def source_bills(bills_doc, since):
    items = []
    for b in (bills_doc or {}).get("bills", []):
        la = b.get("latest_action") or {}
        try:
            d = date.fromisoformat((la.get("date") or "")[:10])
        except ValueError:
            continue
        if d < since:
            continue
        items.append({"source": "bills", "source_name": "Tracked bill", "date": iso(d),
                      "title": f"{b['identifier']}: {b.get('title', '')}", "url": b.get("url"),
                      "summary": la.get("description") or "", "bills": [{"bill": b["identifier"], "tracked": True}]})
    return items


# ---------------------------------------------------------------- main
def load(name):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def prev_last_ok(prev):
    """Date a source last loaded: its recorded last_ok, or the previous check if that one succeeded."""
    prev = prev or {}
    return prev.get("last_ok") or (prev.get("checked") if prev.get("ok") else None)


def main(today=None):
    today = today or date.today()
    since = today - timedelta(days=KEEP_DAYS)
    bills_doc = load("bills.json")
    tracked = {b["identifier"] for b in (bills_doc or {}).get("bills", [])}
    jobs = [
        ("governor", "Governor's Office", "https://azgovernor.gov/news-releases", lambda: source_governor(tracked, since)),
        ("azmirror", "Arizona Mirror", "https://azmirror.com", lambda: source_rss("azmirror", "Arizona Mirror", "https://azmirror.com/feed/", since, tracked)),
        ("chamber", "Chamber Business News", "https://chamberbusinessnews.com", lambda: source_rss("chamber", "Chamber Business News", "https://chamberbusinessnews.com/feed/", since, tracked)),
        ("jlbc", "JLBC Monthly Fiscal Highlights", "https://www.azjlbc.gov", lambda: source_jlbc(today)),
        ("bills", "Tracked bill actions", None, lambda: source_bills(bills_doc, since)),
    ]
    previous = {s["id"]: s for s in (load("updates_feed.json") or {}).get("sources", [])}
    old_items = (load("updates_feed.json") or {}).get("items", [])
    items, sources = [], []
    for sid, name, url, fn in jobs:
        try:
            got = fn()
            for i in got:
                i["feed"] = sid
            sources.append({"id": sid, "name": name, "url": url, "ok": True, "count": len(got), "checked": iso(today)})
            items += got
            print(f"  {name}: {len(got)} items")
        except Exception as e:  # keep the last good items from a source that failed today
            kept = [i for i in old_items if i.get("feed") == sid]
            items += kept
            sources.append({"id": sid, "name": name, "url": url, "ok": False, "count": len(kept), "checked": iso(today),
                            "error": f"{type(e).__name__}: {str(e)[:160]}",
                            "last_ok": prev_last_ok(previous.get(sid))})
            print(f"  {name}: FAILED ({type(e).__name__}); kept {len(kept)} earlier items", file=sys.stderr)
            continue
        sources[-1]["last_ok"] = iso(today)
    seen, unique = set(), []
    for it in sorted(items, key=lambda i: i.get("date") or "", reverse=True):
        if it["url"] in seen:
            continue
        seen.add(it["url"])
        unique.append(it)
    OUT.write_text(json.dumps({"updated": iso(today), "keep_days": KEEP_DAYS, "sources": sources, "items": unique},
                              indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)}: {len(unique)} items")


if __name__ == "__main__":
    main()
