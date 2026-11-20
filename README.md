# Jobscraper

Automated job search for **Bhagya Lekshmi Vikraman Nair**: plant science, hydroponics / controlled-environment agriculture, laboratory work and food safety. It looks for **full-time (entry level), working-student and internship** roles in Germany.

It fetches fresh postings (< 24 h) from six sources, filters them against the portfolio in `llm-cv\okf`, and writes a sortable CSV/XLSX/JSON/MD report. A verification step then has **Claude Haiku 5.5** read each full job description (German level, required experience, portfolio fit) and compare jobs with the applications tracker.

> **Windows + Claude Desktop only.** The Haiku judge runs as Claude Desktop subagents, so there is no Linux or standalone mode.

## Quick start

```powershell
pip install requests openpyxl beautifulsoup4 tqdm
setx TINYFISH_API_KEY "<key>"   # optional, JD fallback
setx JINA_API_KEY "<key>"       # optional, JD fallback
python apify_job_search.py
python verify_jobs.py prepare
# Claude Desktop runs the Haiku subagents (see SKILL.md, Step 3)
python verify_jobs.py finalize
```

In Claude Desktop, ask for "run job search" and the [`SKILL.md`](SKILL.md) steps run end to end. Output goes to `Job Search\YYYY-MM-DD\` (git-ignored).

## Pipeline

```
6 sources in parallel -> title/seniority + Germany location guard
-> within-run dedup -> all-history exact-URL dedup -> export
-> verify prepare: platform checks, TinyFish/Jina description fallback, batch files
-> Haiku 5.5 subagents: German requirement, required experience, portfolio fit, already-applied pairs
-> verify finalize: routing and the verified workbook
```

### Sources

| Source | Method |
|---|---|
| LinkedIn | HTML scraping, 6 locations x all search titles, 24 h filter |
| Indeed | GraphQL API, full descriptions |
| Arbeitnow | REST API |
| Xing | `requests` HTML |
| Stepstone | `requests` HTML |
| ATS Direct | Greenhouse / SmartRecruiters / Ashby public APIs (Eurofins, Lonza, Pivot Bio) |

Wellfound and EU Remote Jobs were removed: both are tech-startup boards with no plant-science postings.

**Description fallback.** When a board's detail page gives no description, [TinyFish Fetch](https://docs.tinyfish.ai/fetch-api) is tried first, then Jina Reader (`r.jina.ai`). A fetched page only counts if it has job-description markers and is not a login wall.

### Search titles

Defined in `config.py` (`SEARCH_ROLES`): Plant Scientist, Plant Research, Research Assistant Plant Science, Pflanzenwissenschaft, Agronom, Hydroponics, Vertical Farming, Controlled Environment Agriculture, Gartenbau, Gewächshaus, Laborant Pflanzen, Laboratory Technician Plant, Food Safety, Qualitätssicherung Lebensmittel, Quality Assurance Food, and Werkstudent / Working Student / Praktikum / Internship variants for plants, lab and hydroponics.

A title must also pass `is_relevant_title()`: a plant / lab / food-safety keyword and no software or unrelated-trade marker.

### Verification filters

| Filter | Action |
|---|---|
| Outside or unknown Germany location | Exclude |
| Exact URL in an earlier dated export | Previously Seen sheet |
| Missing, failed or invalid Haiku judgment | Needs Review sheet |
| Already applied (tracker match) | Already Applied sheet |
| Reposted LinkedIn job | Reposted sheet |
| Haiku rates the job a poor fit for the portfolio | Drop |
| German B2+ required | Drop |
| Required experience > 2 years | Drop |
| Staffing / recruitment agency | Staffing Companies sheet |
| German A1-B1 or preferred | Keep and flag |

Working-student roles are Germany-wide (the old Hamburg/Kiel-only rule is gone).

### Output files

| File | Description |
|---|---|
| `Job_Search_<date>.csv` | UTF-8 BOM, sortable in Excel |
| `Job_Search_<date>.json` | Same data plus descriptions |
| `Job_Search_<date>.xlsx` | Frozen header, autofilter, clickable links |
| `JOB_OPENINGS_LAST_24H.md` | Summary table with apply links |
| `Job_Search_<date>_verified.xlsx` | To Apply plus conditional review sheets |

## Configuration

Everything candidate-specific is in [`config.py`](config.py): search titles, title filters, skill keywords for `match_score`, paths and key lookups.

| Setting | Where |
|---|---|
| Search titles | `config.py` `SEARCH_ROLES` |
| Title filters | `config.py` `DOMAIN_TITLE_KEYWORDS`, `EXCLUDED_DOMAIN_PATTERNS` |
| Experience ceiling | `config.py` `MAX_EXP_YEARS` (2) |
| Judge model / batch size | `config.py` `JUDGE_MODEL`, `JUDGE_BATCH_SIZE` |
| ATS company slugs | `ats_scraper.py` `*_SLUGS` |
| LinkedIn cities | `apify_job_search.py` `LINKEDIN_LOCATIONS` |

Environment variables: `TINYFISH_API_KEY`, `JINA_API_KEY`, `JOBSCRAPER_OUTPUT_DIR`, `JOBSCRAPER_TRACKER_CSV`, `JOBSCRAPER_PORTFOLIO`.

## Project structure

```
Simple-Job-Scraper/
├── config.py                # candidate profile, search titles, filters, paths, keys
├── apify_job_search.py      # scraper: fetchers, filters, dedup, export
├── fetchers.py              # TinyFish + Jina description fallback
├── verify_jobs.py           # prepare / status / finalize verification CLI
├── applied_check.py         # already-applied pair batches + result merge
├── ats_scraper.py           # Greenhouse / SmartRecruiters / Ashby
├── job_identity.py          # stable posting-URL identity and dated-export history
├── location_policy.py       # Germany location eligibility
├── staffing_filter.py       # staffing-agency blocklist
├── dedup_existing_sheets.py # one-off historical dedup cleanup
├── SKILL.md                 # Claude Desktop skill: step-by-step run instructions
├── ARCHITECTURE.md  CHANGELOG.md  apify_job_search.md
├── tests/test_regressions.py
├── .work/                   # judge / applied batches (git-ignored)
└── Job Search/              # output (git-ignored)
```

## Tests

```powershell
python -m unittest discover -s tests -v
```
