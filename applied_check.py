#!/usr/bin/env python3
"""
applied_check.py - Already-Applied Job Detection (Haiku-judged)
================================================================

Reads the applications tracker CSV and the scraped jobs CSV, pre-filters
candidate pairs by company-token / URL overlap, and has Claude Haiku subagents
decide which pairs are the same company and role. verify_jobs.py uses the
result to move already-applied jobs to a separate sheet.

Flow (all files live under WORK_DIR/applied):
  1. prepare_match_input(csv_path) writes pairs_NNN.json batches (10 pairs each)
     plus pairs_all.json.
  2. SKILL.md has Claude Desktop launch one Haiku subagent per batch; each writes
     result_NNN.json: [{"id": 1, "match": true, "reason": "..."}, ...]
  3. load_llm_matches() merges the result files into URL / key sets.
  4. is_already_applied() checks them (falls back to deterministic URL + key
     matching when no pairs file exists).

Tracker: config.APPLICATIONS_TRACKER_CSV (columns: Company, Position, Source URL).
"""

import csv
import json
import re
from pathlib import Path
from tqdm import tqdm

from config import APPLICATIONS_TRACKER_CSV, WORK_DIR, reset_dir

APPLIED_DIR = WORK_DIR / "applied"
PAIRS_ALL_PATH = APPLIED_DIR / "pairs_all.json"
PAIRS_PER_BATCH = 10

# Stopwords for company token pre-filtering (legal suffixes + generic words).
# These are stripped before token matching to avoid false candidate pairs
# (e.g., "Data GmbH" and "Tech GmbH" should not match on "gmbh").
_COMPANY_STOPWORDS = {
    "gmbh", "ag", "inc", "ltd", "co", "kg", "se", "corp", "group",
    "gruppe", "holding", "international", "deutschland", "germany",
    "global", "the", "und", "der", "die", "das", "gbr", "ug",
    "dienstleistungen", "services", "solutions", "technology",
    "technologies", "tech", "systems", "software", "consulting",
    "partners", "energy", "kgaa", "coming", "soon",
}


# ── Lazy import of normalization helpers (avoids a circular import) ─────────

def _get_apify():
    from apify_job_search import normalize_key, _norm_company, _norm_title
    from job_identity import normalize_job_url
    return normalize_key, _norm_company, _norm_title, normalize_job_url


def _company_tokens(name: str) -> set[str]:
    """Extract meaningful tokens from a company name for pre-filtering.

    Lowercases, strips punctuation, removes legal suffixes and generic
    stopwords, and returns tokens of length >= 3.
    """
    name = name.lower()
    name = re.sub(r"[^\w\s]", " ", name)
    return {t for t in name.split() if len(t) >= 3 and t not in _COMPANY_STOPWORDS}


def load_applied_job_keys() -> set[str]:
    """Build a set of normalize_key(company, title) for every job already
    applied to, reading from the applications tracker CSV.

    Returns a set of normalized keys; empty set if the CSV doesn't exist.
    Kept for backward compatibility — verify_jobs.py now uses load_applied_data().
    """
    normalize_key, _, _, _ = _get_apify()

    keys: set[str] = set()
    row_count = 0

    if not APPLICATIONS_TRACKER_CSV.exists():
        print(f"[!] Already-applied detection: CSV not found at {APPLICATIONS_TRACKER_CSV}")
        return keys

    with open(APPLICATIONS_TRACKER_CSV, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            company = (row.get("Company") or "").strip()
            title = (row.get("Position") or "").strip()
            if not company or not title:
                continue
            key = normalize_key(company, title)
            if key:
                keys.add(key)
                row_count += 1

    print(f"[*] Already-applied detection: {row_count} CSV rows → {len(keys)} unique keys")
    return keys


def load_applied_data() -> dict:
    """Build already-applied detection data from the tracker CSV.

    Returns dict with:
        keys:      set[str]  — normalized company::title keys
        companies: dict[str, list[str]] — normalized company → raw tracker titles
        urls:      set[str]  — normalized URLs
        entries:   list[dict] — raw {company, title, url} for LLM input prep
    """
    normalize_key, _norm_company, _norm_title, normalize_job_url = _get_apify()

    keys: set[str] = set()
    companies: dict[str, list[str]] = {}
    urls: set[str] = set()
    entries: list[dict] = []
    row_count = 0

    if not APPLICATIONS_TRACKER_CSV.exists():
        print(f"[!] Already-applied detection: CSV not found at {APPLICATIONS_TRACKER_CSV}")
        return {"keys": keys, "companies": companies, "urls": urls, "entries": entries}

    with open(APPLICATIONS_TRACKER_CSV, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            company = (row.get("Company") or "").strip()
            title = (row.get("Position") or "").strip()
            url = (row.get("Source URL") or "").strip()
            if not company or not title:
                continue
            nc = _norm_company(company)
            nt = _norm_title(title)
            keys.add(f"{nc}::{nt}")
            companies.setdefault(nc, []).append(title)
            if url:
                urls.add(normalize_job_url(url))
            entries.append({"company": company, "title": title, "url": url})
            row_count += 1

    print(
        f"[*] Already-applied detection: {row_count} CSV rows → "
        f"{len(keys)} keys, {len(companies)} companies, {len(urls)} URLs"
    )
    return {"keys": keys, "companies": companies, "urls": urls, "entries": entries}


def prepare_match_input(csv_path: Path) -> int:
    """Pre-filter candidate pairs between today's scraped jobs and tracker entries.

    Uses company token overlap (>= 1 shared meaningful token) to narrow
    the search space, then writes candidate pair batches for
    Haiku classification.

    Returns the number of candidate pairs generated.
    """
    from collections import defaultdict

    # Load today's scraped jobs
    today_jobs: list[dict] = []
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            company = (row.get("company") or "").strip()
            title = (row.get("title") or "").strip()
            url = (row.get("job_url") or "").strip()
            if company or url:
                today_jobs.append({"company": company, "title": title, "url": url})

    # Load tracker entries
    applied_data = load_applied_data()
    tracker_entries = applied_data["entries"]

    # Build token index: tracker company tokens → list of tracker indices
    tracker_by_token: dict[str, list[int]] = defaultdict(list)
    for i, te in enumerate(tracker_entries):
        for token in _company_tokens(te["company"]):
            tracker_by_token[token].append(i)

    # For each today job, find candidate tracker entries
    candidate_pairs: list[dict] = []
    pair_id = 1
    for tj_idx, tj in enumerate(tqdm(today_jobs, desc="Already-applied pairs")):
        candidate_tracker_idxs: set[int] = set()

        # Token overlap
        for token in _company_tokens(tj["company"]):
            for ti in tracker_by_token.get(token, []):
                candidate_tracker_idxs.add(ti)

        # Also check URL match (exact)
        if tj["url"]:
            _, _, _, normalize_job_url = _get_apify()
            nu = normalize_job_url(tj["url"])
            for ti, te in enumerate(tracker_entries):
                if te["url"] and normalize_job_url(te["url"]) == nu:
                    candidate_tracker_idxs.add(ti)

        for ti in candidate_tracker_idxs:
            te = tracker_entries[ti]
            candidate_pairs.append({
                "id": pair_id,
                "scraped_company": tj["company"],
                "scraped_title": tj["title"],
                "scraped_url": tj["url"],
                "tracker_company": te["company"],
                "tracker_title": te["title"],
                "tracker_url": te["url"],
            })
            pair_id += 1

    # Fresh batch files for the Haiku subagents (stale results must not leak in).
    reset_dir(APPLIED_DIR)
    PAIRS_ALL_PATH.write_text(json.dumps(candidate_pairs, ensure_ascii=False), encoding="utf-8")
    for batch_no, start in enumerate(range(0, len(candidate_pairs), PAIRS_PER_BATCH), 1):
        batch_path = APPLIED_DIR / f"pairs_{batch_no:03d}.json"
        batch_path.write_text(
            json.dumps(candidate_pairs[start:start + PAIRS_PER_BATCH], ensure_ascii=False, indent=1),
            encoding="utf-8",
        )

    print(
        f"[*] Already-applied LLM input: {len(today_jobs)} scraped jobs × "
        f"{len(tracker_entries)} tracker entries → {len(candidate_pairs)} candidate pairs"
    )
    return len(candidate_pairs)


def pending_pair_batches() -> list[Path]:
    """Pair batches that do not yet have a result file."""
    return [
        path for path in sorted(APPLIED_DIR.glob("pairs_[0-9]*.json"))
        if not path.with_name(path.name.replace("pairs_", "result_")).exists()
    ]


def load_llm_matches() -> dict | None:
    """Merge Haiku result files into sets of matched scraped URLs and keys.

    Returns None when prepare_match_input() never ran (callers then fall back
    to deterministic URL/key matching). Batches without a result file are
    treated as "no match" and reported.
    """
    if not PAIRS_ALL_PATH.exists():
        return None

    normalize_key, _, _, normalize_job_url = _get_apify()
    pairs = {pair["id"]: pair for pair in json.loads(PAIRS_ALL_PATH.read_text(encoding="utf-8"))}

    urls: set[str] = set()
    keys: set[str] = set()
    for result_path in sorted(APPLIED_DIR.glob("result_[0-9]*.json")):
        try:
            results = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            print(f"[!] Unreadable already-applied result {result_path.name}; ignored")
            continue
        for result in results if isinstance(results, list) else []:
            pair = pairs.get(result.get("id")) if isinstance(result, dict) else None
            if pair is None or result.get("match") is not True:
                continue
            nu = normalize_job_url(pair.get("scraped_url", ""))
            if nu:
                urls.add(nu)
            key = normalize_key(pair.get("scraped_company", ""), pair.get("scraped_title", ""))
            if key:
                keys.add(key)

    pending = pending_pair_batches()
    if pending:
        print(f"[!] {len(pending)} already-applied batch(es) have no result file; treated as no match")
    print(f"[*] Already-applied Haiku matches: {len(urls)} URLs, {len(keys)} keys")
    return {"urls": urls, "keys": keys}


def is_already_applied(
    company: str, title: str, url: str, applied_data: dict,
    llm_matches: dict | None = None,
) -> bool:
    """Check if a job has already been applied to.

    Primary: Haiku matches (pre-computed by the judge subagents).
    Checks both normalized URL and normalized company::title key against
    the LLM match sets.

    Fallback (llm_matches is None): deterministic URL + key match only.
    Used when LLM classification is unavailable (standalone execution).
    """
    normalize_key, _, _, normalize_job_url = _get_apify()

    nurl = normalize_job_url(url)
    key = normalize_key(company, title)

    if llm_matches is not None:
        if nurl and nurl in llm_matches["urls"]:
            return True
        if key and key in llm_matches["keys"]:
            return True
        return False

    # Fallback: deterministic URL + key match
    if nurl and nurl in applied_data["urls"]:
        return True
    if key and key in applied_data["keys"]:
        return True
    return False
