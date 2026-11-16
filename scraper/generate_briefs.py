"""
Draft legislator briefs with Gemini, from the data in data/ and (optionally) private/.

    pip install requests
    python scraper/generate_briefs.py --member 2308 --template committee_brief --dry-run
    python scraper/generate_briefs.py --key-committees --template committee_brief
    python scraper/generate_briefs.py --bill "HB 2001" --template bill_summary

Templates (prompts/templates/): committee_brief, new_member_onboarding,
district_impact_memo, esop_brief, bill_summary. Prompt wording lives in
prompts/system.md, prompts/sbdc_messaging.md and prompts/outreach_policy.md.

Keys and privacy
  Public data only (roster, committees, district, bills, votes):
      GEMINI_API_KEY        a free-tier key is fine
  With --private (business background, campaign finance, notes, client data):
      GEMINI_PAID_KEY       must be a paid-tier key. On the free tier Google may
                            use prompts to improve its products and reviewers
                            may read them, so private data never goes there.

--dry-run writes the exact prompt to private/briefs/ without calling the API.
Drafts are saved to private/briefs/<member_id>_<template>_<date>.md and show
up in private/profiles.html after build_profiles.py.
"""
import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA, PRIVATE, PROMPTS = ROOT / "data", ROOT / "private", ROOT / "prompts"
OUT = PRIVATE / "briefs"
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
KEY_COMMITTEES = {"J:Joint Legislative Budget Committee", "S:Appropriations, Transportation and Technology", "H:Appropriations",
                  "S:Finance", "H:Ways & Means", "H:Commerce", "S:Regulatory Affairs and Government Efficiency",
                  "H:Regulatory Oversight", "H:Rural Economic Development"}


def load(path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def member_context(m, private):
    pop = {f["properties"]["district"]: f["properties"]["population"]
           for f in load(DATA / "districts.geojson", {"features": []})["features"]}
    centers = {c["id"]: c for c in load(DATA / "centers.json", {"centers": []})["centers"]}
    dc = (load(DATA / "district_centers.json", {}) or {}).get("districts", {}).get(str(m["district"]), [])
    bills = load(DATA / "bills.json", {"bills": []})["bills"]
    votes = (load(DATA / "votes.json", {}) or {}).get("members", {}).get(str(m["id"]), [])
    esop = load(DATA / "esop_watch.json", {"bills": []})["bills"]
    ctx = {
        "legislator": {k: m.get(k) for k in ("name", "chamber_name", "district", "party", "leadership_title", "email", "phone", "room")},
        "committees": [{"committee": c["name"], "chamber": c["chamber"], "role": c["role"],
                        "sbdc_priority": f"{c['chamber']}:{c['name']}" in KEY_COMMITTEES} for c in m.get("committees", [])],
        "district": {"number": m["district"], "population_2020": pop.get(m["district"]),
                     "sbdc_centers_serving": [{"name": centers[x["center"]]["name"], "city": centers[x["center"]]["city"],
                                               "phone": centers[x["center"]]["phone"]} for x in dc if x["center"] in centers]},
        "sponsored_tracked_bills": [{"bill": b["identifier"], "title": b["title"], "primary": s["primary"],
                                     "latest_action": b["latest_action"]} for b in bills for s in b["sponsors"] if s["member_id"] == m["id"]],
        "recorded_votes_on_tracked_bills": votes,
        "esop_related_bills": [{"bill": b["identifier"], "title": b["title"], "latest_action": b["latest_action"]} for b in esop],
        "sources": ["azleg.gov member roster", "Senate and House committee lists (2026)", "IRC official legislative map",
                    "arizonasbdc.com locations"] + (["Open States roll-call records"] if bills else []),
    }
    public_impact = (load(DATA / "district_impact.json", {}) or {}).get("districts", {}).get(str(m["district"]))
    if public_impact:
        ctx["district"]["sbdc_results_public"] = public_impact
    if private:
        biz = (load(PRIVATE / "business_background.json", {}) or {}).get("members", {}).get(str(m["id"]))
        fin = (load(PRIVATE / "campaign_finance.json", {}) or {}).get("legislators", {}).get(str(m["id"]))
        imp = (load(PRIVATE / "district_impact.json", {}) or {}).get("districts", {}).get(str(m["district"]))
        ctx["reported_business_background"] = biz or "not reviewed"
        ctx["staff_only_campaign_finance"] = fin["cycles"] if fin else "not available"
        if imp:
            ctx["district"]["sbdc_results"] = imp
        ctx["sources"] += ["Financial disclosure statements and ACC records (private research)", "Spotlight campaign finance (staff only)"]
    return ctx


def bill_context(identifier):
    for b in load(DATA / "bills.json", {"bills": []})["bills"] + load(DATA / "esop_watch.json", {"bills": []})["bills"]:
        if b["identifier"].replace(" ", "").lower() == identifier.replace(" ", "").lower():
            return {"bill": {k: b.get(k) for k in ("identifier", "title", "session", "topic", "latest_action", "actions", "url")},
                    "sponsors": [s["name"] for s in b["sponsors"]], "sources": ["Open States bill record"]}
    sys.exit(f"{identifier} isn't in data/bills.json or data/esop_watch.json. Run openstates_bills.py first.")


def build_prompt(template, context):
    t = (PROMPTS / "templates" / f"{template}.md").read_text(encoding="utf-8")
    return (f"TASK\n{t}\n\nOUTREACH POLICY\n{(PROMPTS / 'outreach_policy.md').read_text(encoding='utf-8')}\n\n"
            f"SBDC MESSAGING\n{(PROMPTS / 'sbdc_messaging.md').read_text(encoding='utf-8')}\n\n"
            f"CONTEXT (JSON)\n{json.dumps(context, indent=2, ensure_ascii=False)}\n")


def call_gemini(prompt, key, model):
    body = {"systemInstruction": {"parts": [{"text": (PROMPTS / "system.md").read_text(encoding="utf-8")}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3}}
    for attempt in range(4):
        r = requests.post(API.format(model=model), headers={"x-goog-api-key": key}, json=body, timeout=120)
        if r.status_code in (429, 503):
            time.sleep(15 * (attempt + 1))
            continue
        r.raise_for_status()
        parts = r.json()["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)
    r.raise_for_status()


def main():
    ap = argparse.ArgumentParser()
    who = ap.add_mutually_exclusive_group(required=True)
    who.add_argument("--member", type=int, nargs="+", help="roster member id(s)")
    who.add_argument("--key-committees", action="store_true", help="everyone on the budget, tax and commerce committees")
    who.add_argument("--bill", help="bill identifier, for the bill_summary template")
    ap.add_argument("--template", required=True, help="committee_brief, new_member_onboarding, district_impact_memo, esop_brief, bill_summary")
    ap.add_argument("--private", action="store_true", help="include private research (needs GEMINI_PAID_KEY)")
    ap.add_argument("--model", default=os.environ.get("GEMINI_MODEL", "gemini-flash-latest"),
                    help="Gemini model name (default gemini-flash-latest; see Google AI Studio for current names)")
    ap.add_argument("--dry-run", action="store_true", help="write the prompt only, no API call")
    args = ap.parse_args()

    if not (PROMPTS / "templates" / f"{args.template}.md").exists():
        sys.exit(f"No template prompts/templates/{args.template}.md")
    key = None
    if not args.dry_run:
        key = os.environ.get("GEMINI_PAID_KEY") if args.private else (os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_PAID_KEY"))
        if not key:
            sys.exit("--private needs GEMINI_PAID_KEY (a paid-tier key). Private data is never sent with a free-tier key."
                     if args.private else "Set GEMINI_API_KEY (from Google AI Studio), or use --dry-run.")

    OUT.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    jobs = []
    if args.bill:
        jobs.append((args.bill.replace(" ", ""), bill_context(args.bill)))
    else:
        roster = [m for m in load(DATA / "legislators.json")["members"] if m["status"] == "active"]
        if args.key_committees:
            chosen = [m for m in roster if any(f"{c['chamber']}:{c['name']}" in KEY_COMMITTEES for c in m.get("committees", []))]
        else:
            ids = set(args.member)
            chosen = [m for m in roster if m["id"] in ids]
            missing = ids - {m["id"] for m in chosen}
            if missing:
                sys.exit(f"Not active legislators: {sorted(missing)}")
        jobs = [(str(m["id"]), member_context(m, args.private)) for m in chosen]

    for i, (ident, ctx) in enumerate(jobs, 1):
        prompt = build_prompt(args.template, ctx)
        stem = f"{ident}_{args.template}_{today}"
        if args.dry_run:
            (OUT / f"{stem}.prompt.txt").write_text(prompt, encoding="utf-8")
            print(f"[{i}/{len(jobs)}] prompt written: private/briefs/{stem}.prompt.txt ({len(prompt):,} characters)")
            continue
        text = call_gemini(prompt, key, args.model)
        header = (f"<!-- Generated {today} with {args.model}; template {args.template}; "
                  f"{'includes private research' if args.private else 'public data only'}. Verify every fact before use. -->\n")
        (OUT / f"{stem}.md").write_text(header + text, encoding="utf-8")
        print(f"[{i}/{len(jobs)}] draft saved: private/briefs/{stem}.md")
    if not args.dry_run:
        print("Run `python scraper/build_profiles.py` to see drafts in private/profiles.html.")


if __name__ == "__main__":
    main()
