"""Layered triage of data/bill_list.csv for SBDC review. Run automatically by
`openstates_bills.py --discover`; run by hand to re-triage after editing the rules:

    python scraper/triage_bills.py

Layer 1  relevance   does the title touch small business at all? (noise is set aside)
Layer 2  category    core small business / business tax / licensing & regulation / workforce / indirect
Layer 3  outcome     signed / vetoed / passed a chamber / died, from Open States latest action
Layer 4  priority    1 review first, 2 review, 3 context only, - set aside

Titles are all Open States gives for Arizona (no summaries or subjects), so this is a first pass
for SBDC staff, not a decision: track=yes stays SBDC's call.
"""
import csv
import re
import sys

STATUS = {"G": "signed into law", "V": "vetoed", "T": "passed (resolution or ballot referral)",
          "W": "sent to governor (superseded budget draft)", "P": "passed at least one chamber", "D": "died in committee"}
TERMS = ["small business", "microbusiness", "entrepreneur", "transaction privilege tax", "income tax credit",
         "business tax", "tax credit", "occupational licens", "regulatory relief", "business licens", "permitting",
         "workforce development", "apprenticeship", "job training", "commerce authority", "economic development",
         "rural development", "employee ownership", "employee stock ownership", "employee-owned",
         "worker cooperative", "business succession", "esop"]

# Layer 2 categories, checked in order; the first that matches the title wins
CATEGORIES = [
    ("core small business", r"small business|entrepreneur|commerce authority|^commerce; |\bcommerce\b.*2026|business|"
                            r"state contracting|procurement|trade offices?|interchange fees|tourism improvement|"
                            r"growth zones|qualified facilit|tax increment financing|capital improvement; financing"),
    ("business tax", r"\bTPT\b|transaction privilege|use tax|corporate income tax|internal revenue code|conformity|"
                     r"taxation|tax corrections|^revenue;|excise tax|municipal tax|rates; fees; taxes|depreciation|"
                     r"tax expenditures|sales tax credit|tax credit; (fraud|health reimbursement)|truth in taxation|"
                     r"vapor products; tax|breeders.*taxes"),
    ("licensing & regulation", r"licens|licensure|certification|registration|administrative procedures|"
                               r"statutory authority|permitting providers|self-certification|development fees|"
                               r"exactions|mobile food|short-term rentals|vacation rentals|board; (revision|"
                               r"continuation|renewals|civil penalties|regulatory)|industrial commission|online lodging|uniform assignment; benefit of creditors|"
                               r"malicious delay|private towing|contractors|liquor|nicotine|public works contracts"),
    ("workforce", r"workforce|apprentic|employ|\bwages?\b|sick leave|unemployment|e-verify|labor relations|"
                  r"trade diploma|fellowship program"),
    ("indirect", r"general appropriations|budget implementation|human services; 2026|environment; 2026|"
                 r"higher education; 2026|child care|housing|zoning|data centers|small modular reactors|"
                 r"energy supply|space commission|military affairs|interstate 11|utilit|line siting|"
                 r"environmental compatibility|rural|tax credit|income tax"),
]
# Titles that match a category word but aren't about business (checked first)
NOT_BUSINESS = r"driver license|instruction permit|elections?|ballot|voting|voter|firearm|weapon|concealed|" \
               r"abortion|death resolution|medical marijuana|special plate; recycling|technical correction; (boating|air|public)|" \
               r"vehicle registration|unmanned aircraft|" \
               r"licenses; (not proof|tax number)|citizenship status|lawful presence|antidiscrimination|" \
               r"discrimination|deer|wolves|predatory|kratom|radiologic|physician|podiatric|genetic counselors|" \
               r"nursing board|midwives|pharmac|dentists|veterinarian|marijuana; qualifying|ESAs|STOs|scholarship"


def classify(title, terms, status):
    t = title
    if re.search(NOT_BUSINESS, t, re.I):
        cat = None
    else:
        cat = next((name for name, pat in CATEGORIES if re.search(pat, t, re.I)), None)
    relevant = cat is not None
    if not relevant:
        prio, why = "-", "title isn't about business" + (" (matched only the verb 'permitting')" if terms == ["permitting"] else "")
    elif cat == "core small business":
        prio, why = "1", "directly about small business, commerce or state contracting"
    elif cat in ("business tax", "licensing & regulation", "workforce"):
        acted = status in ("G", "V", "T", "P")
        prio = "1" if acted else "2"
        why = f"{cat}; " + ("moved in 2026" if acted else "died early; may return in 2027")
    elif re.search(r"general appropriations", t, re.I) and status == "G":
        prio, why = "2", "the enacted state budget: check the Commerce Authority and SBDC funding lines"
    else:
        prio, why = "3", "indirect: budget, housing, energy or general tax context"
    return relevant, cat or "", prio, why


CODE_FROM_STATUS = {v: k for k, v in STATUS.items()}


def status_code(bill):
    """Outcome code from an Open States bill: latest action plus whether it passed a chamber."""
    d = bill.get("latest_action_description") or ""
    if re.search(r"Signed by Governor", d): return "G"
    if re.search(r"Vetoed", d): return "V"
    if re.search(r"Transmit to Secretary of State", d): return "T"
    if re.search(r"Transmit to Governor", d): return "W"
    return "P" if bill.get("latest_passage_date") else "D"


def triage_row(row):
    """Fill priority/category/why on a bill_list row that has title, status and matched_terms."""
    code = CODE_FROM_STATUS.get(row.get("status") or "", "D")
    terms = [t.strip() for t in (row.get("matched_terms") or row.get("found_by") or "").split(";") if t.strip()]
    _, cat, prio, why = classify(row.get("title") or "", terms, code)
    row.update(category=cat, priority=prio, why=why)
    return row


if __name__ == "__main__":
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import openstates_bills as ob
    rows = [triage_row(r) for r in ob.read_list()]
    ob.write_list(rows)
    from collections import Counter
    print("priorities:", dict(Counter(r["priority"] for r in rows)))
