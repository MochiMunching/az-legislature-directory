# Arizona Legislator Directory (AZ SBDC prototype)

Legislative research tools for the AZ SBDC AI-Driven Legislative Research &
Outreach Pipeline. The **public site** (GitHub Pages) holds public information
only. Research that shouldn't be public stays in a **`private/`** folder on your
machine, which git ignores.

## Public site (`index.html`)

| Tab | What it shows |
|---|---|
| All members | Searchable roster; filters for chamber, party, district and committee; key committee tags; copy emails |
| By district | All 30 districts with their senator, two representatives, population and serving centers |
| District map | Official 2022 boundaries, address lookup, shading by senator's party or SBDC clients per 10,000 residents |
| Budget power map | JLBC, Appropriations, Finance, Ways & Means, Commerce, regulatory and rural committees; who sits where |
| Bills & votes | Bills SBDC tracks, with sponsors and roll calls; ESOP watch |
| Committee calendar | Weekly committee meeting days, times and rooms |
| SBDC centers | 10 centers, counties served, legislative and congressional districts |
| Updates | Incoming members, roster change log, data source dates |
| Leadership | Floor leaders in each chamber |

## Publish on GitHub Pages

1. Create a repo and push this folder to `main`.
2. **Settings → Pages → Deploy from a branch → `main` / `/ (root)`**.
3. **Settings → Actions → General → Workflow permissions → Read and write** (lets the refresh job commit).
4. Optional: **Settings → Secrets and variables → Actions → New secret** `OPENSTATES_API_KEY` to refresh bills automatically.

Edit the page in `site/body.html`, then run `python scraper/build_site.py` to rebuild `index.html`.

## Setup

```bash
pip install requests beautifulsoup4 geopandas pandas
```

## Scripts

### Public data (safe to commit)

| Script | What it does |
|---|---|
| `scrape_roster.py` | Pulls the roster from azleg.gov; records changes in `data/changes.json`. `--committees` also visits member pages |
| `committees_snapshot.py` | Loads the 2026 Senate/House committee lists and JLBC (rerun with new lists in Dec/Jan) |
| `members_elect.py` | Turns `data/members_elect.csv` (certified winners) into returning / switching / new |
| `match_districts.py` | Matches centers to districts using the official maps in `data/boundaries/`; geocodes each office. `--level congressional` for U.S. House |
| `openstates_bills.py` | Bills, sponsors, roll calls, ESOP watch (needs `OPENSTATES_API_KEY`). `--discover` lists candidate bills in `data/bill_list.csv`; SBDC sets `track=yes` |
| `update_sources.py` | Records when each data source was last refreshed |
| `build_site.py` | Builds `index.html` from `site/body.html` |

### Private research (writes to `private/`, never committed)

| Script | What it does |
|---|---|
| `match_clients.py` | SBDC client export → district totals. `--publish-aggregates` also writes public per-district counts, hiding districts under 5 clients |
| `spotlight_finance.py` | Campaign finance summaries from the free Spotlight API (totals and categories only, no donor names). `--candidates` lists 2026 candidates |
| `business_research.py` | `init` creates the research sheet; `check` validates it and sets each legislator's reported-business-ties status |
| `generate_briefs.py` | Gemini drafts: committee brief, new member letter, district impact memo, ESOP brief, bill summary. `--dry-run` shows the prompt; `--private` needs `GEMINI_PAID_KEY` |
| `build_profiles.py` | Builds `private/profiles.html`, one offline file with every legislator's public and private information |

Prompt wording lives in `prompts/`. SBDC fills in `prompts/sbdc_messaging.md`
(results, funding, ESOP talking points) and sets `prompts/outreach_policy.md`
(whether drafts may include requests). Until then drafts are educational and
show placeholders instead of numbers.

## Automatic refresh

`.github/workflows/refresh-data.yml` runs at 6:17 AM Arizona time on weekdays
from January to June and on Mondays the rest of the year. It refreshes the
roster and change log, members-elect, bills and votes (if the Open States key
is set) and source dates, then commits any changes. You can also run it from
the Actions tab. Private scripts are never run there.

## Data notes

- Roster: 57th Legislature, Second Regular Session, snapshot 2026-11-09. The 58th
  Legislature convenes January 11, 2027; the scraper picks it up automatically.
- Committees: Senate list revised 3/13/2026, House list revised 3/20/2026,
  statutory committees (JLBC) 1/28/2026. The House list predates Rep. Marshall's
  resignation; his successor Rep. Allen has no assignments listed. The Senate
  has no Commerce committee this session.
- Districts: the redistricting commission's Approved Official Legislative and
  Congressional Maps (KMZ) in `data/boundaries/`, with simplified Census county
  boundaries. A district counts for a center when at least 1% of its area is in
  a served county, or it covers at least 2% of a served county.
- Voting records aren't on the azleg.gov roster; they come from Open States.
- Campaign finance shows who funds a campaign, not how a legislator votes.
  Business ties come only from legislators' own financial disclosures.
- Spotlight field names were checked against live responses in November 2026.
  Legislators often have a separate committee for each race, so the script sums
  every matching committee and lists them in `private/spotlight_committees.csv`.
  Open States fields are still read defensively; check its first run.
- azleg.gov (Sucuri) and Spotlight (Cloudflare) sit behind firewalls. The scripts
  send browser-style headers and say so plainly if a firewall blocks them.
