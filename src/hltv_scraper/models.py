from datetime import date
from pydantic import BaseModel


class TeamResult(BaseModel):
    name: str
    score: int


class MatchResult(BaseModel):
    date: date
    team1: TeamResult
    team2: TeamResult
    event: str
    map_count: int | None = None
    match_url: str | None = None


class PlayerStat(BaseModel):
    name: str
    kills: int | None = None
    deaths: int | None = None
    adr: float | None = None
    kast: float | None = None   # e.g. 72.7 (without the %)
    rating: float | None = None  # HLTV Rating 2.0


class MapResult(BaseModel):
    order: int          # 0 = "All Maps" aggregate, 1+ = individual map
    name: str           # map name or "all" for the aggregate entry
    score_team1: int    # map score; equals series score when order == 0
    score_team2: int
    players_team1: list[PlayerStat] = []       # both sides
    players_team2: list[PlayerStat] = []       # both sides
    players_team1_ct: list[PlayerStat] = []    # CT side
    players_team2_ct: list[PlayerStat] = []    # CT side
    players_team1_t: list[PlayerStat] = []     # T side
    players_team2_t: list[PlayerStat] = []     # T side


class MatchDetail(BaseModel):
    match_id: int
    date: date
    match_time: str | None = None      # e.g. "17:00"
    team1: str
    team2: str
    score_team1: int                    # maps won
    score_team2: int
    event: str
    stage: str | None = None           # e.g. "Quarter-Final", "Group Stage"
    format: str | None = None          # e.g. "bo1", "bo3", "bo5"
    maps: list[MapResult] = []
    match_url: str
