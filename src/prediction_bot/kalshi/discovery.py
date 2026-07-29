"""Esports market discovery and classification.

Identifies likely esports markets from Kalshi market listings,
classifies them by game using keyword matching.

Also detects and filters out multi-event / parlay markets which
bundle many independent outcomes into one contract. These cannot
be matched to a single esports event.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from prediction_bot.data.schema import KalshiMarket

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Multi-event / parlay detection
# ---------------------------------------------------------------------------

# Ticker prefixes for Kalshi multi-event (parlay) and cross-category products.
# These markets bundle multiple independent outcomes; they cannot be matched
# to a single esports event and should be excluded.
MULTI_EVENT_TICKER_PREFIXES = [
    "KXMVESPORTSMULTIGAME",
    "KXMVECROSSCATEGORY",
]

# Markets with many comma-separated sub-outcomes in the title
# are almost certainly multi-event parlays.
MULTI_EVENT_MAX_COMMAS = 2  # > this many commas → flagged as multi-event


def is_multi_event_market(ticker: str, title: str) -> bool:
    """Detect whether a Kalshi market is a multi-event parlay.

    Uses two signals:
    1. Ticker prefix match against known multi-event product families.
    2. Comma count in title — >2 commas strongly suggests a parlay.

    Returns True if the market should be skipped.
    """
    # Check ticker prefix
    for prefix in MULTI_EVENT_TICKER_PREFIXES:
        if ticker.startswith(prefix):
            return True

    # Heuristic: many comma-separated items in title
    return title.count(",") > MULTI_EVENT_MAX_COMMAS


# ---------------------------------------------------------------------------
# Market type classification
# ---------------------------------------------------------------------------

def classify_market_structure(ticker: str, title: str) -> str:
    """Classify the market's structural type.

    Returns one of:
      'simple' — single-outcome market (match winner, etc.)
      'multi-event' — parlay bundling multiple independent outcomes
      'cross-category' — KXMVECROSSCATEGORY product
    """
    if ticker.startswith("KXMVECROSSCATEGORY"):
        return "cross-category"
    if ticker.startswith("KXMVESPORTSMULTIGAME") or title.count(",") > 2:
        return "multi-event"
    return "simple"


# ---------------------------------------------------------------------------
# Keyword-based game classifier
# ---------------------------------------------------------------------------

GAME_KEYWORDS: dict[str, list[str]] = {
    "league-of-legends": [
        "league of legends",
        "league of legend",
        r"\blol\b",
        r"\blck\b",
        r"\blpl\b",
        r"\blec\b",
        r"\blcs\b",
        r"\bworlds\b",
        r"\bmsi\b",
        r"\bt1\b",
        r"\bgen\.?g\b",
        r"\bdplus\b",
        r"\bdk\b",
        r"\bkt rolster\b",
        r"\bhanwha\b",
        r"\bg2\b",
        r"\bfnatic\b",
        r"\bmad lions\b",
        r"\bcloud9\b",
        r"\bteam liquid\b",
        r"\b100 thieves\b",
        r"\bflyquest\b",
    ],
    "cs2": [
        "counter-strike",
        "counter strike",
        r"\bcs2\b",
        r"\bcs:go\b",
        r"\bcsgo\b",
        r"\bnavi\b",
        r"\bfaze\b",
        r"\bg2\b",
        r"\bvitality\b",
        r"\bspirit\b",
        r"\bmouz\b",
        r"\bheroic\b",
        r"\biesf\b",
        r"\biesl\b",
        r"\bblast\b",
        r"\bpgl\b",
        r"\bmajor\b",
        r"\biem\b",
    ],
    "valorant": [
        "valorant",
        r"\bval\b",
        r"\bvct\b",
        r"\bchampions tour\b",
        r"\bsentinels\b",
        r"\bprx\b",
        r"\bpaper rex\b",
        r"\bfnatic\b",
        r"\bloud\b",
        r"\boptic\b",
        r"\bdrx\b",
        r"\bzeta\b",
    ],
    "dota2": [
        "dota 2",
        "dota2",
        r"\bdota\b",
        r"\bthe international\b",
        r"\bti\d",
        r"\bteam spirit\b",
        r"\bog\b",
        r"\bteam liquid\b",
    ],
    "overwatch": [
        "overwatch",
        r"\bowl\b",
        r"\bowcs\b",
        r"\bseoul dynasty\b",
        r"\bdallas fuel\b",
        r"\bshanghai dragons\b",
    ],
    "rainbow-six": [
        "rainbow six",
        "rainbow6",
        r"\br6\b",
        r"\bsiege\b",
    ],
    "rocket-league": [
        "rocket league",
        "rocketleague",
        r"\brlcs\b",
    ],
    "call-of-duty": [
        "call of duty",
        r"\bcod\b",
        r"\bcdl\b",
        r"\boptic\b",
        r"\bfaze\b",
        r"\bthieves\b",
    ],
    "apex-legends": [
        "apex legends",
        "apexlegends",
        r"\balgs\b",
    ],
}

# General esports keywords that indicate an esports market
# but don't pin down a specific game.
ESPORT_KEYWORDS: list[str] = [
    "esports",
    "esport",
    "e-sports",
    "e-sport",
    "gaming",
    "match winner",
    "series winner",
    "championship",
    "tournament",
    r"\bbo1\b",
    r"\bbo3\b",
    r"\bbo5\b",
    r"\bmap\s+\d",
    r"\bgame\s+\d",
    "best of",
    "grand final",
    "lower bracket",
    "upper bracket",
    "playoffs",
    "play-in",
    "playoff",
    "group stage",
]


def classify_game(
    title: str,
    subtitle: str | None = None,
    yes_sub_title: str | None = None,
    no_sub_title: str | None = None,
) -> str | None:
    """Classify a market title into a game using keyword matching.

    Inspects title, subtitle, yes_sub_title, and no_sub_title
    to maximise classification coverage.

    Args:
        title: The market title to classify.
        subtitle: Optional market subtitle.
        yes_sub_title: Optional YES outcome description.
        no_sub_title: Optional NO outcome description.

    Returns:
        Game slug (e.g. 'league-of-legends') or None if not classifiable.
    """
    parts = [title.lower()]
    if subtitle:
        parts.append(subtitle.lower())
    if yes_sub_title:
        parts.append(yes_sub_title.lower())
    if no_sub_title:
        parts.append(no_sub_title.lower())
    text = " ".join(parts)

    for game_slug, keywords in GAME_KEYWORDS.items():
        for kw in keywords:
            if re.search(kw, text):
                return game_slug

    return None


def is_esports(
    title: str,
    subtitle: str | None = None,
    yes_sub_title: str | None = None,
    no_sub_title: str | None = None,
) -> bool:
    """Check whether a market title is likely esports-related.

    Inspects title, subtitle, yes_sub_title, and no_sub_title.

    Args:
        title: The market title.
        subtitle: Optional subtitle.
        yes_sub_title: Optional YES outcome description.
        no_sub_title: Optional NO outcome description.

    Returns:
        True if the title matches esports keywords.
    """
    parts = [title.lower()]
    if subtitle:
        parts.append(subtitle.lower())
    if yes_sub_title:
        parts.append(yes_sub_title.lower())
    if no_sub_title:
        parts.append(no_sub_title.lower())
    text = " ".join(parts)

    for kw in ESPORT_KEYWORDS:
        if re.search(kw, text):
            return True

    # Also check if it classifies as a known game even without generic keywords
    return classify_game(title, subtitle, yes_sub_title, no_sub_title) is not None


def filter_esports_markets(
    markets: list[KalshiMarket],
) -> tuple[list[KalshiMarket], list[KalshiMarket], list[KalshiMarket]]:
    """Split a list of markets into (esports, non-esports, multi-event).

    Multi-event / parlay markets are separated into their own bucket because
    they bundle many independent outcomes and cannot be used for single-match
    probability modeling.

    Args:
        markets: List of parsed KalshiMarket objects.

    Returns:
        Tuple of (esports_simple, non_esports, multi_event_markets).
    """
    esports: list[KalshiMarket] = []
    non_esports: list[KalshiMarket] = []
    multi_event: list[KalshiMarket] = []

    for market in markets:
        if is_multi_event_market(market.ticker, market.title):
            market.estimated_game = classify_game(
                market.title, market.subtitle, market.yes_sub_title, market.no_sub_title,
            )
            multi_event.append(market)
        elif is_esports(market.title, market.subtitle, market.yes_sub_title, market.no_sub_title):
            market.estimated_game = classify_game(
                market.title, market.subtitle, market.yes_sub_title, market.no_sub_title,
            )
            esports.append(market)
        else:
            non_esports.append(market)

    return esports, non_esports, multi_event


def classify_market_type(title: str) -> str:
    """Infer the type of market from its title.

    Returns one of: 'match_winner', 'series_winner', 'map_winner',
    'tournament_winner', 'handicap', 'total_maps', 'other'.
    """
    t = title.lower()

    if re.search(r"match\s+winner", t) or re.search(r"to\s+win\s+the\s+match", t):
        return "match_winner"
    if re.search(r"series\s+winner", t) or re.search(r"win\s+the\s+series", t):
        return "series_winner"
    if re.search(r"tournament\s+winner", t) or re.search(r"win\s+the\s+tournament", t):
        return "tournament_winner"
    if re.search(r"map\s+\d+\s+winner", t) or re.search(r"win\s+map\s+\d+", t):
        return "map_winner"
    if re.search(r"handicap", t) or re.search(r"-\d+\.?\d*", t):
        return "handicap"
    if re.search(r"total\s+maps", t) or re.search(r"over\s+\d+\.?\d*", t):
        return "total_maps"
    # Generic "will X win" or "X to win"
    if re.search(r"will\s+", t) and re.search(r"\bwin\b", t):
        return "match_winner"

    return "other"


# ---------------------------------------------------------------------------
# Sports-market classifier — prefix-based with text fallback
# ---------------------------------------------------------------------------

# Ticker prefixes that are sports-related (derived from real Kalshi data audit).
# These cover baseball (MLB, NPB, KBO, LMB), soccer (Club Friendlies,
# CONMEBOL, European leagues), tennis (ATP, WTA, ITF), basketball
# (WNBA, TBT), and esports (LOL, CS2, Dota2, Valorant).
_SPORTS_TICKER_PREFIXES: frozenset[str] = frozenset({
    # Baseball — MLB
    "KXMLBKS", "KXMLBHRR", "KXMLBTB", "KXMLBHIT", "KXMLBRBI", "KXMLBHR",
    "KXMLBSB", "KXMLBTEAMTOTAL", "KXMLBTOTAL", "KXMLBSPREAD",
    "KXMLBF5TOTAL", "KXMLBF5SPREAD", "KXMLBF3", "KXMLBF5", "KXMLBF7",
    "KXMLBOUTS", "KXMLBGAME", "KXMLBEXTRAS", "KXMLBRFI", "KXNPBRFI",
    # Baseball — NPB (Japan)
    "KXNPBGAME", "KXNPBTOTAL", "KXNPBSPREAD",
    # Baseball — KBO (Korea)
    "KXKBOGAME", "KXKBOTOTAL", "KXKBOSPREAD", "KXKBORFI",
    # Baseball — LMB (Mexico)
    "KXLMBGAME",
    # Soccer — Club Friendlies
    "KXCLUBFGAME", "KXCLUBFTOTAL", "KXCLUBFSPREAD", "KXCLUBFBTTS",
    # Soccer — CONMEBOL
    "KXCONMEBOLSUDTOTAL", "KXCONMEBOLSUDSPREAD", "KXCONMEBOLSUDBTTS",
    "KXCONMEBOLSUD1H", "KXCONMEBOLSUD1HTOTAL", "KXCONMEBOLSUD1HSPREAD",
    "KXCONMEBOLSUD1HBTTS",
    # Soccer — European/SA leagues
    "KXCZEFLSPREAD", "KXCZEFLTOTAL", "KXCZEFLBTTS",
    "KXDIMAYORSPREAD", "KXDIMAYORTOTAL", "KXDIMAYORBTTS",
    "KXEKSTRAKLASASPREAD", "KXEKSTRAKLASATOTAL", "KXEKSTRAKLASABTTS",
    "KXELITESERIENSPREAD", "KXELITESERIENTOTAL", "KXELITESERIENBTTS",
    "KXHNLSPREAD", "KXHNLTOTAL", "KXHNLBTTS",
    "KXLIGAEXPSPREAD", "KXLIGAEXPTOTAL", "KXLIGAEXPBTTS",
    "KXLIGAEXP1H", "KXLIGAEXP1HSPREAD", "KXLIGAEXP1HTOTAL", "KXLIGAEXP1HBTTS",
    "KXPERLIGA1SPREAD", "KXPERLIGA1TOTAL", "KXPERLIGA1BTTS",
    "KXSCOTTISHPREMSPREAD", "KXSCOTTISHPREMTOTAL", "KXSCOTTISHPREMBTTS",
    "KXSCOTTISHPREM1H", "KXSCOTTISHPREM1HSPREAD", "KXSCOTTISHPREM1HTOTAL",
    "KXSCOTTISHPREM1HBTTS",
    "KXUCLSPREAD", "KXUCLTOTAL", "KXUCLBTTS",
    "KXUCL1H", "KXUCL1HSPREAD", "KXUCL1HTOTAL", "KXUCL1HBTTS",
    "KXUECLSPREAD", "KXUECLTOTAL", "KXUECLBTTS", "KXUECLTEAMTOTAL",
    "KXUECL1H", "KXUECL1HSPREAD", "KXUECL1HTOTAL", "KXUECL1HBTTS",
    "KXURYPDSPREAD", "KXURYPDTOTAL", "KXURYPDBTTS",
    # Tennis
    "KXITFMATCH", "KXITFDOUBLES", "KXITFWMATCH", "KXITFWDOUBLES",
    "KXATPMATCH", "KXATPCHALLENGERMATCH", "KXATPEXACTMATCH",
    "KXATPGSPREAD", "KXATPGTOTAL", "KXATPSETWINNER",
    "KXWTA", "KXWTACHALLENGERMATCH", "KXATP",
    # Basketball
    "KXWNBAGAME", "KXWNBAOT", "KXWNBAMENTION", "KXTBTGAME",
    # Esports
    "KXLOLGAME", "KXLOLMAP", "KXLOLTOTALMAPS",
    "KXDOTA2GAME", "KXDOTA2MAP",
    "KXCS2GAME",
    "KXVALORANTGAME", "KXVALORANTMAP",
})


def is_sports_market(
    ticker: str,
    title: str = "",
    rules_primary: str = "",
    subtitle: str | None = None,
    yes_sub_title: str | None = None,
    no_sub_title: str | None = None,
) -> bool:
    """Determine whether a Kalshi market is sports-related.

    Uses a two-tier approach:
    1. **Primary — ticker prefix.** Matches against a curated set of 100+
       sports ticker prefixes derived from real Kalshi data.
    2. **Fallback — text classification.** When the prefix is unknown,
       runs the existing sport-classifier on rules_primary and title to
       detect sports keywords (soccer, basketball, baseball, etc.).

    This avoids false positives on weather/commodities/politics while
    catching newly introduced sports ticker families.

    Args:
        ticker: The market ticker (e.g. "KXMLBKS-26JUL28...").
        title: Market title.
        rules_primary: rules_primary text.
        subtitle: Optional subtitle.
        yes_sub_title: Optional YES outcome.
        no_sub_title: Optional NO outcome.

    Returns:
        True if the market is sports-related.
    """
    # Primary: ticker prefix lookup
    if ticker:
        prefix = ticker.split("-")[0]
        if prefix in _SPORTS_TICKER_PREFIXES:
            return True

    # Fallback: text-based classification (for new/unknown prefixes)
    text_parts = [title, rules_primary]
    if subtitle:
        text_parts.append(subtitle)
    if yes_sub_title:
        text_parts.append(yes_sub_title)
    if no_sub_title:
        text_parts.append(no_sub_title)

    from prediction_bot.agents.schema import _classify_sport
    from prediction_bot.kalshi.discovery import is_esports

    combined = " ".join(p for p in text_parts if p)
    return (
        _classify_sport(combined) is not None
        or is_esports(title, subtitle, yes_sub_title, no_sub_title)
    )


def split_markets_sports_non_sports(
    markets: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split a list of raw Kalshi market dicts into (sports, non_sports).

    Uses is_sports_market() which combines ticker-prefix lookup and
    rules_primary/title classification.

    Args:
        markets: List of raw Kalshi market dicts.

    Returns:
        Tuple of (sports_markets, non_sports_markets).
    """
    sports: list[dict[str, Any]] = []
    non_sports: list[dict[str, Any]] = []

    for m in markets:
        if is_sports_market(
            ticker=m.get("ticker", ""),
            title=m.get("title", ""),
            rules_primary=m.get("rules_primary", ""),
            subtitle=m.get("subtitle"),
            yes_sub_title=m.get("yes_sub_title"),
            no_sub_title=m.get("no_sub_title"),
        ):
            sports.append(m)
        else:
            non_sports.append(m)

    return sports, non_sports


# ---------------------------------------------------------------------------
# Esports-only filter
# ---------------------------------------------------------------------------

_ESPORTS_TICKER_PREFIXES: frozenset[str] = frozenset({
    pfx for pfx in _SPORTS_TICKER_PREFIXES
    if pfx.startswith(("KXLOL", "KXDOTA2", "KXCS2", "KXVALORANT"))
})


def is_esports_market(
    ticker: str,
    title: str = "",
    rules_primary: str = "",
    subtitle: str | None = None,
    yes_sub_title: str | None = None,
    no_sub_title: str | None = None,
) -> bool:
    """Determine whether a Kalshi market is esports.

    Esports = League of Legends, CS2, Dota 2, Valorant, and any other
    market whose normalize_contract() yields sport == "esports".

    Two-tier check:
    1. Ticker prefix — matches known esports families (KXLOL*, KXDOTA2*,
       KXCS2*, KXVALORANT*).
    2. Fallback — runs normalize_contract() for new/unknown esports
       prefixes detected via rules_primary/title.

    Soccer, basketball, tennis, baseball, football, and all non-sports
    markets return False.
    """
    # Primary: ticker prefix lookup (instant, no API call)
    if ticker:
        prefix = ticker.split("-")[0]
        if prefix in _ESPORTS_TICKER_PREFIXES:
            return True

    # Fallback: normalize_contract for new/unknown esports prefixes
    raw = {
        "ticker": ticker,
        "title": title,
        "rules_primary": rules_primary,
        "subtitle": subtitle,
        "yes_sub_title": yes_sub_title,
        "no_sub_title": no_sub_title,
    }
    from prediction_bot.agents.schema import normalize_contract
    nc = normalize_contract(raw)
    return nc.sport == "esports"


def split_markets_esports_excluded(
    markets: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split raw Kalshi markets into (esports, excluded).

    Esports = LOL, CS2, Dota2, Valorant (and any other market whose
    normalize_contract() yields sport == "esports").

    Excluded = traditional sports (soccer, baseball, tennis, basketball,
    football, etc.) and non-sports (weather, commodities, politics).

    Args:
        markets: List of raw Kalshi market dicts.

    Returns:
        Tuple of (esports_markets, excluded_markets).
    """
    esports: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    for m in markets:
        if is_esports_market(
            ticker=m.get("ticker", ""),
            title=m.get("title", ""),
            rules_primary=m.get("rules_primary", ""),
            subtitle=m.get("subtitle"),
            yes_sub_title=m.get("yes_sub_title"),
            no_sub_title=m.get("no_sub_title"),
        ):
            esports.append(m)
        else:
            excluded.append(m)

    return esports, excluded


# ---------------------------------------------------------------------------
# Major league / Tier 1 filter
# ---------------------------------------------------------------------------

# Known Tier 1 / major esports leagues and tournaments.
# These are the top professional circuits with the best-known teams.
# Minor/regional leagues (CBLOL, VCS, PCS, LJL, LCO, TCL, etc.) and
# academy/amateur circuits are excluded from predictions.
_MAJOR_LEAGUE_KEYWORDS: dict[str, list[str]] = {
    "league-of-legends": [
        # Tier 1 leagues
        r"\blck\b",               # Korea (League of Legends Champions Korea)
        r"\blpl\b",               # China (League of Legends Pro League)
        r"\blec\b",               # Europe (League of Legends EMEA Championship)
        r"\blcs\b",               # North America (League of Legends Championship Series)
        r"\blta\b",               # Americas (League of Legends The Americas)
        # Internationals
        r"\bworlds\b",            # World Championship
        r"\bmsi\b",               # Mid-Season Invitational
        r"\bfirst stand\b",       # First Stand tournament
        r"\bkespa cup\b",         # KeSPA Cup (Korea)
        r"\bdemacia cup\b",       # Demacia Cup (China)
    ],
    "cs2": [
        # Tier 1 tournaments
        r"\biesl\b",              # ESL Pro League
        r"\biem\b",               # Intel Extreme Masters
        r"\bblast\b",             # BLAST Premier
        r"\bpgl\b",               # PGL Major
        r"\bmajor\b",             # Major Championship
        r"\bkatowice\b",          # IEM Katowice
        r"\bcologne\b",           # IEM Cologne
    ],
    "dota2": [
        # Tier 1 tournaments
        r"\bthe international\b", # The International
        r"\bti\d",                # TI<number>
        r"\briyadh masters\b",    # Riyadh Masters
        r"\besl one\b",           # ESL One
        r"\bdreamleague\b",       # DreamLeague
        r"\bbetboom dacha\b",     # BetBoom Dacha
        r"\bblast\b",             # BLAST Slam
        r"\bpgl\b",               # PGL Wallachia/Arlington
        r"\bbirmingham\b",        # ESL One Birmingham
    ],
    "valorant": [
        # Tier 1 tournaments
        r"\bvct\b",               # Valorant Champions Tour
        r"\bchampions\b",         # VCT Champions
        r"\bmasters\b",           # VCT Masters
        r"\bkickoff\b",           # VCT Kickoff
    ],
}

# Known minor/regional leagues to explicitly exclude, per game.
# These are keyword patterns that identify non-Tier-1 circuits.
# Each game's list only fires for that specific game — avoids cross-game
# false positives (e.g., "challengers" excludes Valorant but not CS2 ESL).
_MINOR_LEAGUE_KEYWORDS: dict[str, list[str]] = {
    "league-of-legends": [
        r"\bcblol\b",            # Brazil
        r"\bvcs\b",              # Vietnam
        r"\bpcs\b",              # Pacific
        r"\bljl\b",              # Japan
        r"\blco\b",              # Oceania
        r"\btcl\b",              # Turkey
        r"\blla\b",              # Latin America
        r"\blcl\b",              # Latin America (old)
        r"\bacl\b",              # Academy
        r"\bchallengers\b",      # LCK Challengers / any challenger league
        r"\bem\b",               # European Masters / EMEA Masters
        r"\bprime league\b",     # DACH regional
        r"\bhitpoint\b",         # Czech/Slovak
        r"\blfl\b",              # France
        r"\bnlc\b",              # UK/Nordic
        r"\bpg nationals\b",     # Poland
        r"\bgrunex\b",           # DACH open
        r"\bultraliga\b",        # Poland
        r"\bsuperliga\b",        # Spain
        r"\bgll\b",              # Greece/Balkans
        r"\bhonor league\b",     # MENA
        r"\blplol\b",            # Latin America (Riot)
        r"\bners\b",             # ERL (Nordic)
    ],
    "cs2": [
        r"\bcct\b",              # Champion of Champions Tour (Tier 2)
        r"\besea\b",             # ESEA League (Tier 2-3)
        r"\byalla\b",            # Yalla Compass (Tier 2)
        r"\bthunderpick\b",      # Thunderpick (Tier 2-3)
        r"\belisa\b",            # Elisa Invitational (Tier 2)
        r"\bhellcase\b",         # Hellcase (Tier 3)
        r"\bskin\b",             # Skin.Club / skin betting cups
        r"\becs\b",              # Esports Championship Series (defunct)
        r"\bstake\b",            # Stake Ranked (crypto betting)
        r"\bgamezone\b",         # GameZone
        r"\bepic\b",             # Epic Gamer Challenge
        r"\bpraim\b",            # Praim League
        r"\besea\b",             # ESEA
    ],
    "dota2": [
        r"\bdpc\b",              # Dota Pro Circuit (regional/defunct)
        r"\bresport\b",          # RES Regional Series
        r"\bcct\b",              # CCT (Tier 2)
        r"\besea\b",             # ESEA
    ],
    "valorant": [
        r"\bchallengers\b",      # VCT Challengers (Tier 2)
        r"\bgame changers\b",    # Game Changers (women's, smaller)
    ],
}

# Generic minor keywords that apply regardless of game.
# Keep these minimal to avoid false positives.
_GENERIC_MINOR_KEYWORDS: list[str] = [
    r"\bacademy\b",
    r"\bamateur\b",
    r"\bopen\s+cup\b",
    r"\bopen\s+qualifier\b",
]


def is_major_esports_league(
    ticker: str | None = None,
    title: str | None = None,
    rules_primary: str | None = None,
    subtitle: str | None = None,
) -> bool:
    """Determine whether an esports market belongs to a Tier 1 / major league.

    Filters out small regional leagues, academy circuits, amateur tournaments,
    and qualifiers. Only the top professional circuits are kept:

    - League of Legends: LCK, LPL, LEC, LCS/LTA, Worlds, MSI, First Stand
    - CS2: ESL Pro League, IEM, BLAST Premier, PGL/BLAST Major
    - Dota 2: The International, Riyadh Masters, ESL One, DreamLeague
    - Valorant: VCT Champions, Masters, Kickoff

    Uses two passes:
    1. Negative check — if a known minor league keyword is present, return False.
    2. Positive check — if a known major league keyword is present, return True.
    3. If neither matches, defaults to False (conservative: exclude unknown leagues).

    Args:
        ticker: Kalshi ticker (used to determine the game, then look up
            game-specific keywords).
        title: Market title.
        rules_primary: rules_primary text.
        subtitle: Optional subtitle.

    Returns:
        True if this market belongs to a Tier 1 league and should be kept.
    """
    # Build combined text for keyword scanning
    text_parts: list[str] = []
    if title:
        text_parts.append(title.lower())
    if rules_primary:
        text_parts.append(rules_primary.lower())
    if subtitle:
        text_parts.append(subtitle.lower())
    combined = " ".join(text_parts)

    if not combined:
        return False

    # Determine the game from ticker prefix
    game: str | None = None
    if ticker:
        prefix = ticker.split("-")[0]
        if prefix.startswith("KXLOL"):
            game = "league-of-legends"
        elif prefix.startswith("KXCS2"):
            game = "cs2"
        elif prefix.startswith("KXDOTA2"):
            game = "dota2"
        elif prefix.startswith("KXVALORANT"):
            game = "valorant"

    # Pass 1: reject known minor leagues (negative filter)
    # First check generic minor keywords (apply regardless of game)
    for kw in _GENERIC_MINOR_KEYWORDS:
        if re.search(kw, combined):
            return False
    # Then check game-specific minor keywords
    if game and game in _MINOR_LEAGUE_KEYWORDS:
        if any(
            re.search(kw, combined) for kw in _MINOR_LEAGUE_KEYWORDS[game]
        ):
            return False

    # Pass 2: require a known major league (positive filter)
    if game and game in _MAJOR_LEAGUE_KEYWORDS:
        return any(
            re.search(kw, combined) for kw in _MAJOR_LEAGUE_KEYWORDS[game]
        )

    # Unknown game — default to exclude
    return False


def filter_major_league_only(
    markets: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split a list of esports markets into (major_league, minor_league).

    Args:
        markets: List of raw Kalshi market dicts (should already be
            pre-filtered to esports only).

    Returns:
        Tuple of (major_league_markets, minor_league_markets).
    """
    major: list[dict[str, Any]] = []
    minor: list[dict[str, Any]] = []

    for m in markets:
        if is_major_esports_league(
            ticker=m.get("ticker"),
            title=m.get("title"),
            rules_primary=m.get("rules_primary"),
            subtitle=m.get("subtitle"),
        ):
            major.append(m)
        else:
            minor.append(m)

    return major, minor
