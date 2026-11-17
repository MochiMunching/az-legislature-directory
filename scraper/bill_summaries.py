"""Turn data/bill_summaries.csv into data/bill_summaries.json for the site.

The CSV is the file people edit (Excel is fine). One row per bill:
  bill         e.g. HB 2289
  what         what the bill does, in plain language
  who          who it affects
  why          why it matters for small business
  outcome      what happened to it (optional; the site also shows the status)
  sources      official summary URLs it was written from, separated by spaces
  drafted      date the draft was written
  reviewed_by  name of the SBDC reviewer; leave blank while it's a draft
  reviewed_on  date reviewed
Summaries with no reviewer show on the site as "Draft, not yet reviewed by SBDC".

    python scraper/bill_summaries.py
"""

import csv
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "bill_summaries.csv"
OUT = ROOT / "data" / "bill_summaries.json"
FIELDS = ["bill", "what", "who", "why", "outcome", "sources", "drafted", "reviewed_by", "reviewed_on"]


def main():
    if not SRC.exists():
        print("No data/bill_summaries.csv yet; skipping.")
        return
    with SRC.open(encoding="utf-8-sig", newline="") as f:      # utf-8-sig: Excel's BOM
        rows = [r for r in csv.DictReader(f) if (r.get("bill") or "").strip()]
    bills = {}
    for r in rows:
        m = re.match(r"\s*([A-Z]+)\s*(\d+)", r["bill"].upper())     # "hb2289" -> "HB 2289"
        ident = f"{m.group(1)} {m.group(2)}" if m else r["bill"].strip()
        bills[ident] = {
            "what": (r.get("what") or "").strip(), "who": (r.get("who") or "").strip(),
            "why": (r.get("why") or "").strip(), "outcome": (r.get("outcome") or "").strip(),
            "sources": (r.get("sources") or "").split(), "drafted": (r.get("drafted") or "").strip(),
            "reviewed_by": (r.get("reviewed_by") or "").strip(), "reviewed_on": (r.get("reviewed_on") or "").strip(),
        }
    reviewed = sum(1 for b in bills.values() if b["reviewed_by"])
    OUT.write_text(json.dumps({"updated": date.today().isoformat(), "bills": bills}, indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)}: {len(bills)} summaries, {reviewed} reviewed")


if __name__ == "__main__":
    main()
