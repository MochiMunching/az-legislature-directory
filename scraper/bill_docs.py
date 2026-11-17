"""Collect the Legislature's own plain-English summaries for tracked bills.

For each bill in data/bills.json this finds the House "summary" and Senate
"fact sheet" pages on azleg.gov, downloads the most final version of each, and
saves the text to data/bill_docs.json. Those official summaries are the source
for the plain-language summaries in data/bill_summaries.json.

Where the links come from:
  1. The "documents" list Open States returns for each bill (saved by
     openstates_bills.py), and
  2. azleg.gov's own bill-status lookup, as a backup.

A bill is fetched again only when its latest action changes, so once the
session is over this makes no requests at all. Run from the repository root:
    python scraper/bill_docs.py
"""

import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "bill_docs.json"
AZLEG_API = "https://apps.azleg.gov/api"
MAX_CHARS = 9000          # per document; fact sheets are usually 1-4 pages
DELAY = 1.5               # seconds between azleg.gov requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
}
SUMMARY_URL = re.compile(r"azleg\.gov/legtext/\d+leg/\w+/summary/[^\s\"'<>]+\.htm", re.I)

# Later stages of a bill win over earlier ones.
STAGE_RANK = [
    (r"chapter", 90), (r"signed|governor", 85), (r"veto", 85), (r"final|aspassed|as ?passed|transmit", 80),
    (r"conf|ccr", 75), (r"engross|asengrossed", 60), (r"amended|asamended|cow|caucus", 40),
]


def stage_score(url):
    name = url.rsplit("/", 1)[-1].lower()
    score = max([s for pat, s in STAGE_RANK if re.search(pat, name)] or [10])
    m = re.search(r"_(\d{2})(\d{2})(\d{2})_", name)          # House files carry MMDDYY
    stamp = f"{m.group(3)}{m.group(1)}{m.group(2)}" if m else "000000"
    return (score, stamp, name)


def chamber_of(url):
    name = url.rsplit("/", 1)[-1]
    return "House summary" if name.upper().startswith("H.") else "Senate fact sheet" if name.upper().startswith("S.") else "Summary"


def get(session, url, **kw):
    r = session.get(url, headers=HEADERS, timeout=45, **kw)
    r.raise_for_status()
    if "sucuri" in r.text[:3000].lower() and "firewall" in r.text[:3000].lower():
        raise RuntimeError("blocked by the azleg.gov firewall")
    time.sleep(DELAY)
    return r


def walk_urls(obj):
    """Every summary-page URL anywhere inside a JSON value."""
    if isinstance(obj, dict):
        for v in obj.values():
            yield from walk_urls(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_urls(v)
    elif isinstance(obj, str):
        for m in SUMMARY_URL.finditer(obj.replace("\\", "/")):
            yield m.group(0)


def azleg_session_id(legislators):
    m = re.search(r"session=(\d+)", json.dumps(legislators.get("members", [])[:3]))
    return m.group(1) if m else None


def azleg_summary_urls(session, bill, session_id):
    """Backup: azleg.gov bill-status lookup -> document list -> summary pages."""
    num = bill["identifier"].replace(" ", "")
    body = "S" if num.upper().startswith("S") else "H"
    info = get(session, f"{AZLEG_API}/Bill/", params={"billNumber": num, "sessionId": session_id,
                                                         "legislativeBody": body}).json()
    bill_id = (info or {}).get("BillId") or (info or {}).get("BillStatusId") or (info or {}).get("Id")
    if not bill_id:
        return []
    docs = get(session, f"{AZLEG_API}/DocType/", params={"billStatusId": bill_id}).json()
    return list(walk_urls(docs))


def page_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    lines = []
    for line in soup.get_text("\n").splitlines():
        line = " ".join(line.split())
        if not line or "DOCUMENT FOOTER" in line or re.fullmatch(r"[☐☒\s]*", line):
            continue
        lines.append(line)
    return "\n".join(lines)[:MAX_CHARS]


def pick(urls):
    """Most final House summary and most final Senate fact sheet."""
    best = {}
    for u in {u.replace("http://", "https://") for u in urls}:
        k = chamber_of(u)
        if k not in best or stage_score(u) > stage_score(best[k]):
            best[k] = u
    return [best[k] for k in ("Senate fact sheet", "House summary", "Summary") if k in best]


def main(today=None):
    today = today or date.today()
    bills = json.loads((DATA / "bills.json").read_text(encoding="utf-8")).get("bills", [])
    legislators = json.loads((DATA / "legislators.json").read_text(encoding="utf-8"))
    session_id = azleg_session_id(legislators)
    old = {}
    if OUT.exists():
        old = {d["bill"]: d for d in json.loads(OUT.read_text(encoding="utf-8")).get("bills", [])}

    s = requests.Session()
    out, fetched, kept, failed = [], 0, 0, 0
    for b in bills:
        ident, last = b["identifier"], (b.get("latest_action") or {}).get("date")
        prev = old.get(ident)
        if prev and prev.get("latest_action") == last and prev.get("docs"):
            out.append(prev); kept += 1
            continue
        try:
            urls = [d["url"] for d in b.get("documents") or [] if SUMMARY_URL.search(d.get("url") or "")]
            if not urls and session_id:
                urls = azleg_summary_urls(s, b, session_id)
            docs = []
            for u in pick(urls):
                docs.append({"label": chamber_of(u), "url": u, "text": page_text(get(s, u).text)})
            entry = {"bill": ident, "title": b.get("title"), "latest_action": last,
                     "fetched": today.isoformat(), "docs": docs}
            if not docs:
                entry["error"] = "no summary or fact sheet found"
                failed += 1
            else:
                fetched += 1
            out.append(entry)
            print(f"  {ident}: {len(docs)} document(s)")
        except Exception as e:                       # keep going; keep the old copy if there is one
            failed += 1
            print(f"  ! {ident}: {type(e).__name__}: {str(e)[:150]}", file=sys.stderr)
            out.append(prev or {"bill": ident, "title": b.get("title"), "latest_action": None,
                                "fetched": today.isoformat(), "docs": [], "error": f"{type(e).__name__}: {str(e)[:150]}"})

    OUT.write_text(json.dumps({"updated": today.isoformat(), "bills": out}, indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)}: {fetched} fetched, {kept} unchanged, {failed} without documents")


if __name__ == "__main__":
    main()
