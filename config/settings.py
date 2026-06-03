"""
FinMetrics Configuration
========================
All environment-driven settings. Never hardcode credentials.
Copy config/.env.example to config/.env and populate before running.

Environment variables are loaded from config/.env if python-dotenv is
installed, or from the shell environment directly. The .env file is
git-ignored — never commit credentials.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field

# ── Project Paths ─────────────────────────────────────────────────────────────
ROOT_DIR    = Path(__file__).parent.parent
CONFIG_DIR  = ROOT_DIR / "config"
DATA_DIR    = ROOT_DIR / "data"
RAW_DIR     = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
REFERENCE_DIR = DATA_DIR / "reference"
DOCS_DIR    = ROOT_DIR / "docs"

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(CONFIG_DIR / ".env")
except ImportError:
    pass  # dotenv optional — shell env vars work fine


# ── Database ──────────────────────────────────────────────────────────────────
@dataclass
class DatabaseConfig:
    """PostgreSQL connection settings."""
    host:     str = field(default_factory=lambda: os.getenv("DB_HOST", "localhost"))
    port:     int = field(default_factory=lambda: int(os.getenv("DB_PORT", "5432")))
    name:     str = field(default_factory=lambda: os.getenv("DB_NAME", "finmetrics_db"))
    user:     str = field(default_factory=lambda: os.getenv("DB_USER", "finmetrics"))
    password: str = field(default_factory=lambda: os.getenv("DB_PASSWORD", ""))

    @property
    def url(self) -> str:
        return (
            f"postgresql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )

    @property
    def url_safe(self) -> str:
        """URL with password masked — safe for logging."""
        return (
            f"postgresql://{self.user}:***"
            f"@{self.host}:{self.port}/{self.name}"
        )


# ── EDGAR API ─────────────────────────────────────────────────────────────────
@dataclass
class EdgarConfig:
    """
    SEC EDGAR API configuration.

    EDGAR requires a descriptive User-Agent header for all requests.
    Format: "CompanyName contact@email.com"
    Requests without a valid User-Agent return HTTP 403.

    Rate limit: 10 requests/second across all EDGAR domains.
    We target 8/sec in practice to stay safely below the limit.
    """
    base_url:       str = "https://data.sec.gov"
    submissions_url: str = "https://data.sec.gov/submissions"
    facts_url:      str = "https://data.sec.gov/api/xbrl/companyfacts"
    concept_url:    str = "https://data.sec.gov/api/xbrl/companyconcept"
    tickers_url:    str = "https://sec.gov/files/company_tickers.json"
    rss_url:        str = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=10-K&dateb=&owner=include&count=40&search_text=&output=atom"

    # Rate limiting — 10 req/sec max; target 8/sec
    requests_per_second: float = 8.0
    retry_attempts:      int   = 3
    retry_backoff:       float = 2.0  # seconds, doubles each retry

    # User-Agent — REQUIRED by SEC; 403 without it
    user_agent: str = field(
        default_factory=lambda: os.getenv(
            "EDGAR_USER_AGENT",
            "FinMetrics contact@finmetrics.io"  # Replace with real email
        )
    )

    # Forms to collect
    domestic_forms: tuple = ("10-K", "10-Q")
    foreign_forms:  tuple = ("20-F", "6-K")
    all_forms:      tuple = ("10-K", "10-Q", "20-F", "6-K")


# ── FX / Currency ─────────────────────────────────────────────────────────────
@dataclass
class FxConfig:
    """
    FX rate data sources.
    All free, no API keys required.

    ECB covers: EUR, JPY, KRW, TWD vs USD (via USD/EUR cross)
    Fed H.10 covers: direct USD rates for major currencies
    """
    ecb_url:     str = "https://data-api.ecb.europa.eu/service/data/EXR"
    fed_h10_url: str = "https://www.federalreserve.gov/releases/h10/current/default.htm"
    base_currency: str = "USD"
    supported_currencies: tuple = ("EUR", "JPY", "KRW", "TWD")

    # Refresh frequency — daily rates needed for period-average calculations
    refresh_days: int = 1


# ── Pipeline ──────────────────────────────────────────────────────────────────
@dataclass
class PipelineConfig:
    """Pipeline behavior and limits."""

    # How many years of history to load on initial company ingestion
    initial_history_years: int = 10

    # Minimum data quality score to include in metrics table (0-100)
    min_completeness_score: int = 40

    # Batch size for bulk company loads
    batch_size: int = 10

    # Dry run — parse and validate but do not write to database
    dry_run: bool = field(
        default_factory=lambda: os.getenv("DRY_RUN", "false").lower() == "true"
    )

    # Fiscal year end month for TTM calculation fallback
    default_fy_end_month: int = 12  # December

    # Supported filing system identifiers
    filing_systems: tuple = ("EDGAR", "ESMA", "EDINET", "DART", "TWSE")

    # Accounting standards
    accounting_standards: tuple = ("US-GAAP", "IFRS", "J-GAAP", "K-IFRS", "TW-GAAP")


# ── Logging ───────────────────────────────────────────────────────────────────
@dataclass
class LoggingConfig:
    """Logging configuration."""
    level:   str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    format:  str = "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s"
    datefmt: str = "%Y-%m-%d %H:%M:%S"

    # Log file — optional; defaults to stdout only
    log_file: str = field(
        default_factory=lambda: os.getenv("LOG_FILE", "")
    )


# ── Global Config Instance ────────────────────────────────────────────────────
class Config:
    """
    Singleton config object.
    Import and use:  from config.settings import config
    """
    def __init__(self):
        self.db       = DatabaseConfig()
        self.edgar    = EdgarConfig()
        self.fx       = FxConfig()
        self.pipeline = PipelineConfig()
        self.logging  = LoggingConfig()

    def validate(self) -> list[str]:
        """
        Returns a list of validation warnings.
        Call at startup to catch missing environment variables.
        """
        warnings = []
        if not self.db.password:
            warnings.append("DB_PASSWORD not set — database connection will fail")
        if self.edgar.user_agent == "FinMetrics contact@finmetrics.io":
            warnings.append("EDGAR_USER_AGENT is using default — set a real email address")
        if self.pipeline.dry_run:
            warnings.append("DRY_RUN=true — pipeline will not write to database")
        return warnings


config = Config()
