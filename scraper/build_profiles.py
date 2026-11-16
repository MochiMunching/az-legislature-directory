"""
Build private/profiles.html: one page with a profile for every legislator,
combining the public data in data/ with the private research in private/.

    python scraper/build_profiles.py

Open private/profiles.html in a browser. Everything is embedded in the file,
so it works offline. It contains private research: don't publish or commit it.

Private inputs (all optional):
  private/business_background.json   from business_research.py check
  private/campaign_finance.json      from spotlight_finance.py
  private/notes.csv                  member_id,date,author,note  (staff research notes)
  private/briefs/<member_id>.md      drafted briefs (from generate_briefs.py)
"""
import csv
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA, PRIVATE = ROOT / "data", ROOT / "private"


def load(path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def main():
    PRIVATE.mkdir(exist_ok=True)
    geo = load(DATA / "districts.geojson", {"features": []})
    notes = {}
    if (PRIVATE / "notes.csv").exists():
        with (PRIVATE / "notes.csv").open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if (r.get("member_id") or "").strip().isdigit():
                    notes.setdefault(r["member_id"].strip(), []).append({k: r.get(k, "") for k in ("date", "author", "note")})
    briefs = {}
    if (PRIVATE / "briefs").exists():
        for p in sorted((PRIVATE / "briefs").glob("*.md")):
            briefs.setdefault(p.stem.split("_")[0], []).append({"file": p.name, "text": p.read_text(encoding="utf-8")})

    bundle = {
        "built": date.today().isoformat(),
        "roster": load(DATA / "legislators.json"),
        "centers": load(DATA / "centers.json"),
        "district_centers": load(DATA / "district_centers.json"),
        "population": {f["properties"]["district"]: f["properties"]["population"] for f in geo["features"]},
        "bills": load(DATA / "bills.json"),
        "votes": load(DATA / "votes.json"),
        "business": load(PRIVATE / "business_background.json"),
        "finance": load(PRIVATE / "campaign_finance.json"),
        "notes": notes,
        "briefs": briefs,
    }
    html = TEMPLATE.replace("__DATA__", json.dumps(bundle, ensure_ascii=False).replace("</", "<\\/"))
    out = PRIVATE / "profiles.html"
    out.write_text(html, encoding="utf-8")
    have = [k for k in ("business", "finance", "bills") if bundle[k]] + (["notes"] if notes else []) + (["briefs"] if briefs else [])
    print(f"Wrote {out.relative_to(ROOT)} ({', '.join(have) or 'public data only'})")


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Legislator Profiles (private)</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root { --bg:#f6f8f7; --surface:#fff; --sunk:#ecf1ef; --fg:#16201e; --muted:#5a6865; --line:#d7e0dd; --accent:#1f6b63; --accent-ink:#fff; --accent-soft:#dcece8;
  --rep:#a4473c; --rep-soft:#f5e3e0; --dem:#345a8f; --dem-soft:#e1e8f3; --warn-bg:#fbf3df; --warn-fg:#6d5414; --private:#7a3e8e; --private-soft:#f1e6f5;
  --font-body:"Public Sans",system-ui,-apple-system,"Segoe UI",sans-serif; --font-mono:"IBM Plex Mono",ui-monospace,Menlo,monospace; }
@media (prefers-color-scheme: dark) { :root { --bg:#101615; --surface:#171f1d; --sunk:#1d2725; --fg:#e4ecea; --muted:#97a7a3; --line:#2b3734; --accent:#5bb5a9; --accent-ink:#0c1312; --accent-soft:#1d3632;
  --rep:#e08a7f; --rep-soft:#3a2422; --dem:#8fb0e3; --dem-soft:#1f2a3c; --warn-bg:#2f2915; --warn-fg:#e6cf8a; --private:#cfa0e0; --private-soft:#2f2236; color-scheme:dark; } }
* { box-sizing:border-box } body { margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 var(--font-body); -webkit-font-smoothing:antialiased }
.banner { background:var(--private-soft); color:var(--private); padding:8px max(16px, env(safe-area-inset-left)); font-size:13px; font-weight:600 }
.app { display:grid; grid-template-columns:300px minmax(0,1fr); min-height:calc(100vh - 37px) }
aside { border-right:1px solid var(--line); background:var(--surface); display:grid; grid-template-rows:auto 1fr; max-height:calc(100vh - 37px); position:sticky; top:0 }
.filters { padding:14px; display:grid; gap:8px; border-bottom:1px solid var(--line) }
.filters input, .filters select { width:100%; padding:8px 10px; border:1px solid var(--line); border-radius:6px; background:var(--surface); color:var(--fg); font:inherit }
.list { overflow:auto }
.li { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:2px 8px; padding:9px 14px; border-bottom:1px solid var(--line); cursor:pointer; background:none; border-left:0; border-right:0; border-top:0; width:100%; text-align:left; font:inherit; color:inherit }
.li:hover { background:var(--sunk) } .li[aria-current="true"] { background:var(--accent-soft) }
.li .n { font-weight:600; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap } .li .m { font-size:12px; color:var(--muted); grid-column:1/-1 }
main { padding:24px max(16px, env(safe-area-inset-right)) 48px max(24px, env(safe-area-inset-left)); max-width:1000px }
h1 { font-size:30px; margin:0; letter-spacing:-.02em } h2 { font-size:15px; text-transform:uppercase; letter-spacing:.07em; color:var(--muted); margin:28px 0 10px }
h2.priv::after { content:"Private"; margin-left:8px; font-size:11px; padding:1px 6px; border-radius:4px; background:var(--private-soft); color:var(--private); letter-spacing:.04em }
.sub { color:var(--muted); margin:4px 0 0 } .title { color:var(--accent); font-weight:600 }
.chip { display:inline-block; min-width:22px; text-align:center; font-family:var(--font-mono); font-size:12px; padding:1px 6px; border-radius:4px }
.chip.R { background:var(--rep-soft); color:var(--rep) } .chip.D { background:var(--dem-soft); color:var(--dem) }
.cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:10px; margin-top:16px }
.card { background:var(--surface); border:1px solid var(--line); border-radius:8px; padding:12px; display:grid; gap:4px; align-content:start }
.card .k { font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted) } .card .v { font-weight:600 }
.mono { font-family:var(--font-mono); font-size:13px; font-variant-numeric:tabular-nums }
table { width:100%; border-collapse:collapse; background:var(--surface); border:1px solid var(--line); border-radius:8px; overflow:hidden }
th, td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); font-size:14px; vertical-align:top } th { background:var(--sunk); font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted) }
.tw { overflow-x:auto }
.tags { display:flex; flex-wrap:wrap; gap:4px } .tag { font-size:12px; padding:2px 7px; border-radius:4px; background:var(--sunk); border:1px solid var(--line) } .tag.lead { background:var(--accent-soft); color:var(--accent); border-color:transparent; font-weight:600 }
.empty { border:1px dashed var(--line); border-radius:8px; padding:12px; color:var(--muted); font-size:14px; background:var(--surface) }
.empty code { font-family:var(--font-mono); font-size:12px; background:var(--sunk); padding:1px 4px; border-radius:3px; color:var(--fg) }
.status { display:inline-block; font-size:12px; font-weight:600; padding:2px 8px; border-radius:4px; background:var(--sunk); color:var(--muted) }
.status.ties { background:var(--accent-soft); color:var(--accent) }
.bars { display:grid; gap:6px } .bar { display:grid; grid-template-columns:170px minmax(0,1fr) 54px; gap:8px; align-items:center; font-size:13px }
.bar .track { height:8px; background:var(--sunk); border-radius:4px; overflow:hidden } .bar .fill { height:100%; background:var(--accent) }
.bar .pct { font-family:var(--font-mono); text-align:right; font-variant-numeric:tabular-nums }
.cycle { background:var(--surface); border:1px solid var(--line); border-radius:8px; padding:12px; display:grid; gap:10px; margin-bottom:10px }
.cycle h3 { margin:0; font-size:15px; display:flex; justify-content:space-between; gap:8px; flex-wrap:wrap } .cycle h3 span { font-family:var(--font-mono); font-weight:400; color:var(--muted); font-size:13px }
.note { background:var(--surface); border:1px solid var(--line); border-radius:8px; padding:10px 12px; margin-bottom:8px; font-size:14px } .note .h { font-size:12px; color:var(--muted) }
pre.brief { white-space:pre-wrap; background:var(--surface); border:1px solid var(--line); border-radius:8px; padding:14px; font:14px/1.55 var(--font-body) }
.opt-yes { color:var(--accent); font-weight:600 } .opt-no { color:var(--warn-fg); font-weight:600 }
a { color:var(--accent) }
@media (max-width:820px) { .app { grid-template-columns:minmax(0,1fr) } aside { position:static; max-height:340px } }
</style></head><body>
<div class="banner">Private research file. Contains staff research and campaign finance summaries. Don't publish or commit it.</div>
<div class="app">
  <aside><div class="filters">
    <input id="q" type="search" placeholder="Search name or district" aria-label="Search legislators">
    <select id="f" aria-label="Filter"><option value="">All legislators</option><option value="ties">Reported business ties</option><option value="unreviewed">Business background not reviewed</option><option value="key">On budget, tax or commerce committees</option><option value="S">Senate</option><option value="H">House</option></select>
  </div><div class="list" id="list"></div></aside>
  <main id="main"></main>
</div>
<script id="bundle" type="application/json">__DATA__</script>
<script>
(() => {
  const D = JSON.parse(document.getElementById("bundle").textContent);
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const money = (n) => n == null ? "—" : "$" + Math.round(n).toLocaleString();
  const pct = (x) => x == null ? "—" : Math.round(x * 100) + "%";
  const members = D.roster.members.filter((m) => m.status === "active").sort((a, b) => a.district - b.district || (a.chamber === "S" ? -1 : 1));
  const KEY = new Set(["J:Joint Legislative Budget Committee", "S:Appropriations, Transportation and Technology", "H:Appropriations", "S:Finance", "H:Ways & Means", "H:Commerce", "S:Regulatory Affairs and Government Efficiency", "H:Regulatory Oversight", "H:Rural Economic Development"]);
  const isKey = (c) => KEY.has(`${c.chamber}:${c.name}`);
  const biz = (id) => D.business?.members?.[id];
  const centerName = Object.fromEntries((D.centers?.centers || []).map((c) => [c.id, c.name]));
  let current = null;

  function listRows() {
    const q = $("q").value.toLowerCase(), f = $("f").value;
    return members.filter((m) => (!q || (m.name + " ld" + m.district + " district " + m.district).toLowerCase().includes(q)) &&
      (!f || (f === "ties" && biz(m.id)?.reported_business_ties) || (f === "unreviewed" && (!biz(m.id) || biz(m.id).status === "not reviewed")) ||
       (f === "key" && (m.committees || []).some(isKey)) || f === m.chamber));
  }
  function renderList() {
    $("list").innerHTML = listRows().map((m) => `<button class="li" data-id="${m.id}" aria-current="${m.id === current}">
      <span class="n">${esc(m.name)}</span><span class="chip ${m.party}">${m.party}</span>
      <span class="m">${m.chamber === "S" ? "Senator" : "Representative"} · LD ${m.district}${biz(m.id)?.reported_business_ties ? " · business ties" : ""}</span></button>`).join("") || `<div class="li"><span class="m">No matches</span></div>`;
  }
  const empty = (html) => `<div class="empty">${html}</div>`;

  function render(id) {
    current = id; renderList();
    const m = members.find((x) => x.id === id); if (!m) return;
    const comms = m.committees || [];
    const dc = D.district_centers?.districts?.[m.district] || [];
    const sponsored = (D.bills?.bills || []).filter((b) => b.sponsors.some((s) => s.member_id === id));
    const votes = D.votes?.members?.[id] || [];
    const b = biz(id), fin = D.finance?.legislators?.[id], notes = D.notes[id] || [], briefs = D.briefs[id] || [];
    $("main").innerHTML = `
      <h1>${esc(m.name)} <span class="chip ${m.party}">${m.party}</span></h1>
      <p class="sub">${m.chamber_name === "Senate" ? "State Senator" : "State Representative"}, Legislative District ${m.district}${m.leadership_title ? ` · <span class="title">${esc(m.leadership_title)}</span>` : ""}</p>
      <div class="cards">
        <div class="card"><span class="k">Contact</span><span class="mono">${esc(m.email || "—")}</span><span class="mono">${esc(m.phone || "—")}</span><span>${esc(m.room || "")}, 1700 W. Washington</span></div>
        <div class="card"><span class="k">District</span><span class="v">Population ${D.population[m.district]?.toLocaleString() ?? "—"}</span><span>${dc.length ? "Served by " + dc.map((x) => esc(centerName[x.center] || x.center)).join(", ") : "No center match yet"}</span></div>
        <div class="card"><span class="k">Key committees</span><span class="v">${comms.filter(isKey).length}</span><span>${comms.filter((c) => isKey(c) && c.role !== "Member").map((c) => esc(c.role + ", " + c.name)).join("<br>") || "No chair or vice chair roles"}</span></div>
        <div class="card"><span class="k">Business background</span><span class="status ${b?.reported_business_ties ? "ties" : ""}">${esc(b?.status || "not reviewed")}</span>${b?.reported_business_ties ? `<span>${b.reported_business_ties} reported, ${b.verified_in_acc} verified in ACC</span>` : ""}</div>
      </div>

      <h2>Committees</h2>
      ${comms.length ? `<div class="tags">${comms.map((c) => `<span class="tag ${isKey(c) ? "lead" : ""}">${c.role !== "Member" ? esc(c.role) + " · " : ""}${esc(c.name)}${c.chamber === "J" ? " (joint)" : ""}</span>`).join("")}</div>` : empty("No committee assignments listed.")}

      <h2>Sponsored bills SBDC tracks</h2>
      ${D.bills ? (sponsored.length ? `<div class="tw"><table><tr><th>Bill</th><th>Title</th><th>Role</th><th>Latest action</th></tr>${sponsored.map((x) => {
        const s = x.sponsors.find((y) => y.member_id === id);
        return `<tr><td class="mono">${x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.identifier)}</a>` : esc(x.identifier)}</td><td>${esc(x.title)}</td><td>${s.primary ? "Primary" : "Cosponsor"}</td><td>${esc(x.latest_action?.date)} ${esc(x.latest_action?.description)}</td></tr>`;
      }).join("")}</table></div>` : empty("None of the tracked bills list this legislator as a sponsor.")) : empty("Run <code>openstates_bills.py</code> to load tracked bills.")}

      <h2>Votes on tracked bills</h2>
      ${D.votes ? (votes.length ? `<div class="tw"><table><tr><th>Bill</th><th>Date</th><th>Motion</th><th>Vote</th><th>Result</th></tr>${votes.map((v) => `<tr><td class="mono">${esc(v.bill)}</td><td class="mono">${esc(v.date)}</td><td>${esc(v.motion)}</td><td class="opt-${esc(v.option)}">${esc(v.option)}</td><td>${esc(v.result)}</td></tr>`).join("")}</table></div>` : empty("No recorded votes on tracked bills.")) : empty("Run <code>openstates_bills.py</code> to load votes.")}

      <h2 class="priv">Business background</h2>
      ${!b || b.status === "not reviewed" ? empty("Not reviewed yet. Add rows to <code>private/business_background.csv</code> from this legislator's financial disclosure statement, then run <code>business_research.py check</code>.")
        : b.entries.length ? `<div class="tw"><table><tr><th>Business</th><th>Reported as</th><th>ACC record</th><th>Source</th></tr>${b.entries.map((e) => `<tr><td>${esc(e.business_name)}${e.role_or_description ? `<br><span class="sub">${esc(e.role_or_description)}</span>` : ""}</td><td>${esc(e.interest_type.replace("_", " "))}${e.disclosure_year ? ` (${esc(e.disclosure_year)})` : ""}</td>
          <td>${e.acc_entity_number ? `${e.acc_url ? `<a href="${esc(e.acc_url)}" target="_blank" rel="noopener">${esc(e.acc_entity_number)}</a>` : esc(e.acc_entity_number)}<br><span class="sub">${esc(e.acc_status)}${e.acc_formed ? ", formed " + esc(e.acc_formed) : ""}</span>` : `<span class="sub">Not verified</span>`}</td>
          <td>${e.disclosure_url ? `<a href="${esc(e.disclosure_url)}" target="_blank" rel="noopener">Disclosure</a>` : "—"}</td></tr>`).join("")}</table></div>` : empty("The financial disclosure statement lists no business interests.")}

      <h2 class="priv">Campaign finance</h2>
      ${!D.finance ? empty("Run <code>spotlight_finance.py</code> to load campaign finance summaries.") : !fin ? empty("No campaign committee matched. Set <code>override_id</code> in <code>private/spotlight_committees.csv</code> and rerun.") :
        Object.entries(fin.cycles).sort((a, c) => c[0].localeCompare(a[0])).map(([y, c]) => `<div class="cycle"><h3>${y} cycle <span>${money(c.receipts)} raised · ${c.contributions.toLocaleString()} contributions</span></h3>
          <div class="bars">${[["In-state", c.shares.in_state], ["Business community", c.shares.business_community], ...Object.entries(c.by_source).map(([k, v]) => [k, c.receipts ? v / c.receipts : 0])].map(([k, v]) =>
            `<div class="bar"><span>${esc(k)}</span><span class="track"><span class="fill" style="display:block;width:${Math.round((v || 0) * 100)}%"></span></span><span class="pct">${pct(v)}</span></div>`).join("")}</div></div>`).join("") +
        `<p class="sub" style="font-size:13px">Committee ${esc(fin.committee_id)} (${esc(fin.match_note)}). Contributions show who funds a campaign, not how a legislator votes.</p>`}

      <h2 class="priv">Research notes</h2>
      ${notes.length ? notes.map((n) => `<div class="note"><div class="h">${esc(n.date)} · ${esc(n.author)}</div>${esc(n.note)}</div>`).join("") : empty("No notes. Add rows to <code>private/notes.csv</code> (member_id, date, author, note).")}

      <h2 class="priv">Draft briefs</h2>
      ${briefs.length ? briefs.map((x) => `<p class="sub mono">${esc(x.file)}</p><pre class="brief">${esc(x.text)}</pre>`).join("") : empty("No drafts yet. Briefs from the draft generator appear here.")}
      <p class="sub" style="font-size:12px;margin-top:28px">Built ${esc(D.built)} from data/ and private/.</p>`;
    window.scrollTo(0, 0);
  }
  $("list").addEventListener("click", (e) => { const b = e.target.closest("[data-id]"); if (b) { render(+b.dataset.id); location.hash = b.dataset.id; } });
  $("q").addEventListener("input", renderList); $("f").addEventListener("change", renderList);
  const start = +location.hash.slice(1) || members[0].id;
  render(members.some((m) => m.id === start) ? start : members[0].id);
})();
</script></body></html>
"""

if __name__ == "__main__":
    main()
