SITE_NAME = "HLTV"
HLTV_BASE_URL = "https://www.hltv.org"
RESULTS_PATH = "/results"
RESULTS_URL = f"{HLTV_BASE_URL}{RESULTS_PATH}"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# Browser
BROWSER_HEADLESS = True
PAGE_TIMEOUT_MS = 30_000
SELECTOR_TIMEOUT_MS = 15_000

# CSS selectors — results list page
SEL_RESULTS_HOLDER  = ".results-all"
SEL_RESULTS_SUBLIST = ".results-sublist"
SEL_PAGINATION_DATA = ".pagination-data"   # element containing the total result count
SEL_DATE_HEADING    = ".standard-headline"
SEL_RESULT_ROW      = ".result-con a.a-reset"
SEL_TEAM            = ".team"
SEL_SCORE           = ".result-score span"
SEL_EVENT           = ".event-name"

# Pagination
PAGE_SIZE = 100

# CSS selectors — match detail page (banner / header)
SEL_MATCH_DATE      = ".timeAndEvent .date"
SEL_MATCH_TIME      = ".timeAndEvent .time"
SEL_MATCH_EVENT     = ".timeAndEvent .text-ellipsis"
SEL_MATCH_STAGE     = ".timeAndEvent .preposition + a"   # e.g. "Quarter-Final"
SEL_MATCH_FORMAT    = ".veto-box .standard-box"          # contains "Best of X"

# CSS selectors — match detail page (maps)
SEL_MAP_HOLDER      = ".mapholder"
SEL_MAP_NAME        = ".mapname"
SEL_MAP_SCORE       = ".results-team-score"

# CSS selectors — match detail page (player stats)
# Stats live in .matchstats > .stats-content (NOT inside .mapholder)
# Each stats-content has 6 tables: [totalstats, ctstats, tstats] for team1 then team2
# sections[0] = "All Maps" aggregate; sections[1:] = individual maps (same order as mapholders)
SEL_MATCH_STATS     = ".matchstats"
SEL_STATS_TABLE     = "table.totalstats"   # both-side stats
SEL_STATS_TABLE_CT  = "table.ctstats"      # CT-side stats (has class "hidden" but data is in HTML)
SEL_STATS_TABLE_T   = "table.tstats"       # T-side stats  (has class "hidden" but data is in HTML)
SEL_PLAYER_NICK     = ".player-nick"
# KD column: one td.kd.traditional-data cell containing "46-23" (kills dash deaths)
SEL_STAT_KD         = ".kd"
SEL_STAT_ADR        = ".adr"
SEL_STAT_KAST       = ".kast"
SEL_STAT_RATING     = "td.rating"          # actual class is "rating" (not "rating2")

# Cookies persisted to avoid solving Cloudflare on every run
COOKIES_FILE    = "hltv_cookies.json"
BROWSER_CHANNEL = "chrome"

# Delay between individual match page requests (seconds)
MATCH_REQUEST_DELAY = 1.5

# Flush buffer to Parquet every N matches to avoid losing progress on crash
SAVE_EVERY_N = 5

# Output directory for scraped data
DATA_DIR = "data/datasets"

# Debug HTML sampling — paths and per-category counts for debug_sample_matches.py
DEBUG_MATCH_DIR    = "data/debug_match"
DEBUG_RECENT_COUNT = 5   # most recent matches to sample
DEBUG_OLDEST_COUNT = 5   # oldest matches to sample
DEBUG_RANDOM_COUNT = 5   # random matches sampled from a middle page
