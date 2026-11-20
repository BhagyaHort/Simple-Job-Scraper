"""Shared configuration for the Jobscraper pipeline (Windows / Claude Desktop).

Everything candidate-specific lives here: search titles, title filters, skill
keywords, paths and API-key lookups. Paths default to locations next to this
file and can be overridden with environment variables.

Environment variables (all optional):
    JOBSCRAPER_OUTPUT_DIR   where dated exports are written (default: ./Job Search)
    JOBSCRAPER_TRACKER_CSV  applications tracker CSV (default: llm-cv tracker)
    JOBSCRAPER_PORTFOLIO    portfolio folder (default: llm-cv/okf)
    TINYFISH_API_KEY        TinyFish Fetch API key (JD fallback fetcher)
    JINA_API_KEY            Jina Reader key (optional; works keyless at a low rate limit)
"""

import os
import re
import sys
from pathlib import Path

# Windows consoles default to cp1252 and crash on the check-mark/arrow glyphs
# used in progress output; force UTF-8 on every entry point that imports this.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT_DIR = Path(__file__).resolve().parent

# ── Paths ────────────────────────────────────────────────────────────────────
_DOCUMENTS = Path.home() / "OneDrive" / "Documents"
if not _DOCUMENTS.exists():
    _DOCUMENTS = Path.home() / "Documents"

PORTFOLIO_DIR = Path(os.getenv("JOBSCRAPER_PORTFOLIO", _DOCUMENTS / "llm-cv" / "okf"))
BASE_RESUMES_DIR = PORTFOLIO_DIR / "base_files"
JOB_SEARCH_DIR = Path(os.getenv("JOBSCRAPER_OUTPUT_DIR", ROOT_DIR / "Job Search"))
APPLICATIONS_TRACKER_CSV = Path(os.getenv(
    "JOBSCRAPER_TRACKER_CSV",
    _DOCUMENTS / "llm-cv" / "Applications" / "applications_tracker.csv",
))
# Scratch space for the scrape -> judge -> finalize hand-off (git-ignored).
WORK_DIR = ROOT_DIR / ".work"

# ── API keys ─────────────────────────────────────────────────────────────────
def _env_or_user_setting(name: str) -> str:
    """Process env var, else the Windows user env saved by `setx` (works without a restart)."""
    value = os.getenv(name, "")
    if value:
        return value
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            return str(winreg.QueryValueEx(key, name)[0])
    except (ImportError, OSError):
        return ""


TINYFISH_API_KEY = _env_or_user_setting("TINYFISH_API_KEY")
JINA_API_KEY = _env_or_user_setting("JINA_API_KEY")

# ── Judge ────────────────────────────────────────────────────────────────────
JUDGE_MODEL = "claude-haiku-5-5"  # Claude Desktop subagents use model="haiku"
JUDGE_BATCH_SIZE = 5              # job descriptions per Haiku subagent

# ── Search titles (portfolio: plant science, hydroponics/CEA, food safety/QC) ─
# Role-type keywords (Werkstudent / Praktikum / Intern) are searched explicitly
# because the boards treat them as distinct result sets.
SEARCH_ROLES = [
    # Plant science & research
    "Plant Scientist",
    "Plant Research",
    "Research Assistant Plant Science",
    "Pflanzenwissenschaft",
    "Agronom",
    # Hydroponics / controlled-environment agriculture
    "Hydroponics",
    "Vertical Farming",
    "Controlled Environment Agriculture",
    "Gartenbau",
    "Gewächshaus",
    # Laboratory / analytics
    "Laborant Pflanzen",
    "Laboratory Technician Plant",
    # Quality & food safety
    "Food Safety",
    "Qualitätssicherung Lebensmittel",
    "Quality Assurance Food",
    # Student & intern roles
    "Werkstudent Pflanzen",
    "Werkstudent Labor",
    "Working Student Plant",
    "Praktikum Pflanzen",
    "Praktikum Labor",
    "Internship Plant Science",
    "Internship Hydroponics",
]

# ── Title filters ────────────────────────────────────────────────────────────
MAX_EXP_YEARS = 2
FRESHNESS_HOURS = 24

EXCLUDED_TITLE_PATTERNS = re.compile(
    r"\b(senior|sr|lead|head|principal|staff|manager|director|architect|vp|chief|expert|team lead)\b",
    re.IGNORECASE,
)

# A title must contain one of these domain words...
DOMAIN_TITLE_KEYWORDS = re.compile(
    r"\b(?:plant|pflanz|hydropon|horticult|gartenbau|gärtner|agrar|agri\b|agricultur|agronom|"
    r"crop|greenhouse|gewächshaus|vertical farm|vertikal|controlled[- ]environment|\bcea\b|"
    r"food safety|lebensmittel|food quality|qualitätssicherung|qualitätskontrolle|"
    r"quality (?:assurance|control)|\bqa\b|\bqc\b|\bhaccp\b|"
    r"labor|laborant|laborat|lab technician|\blab\b|"
    r"biolog|botan|phyto|biotech|mikrobio|microbio|"
    r"gemüse|vegetable|microgreen|mushroom|pilz|saatgut|seed|"
    r"soil|bodenkunde|bodenwissenschaft|nutrient|phenotyp|r&d|forschung|research assistant|wissenschaftl)",
    re.IGNORECASE,
)

# ...and must not look like a software / unrelated-trade title.
EXCLUDED_DOMAIN_PATTERNS = re.compile(
    r"\b(software|developer|entwickler|devops|frontend|backend|full[- ]?stack|"
    r"data engineer|data scientist|machine learning|sap|sales|vertrieb|marketing|"
    r"recruit\w*|accountant|buchhalt\w*|pflegekraft|pflege|erzieher\w*|"
    r"qa engineer|test engineer|software tester|automation engineer|"
    r"bodenleger\w*|landschaftsbau|forstwirt\w*|tierpfleger\w*|lager\w*|packstation|"
    r"schichtleit\w*|kfz|elektriker\w*|monteur\w*|"
    r"auszubildende\w*|ausbildung\w*|azubi|duales studium)\b",
    re.IGNORECASE,
)

# ── Match scoring (share of portfolio skills mentioned in the posting) ───────
SKILL_KEYWORDS = [
    "hydropon", "greenhouse", "gewächshaus", "plant", "pflanz", "microgreen",
    "nutrient", "nährstoff", "ph ", "ec ", "food safety", "lebensmittelsicherheit",
    "haccp", "quality control", "qualitätssicherung", "laborator", "labor",
    "extraction", "isotope", "imagej", "excel", "phenotyp", "experiment",
    "versuch", "literature review", "data analysis", "datenanalyse", "sampling",
    "probenahme", "vertical farm", "controlled environment", "horticult",
    "gartenbau",
]

# Non-German-speaking posting languages are fine; this is the candidate's level
# (used by the judge instructions in verify_jobs.py).
CANDIDATE_GERMAN_LEVEL = "A2"
CANDIDATE_ENGLISH_LEVEL = "C2"

WINDOWS_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def match_score(text: str) -> int:
    """Percentage of portfolio skill keywords found in ``text`` (capped at 100)."""
    lowered = (text or "").lower()
    hits = sum(1 for keyword in SKILL_KEYWORDS if keyword in lowered)
    return min(100, int(hits / len(SKILL_KEYWORDS) * 100 * 3))


def is_relevant_title(title: str) -> bool:
    """True when the title has a domain keyword and no software/unrelated marker."""
    return bool(DOMAIN_TITLE_KEYWORDS.search(title)) and not EXCLUDED_DOMAIN_PATTERNS.search(title)


def reset_dir(path: Path) -> Path:
    """Empty ``path`` (creating it if needed) without failing on OneDrive/Windows locks.

    Removing a folder inside a OneDrive-synced tree can raise PermissionError
    while the sync client holds the directory, so only the files are deleted and
    the directory itself is kept.
    """
    path.mkdir(parents=True, exist_ok=True)
    for child in path.rglob("*"):
        if child.is_file():
            child.unlink(missing_ok=True)
    return path
