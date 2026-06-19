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
SELECTOR_TIMEOUT_MS = 5_000

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

# CSS selectors — match detail page (lineups)
SEL_LINEUPS       = ".lineups .lineup"           # two elements: team1, team2
SEL_LINEUP_PLAYER = ".flagAlign .text-ellipsis"  # player nick inside each lineup

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
# Delay between match page requests — randomised in this range to avoid rate-limiting
MATCH_REQUEST_DELAY_MIN = 0.3
MATCH_REQUEST_DELAY_MAX = 0.8

# Flush buffer to Parquet every N matches to avoid losing progress on crash
SAVE_EVERY_N = 5

# Output directory for scraped data
DATA_DIR = "data/datasets/results"

# Debug HTML sampling — paths and per-category counts for debug_sample_matches.py
DEBUG_MATCH_DIR    = "data/debug_match"
DEBUG_RECENT_COUNT = 5   # most recent matches to sample
DEBUG_OLDEST_COUNT = 5   # oldest matches to sample
DEBUG_RANDOM_COUNT = 5   # random matches sampled from a middle page

# Earliest year with HLTV data (used when iterating all years automatically)
HLTV_START_YEAR = 2012

# ── Team stats page ────────────────────────────────────────────────────────────
STATS_TEAMS_URL = f"{HLTV_BASE_URL}/stats/teams"

# Filter dimensions (empty string = "All" / default)
STATS_MATCH_TYPES = ["", "Majors", "BigEvents", "MvpEvents", "Lan", "Online"]
STATS_MAPS = [
    "",               # All maps
    "de_ancient",
    "de_anubis",
    "de_dust2",
    "de_inferno",
    "de_mirage",
    "de_nuke",
    "de_overpass",
    "de_cache",
    "de_cobblestone",
    "de_season",
    "de_train",
    "de_tuscan",
    "de_vertigo",
]
STATS_CS_VERSIONS = ["", "CS2", "CSGO"]   # "" = Both

# CSS selectors — team stats table
SEL_STATS_TABLE       = "table.stats-table"
SEL_STATS_TEAM_CELL   = "td.teamCol-teams-overview"
SEL_STATS_RATING_CELL = "td.ratingCol"

# Output
STATS_TEAMS_DATA_DIR = "data/datasets/team_stats"
STATS_TEAMS_PARQUET  = "team_stats.parquet"
STATS_TEAMS_PROGRESS = "progress.json"
STATS_SAVE_EVERY     = 50   # flush to Parquet every N combinations

# ── Player stats page ──────────────────────────────────────────────────────────
STATS_PLAYERS_URL = f"{HLTV_BASE_URL}/stats/players"

# Opponent ranking filter — empty string = "All" (no filter)
STATS_RANKING_FILTERS = ["All"]  # extend with Top5/Top10/Top20/Top50/Top100 if needed

# Output
STATS_PLAYERS_DATA_DIR = "data/datasets/player_stats"
STATS_PLAYERS_PARQUET  = "player_stats.parquet"
STATS_PLAYERS_PROGRESS = "progress.json"
