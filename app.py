import json
import os
import unicodedata
from datetime import datetime, timezone
from urllib.parse import quote, unquote
from zoneinfo import ZoneInfo
import requests
import streamlit as st

st.set_page_config(
    page_title="FIFA World Cup 2026",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="auto",
)

# ── Session state ──────────────────────────────────────────────────────────────
for key, default in [
    ("view", "home"),
    ("selected_group", None),
    ("selected_country", None),
    ("selected_player", 0),
    ("compare_p1", None),
    ("compare_p2", None),
    ("calendar_tz", "UTC"),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ── Deep-link handling ─────────────────────────────────────────────────────────
if "player" in st.query_params:
    try:
        enc_country, idx_str = st.query_params["player"].split("|")
        st.session_state.view = "country"
        st.session_state.selected_country = unquote(enc_country)
        st.session_state.selected_player = int(idx_str)
    except (ValueError, KeyError):
        pass
    st.query_params.clear()
    st.rerun()

if "country" in st.query_params:
    try:
        country_key = unquote(st.query_params["country"])
        st.session_state.view = "country"
        st.session_state.selected_country = country_key
        st.session_state.selected_player = 0
    except (ValueError, KeyError):
        pass
    st.query_params.clear()
    st.rerun()


# ── CSS ────────────────────────────────────────────────────────────────────────
# The sidebar is only useful on the player-profile ("country") view, where it
# acts as a quick squad jump-list. Hide it everywhere else.
_sidebar_css = (
    "" if st.session_state.view == "country" else
    'section[data-testid="stSidebar"] { display: none; }\n'
    '[data-testid="collapsedControl"] { display: none; }'
)

st.markdown("""
<style>
""" + _sidebar_css + """
  .block-container { padding-top: 3.5rem; padding-bottom: 2rem; }

  .group-card {
    background: #1E293B; border-radius: 12px;
    padding: 1rem 1rem 0.5rem 1rem; margin-bottom: 0.25rem;
    border-top: 4px solid var(--g-color);
  }
  .group-label {
    font-size: 11px; font-weight: 700; letter-spacing: 2px;
    text-transform: uppercase; color: var(--g-color); margin-bottom: 4px;
  }
  .group-countries { font-size: 13px; color: #CBD5E1; line-height: 1.8; }

  .country-card {
    background: #1E293B; border-radius: 12px;
    padding: 1.5rem 1rem; text-align: center;
    border-top: 4px solid var(--g-color);
  }
  .country-name-big { font-size: 1.1rem; font-weight: 700; color: white; }
  .country-sub { font-size: 12px; color: #94A3B8; margin-top: 4px; }

  .pos-badge {
    display: inline-block; padding: 3px 10px; border-radius: 999px;
    font-size: 12px; font-weight: 600; color: white; margin-bottom: 6px;
  }
  .info-pill {
    display: inline-block; background: #0F172A; border: 1px solid #334155;
    border-radius: 8px; padding: 4px 12px; font-size: 12px; color: #CBD5E1;
    margin: 3px 4px 3px 0;
  }
  .info-pill span { color: white; font-weight: 600; }

  .stat-box {
    background: #1E293B; border-radius: 10px; padding: 0.8rem;
    text-align: center; border: 1px solid #334155;
  }
  .stat-val { font-size: 1.6rem; font-weight: 800; color: white; line-height: 1; }
  .stat-lbl { font-size: 10px; color: #CBD5E1; margin-top: 4px; text-transform: uppercase; letter-spacing: 1px; }

  .league-row {
    display: flex; align-items: center; gap: 10px;
    background: #1E293B; border-radius: 8px; padding: 8px 12px; margin-bottom: 6px;
  }
  .league-name { font-size: 13px; color: white; font-weight: 600; }
  .league-sub  { font-size: 11px; color: #CBD5E1; }

  .injured-badge {
    display: inline-block; background: #7F1D1D; color: #FCA5A5;
    border-radius: 999px; padding: 3px 10px; font-size: 11px; font-weight: 700;
  }

  .breadcrumb { font-size: 13px; color: #64748B; margin-bottom: 0.5rem; }
  .breadcrumb span { color: #94A3B8; }

  div[data-testid="stButton"] > button { border-radius: 8px; width: 100%; }
</style>
""", unsafe_allow_html=True)

# ── Constants ──────────────────────────────────────────────────────────────────
COUNTRIES_ORDERED = [
    "México",            "Sudáfrica",          "Corea del Sur",  "República Checa",
    "Canadá",            "Bosnia y Herzegovina","Qatar",          "Suiza",
    "Brasil",            "Marruecos",           "Haití",          "Escocia",
    "Estados Unidos",    "Paraguay",            "Australia",      "Turquía",
    "Alemania",          "Curazao",             "Costa de Marfil","Ecuador",
    "Países Bajos",      "Japón",               "Suecia",         "Túnez",
    "Bélgica",           "Egipto",              "Irán",           "Nueva Zelanda",
    "España",            "Cabo Verde",          "Arabia Saudita", "Uruguay",
    "Francia",           "Senegal",             "Irak",           "Noruega",
    "Argentina",         "Argelia",             "Austria",        "Jordania",
    "Portugal",          "RD Congo",            "Uzbekistán",     "Colombia",
    "Inglaterra",        "Croacia",             "Ghana",          "Panamá",
]

GROUP_LETTERS  = list("ABCDEFGHIJKL")
COUNTRY_GROUP  = {c: GROUP_LETTERS[i // 4] for i, c in enumerate(COUNTRIES_ORDERED)}
GROUPS         = {g: [c for c in COUNTRIES_ORDERED if COUNTRY_GROUP[c] == g] for g in GROUP_LETTERS}
GROUP_COLORS   = {
    "A": "#EF4444", "B": "#F97316", "C": "#F59E0B", "D": "#EAB308",
    "E": "#84CC16", "F": "#22C55E", "G": "#14B8A6", "H": "#06B6D4",
    "I": "#3B82F6", "J": "#6366F1", "K": "#A855F7", "L": "#EC4899",
}
POSITION_ORDER = ["Goalkeeper", "Defender", "Midfielder", "Forward"]
POSITION_COLOR = {
    "Goalkeeper": "#F59E0B", "Defender": "#10B981",
    "Midfielder": "#3B82F6", "Forward":  "#EF4444",
}
COUNTRY_FLAGS = {
    "México": "🇲🇽", "Sudáfrica": "🇿🇦", "Corea del Sur": "🇰🇷", "República Checa": "🇨🇿",
    "Canadá": "🇨🇦", "Bosnia y Herzegovina": "🇧🇦", "Qatar": "🇶🇦", "Suiza": "🇨🇭",
    "Brasil": "🇧🇷", "Marruecos": "🇲🇦", "Haití": "🇭🇹", "Escocia": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "Estados Unidos": "🇺🇸", "Paraguay": "🇵🇾", "Australia": "🇦🇺", "Turquía": "🇹🇷",
    "Alemania": "🇩🇪", "Curazao": "🇨🇼", "Costa de Marfil": "🇨🇮", "Ecuador": "🇪🇨",
    "Países Bajos": "🇳🇱", "Japón": "🇯🇵", "Suecia": "🇸🇪", "Túnez": "🇹🇳",
    "Bélgica": "🇧🇪", "Egipto": "🇪🇬", "Irán": "🇮🇷", "Nueva Zelanda": "🇳🇿",
    "España": "🇪🇸", "Cabo Verde": "🇨🇻", "Arabia Saudita": "🇸🇦", "Uruguay": "🇺🇾",
    "Francia": "🇫🇷", "Senegal": "🇸🇳", "Irak": "🇮🇶", "Noruega": "🇳🇴",
    "Argentina": "🇦🇷", "Argelia": "🇩🇿", "Austria": "🇦🇹", "Jordania": "🇯🇴",
    "Portugal": "🇵🇹", "RD Congo": "🇨🇩", "Uzbekistán": "🇺🇿", "Colombia": "🇨🇴",
    "Inglaterra": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "Croacia": "🇭🇷", "Ghana": "🇬🇭", "Panamá": "🇵🇦",
}

# ── Data ───────────────────────────────────────────────────────────────────────
EXCLUDED_LEAGUES = {"fifa club world cup", "fifa club world cup - play-in"}

# Leagues/competitions in these countries run on a Jan–Dec calendar, so a
# season tagged "2026" means the 2026 calendar year. Everything else is
# assumed to follow the Aug–May convention, where season "2025" means the
# 2025-26 campaign.
CALENDAR_YEAR_COUNTRIES = {
    "Argentina", "Bolivia", "Brazil", "Chile", "Colombia", "Ecuador",
    "Paraguay", "Peru", "Uruguay", "Venezuela", "Mexico", "USA", "Canada",
    "World",
}

def season_label(block):
    """Human-friendly season label, e.g. '2025' or '2025-26'."""
    season = block.get("_season")
    country = (block.get("league", {}) or {}).get("country", "")
    if country in CALENDAR_YEAR_COUNTRIES:
        return str(season)
    return f"{season}-{str(season + 1)[-2:]}"

def relevant_blocks(player):
    """Combine statistics_2025 + statistics_2026, dropping FIFA Club World Cup blocks."""
    blocks = []
    for season in (2025, 2026):
        for b in (player.get(f"statistics_{season}") or []):
            league_name = (b.get("league", {}) or {}).get("name", "")
            if league_name.strip().lower() in EXCLUDED_LEAGUES:
                continue
            blocks.append({**b, "_season": season})
    return blocks

@st.cache_data(ttl=3600)
def load_data():
    url = "https://raw.githubusercontent.com/los591/g11-data/main/og_backup_pre_inaug.json"
    resp = requests.get(url, headers={"Authorization": f"token {st.secrets['github_token']}"}, timeout=30)
    resp.raise_for_status()
    flat = resp.json()

    all_players: dict[str, list] = {}
    for p in flat:
        all_players.setdefault(p["country"], []).append(p)

    for squad in all_players.values():
        squad.sort(key=lambda x: (
            POSITION_ORDER.index(x["position"]) if x["position"] in POSITION_ORDER else 99,
            x["player"],
        ))
    return all_players

all_players = load_data()

# Maps internal (Spanish) country keys -> English display names for the UI.
COUNTRY_DISPLAY = {
    country: squad[0].get("country_for_app", country)
    for country, squad in all_players.items() if squad
}


@st.cache_data(ttl=3600)
def load_fixtures():
    url = "https://raw.githubusercontent.com/los591/g11-data/main/wc_fixtures.json"
    try:
        resp = requests.get(url, headers={"Authorization": f"token {st.secrets['github_token']}"}, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []

wc_fixtures = load_fixtures()

# ── Search index ───────────────────────────────────────────────────────────────
def normalize(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower()

@st.cache_data
def build_search_index():
    index = []
    for country, squad in all_players.items():
        for idx, p in enumerate(squad):
            index.append({
                "country":  country,
                "idx":      idx,
                "player":   p["player"],
                "club":     p["club"],
                "position": p["position"],
                "group":    COUNTRY_GROUP.get(country, "?"),
                "photo":    (p.get("player_info") or {}).get("photo") or p.get("player_photo", ""),
                "norm":     normalize(p["player"]),
                "club_norm": normalize(p["club"]),
            })
    return index

SEARCH_INDEX = build_search_index()


@st.cache_data(ttl=3600)
def compute_standings():
    """Derive group standings from wc_match_performances data."""
    team_stats = {}
    for country, squad in all_players.items():
        if not squad:
            continue
        tid = squad[0].get("country_id")
        if tid:
            team_stats[tid] = {
                "name":    COUNTRY_DISPLAY.get(country, country),
                "country": country,
                "group":   COUNTRY_GROUP.get(country, "?"),
                "P": 0, "W": 0, "D": 0, "L": 0,
                "GF": 0, "GA": 0, "GD": 0, "Pts": 0,
            }

    fixture_goals = {}  # {fixture_id: {team_id: total_goals}}
    for squad in all_players.values():
        for player in squad:
            for perf in player.get("wc_match_performances") or []:
                fid = perf["fixture_id"]
                tid = perf["team_id"]
                goals = (perf.get("goals") or {}).get("total") or 0
                fixture_goals.setdefault(fid, {}).setdefault(tid, 0)
                fixture_goals[fid][tid] += goals

    for fid, teams in fixture_goals.items():
        tids = [t for t in teams if t in team_stats]
        if len(tids) != 2:
            continue
        t1, t2 = tids[0], tids[1]
        g1, g2 = teams[t1], teams[t2]
        for tid in (t1, t2):
            team_stats[tid]["P"] += 1
        team_stats[t1]["GF"] += g1
        team_stats[t1]["GA"] += g2
        team_stats[t2]["GF"] += g2
        team_stats[t2]["GA"] += g1
        if g1 > g2:
            team_stats[t1]["W"] += 1
            team_stats[t1]["Pts"] += 3
            team_stats[t2]["L"] += 1
        elif g2 > g1:
            team_stats[t2]["W"] += 1
            team_stats[t2]["Pts"] += 3
            team_stats[t1]["L"] += 1
        else:
            team_stats[t1]["D"] += 1
            team_stats[t1]["Pts"] += 1
            team_stats[t2]["D"] += 1
            team_stats[t2]["Pts"] += 1

    for t in team_stats.values():
        t["GD"] = t["GF"] - t["GA"]
    return team_stats


@st.cache_data(ttl=3600)
def build_leaderboard():
    """Flat list of all players who have played at least 1 WC minute."""
    rows = []
    for country, squad in all_players.items():
        for idx, player in enumerate(squad):
            agg = player.get("wc_aggregates") or {}
            minutes = (agg.get("games") or {}).get("minutes") or 0
            if not minutes:
                continue
            games   = agg.get("games") or {}
            goals_d = agg.get("goals") or {}
            cards   = agg.get("cards") or {}
            rating  = games.get("rating")
            try:
                rating = float(rating) if rating is not None else None
            except (TypeError, ValueError):
                rating = None
            rows.append({
                "player":      player["player"],
                "country":     country,
                "idx":         idx,
                "position":    player.get("position", ""),
                "photo":       (player.get("player_info") or {}).get("photo") or player.get("player_photo", ""),
                "minutes":     minutes,
                "goals":       goals_d.get("total") or 0,
                "assists":     goals_d.get("assists") or 0,
                "saves":       goals_d.get("saves") or 0,
                "rating":      rating,
                "yellow":      cards.get("yellow") or 0,
                "red":         cards.get("red") or 0,
                "offsides":    agg.get("offsides") or 0,
            })
    return rows


# ── Stat helpers ───────────────────────────────────────────────────────────────
def _sum(blocks, *keys):
    """Sum a nested key path across all stat blocks, ignoring None."""
    total = 0
    for b in blocks:
        val = b
        for k in keys:
            val = (val or {}).get(k)
        total += val or 0
    return total

def _avg_rating(blocks):
    ratings, apps = [], []
    for b in blocks:
        try:
            r = float(b.get("games", {}).get("rating") or 0)
            a = int(b.get("games", {}).get("appearences") or 0)
            if r and a:
                ratings.append(r * a)
                apps.append(a)
        except (ValueError, TypeError):
            pass
    if not apps:
        return None
    return sum(ratings) / sum(apps)

def aggregate(blocks):
    """Return a flat dict of aggregated stats across all league blocks."""
    if not blocks:
        return {}
    return {
        "appearances":    _sum(blocks, "games", "appearences"),
        "minutes":        _sum(blocks, "games", "minutes"),
        "rating":         _avg_rating(blocks),
        "goals":          _sum(blocks, "goals", "total"),
        "assists":        _sum(blocks, "goals", "assists"),
        "saves":          _sum(blocks, "goals", "saves"),
        "conceded":       _sum(blocks, "goals", "conceded"),
        "shots":          _sum(blocks, "shots", "total"),
        "shots_on":       _sum(blocks, "shots", "on"),
        "passes":         _sum(blocks, "passes", "total"),
        "key_passes":     _sum(blocks, "passes", "key"),
        "tackles":        _sum(blocks, "tackles", "total"),
        "interceptions":  _sum(blocks, "tackles", "interceptions"),
        "blocks":         _sum(blocks, "tackles", "blocks"),
        "duels_total":    _sum(blocks, "duels", "total"),
        "duels_won":      _sum(blocks, "duels", "won"),
        "dribbles_att":   _sum(blocks, "dribbles", "attempts"),
        "dribbles_ok":    _sum(blocks, "dribbles", "success"),
        "fouls_drawn":    _sum(blocks, "fouls", "drawn"),
        "fouls_comm":     _sum(blocks, "fouls", "committed"),
        "yellow":         _sum(blocks, "cards", "yellow"),
        "red":            _sum(blocks, "cards", "red"),
        "pen_scored":     _sum(blocks, "penalty", "scored"),
        "pen_missed":     _sum(blocks, "penalty", "missed"),
        "pen_saved":      _sum(blocks, "penalty", "saved"),
    }

def flatten_wc_aggregate(agg):
    """Flatten a player's wc_aggregates block into the same flat-stat shape
    produced by aggregate(), so it can be rendered with the same stat_box helpers."""
    if not agg:
        return {}
    games    = agg.get("games", {}) or {}
    goals    = agg.get("goals", {}) or {}
    shots    = agg.get("shots", {}) or {}
    passes   = agg.get("passes", {}) or {}
    tackles  = agg.get("tackles", {}) or {}
    duels    = agg.get("duels", {}) or {}
    dribbles = agg.get("dribbles", {}) or {}
    fouls    = agg.get("fouls", {}) or {}
    cards    = agg.get("cards", {}) or {}
    penalty  = agg.get("penalty", {}) or {}
    rating   = games.get("rating")
    try:
        rating = float(rating) if rating is not None else None
    except (TypeError, ValueError):
        rating = None
    return {
        "appearances":   agg.get("appearances") or 0,
        "minutes":       games.get("minutes") or 0,
        "rating":        rating,
        "goals":         goals.get("total") or 0,
        "assists":       goals.get("assists") or 0,
        "saves":         goals.get("saves") or 0,
        "conceded":      goals.get("conceded") or 0,
        "shots":         shots.get("total") or 0,
        "shots_on":      shots.get("on") or 0,
        "passes":        passes.get("total") or 0,
        "key_passes":    passes.get("key") or 0,
        "pass_accuracy": passes.get("accuracy"),
        "tackles":       tackles.get("total") or 0,
        "interceptions": tackles.get("interceptions") or 0,
        "blocks":        tackles.get("blocks") or 0,
        "duels_total":   duels.get("total") or 0,
        "duels_won":     duels.get("won") or 0,
        "dribbles_att":  dribbles.get("attempts") or 0,
        "dribbles_ok":   dribbles.get("success") or 0,
        "fouls_drawn":   fouls.get("drawn") or 0,
        "fouls_comm":    fouls.get("committed") or 0,
        "yellow":        cards.get("yellow") or 0,
        "red":           cards.get("red") or 0,
        "pen_scored":    penalty.get("scored") or 0,
        "pen_missed":    penalty.get("missed") or 0,
        "pen_saved":     penalty.get("saved") or 0,
        "offsides":      agg.get("offsides") or 0,
    }

def wc_match_table_rows(performances):
    """Build one table row per WC fixture a player appeared in, most recent first."""
    rows = []
    for m in sorted(performances, key=lambda x: x.get("date", ""), reverse=True):
        games   = m.get("games", {}) or {}
        goals   = m.get("goals", {}) or {}
        shots   = m.get("shots", {}) or {}
        passes  = m.get("passes", {}) or {}
        tackles = m.get("tackles", {}) or {}
        duels   = m.get("duels", {}) or {}
        cards   = m.get("cards", {}) or {}

        rating = games.get("rating")
        try:
            rating = float(rating) if rating is not None else None
        except (TypeError, ValueError):
            rating = None

        accuracy = passes.get("accuracy")
        accuracy_str = f"{accuracy:.0f}%" if isinstance(accuracy, (int, float)) else "—"

        rows.append({
            "Date":      m.get("date", "—"),
            "Opponent":  m.get("opponent", "—"),
            "Min":       games.get("minutes") or 0,
            "Rating":    rating,
            "Goals":     goals.get("total") or 0,
            "Assists":   goals.get("assists") or 0,
            "Shots":     shots.get("total") or 0,
            "On Target": shots.get("on") or 0,
            "Passes":    passes.get("total") or 0,
            "Pass Acc.": accuracy_str,
            "Tackles":   tackles.get("total") or 0,
            "Duels Won": duels.get("won") or 0,
            "Yellow":    cards.get("yellow") or 0,
            "Red":       cards.get("red") or 0,
        })
    return rows

def fmt(val, decimals=0, suffix=""):
    if val is None:
        return "—"
    if decimals:
        return f"{val:.{decimals}f}{suffix}"
    return f"{int(val)}{suffix}"

def pct(num, den):
    if not den:
        return "—"
    return f"{num/den*100:.0f}%"

def stat_box(val, label):
    return (
        f"<div class='stat-box'>"
        f"  <div class='stat-val'>{val}</div>"
        f"  <div class='stat-lbl'>{label}</div>"
        f"</div>"
    )

# ── Navigation ─────────────────────────────────────────────────────────────────
def go_home():
    st.session_state.view = "home"
    st.session_state.selected_group = st.session_state.selected_country = None
    st.session_state.selected_player = 0

def go_group(g):
    st.session_state.view = "group"
    st.session_state.selected_group = g
    st.session_state.selected_country = None
    st.session_state.selected_player = 0

def go_country(c):
    st.session_state.view = "country"
    st.session_state.selected_country = c
    st.session_state.selected_player = 0

def go_player(country, idx):
    st.session_state.view = "country"
    st.session_state.selected_country = country
    st.session_state.selected_player = idx

def go_standings():
    st.session_state.view = "standings"
    st.session_state.selected_group = st.session_state.selected_country = None
    st.session_state.selected_player = 0

def go_calendar():
    st.session_state.view = "calendar"
    st.session_state.selected_group = st.session_state.selected_country = None
    st.session_state.selected_player = 0

def go_compare():
    st.session_state.view = "compare"
    st.session_state.selected_group = st.session_state.selected_country = None
    st.session_state.selected_player = 0

# ── Banner ─────────────────────────────────────────────────────────────────────
def render_banner():
    st.markdown("""
    <div style="position:relative; background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 60%,#0f3460 100%);
                padding:2rem 2.5rem; border-radius:16px; text-align:center;
                margin-bottom:1.5rem; border:1px solid #1e40af;">
      <div style="position:absolute; top:16px; left:18px; display:flex;
                  align-items:center; gap:10px; z-index:2;">
        <div style="width:56px; height:64px;
                    background:linear-gradient(160deg,#1e3a8a 0%,#0f172a 75%);
                    clip-path:polygon(50% 0%,100% 18%,100% 68%,50% 100%,0% 68%,0% 18%);
                    border:2px solid #FBBF24;
                    display:flex; flex-direction:column; align-items:center;
                    justify-content:center; gap:2px;
                    box-shadow:0 0 18px rgba(251,191,36,0.5);">
          <span style="font-size:1.2rem; line-height:1;">⚽</span>
          <span style="font-weight:900; font-size:0.85rem; color:#FBBF24;
                      letter-spacing:1px; line-height:1;">G11</span>
        </div>
        <div style="text-align:left;">
          <div style="font-size:1rem; font-weight:900; letter-spacing:5px;
                      color:white; line-height:1.1;">G11</div>
          <div style="font-size:0.55rem; font-weight:700; letter-spacing:2px;
                      color:#93C5FD; text-transform:uppercase;">Sports Intel</div>
        </div>
      </div>
      <div style="font-size:3rem; line-height:1;">⚽</div>
      <div style="font-size:1rem; font-weight:700; letter-spacing:6px;
                  color:#93C5FD; text-transform:uppercase; margin-top:0.5rem;">FIFA</div>
      <div style="font-size:2.4rem; font-weight:900; color:white;
                  letter-spacing:2px; line-height:1.1;">WORLD CUP</div>
      <div style="font-size:2.8rem; font-weight:900;
                  background:linear-gradient(90deg,#EF4444,#F97316,#F59E0B,#22C55E,#3B82F6,#A855F7);
                  -webkit-background-clip:text; -webkit-text-fill-color:transparent;
                  letter-spacing:4px;">2026</div>
      <div style="font-size:0.85rem; color:#64748B; margin-top:0.4rem;
                  letter-spacing:3px;">USA &nbsp;·&nbsp; CANADA &nbsp;·&nbsp; MÉXICO</div>
    </div>
    """, unsafe_allow_html=True)

# ── Leaderboard row helper ─────────────────────────────────────────────────────
def _lb_section(rows, stat_key, stat_label, decimals=0, extra_key=None, extra_label=None, top_n=25):
    filtered = [r for r in rows if (r.get(stat_key) or 0) > 0]
    if not filtered:
        st.info("No data yet — check back after matches are played.")
        return
    for i, row in enumerate(filtered[:top_n]):
        photo_col, info_col, stat_col, btn_col = st.columns([0.55, 4.5, 1.2, 1.4])
        with photo_col:
            rank_html = f"<div style='font-size:11px;color:#64748B;text-align:center;margin-bottom:2px'>{i + 1}</div>"
            if row["photo"]:
                st.markdown(
                    rank_html +
                    f"<img src='{row['photo']}' style='width:36px;height:36px;"
                    "border-radius:6px;object-fit:cover;display:block;margin:0 auto'>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    rank_html +
                    "<div style='width:36px;height:36px;background:#0F172A;"
                    "border-radius:6px;display:flex;align-items:center;justify-content:center;"
                    "font-size:18px;margin:0 auto'>👤</div>",
                    unsafe_allow_html=True,
                )
        with info_col:
            flag = COUNTRY_FLAGS.get(row["country"], "")
            country_disp = COUNTRY_DISPLAY.get(row["country"], row["country"])
            st.markdown(
                f"**{row['player']}**<br>"
                f"<span class='info-pill'>{flag} {country_disp}</span> "
                f"<span class='info-pill'>{row['position']}</span>",
                unsafe_allow_html=True,
            )
        with stat_col:
            val = row.get(stat_key)
            disp = (
                f"{val:.{decimals}f}" if decimals and val is not None
                else str(int(val)) if val is not None else "—"
            )
            extra_html = ""
            if extra_key:
                ev = row.get(extra_key) or 0
                if ev:
                    extra_html = (
                        f"<div style='font-size:11px;color:#FCA5A5;margin-top:4px'>"
                        f"{int(ev)} {extra_label}</div>"
                    )
            st.markdown(
                f"<div class='stat-box'>"
                f"  <div class='stat-val'>{disp}</div>"
                f"  <div class='stat-lbl'>{stat_label}</div>"
                f"  {extra_html}"
                f"</div>",
                unsafe_allow_html=True,
            )
        with btn_col:
            if st.button("View →", key=f"lb_{stat_key}_{i}_{row['country']}_{row['idx']}"):
                go_player(row["country"], row["idx"])
                st.rerun()


# ── VIEW: STANDINGS ────────────────────────────────────────────────────────────
def render_standings():
    render_banner()

    back_col, _ = st.columns([1, 9])
    with back_col:
        if st.button("← Home"):
            go_home(); st.rerun()

    st.markdown("<h2 style='margin:0.5rem 0 1rem 0'>📊 Standings & Leaderboards</h2>",
                unsafe_allow_html=True)

    tab_st, tab_lb = st.tabs(["📊 Group Standings", "🏆 Leaderboards"])

    with tab_st:
        standings = compute_standings()
        st.caption(
            "Standings are derived from player goal tallies and may differ slightly "
            "from official scores when own goals are involved. "
            "Top 2 from each group qualify automatically; best 8 third-place teams also advance."
        )
        st.markdown("")
        for row_start in range(0, 12, 3):
            cols = st.columns(3, gap="medium")
            for ci, g in enumerate(GROUP_LETTERS[row_start:row_start + 3]):
                color = GROUP_COLORS[g]
                group_teams = sorted(
                    [t for t in standings.values() if t["group"] == g],
                    key=lambda x: (-x["Pts"], -x["GD"], -x["GF"]),
                )
                table_rows = []
                for t in group_teams:
                    flag = COUNTRY_FLAGS.get(t["country"], "")
                    gd = t["GD"]
                    gd_str = f"+{gd}" if gd > 0 else str(gd)
                    table_rows.append({
                        "Team": f"{flag} {t['name']}",
                        "P":    t["P"],
                        "Pts":  t["Pts"],
                        "GD":   gd_str,
                        "W":    t["W"],
                        "D":    t["D"],
                        "L":    t["L"],
                        "GF":   t["GF"],
                        "GA":   t["GA"],
                    })
                with cols[ci]:
                    st.markdown(
                        f"<div style='color:{color};font-weight:800;font-size:0.95rem;"
                        f"letter-spacing:2px;margin-bottom:6px;text-transform:uppercase'>"
                        f"Group {g}</div>",
                        unsafe_allow_html=True,
                    )
                    st.dataframe(
                        table_rows,
                        use_container_width=True,
                        hide_index=True,
                        height=175,
                        column_config={
                            "Team": st.column_config.TextColumn(width="medium"),
                            "P":    st.column_config.NumberColumn(width="small"),
                            "W":    st.column_config.NumberColumn(width="small"),
                            "D":    st.column_config.NumberColumn(width="small"),
                            "L":    st.column_config.NumberColumn(width="small"),
                            "GF":   st.column_config.NumberColumn(width="small"),
                            "GA":   st.column_config.NumberColumn(width="small"),
                            "GD":   st.column_config.TextColumn(width="small"),
                            "Pts":  st.column_config.NumberColumn(width="small"),
                        },
                    )
            st.markdown("")

    with tab_lb:
        lb = build_leaderboard()
        t_goals, t_assists, t_mins, t_rating, t_yellow, t_red, t_offsides, t_saves = st.tabs([
            "⚽ Goals", "🅰️ Assists", "⏱️ Minutes", "⭐ Rating",
            "🟨 Yellow Cards", "🟥 Red Cards", "🚩 Offsides", "🧤 Saves (GK)",
        ])
        with t_goals:
            _lb_section(sorted(lb, key=lambda x: (-x["goals"], -x["assists"])), "goals", "Goals")
        with t_assists:
            _lb_section(sorted(lb, key=lambda x: (-x["assists"], -x["goals"])), "assists", "Assists")
        with t_mins:
            _lb_section(sorted(lb, key=lambda x: -x["minutes"]), "minutes", "Minutes")
        with t_rating:
            rated = [r for r in lb if r["rating"] is not None]
            _lb_section(sorted(rated, key=lambda x: -x["rating"]), "rating", "Avg Rating", decimals=2)
        with t_yellow:
            _lb_section(sorted(lb, key=lambda x: (-x["yellow"], -x["minutes"])), "yellow", "🟨 Yellow Cards")
        with t_red:
            _lb_section(sorted(lb, key=lambda x: (-x["red"], -x["minutes"])), "red", "🟥 Red Cards")
        with t_offsides:
            _lb_section(sorted(lb, key=lambda x: -x["offsides"]), "offsides", "Offsides")
        with t_saves:
            gks = [r for r in lb if r["position"] == "Goalkeeper"]
            _lb_section(sorted(gks, key=lambda x: -x["saves"]), "saves", "Saves")


# ── Match card helper ──────────────────────────────────────────────────────────
_PLAYED = {"FT", "AET", "PEN"}

# Display label → IANA timezone name
TIMEZONES = {
    "UTC":               "UTC",
    "ET  — New York / Miami":        "America/New_York",
    "CT  — Chicago / Mexico City":   "America/Chicago",
    "MT  — Denver / Calgary":        "America/Denver",
    "PT  — Los Angeles / Vancouver": "America/Los_Angeles",
    "BRT — São Paulo / Buenos Aires":"America/Sao_Paulo",
    "GMT — London / Lisbon":         "Europe/London",
    "CET — Paris / Madrid / Rome":   "Europe/Paris",
    "EET — Cairo / Istanbul":        "Europe/Istanbul",
    "GST — Dubai / Riyadh":          "Asia/Dubai",
    "PKT — Karachi":                 "Asia/Karachi",
    "IST — Mumbai / Delhi":          "Asia/Kolkata",
    "WIB — Jakarta":                 "Asia/Jakarta",
    "CST — Beijing / Seoul":         "Asia/Shanghai",
    "JST — Tokyo":                   "Asia/Tokyo",
    "AEST— Sydney / Melbourne":      "Australia/Sydney",
}

def _render_match_card(fixture, team_id_to_group):
    played    = fixture["status"] in _PLAYED
    group     = team_id_to_group.get(fixture["home_team_id"], "?")
    color     = GROUP_COLORS.get(group, "#3B82F6")
    home_name = fixture.get("home_team", "")
    away_name = fixture.get("away_team", "")
    home_logo = fixture.get("home_logo", "")
    away_logo = fixture.get("away_logo", "")

    # Wrap team names in country deep-links when available
    link_style = "color:inherit;text-decoration:underline;text-decoration-style:dotted;text-underline-offset:3px"
    home_key = fixture.get("_home_country_key")
    away_key = fixture.get("_away_country_key")
    if home_key:
        home_name = f"<a href='?country={quote(home_key)}' target='_self' style='{link_style}'>{home_name}</a>"
    if away_key:
        away_name = f"<a href='?country={quote(away_key)}' target='_self' style='{link_style}'>{away_name}</a>"

    home_img = (
        f"<img src='{home_logo}' style='width:28px;height:28px;object-fit:contain;vertical-align:middle'>"
        if home_logo else "🏟️"
    )
    away_img = (
        f"<img src='{away_logo}' style='width:28px;height:28px;object-fit:contain;vertical-align:middle'>"
        if away_logo else "🏟️"
    )

    if played:
        hg = fixture.get("home_goals") or 0
        ag = fixture.get("away_goals") or 0
        if hg > ag:
            h_style, a_style = "font-weight:900;color:white", "color:#64748B"
        elif ag > hg:
            h_style, a_style = "color:#64748B", "font-weight:900;color:white"
        else:
            h_style = a_style = "font-weight:700;color:white"
        mid_html = (
            f"<span style='font-size:1.25rem;font-weight:900;color:white'>{hg} – {ag}</span><br>"
            f"<span style='font-size:10px;color:#64748B;letter-spacing:1px'>{fixture['status']}</span>"
        )
    else:
        h_style = a_style = "color:#94A3B8"
        time_str = fixture.get("_local_time") or fixture.get("time", "")
        tz_label = fixture.get("_tz_abbr", "UTC")
        mid_html = (
            f"<span style='font-size:0.95rem;color:#475569;font-weight:600'>vs</span><br>"
            + (f"<span style='font-size:10px;color:#64748B'>{time_str} {tz_label}</span>" if time_str else "")
        )

    round_label = fixture.get("round", "")
    round_pill  = (
        f"<span style='font-size:10px;color:#64748B;margin-left:8px'>{round_label}</span>"
        if round_label else ""
    )

    st.markdown(
        f"<div style='background:#1E293B;border-radius:10px;padding:10px 14px;"
        f"margin-bottom:6px;border-left:3px solid {color};'>"
        f"  <div style='display:flex;align-items:center;'>"
        f"    <div style='flex:1;display:flex;align-items:center;gap:8px;'>"
        f"      {home_img}"
        f"      <span style='font-size:13px;{h_style}'>{home_name}</span>"
        f"    </div>"
        f"    <div style='text-align:center;min-width:90px;'>{mid_html}</div>"
        f"    <div style='flex:1;display:flex;align-items:center;gap:8px;justify-content:flex-end;'>"
        f"      <span style='font-size:13px;{a_style}'>{away_name}</span>"
        f"      {away_img}"
        f"    </div>"
        f"  </div>"
        f"  {round_pill}"
        f"</div>",
        unsafe_allow_html=True,
    )


# ── VIEW: CALENDAR ─────────────────────────────────────────────────────────────
def render_calendar():
    render_banner()

    back_col, _ = st.columns([1, 9])
    with back_col:
        if st.button("← Home"):
            go_home(); st.rerun()

    st.markdown("<h2 style='margin:0.5rem 0 1rem 0'>📅 Match Calendar</h2>",
                unsafe_allow_html=True)

    if not wc_fixtures:
        st.info("Match calendar will be available once fixtures are loaded. Check back shortly.")
        return

    # team_id → group letter (for colored left border on cards)
    team_id_to_group = {
        squad[0]["country_id"]: COUNTRY_GROUP.get(country, "?")
        for country, squad in all_players.items()
        if squad and squad[0].get("country_id")
    }
    # team_id → internal country key (Spanish name, used for deep-link navigation)
    team_id_to_country_key = {
        squad[0]["country_id"]: country
        for country, squad in all_players.items()
        if squad and squad[0].get("country_id")
    }

    # Controls row: group filter + timezone selector
    filter_col, tz_col, _ = st.columns([2, 3, 3])
    with filter_col:
        filter_opts = ["All matches"] + [f"Group {g}" for g in GROUP_LETTERS]
        selected_filter = st.selectbox("Filter by group", filter_opts, label_visibility="collapsed")
    with tz_col:
        tz_labels = list(TIMEZONES.keys())
        saved_tz  = st.session_state.get("calendar_tz", "UTC")
        saved_idx = tz_labels.index(saved_tz) if saved_tz in tz_labels else 0
        selected_tz_label = st.selectbox(
            "Timezone", tz_labels, index=saved_idx, label_visibility="collapsed"
        )
        st.session_state["calendar_tz"] = selected_tz_label

    tz = ZoneInfo(TIMEZONES[selected_tz_label])
    tz_abbr = selected_tz_label.split("—")[0].strip()

    if selected_filter == "All matches":
        shown = wc_fixtures
    else:
        target_group = selected_filter.replace("Group ", "")
        shown = [
            f for f in wc_fixtures
            if team_id_to_group.get(f["home_team_id"]) == target_group
            or team_id_to_group.get(f["away_team_id"]) == target_group
        ]

    if not shown:
        st.info("No matches found for this filter.")
        return

    # Convert each fixture to local time and group by local date
    def _localise(f):
        date_s, time_s = f.get("date", ""), f.get("time", "")
        extra = {
            "_home_country_key": team_id_to_country_key.get(f.get("home_team_id")),
            "_away_country_key": team_id_to_country_key.get(f.get("away_team_id")),
            "_tz_abbr": tz_abbr,
        }
        if date_s and time_s:
            try:
                utc_dt = datetime.strptime(f"{date_s} {time_s}", "%Y-%m-%d %H:%M").replace(
                    tzinfo=timezone.utc
                )
                local_dt = utc_dt.astimezone(tz)
                return {**f, **extra,
                        "_local_date": local_dt.strftime("%Y-%m-%d"),
                        "_local_time": local_dt.strftime("%H:%M")}
            except ValueError:
                pass
        return {**f, **extra, "_local_date": date_s, "_local_time": time_s}

    localised = [_localise(f) for f in shown]

    by_date: dict[str, list] = {}
    for f in localised:
        by_date.setdefault(f["_local_date"], []).append(f)

    for date in sorted(by_date.keys()):
        try:
            dt = datetime.strptime(date, "%Y-%m-%d")
            date_label = dt.strftime(f"%A, %B {dt.day}")
        except ValueError:
            date_label = date

        st.markdown(
            f"<div style='font-size:0.8rem;font-weight:700;letter-spacing:2px;color:#64748B;"
            f"text-transform:uppercase;margin:1.2rem 0 0.5rem 0'>{date_label}</div>",
            unsafe_allow_html=True,
        )
        for fixture in sorted(by_date[date], key=lambda x: x.get("_local_time", "")):
            _render_match_card(fixture, team_id_to_group)


# ── Player picker helper ───────────────────────────────────────────────────────
def _render_player_picker(slot):
    key_ref = f"compare_p{slot}"
    ref     = st.session_state.get(key_ref)

    st.markdown(
        f"<div style='font-size:11px;font-weight:700;color:#94A3B8;letter-spacing:2px;"
        f"text-transform:uppercase;margin-bottom:8px'>Player {slot}</div>",
        unsafe_allow_html=True,
    )

    if ref:
        player    = all_players[ref["country"]][ref["idx"]]
        photo_url = (player.get("player_info") or {}).get("photo") or player.get("player_photo", "")
        flag      = COUNTRY_FLAGS.get(ref["country"], "")
        country_d = COUNTRY_DISPLAY.get(ref["country"], ref["country"])
        pos_color = POSITION_COLOR.get(player["position"], "#6B7280")

        ph_col, info_col, btn_col = st.columns([1, 5, 1])
        with ph_col:
            if photo_url:
                st.image(photo_url, width=56)
            else:
                st.markdown(
                    "<div style='width:56px;height:56px;background:#0F172A;border-radius:8px;"
                    "display:flex;align-items:center;justify-content:center;font-size:24px'>👤</div>",
                    unsafe_allow_html=True,
                )
        with info_col:
            st.markdown(
                f"**{player['player']}**<br>"
                f"<span class='info-pill' style='background:{pos_color};color:white;border:none'>"
                f"{player['position']}</span> "
                f"<span class='info-pill'>{flag} {country_d}</span> "
                f"<span class='info-pill'>🏟️ {player['club']}</span>",
                unsafe_allow_html=True,
            )
        with btn_col:
            if st.button("✕", key=f"clear_p{slot}", help="Clear selection"):
                st.session_state[key_ref] = None
                if f"cmp_q{slot}" in st.session_state:
                    st.session_state[f"cmp_q{slot}"] = ""
                st.rerun()
    else:
        q = st.text_input(
            f"Search player {slot}",
            key=f"cmp_q{slot}",
            placeholder="Name or club...",
            label_visibility="collapsed",
        )
        if q.strip():
            qn   = normalize(q.strip())
            hits = [r for r in SEARCH_INDEX if qn in r["norm"] or qn in r["club_norm"]][:25]
            if not hits:
                st.caption("No players found.")
            for r in hits:
                r_flag  = COUNTRY_FLAGS.get(r["country"], "")
                r_cdisp = COUNTRY_DISPLAY.get(r["country"], r["country"])
                if st.button(
                    f"{r['player']}  ·  {r_flag} {r_cdisp}  ·  {r['position']}",
                    key=f"pick_p{slot}_{r['country']}_{r['idx']}",
                    use_container_width=True,
                ):
                    st.session_state[key_ref] = {"country": r["country"], "idx": r["idx"]}
                    st.rerun()


# ── Comparison stat row helper ─────────────────────────────────────────────────
def _cmp_stat_row(disp1, label, disp2, raw1=None, raw2=None):
    """P1 stat box | centered label | P2 stat box. Higher value gets green border."""
    border1 = border2 = ""
    try:
        if raw1 is not None and raw2 is not None:
            if float(raw1) > float(raw2):
                border1 = "border:2px solid #22C55E;"
            elif float(raw2) > float(raw1):
                border2 = "border:2px solid #22C55E;"
    except (TypeError, ValueError):
        pass
    c1, clabel, c2 = st.columns([3, 2, 3])
    c1.markdown(
        f"<div class='stat-box' style='{border1}'><div class='stat-val'>{disp1}</div></div>",
        unsafe_allow_html=True,
    )
    clabel.markdown(
        f"<div style='text-align:center;padding-top:1.1rem;font-size:10px;color:#94A3B8;"
        f"text-transform:uppercase;letter-spacing:1px;font-weight:700'>{label}</div>",
        unsafe_allow_html=True,
    )
    c2.markdown(
        f"<div class='stat-box' style='{border2}'><div class='stat-val'>{disp2}</div></div>",
        unsafe_allow_html=True,
    )


def _render_wc_comparison(p1, p2):
    wc1  = flatten_wc_aggregate(p1.get("wc_aggregates") or {})
    wc2  = flatten_wc_aggregate(p2.get("wc_aggregates") or {})
    pos1 = p1.get("position", "")
    pos2 = p2.get("position", "")

    if not wc1 and not wc2:
        st.info("Neither player has WC match data yet — check back after matches are played.")
        return

    def _r(label, key, decimals=0):
        v1 = wc1.get(key)
        v2 = wc2.get(key)
        d1 = fmt(v1, decimals) if v1 is not None else "—"
        d2 = fmt(v2, decimals) if v2 is not None else "—"
        _cmp_stat_row(d1, label, d2, v1, v2)

    nc1, _, nc2 = st.columns([3, 2, 3])
    nc1.markdown(
        f"<div style='text-align:center;font-size:13px;font-weight:700;color:#93C5FD;"
        f"margin-bottom:4px'>{COUNTRY_FLAGS.get(p1.get('country',''),'')}"
        f" {p1['player']}</div>",
        unsafe_allow_html=True,
    )
    nc2.markdown(
        f"<div style='text-align:center;font-size:13px;font-weight:700;color:#93C5FD;"
        f"margin-bottom:4px'>{COUNTRY_FLAGS.get(p2.get('country',''),'')}"
        f" {p2['player']}</div>",
        unsafe_allow_html=True,
    )
    st.caption("🟢 Green border = higher value")
    st.markdown("")

    _r("Minutes", "minutes")
    _r("Avg Rating",  "rating", decimals=2)
    st.markdown("")

    _r("Goals",   "goals")
    _r("Assists", "assists")
    if pos1 == "Goalkeeper" or pos2 == "Goalkeeper":
        _r("Saves",          "saves")
        _r("Goals Conceded", "conceded")
    else:
        _r("Shots",      "shots")
        _r("Key Passes", "key_passes")
    st.markdown("")

    _r("Tackles",       "tackles")
    _r("Interceptions", "interceptions")
    st.markdown("")

    _r("Yellow Cards", "yellow")
    _r("Red Cards",    "red")
    _r("Offsides",     "offsides")


def _render_leagues_comparison(p1, p2):
    col1, col2 = st.columns(2, gap="large")

    for col, player in ((col1, p1), (col2, p2)):
        with col:
            flag    = COUNTRY_FLAGS.get(player.get("country", ""), "")
            country = COUNTRY_DISPLAY.get(player.get("country", ""), player.get("country", ""))
            st.markdown(
                f"<div style='font-weight:700;color:white;margin-bottom:8px'>"
                f"{flag} {player['player']}</div>",
                unsafe_allow_html=True,
            )
            blocks = relevant_blocks(player)
            if not blocks:
                st.caption("No 2025/2026 season stats available.")
                continue
            pos = player.get("position", "")
            for b in sorted(
                blocks,
                key=lambda x: (x.get("games", {}).get("appearences") or 0, x.get("_season", 0)),
                reverse=True,
            ):
                games  = b.get("games", {}) or {}
                league = b.get("league", {}) or {}
                team   = b.get("team", {}) or {}
                goals  = b.get("goals", {}) or {}
                apps   = games.get("appearences") or 0
                mins   = games.get("minutes") or 0
                rating = games.get("rating")
                if not apps:
                    continue
                logo_html = (
                    f"<img src='{team.get('logo','')}' style='width:20px;height:20px;"
                    f"object-fit:contain;border-radius:3px'>"
                    if team.get("logo") else "🏟️"
                )
                flag_html = (
                    f"<img src='{league.get('flag','')}' style='width:16px;height:11px;"
                    f"object-fit:cover;border-radius:2px'>"
                    if league.get("flag") else ""
                )
                rating_str = f" · ⭐ {float(rating):.2f}" if rating else ""
                if pos == "Goalkeeper":
                    extra = f" · 🧤 {goals.get('saves') or 0} saves"
                else:
                    extra = (
                        f" · ⚽ {goals.get('total') or 0}"
                        f"  · 🅰️ {goals.get('assists') or 0}"
                    )
                st.markdown(
                    f"<div class='league-row'>"
                    f"  {logo_html}"
                    f"  <div style='flex:1'>"
                    f"    <div class='league-name'>{team.get('name','—')}</div>"
                    f"    <div class='league-sub'>{flag_html} {league.get('name','—')} · "
                    f"    {apps} apps · {mins} min{rating_str}{extra}</div>"
                    f"  </div>"
                    f"  <span class='info-pill'>{season_label(b)}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )


# ── VIEW: COMPARE ──────────────────────────────────────────────────────────────
def render_compare():
    render_banner()

    back_col, _ = st.columns([1, 9])
    with back_col:
        if st.button("← Home"):
            go_home(); st.rerun()

    st.markdown("<h2 style='margin:0.5rem 0 1rem 0'>⚔️ Player Comparison</h2>",
                unsafe_allow_html=True)

    pick1, pick2 = st.columns(2, gap="large")
    with pick1:
        _render_player_picker(1)
    with pick2:
        _render_player_picker(2)

    p1_ref = st.session_state.get("compare_p1")
    p2_ref = st.session_state.get("compare_p2")

    if not p1_ref or not p2_ref:
        st.markdown("")
        st.info("Search and select two players above to compare them.")
        return

    p1 = all_players[p1_ref["country"]][p1_ref["idx"]]
    p2 = all_players[p2_ref["country"]][p2_ref["idx"]]

    st.divider()

    tab_wc, tab_leagues = st.tabs(["⚽ World Cup Stats", "🏆 Pre-WC Leagues"])
    with tab_wc:
        _render_wc_comparison(p1, p2)
    with tab_leagues:
        _render_leagues_comparison(p1, p2)


# ── VIEW: HOME ─────────────────────────────────────────────────────────────────
def render_home():
    render_banner()

    _c1, _c2, _c3, _ = st.columns([2, 2, 2, 2])
    with _c1:
        if st.button("📊 Standings & Leaderboards →", use_container_width=True):
            go_standings(); st.rerun()
    with _c2:
        if st.button("📅 Match Calendar →", use_container_width=True):
            go_calendar(); st.rerun()
    with _c3:
        if st.button("⚔️ Compare Players →", use_container_width=True):
            go_compare(); st.rerun()
    st.markdown("")

    query = st.text_input(
        "🔍 Search for a player or club",
        placeholder="e.g. Messi, Mbappé, Pedri, Real Madrid...",
        label_visibility="collapsed",
    )
    if query.strip():
        q = normalize(query.strip())
        results = [r for r in SEARCH_INDEX if q in r["norm"] or q in r["club_norm"]]

        if not results:
            st.info(f"No players found matching \"{query}\".")
        else:
            st.markdown(f"**{len(results)} result{'s' if len(results) != 1 else ''} for \"{query}\"**")
            for r in results[:25]:
                color = GROUP_COLORS.get(r["group"], "#3B82F6")
                pos_color = POSITION_COLOR.get(r["position"], "#6B7280")
                photo_col, info_col, btn_col = st.columns([1, 5, 2])
                profile_link = f"?player={quote(r['country'])}|{r['idx']}"
                with photo_col:
                    if r["photo"]:
                        st.markdown(
                            f"<a href='{profile_link}' target='_self'>"
                            f"<img src='{r['photo']}' style='width:48px;height:48px;"
                            f"border-radius:8px;object-fit:cover;cursor:pointer;display:block'></a>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            f"<a href='{profile_link}' target='_self' style='text-decoration:none'>"
                            "<div style='width:48px;height:48px;background:#0F172A;"
                            "border-radius:8px;display:flex;align-items:center;"
                            "justify-content:center;font-size:22px;cursor:pointer'>👤</div></a>",
                            unsafe_allow_html=True,
                        )
                with info_col:
                    st.markdown(
                        f"**{r['player']}**<br>"
                        f"<span class='info-pill' style='background:{pos_color};color:white;border:none'>{r['position']}</span> "
                        f"<span class='info-pill'>🌍 {COUNTRY_DISPLAY.get(r['country'], r['country'])} · Group {r['group']}</span> "
                        f"<span class='info-pill'>🏟️ {r['club']}</span>",
                        unsafe_allow_html=True,
                    )
                with btn_col:
                    if st.button("View Profile →", key=f"search_{r['country']}_{r['idx']}", use_container_width=True):
                        go_player(r["country"], r["idx"]); st.rerun()
            if len(results) > 25:
                st.caption(f"Showing first 25 of {len(results)} results — refine your search to narrow down.")
        st.divider()

    st.markdown("#### Select a Group")
    for row_start in range(0, 12, 4):
        cols = st.columns(4, gap="small")
        for ci, group in enumerate(GROUP_LETTERS[row_start:row_start + 4]):
            color = GROUP_COLORS[group]
            with cols[ci]:
                st.markdown(
                    f"<div class='group-card' style='--g-color:{color}'>"
                    f"<div class='group-label'>Group {group}</div>"
                    f"<div class='group-countries'>"
                    + "".join(f"<div>{COUNTRY_DISPLAY.get(c, c)}</div>" for c in GROUPS[group])
                    + "</div></div>",
                    unsafe_allow_html=True,
                )
                if st.button(f"Group {group}", key=f"grp_{group}"):
                    go_group(group); st.rerun()

# ── VIEW: GROUP ────────────────────────────────────────────────────────────────
def render_group():
    group = st.session_state.selected_group
    color = GROUP_COLORS[group]
    render_banner()

    back, home, title = st.columns([1, 1, 7])
    with back:
        if st.button("← Groups"): go_home(); st.rerun()
    with home:
        if st.button("🏠 Home"): go_home(); st.rerun()
    with title:
        st.markdown(
            f"<div class='breadcrumb'>Groups › "
            f"<span style='color:{color};font-weight:700'>Group {group}</span></div>",
            unsafe_allow_html=True,
        )
    st.markdown(f"<h2 style='color:{color};margin:0 0 1.2rem 0'>Group {group}</h2>",
                unsafe_allow_html=True)

    cols = st.columns(4, gap="medium")
    for i, country in enumerate(GROUPS[group]):
        squad     = all_players.get(country, [])
        n_photos  = sum(1 for p in squad if p.get("player_photo"))
        with cols[i]:
            st.markdown(
                f"<div class='country-card' style='--g-color:{color}'>"
                f"<div class='country-name-big'>{COUNTRY_DISPLAY.get(country, country)}</div>"
                f"<div class='country-sub'>{len(squad)} players</div>"
                f"<div class='country-sub'>{n_photos} with photo</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
            if st.button("View Squad", key=f"cty_{country}"):
                go_country(country); st.rerun()

# ── Sidebar squad navigator ───────────────────────────────────────────────────
def render_squad_sidebar(squad, sel_idx, country, group, color):
    with st.sidebar:
        if st.button("🏠 Home", key="sb_home", use_container_width=True):
            go_home(); st.rerun()
        st.markdown(
            f"<div style='font-weight:800;font-size:1.05rem;margin-bottom:0.25rem'>"
            f"{COUNTRY_DISPLAY.get(country, country)} <span style='color:{color}'>· Group {group}</span></div>"
            f"<div style='font-size:12px;color:#64748B;margin-bottom:0.75rem'>"
            f"Tap a player to jump to their profile</div>",
            unsafe_allow_html=True,
        )
        for pos_group in POSITION_ORDER:
            group_players = [(i, p) for i, p in enumerate(squad) if p["position"] == pos_group]
            if not group_players:
                continue
            bg = POSITION_COLOR[pos_group]
            st.markdown(
                f"<span style='background:{bg};color:white;padding:2px 10px;"
                f"border-radius:999px;font-size:11px;font-weight:600'>{pos_group}s</span>",
                unsafe_allow_html=True,
            )
            for idx, p in group_players:
                is_sel = idx == sel_idx
                label = ("⭐ " if is_sel else "") + p["player"]
                if st.button(label, key=f"sb_{idx}", use_container_width=True,
                              type="primary" if is_sel else "secondary"):
                    st.session_state.selected_player = idx
                    st.rerun()
        st.markdown("")

# ── VIEW: COUNTRY / SQUAD ──────────────────────────────────────────────────────
def render_country():
    country  = st.session_state.selected_country
    squad    = all_players.get(country, [])
    group    = COUNTRY_GROUP.get(country, "?")
    color    = GROUP_COLORS.get(group, "#3B82F6")
    sel_idx  = min(st.session_state.selected_player, len(squad) - 1)
    player   = squad[sel_idx]

    render_squad_sidebar(squad, sel_idx, country, group, color)

    st.caption("« On desktop, tap a player in the sidebar to jump to their profile.")

    jump_idx = st.selectbox(
        "🔎 Jump to player",
        options=range(len(squad)),
        index=sel_idx,
        format_func=lambda i: f"{squad[i]['position']} — {squad[i]['player']}",
        key=f"jump_{country}_{sel_idx}",
    )
    if jump_idx != sel_idx:
        st.session_state.selected_player = jump_idx
        st.rerun()

    # ── Header / breadcrumb ───────────────────────────────────────────────────
    back, home, cal, title = st.columns([1, 1, 1, 6])
    with back:
        if st.button(f"← Group {group}"):
            go_group(group); st.rerun()
    with home:
        if st.button("🏠 Home"): go_home(); st.rerun()
    with cal:
        if st.button("📅 Calendar"): go_calendar(); st.rerun()
    with title:
        st.markdown(
            f"<div class='breadcrumb'>Groups › "
            f"<span style='color:{color}'>Group {group}</span> › "
            f"<span style='color:white'>{COUNTRY_DISPLAY.get(country, country)}</span></div>",
            unsafe_allow_html=True,
        )
    st.markdown(
        f"<h2 style='margin:0 0 1rem 0'>{COUNTRY_DISPLAY.get(country, country)} "
        f"<span style='font-size:1rem;background:{color};color:white;"
        f"padding:3px 12px;border-radius:999px;font-weight:600;vertical-align:middle'>"
        f"Group {group}</span></h2>",
        unsafe_allow_html=True,
    )

    # ── Player card ───────────────────────────────────────────────────────────
    info   = player.get("player_info") or {}
    blocks = relevant_blocks(player)
    stats  = aggregate(blocks)
    pos    = player["position"]
    pos_color = POSITION_COLOR.get(pos, "#6B7280")

    photo_url = info.get("photo") or player.get("player_photo") or ""
    birth     = info.get("birth", {}) or {}
    injured   = info.get("injured", False)

    photo_col, bio_col = st.columns([1, 3], gap="large")

    with photo_col:
        if photo_url:
            st.image(photo_url, width=190)
        else:
            st.markdown(
                "<div style='width:190px;height:190px;background:#0F172A;"
                "border-radius:12px;display:flex;align-items:center;"
                "justify-content:center;font-size:64px;border:1px solid #1E293B'>👤</div>",
                unsafe_allow_html=True,
            )

    with bio_col:
        injured_badge = " <span class='injured-badge'>⚠ INJURED</span>" if injured else ""
        st.markdown(
            f"<div style='margin-bottom:0.3rem'>"
            f"  <span class='pos-badge' style='background:{pos_color}'>{pos}</span>"
            f"  {injured_badge}"
            f"</div>"
            f"<h2 style='margin:0 0 0.6rem 0'>{player['player']}</h2>",
            unsafe_allow_html=True,
        )

        pills = []
        if birth.get("date"):
            pills.append(f"📅 Born <span>{birth['date']}</span>")
        if birth.get("place"):
            pills.append(f"📍 {birth['place']}, {birth.get('country','')}")
        if info.get("nationality"):
            pills.append(f"🌍 <span>{info['nationality']}</span>")
        if info.get("height"):
            pills.append(f"📏 <span>{info['height']} cm</span>")
        if info.get("weight"):
            pills.append(f"⚖️ <span>{info['weight']} kg</span>")
        pills.append(f"🏟️ <span>{player['club']}</span>")

        st.markdown(
            "".join(f"<span class='info-pill'>{p}</span>" for p in pills),
            unsafe_allow_html=True,
        )

    st.markdown("")

    # ── Stats tabs ────────────────────────────────────────────────────────────
    STATS_NOTE = (
        "ℹ️ Totals combine the 2025-26 season (Aug 2025–May 2026, e.g. European "
        "leagues) and the 2026 season (Jan–Dec, e.g. South American leagues, "
        "MLS, national teams) to date — see the **Leagues** tab for the "
        "breakdown. FIFA Club World Cup appearances are excluded."
    )

    tab_wc, tab_leagues = st.tabs(
        ["🌎 World Cup Performance", "🏆 Pre-WC Leagues"]
    )

    # ── World Cup Performance ────────────────────────────────────────────────
    with tab_wc:
        wc_aggregates = player.get("wc_aggregates") or {}
        wc_matches    = player.get("wc_match_performances") or []

        if not wc_aggregates or not wc_matches:
            st.info("⚽ Player has either not played yet or statistics are coming soon.")
        else:
            wc_stats = flatten_wc_aggregate(wc_aggregates)
            st.caption(f"ℹ️ Live totals across {wc_stats['appearances']} World Cup 2026 match"
                       f"{'es' if wc_stats['appearances'] != 1 else ''} played so far for "
                       f"{wc_aggregates.get('team', player['country'])}.")

            c = st.columns(4)
            c[0].markdown(stat_box(fmt(wc_stats["minutes"]), "Minutes"), unsafe_allow_html=True)
            c[1].markdown(stat_box(fmt(wc_stats["rating"], 2) if wc_stats["rating"] else "—", "Avg Rating"), unsafe_allow_html=True)
            c[2].markdown(stat_box(fmt(wc_stats["goals"]), "Goals"), unsafe_allow_html=True)
            c[3].markdown(stat_box(fmt(wc_stats["assists"]), "Assists"), unsafe_allow_html=True)

            st.markdown("")
            c2 = st.columns(5)
            if pos == "Goalkeeper":
                c2[0].markdown(stat_box(fmt(wc_stats["saves"]), "Saves"), unsafe_allow_html=True)
                c2[1].markdown(stat_box(fmt(wc_stats["conceded"]), "Goals Conceded"), unsafe_allow_html=True)
            else:
                c2[0].markdown(stat_box(fmt(wc_stats["shots"]), "Shots"), unsafe_allow_html=True)
                c2[1].markdown(stat_box(pct(wc_stats["shots_on"], wc_stats["shots"]), "Shot Accuracy"), unsafe_allow_html=True)
            c2[2].markdown(stat_box(fmt(wc_stats["passes"]), "Passes"), unsafe_allow_html=True)
            c2[3].markdown(stat_box(fmt(wc_stats["yellow"]), "Yellow Cards"), unsafe_allow_html=True)
            c2[4].markdown(stat_box(fmt(wc_stats["red"]), "Red Cards"), unsafe_allow_html=True)

            st.markdown("")
            st.markdown("**Match by match**")
            st.dataframe(
                wc_match_table_rows(wc_matches),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Rating": st.column_config.NumberColumn(format="%.1f"),
                },
            )

    with tab_leagues:
        if stats:
            st.markdown("**Season appearances by league (2025 & 2026)**")
            st.caption(
                "ℹ️ Seasons are labeled **2025-26** for leagues that run "
                "Aug–May (e.g. most European leagues), and as a single "
                "year (e.g. **2026**) for leagues that run Jan–Dec "
                "(e.g. South American leagues, MLS, national teams)."
            )
            for b in sorted(
                blocks,
                key=lambda x: (x.get("games", {}).get("appearences") or 0, x.get("_season", 0)),
                reverse=True,
            ):
                games  = b.get("games", {}) or {}
                league = b.get("league", {}) or {}
                team   = b.get("team", {}) or {}
                goals  = b.get("goals", {}) or {}
                apps   = games.get("appearences") or 0
                mins   = games.get("minutes") or 0
                rating = games.get("rating")
                season = b.get("_season")
                if not apps:
                    continue
                team_logo = team.get("logo", "")
                league_flag = league.get("flag", "")
                logo_html = (
                    f"<img src='{team_logo}' style='width:24px;height:24px;"
                    f"object-fit:contain;border-radius:4px'>"
                    if team_logo else "🏟️"
                )
                flag_html = (
                    f"<img src='{league_flag}' style='width:20px;height:14px;"
                    f"object-fit:cover;border-radius:2px'>"
                    if league_flag else ""
                )
                rating_str = f"  ·  ⭐ {float(rating):.2f}" if rating else ""
                season_html = (
                    f"<span class='info-pill' style='margin:0 0 0 8px'>{season_label(b)}</span>"
                    if season else ""
                )
                if pos == "Goalkeeper":
                    saves = goals.get("saves") or 0
                    extra_str = f"  ·  🧤 {saves} saves"
                else:
                    g = goals.get("total") or 0
                    a = goals.get("assists") or 0
                    extra_str = f"  ·  ⚽ {g} goals  ·  🅰️ {a} assists"
                st.markdown(
                    f"<div class='league-row'>"
                    f"  {logo_html}"
                    f"  <div style='flex:1'>"
                    f"    <div class='league-name'>{team.get('name','—')}</div>"
                    f"    <div class='league-sub'>{flag_html} {league.get('name','—')} · "
                    f"    {apps} apps · {mins} min{rating_str}{extra_str}</div>"
                    f"  </div>"
                    f"  {season_html}"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.info("No 2025/2026 season statistics available for this player.")

    st.divider()

    # ── Full squad grid ───────────────────────────────────────────────────────
    st.markdown(f"#### Full Squad — {COUNTRY_DISPLAY.get(country, country)}")
    st.caption("Tap a photo or ▸ to view that player's profile.")
    for pos_group in POSITION_ORDER:
        group_players = [(i, p) for i, p in enumerate(squad) if p["position"] == pos_group]
        if not group_players:
            continue
        bg = POSITION_COLOR[pos_group]
        st.markdown(
            f"<span style='background:{bg};color:white;padding:3px 12px;"
            f"border-radius:999px;font-size:12px;font-weight:600'>{pos_group}s</span>",
            unsafe_allow_html=True,
        )
        cols = st.columns(len(group_players), gap="small")
        for col, (idx, p) in zip(cols, group_players):
            is_sel = idx == sel_idx
            photo  = (p.get("player_info") or {}).get("photo") or p.get("player_photo", "")
            profile_link = f"?player={quote(country)}|{idx}"
            with col:
                if photo:
                    st.markdown(
                        f"<a href='{profile_link}' target='_self'>"
                        f"<img src='{photo}' style='width:100%;aspect-ratio:1;"
                        f"object-fit:cover;border-radius:8px;cursor:pointer;display:block'></a>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f"<a href='{profile_link}' target='_self' style='text-decoration:none'>"
                        "<div style='aspect-ratio:1;background:#0F172A;border-radius:8px;"
                        "display:flex;align-items:center;justify-content:center;"
                        "font-size:28px;cursor:pointer'>👤</div></a>",
                        unsafe_allow_html=True,
                    )
                name_style = "color:#F59E0B;font-weight:700" if is_sel else ""
                st.markdown(
                    f"<p style='font-size:10px;text-align:center;margin:2px 0 0 0;"
                    f"line-height:1.3;{name_style}'>{p['player']}</p>",
                    unsafe_allow_html=True,
                )
                if st.button("▸", key=f"p_{idx}", help=p["player"]):
                    st.session_state.selected_player = idx; st.rerun()
        st.markdown("")

# ── Router ─────────────────────────────────────────────────────────────────────
view = st.session_state.view
if   view == "home":      render_home()
elif view == "group":     render_group()
elif view == "country":   render_country()
elif view == "standings": render_standings()
elif view == "calendar":  render_calendar()
elif view == "compare":   render_compare()

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown(
    "<div style='text-align:center; margin-top:2.5rem; padding:1rem;"
    " border-top:1px solid #1E293B; font-size:12px; color:#64748B;'>"
    "Questions or interested in accessing the underlying data for research? "
    "Email <a href='mailto:codingexperimentscarlos@gmail.com' "
    "style='color:#93C5FD; text-decoration:none;'>"
    "codingexperimentscarlos@gmail.com</a>"
    "</div>",
    unsafe_allow_html=True,
)
