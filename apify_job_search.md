# Platform notes

Technical notes for each source. Run instructions are in `SKILL.md`; candidate settings are in `config.py`. The scraper is `apify_job_search.py` (the name is historical; nothing uses Apify).

## Sources

| Source | Method | Notes |
|---|---|---|
| LinkedIn | Free HTML scraping | 6 locations x every title in `SEARCH_ROLES`, `f_TPR=r86400` (24 h). 5 workers, backoff on 429. Descriptions come from JSON-LD on detail pages. |
| Indeed | GraphQL (`apis.indeed.com/graphql`) | Same endpoint as the Indeed iOS app, `indeed-co: DE`, `dateOnIndeed` 24 h filter, full descriptions. The `what` parameter is fuzzy, so the title filter is essential. |
| Arbeitnow | REST (`/api/job-board-api`) | One call, filtered locally by `created_at`. |
| Xing | `requests` HTML | `data-testid` attributes and `<time dateTime>`. Sponsored listings without a date are skipped. |
| Stepstone | `requests` HTML | Path-based URLs (`/jobs/{slug}/in-deutschland`) and `ag=age_1` for 24 h; `?keyword=` returns generic results. |
| ATS Direct | Public JSON APIs | Greenhouse `boards-api.greenhouse.io/v1/boards/{slug}/jobs`, SmartRecruiters `api.smartrecruiters.com/v1/companies/{slug}/postings` (slugs are case-sensitive), Ashby `jobs.ashbyhq.com/{slug}`. |

Removed on 2026-11-20: Wellfound and EU Remote Jobs (tech-startup boards, no plant-science roles).

## Description fallback (`fetchers.py`)

When a detail page has no JSON-LD description, `fetch_job_description(url)` tries:

1. **TinyFish Fetch** - `POST https://api.fetch.tinyfish.ai`, `X-API-Key: $TINYFISH_API_KEY`, body `{"urls": [...], "format": "markdown"}`; up to 10 URLs per call; the text is in `results[].text`. Free allowance 1,000 URLs/day, 150 URLs/min.
2. **Jina Reader** - `GET https://r.jina.ai/<url>`; `JINA_API_KEY` is optional (higher rate limit).

A result counts only when it is at least 200 characters, contains job-description section markers (Aufgaben, Profil, Requirements, ...), and is not a login or captcha wall.

## Cross-run deduplication

`load_seen_job_urls()` scans every dated export folder earlier than the current run date, using exact stable posting-URL identity only, and fails loudly if a dated export is unreadable. Historical outputs are never rewritten.

| Identity | Normalization |
|---|---|
| LinkedIn | Numeric job ID from the path or job-ID query |
| Indeed | `jk` value on a real Indeed domain |
| Other sites | Lowercase scheme/host, case-sensitive path, sorted query pairs, tracking keys removed |

No company/title fuzzy matching is used across dates. Within-run company/title dedup is separate. Same-day reruns preserve eligible rows already exported that day.

## Gotchas

- **Console encoding:** Windows consoles default to cp1252; `config.py` forces UTF-8 on stdout/stderr, and every file is opened with an explicit encoding.
- **Output layout:** each run writes into `Job Search\YYYY-MM-DD\` (override with `JOBSCRAPER_OUTPUT_DIR`).
- **LinkedIn rate limiting:** about 5% of requests return 429; a short backoff retry handles most.
- **Slug discovery for ATS:** a slug is valid when the API returns 200, even with zero postings.
