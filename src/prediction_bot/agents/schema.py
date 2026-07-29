"""Prediction agent schemas — contracts, events, predictions.

Phase 1 redesign: Kalshi markets are contracts, not events.
One match creates many contracts (map winner, match winner, totals, spreads).
rules_primary is the authoritative parsing source.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PredictionConfidence(str, Enum):
    """Hermes confidence level for a prediction."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ContractType(str, Enum):
    """Classification of what a Kalshi contract settles on."""

    MATCH_WINNER = "match_winner"
    MAP_WINNER = "map_winner"
    SET_WINNER = "set_winner"
    SERIES_WINNER = "series_winner"
    TOURNAMENT_WINNER = "tournament_winner"
    TOTAL_GOALS = "total_goals"
    TOTAL_MAPS = "total_maps"
    TOTAL_GAMES = "total_games"
    TOTAL_RUNS = "total_runs"
    PLAYER_PROP = "player_prop"
    HANDICAP = "handicap"
    SPREAD = "spread"
    BTTS = "btts"
    OTHER = "other"


class Sport(str, Enum):
    """Broad sport classification."""

    ESPORTS = "esports"
    SOCCER = "soccer"
    BASKETBALL = "basketball"
    FOOTBALL = "football"
    BASEBALL = "baseball"
    HOCKEY = "hockey"
    TENNIS = "tennis"
    MMA = "mma"
    OTHER = "other"


# ---------------------------------------------------------------------------
# rules_primary parser — Phase 2
# ---------------------------------------------------------------------------

# Boundary markers that end the yes_outcome clause.
# Ordered: check more specific (with lookahead) before generic.
_YES_OUTCOME_BOUNDARIES = (
    # ", then the market resolves" — universal end
    r", then the market resolves",
    # Esports colon — "in the <Tournament>: <teams> <Game> match" (map/totals)
    r" in the .+?: .+?(?:League of Legends|Dota\s*2|CS2|Valorant|Counter.?Strike|Overwatch|"
    r"Rainbow\s*Six|Rocket\s*League|Call of Duty|Apex\s*Legends) match",
    # "in (the) <TeamA> vs <TeamB> professional <sport> game/match"
    r" in (?:the )?.+? vs .+? professional (?:baseball|soccer|basketball|football|"
    r"hockey|tennis|Club Friendlies|CONMEBOL|women's Pro Basketball) (?:game|match)",
    # "wins the <TeamA> vs <TeamB> professional <sport> game" (soccer/tennis/bball)
    r" wins the .+? vs .+? professional (?:soccer|basketball|football|baseball|hockey|tennis)"
    r" (?:game|match)",
    # "wins the <TeamA> vs <TeamB> (Japan NPB|Korea KBO|Mexico LMB|WNBA) game"
    r" wins the .+? vs .+? (?:Japan NPB|Korea KBO|Mexico LMB|women's Pro Basketball) game",
    # "is the result of <TeamA> vs <TeamB> professional..." (Tie)
    r" is the result of .+? vs .+? professional (?:soccer|Club Friendlies|CONMEBOL)"
    r" (?:game|match)",
    # Baseball player props: boundary is "in (the) <TeamA> vs <TeamB> professional baseball game"
    r" in (?:the )?.+? vs .+? professional baseball game",
    # Spread: "win by more than N runs in the <TeamA> vs <TeamB> ..."
    r" win by more than [\d.]+ runs? in the .+? vs .+?"
    r" (?:Japan NPB|Korea KBO|Mexico LMB|professional baseball) game",
    # Baseball totals: "collectively score more than N runs"
    r" collectively score more than [\d.]+ runs? in the .+? and .+?"
    r" (?:College )?[Bb]aseball game",
    # Soccer BTTS
    r" in the .+? vs .+? (?:Club Friendlies|CONMEBOL|Liga de Expansión|CzeFL|Dimayor|"
    r"Ekstraklasa|Eliteserien|HNL|PerLiga|Scottish Prem|UCL|UECL|Ury PD) match",
    # Tennis match: "professional tennis match in the"
    r" professional tennis match in the",
    # Tennis tournament: "professional tennis tournament"
    r" professional tennis tournament",
    # WNBA: "women's Pro Basketball game"
    r" women's Pro Basketball game",
    # Spread in tennis "above N games in the <teams> professional tennis match"
    r" above [\d.]+ games in the .+? vs .+? professional tennis match",
    r" above [\d.]+ games in the .+? professional tennis match",
    # General "professional <sport>" boundary
    r" professional (?:baseball|soccer|basketball|football|tennis)",
    # General NPB/KBO/LMB game
    r" (?:Japan NPB|Korea KBO|Mexico LMB) game",
)

_F = re.IGNORECASE


# ---------------------------------------------------------------------------
# Ticker prefix → contract_type + sport/game map
# ---------------------------------------------------------------------------
# Ticker prefixes are machine-generated and are the most reliable signal for
# contract type and game classification.  This map is the PRIMARY source;
# rules_primary and title are fallbacks/confirmations.
#
# Each entry: prefix → (contract_type, sport, game_or_none)
#   contract_type: one of the ContractType enum values
#   sport: one of the Sport enum values
#   game: esports game slug, or None for traditional sports
# ---------------------------------------------------------------------------

_TICKER_PREFIX_MAP: dict[str, tuple[str, str, str | None]] = {
    # ── Esports ──
    # League of Legends
    "KXLOLGAME":      ("match_winner",     "esports", "league-of-legends"),
    "KXLOLMAP":       ("map_winner",       "esports", "league-of-legends"),
    "KXLOLTOTALMAPS": ("total_maps",       "esports", "league-of-legends"),
    # Dota 2
    "KXDOTA2GAME":    ("match_winner",     "esports", "dota2"),
    "KXDOTA2MAP":     ("map_winner",       "esports", "dota2"),
    # CS2
    "KXCS2GAME":      ("match_winner",     "esports", "cs2"),
    # Valorant
    "KXVALORANTGAME": ("match_winner",     "esports", "valorant"),
    "KXVALORANTMAP":  ("map_winner",       "esports", "valorant"),
    # ── Baseball — MLB ──
    "KXMLBKS":        ("player_prop",      "baseball", None),
    "KXMLBHRR":       ("player_prop",      "baseball", None),
    "KXMLBTB":        ("player_prop",      "baseball", None),
    "KXMLBHIT":       ("player_prop",      "baseball", None),
    "KXMLBRBI":       ("player_prop",      "baseball", None),
    "KXMLBHR":        ("player_prop",      "baseball", None),
    "KXMLBSB":        ("player_prop",      "baseball", None),
    "KXMLBOUTS":      ("player_prop",      "baseball", None),
    "KXMLBGAME":      ("match_winner",     "baseball", None),
    "KXMLBTEAMTOTAL": ("total_runs",       "baseball", None),
    "KXMLBTOTAL":     ("total_runs",       "baseball", None),
    "KXMLBSPREAD":    ("spread",           "baseball", None),
    "KXMLBEXTRAS":    ("other",            "baseball", None),
    "KXMLBRFI":       ("other",            "baseball", None),
    "KXMLBF3":        ("other",            "baseball", None),
    "KXMLBF5":        ("other",            "baseball", None),
    "KXMLBF7":        ("other",            "baseball", None),
    "KXMLBF5TOTAL":   ("total_runs",       "baseball", None),
    "KXMLBF5SPREAD":  ("spread",           "baseball", None),
    # Baseball — NPB (Japan)
    "KXNPBGAME":      ("match_winner",     "baseball", None),
    "KXNPBTOTAL":     ("total_runs",       "baseball", None),
    "KXNPBSPREAD":    ("spread",           "baseball", None),
    "KXNPBRFI":       ("other",            "baseball", None),
    # Baseball — KBO (Korea)
    "KXKBOGAME":      ("match_winner",     "baseball", None),
    "KXKBOTOTAL":     ("total_runs",       "baseball", None),
    "KXKBOSPREAD":    ("spread",           "baseball", None),
    "KXKBORFI":       ("other",            "baseball", None),
    # Baseball — LMB (Mexico)
    "KXLMBGAME":      ("match_winner",     "baseball", None),
    # ── Soccer ──
    "KXCLUBFGAME":    ("match_winner",     "soccer", None),
    "KXCLUBFTOTAL":   ("total_goals",      "soccer", None),
    "KXCLUBFSPREAD":  ("spread",           "soccer", None),
    "KXCLUBFBTTS":    ("btts",             "soccer", None),
    # CONMEBOL
    "KXCONMEBOLSUDTOTAL":   ("total_goals",  "soccer", None),
    "KXCONMEBOLSUDSPREAD":  ("spread",       "soccer", None),
    "KXCONMEBOLSUDBTTS":    ("btts",         "soccer", None),
    "KXCONMEBOLSUD1H":      ("match_winner", "soccer", None),
    "KXCONMEBOLSUD1HTOTAL": ("total_goals",  "soccer", None),
    "KXCONMEBOLSUD1HSPREAD":("spread",       "soccer", None),
    "KXCONMEBOLSUD1HBTTS":  ("btts",         "soccer", None),
    # European / SA leagues — TOTAL / SPREAD / BTTS / 1H
    "KXCZEFLTOTAL":     ("total_goals",  "soccer", None),
    "KXCZEFLSPREAD":    ("spread",       "soccer", None),
    "KXCZEFLBTTS":      ("btts",         "soccer", None),
    "KXDIMAYORTOTAL":   ("total_goals",  "soccer", None),
    "KXDIMAYORSPREAD":  ("spread",       "soccer", None),
    "KXDIMAYORBTTS":    ("btts",         "soccer", None),
    "KXEKSTRAKLASATOTAL":  ("total_goals",  "soccer", None),
    "KXEKSTRAKLASASPREAD": ("spread",       "soccer", None),
    "KXEKSTRAKLASABTTS":   ("btts",         "soccer", None),
    "KXELITESERIENTOTAL":  ("total_goals",  "soccer", None),
    "KXELITESERIENSPREAD": ("spread",       "soccer", None),
    "KXELITESERIENBTTS":   ("btts",         "soccer", None),
    "KXHNLTOTAL":       ("total_goals",  "soccer", None),
    "KXHNLSPREAD":      ("spread",       "soccer", None),
    "KXHNLBTTS":        ("btts",         "soccer", None),
    "KXLIGAEXPTOTAL":   ("total_goals",  "soccer", None),
    "KXLIGAEXPSPREAD":  ("spread",       "soccer", None),
    "KXLIGAEXPBTTS":    ("btts",         "soccer", None),
    "KXLIGAEXP1H":         ("match_winner", "soccer", None),
    "KXLIGAEXP1HTOTAL":    ("total_goals",  "soccer", None),
    "KXLIGAEXP1HSPREAD":   ("spread",       "soccer", None),
    "KXLIGAEXP1HBTTS":     ("btts",         "soccer", None),
    "KXPERLIGA1TOTAL":  ("total_goals",  "soccer", None),
    "KXPERLIGA1SPREAD": ("spread",       "soccer", None),
    "KXPERLIGA1BTTS":   ("btts",         "soccer", None),
    "KXSCOTTISHPREMTOTAL":  ("total_goals",  "soccer", None),
    "KXSCOTTISHPREMSPREAD": ("spread",       "soccer", None),
    "KXSCOTTISHPREMBTTS":   ("btts",         "soccer", None),
    "KXSCOTTISHPREM1H":        ("match_winner", "soccer", None),
    "KXSCOTTISHPREM1HTOTAL":   ("total_goals",  "soccer", None),
    "KXSCOTTISHPREM1HSPREAD":  ("spread",       "soccer", None),
    "KXSCOTTISHPREM1HBTTS":    ("btts",         "soccer", None),
    "KXUCLTOTAL":       ("total_goals",  "soccer", None),
    "KXUCLSPREAD":      ("spread",       "soccer", None),
    "KXUCLBTTS":        ("btts",         "soccer", None),
    "KXUCL1H":          ("match_winner", "soccer", None),
    "KXUCL1HTOTAL":     ("total_goals",  "soccer", None),
    "KXUCL1HSPREAD":    ("spread",       "soccer", None),
    "KXUCL1HBTTS":      ("btts",         "soccer", None),
    "KXUECLTOTAL":      ("total_goals",  "soccer", None),
    "KXUECLSPREAD":     ("spread",       "soccer", None),
    "KXUECLBTTS":       ("btts",         "soccer", None),
    "KXUECLTEAMTOTAL":  ("total_goals",  "soccer", None),
    "KXUECL1H":         ("match_winner", "soccer", None),
    "KXUECL1HTOTAL":    ("total_goals",  "soccer", None),
    "KXUECL1HSPREAD":   ("spread",       "soccer", None),
    "KXUECL1HBTTS":     ("btts",         "soccer", None),
    "KXURYPDTOTAL":     ("total_goals",  "soccer", None),
    "KXURYPDSPREAD":    ("spread",       "soccer", None),
    "KXURYPDBTTS":      ("btts",         "soccer", None),
    # ── Tennis ──
    "KXITFMATCH":             ("match_winner", "tennis", None),
    "KXITFDOUBLES":           ("match_winner", "tennis", None),
    "KXITFWMATCH":            ("match_winner", "tennis", None),
    "KXITFWDOUBLES":          ("match_winner", "tennis", None),
    "KXATPMATCH":             ("match_winner", "tennis", None),
    "KXATPCHALLENGERMATCH":   ("match_winner", "tennis", None),
    "KXATPEXACTMATCH":        ("match_winner", "tennis", None),
    "KXATPGSPREAD":           ("total_games",  "tennis", None),
    "KXATPGTOTAL":            ("total_games",  "tennis", None),
    "KXATPSETWINNER":         ("set_winner",   "tennis", None),
    "KXWTA":                  ("tournament_winner", "tennis", None),
    "KXWTACHALLENGERMATCH":   ("match_winner", "tennis", None),
    "KXATP":                  ("tournament_winner", "tennis", None),
    # ── Basketball ──
    "KXWNBAGAME":     ("match_winner", "basketball", None),
    "KXWNBAOT":       ("other",        "basketball", None),
    "KXWNBAMENTION":  ("other",        "basketball", None),
    "KXTBTGAME":      ("match_winner", "basketball", None),
}


def parse_ticker(ticker: str) -> dict[str, str | None]:
    """Extract contract_type, sport, and game from a Kalshi ticker.

    The ticker prefix is the #1 determinant — it is machine-generated and
    encodes the contract type and sport/game with 100% reliability.

    Returns a dict with 'contract_type', 'sport', and 'game'.
    All values are None if the ticker prefix is not recognised.
    """
    if not ticker:
        return {"contract_type": None, "sport": None, "game": None}

    prefix = ticker.split("-")[0]
    entry = _TICKER_PREFIX_MAP.get(prefix)
    if entry is None:
        return {"contract_type": None, "sport": None, "game": None}

    ct, sport, game = entry
    return {"contract_type": ct, "sport": sport, "game": game}


def _apply_yes_outcome_cleanup(outcome: str) -> str:
    """Clean up the yes_outcome by removing tournament/team context."""
    # Esports match winner: "X wins the <Tournament>: <teams> <Game> match..." → "X wins"
    m = re.search(
        r"\s+wins the .+?: .+?(?:League of Legends|Dota\s*2|CS2|Valorant|Counter.?Strike)"
        r" match.*$",
        outcome, _F,
    )
    if m:
        return outcome[: m.start()] + " wins"

    # Dota2 no-"the": "X wins <Tournament>: <teams> Dota 2 match..." → "X wins"
    m = re.search(r"\s+wins [A-Z].+?: .+?Dota\s*2 match.*$", outcome, _F)
    if m:
        return outcome[: m.start()] + " wins"

    # Double colon
    m = re.search(
        r"\s+wins the .+?: .+?: .+?(?:Valorant|League of Legends|CS2) match.*$",
        outcome, _F,
    )
    if m:
        return outcome[: m.start()] + " wins"

    # Soccer match winner: "X wins the X vs Y professional ... game..." → "X wins"
    m = re.search(
        r"\s+wins the .+? vs .+? professional .+?"
        r" (?:soccer|basketball|football|baseball|hockey) game.*$",
        outcome, _F,
    )
    if m:
        return outcome[: m.start()] + " wins"

    # NPB/KBO/LMB/WNBA match winner
    m = re.search(
        r"\s+wins the .+? vs .+?"
        r" (?:Japan NPB|Korea KBO|Mexico LMB|women's Pro Basketball) game.*$",
        outcome, _F,
    )
    if m:
        return outcome[: m.start()] + " wins"

    # Tennis match winner
    m = re.search(r"\s+wins the .+? vs .+? professional tennis match.*$", outcome, _F)
    if m:
        return outcome[: m.start()] + " wins"

    # Tie
    m = re.search(
        r"\s+is the result of the .+? vs .+? professional .+?"
        r" (?:soccer|Club Friendlies) game.*$",
        outcome, _F,
    )
    if m:
        return outcome[: m.start()]

    # Baseball player prop: strip "in the X vs Y professional baseball game..."
    m = re.search(r"\s+in (?:the )?.+? vs .+? professional baseball game.*$", outcome, _F)
    if m:
        return outcome[: m.start()]

    # Spread: strip trailing "in the X vs Y professional ..."
    m = re.search(r"\s+in (?:the )?.+? vs .+? professional .+$", outcome, _F)
    if m:
        return outcome[: m.start()]

    # General: remove trailing ", originally scheduled..." or ", then..."
    outcome = re.sub(r",?\s*(?:then|originally)\s.*$", "", outcome, flags=_F).strip()
    return outcome


def parse_rules_primary(rules: str) -> dict[str, Any]:
    """Parse a Kalshi rules_primary string into structured fields."""
    if not rules or not rules.strip():
        return _empty_parse_result()

    text = rules.strip()

    result: dict[str, Any] = {
        "yes_outcome": None,
        "tournament": None,
        "game": None,
        "sport": None,
        "participants": None,
        "map_number": None,
        "contract_type": None,
        "threshold": None,
        "extra_info": {},
    }

    yes_outcome = _extract_yes_outcome(text)
    result["yes_outcome"] = yes_outcome
    result["sport"] = _classify_sport(text)
    result["game"] = _extract_game(text, result["sport"])
    result["tournament"] = _extract_tournament(text)
    result["participants"] = _extract_participants(text)

    m = re.search(r"(?:map|game|set)\s+(\d+)", yes_outcome or text, _F)
    if m:
        result["map_number"] = int(m.group(1))

    result["contract_type"] = _classify_contract_type(yes_outcome or "", text)
    result["threshold"] = _extract_threshold(yes_outcome or "", text)

    return result


def _empty_parse_result() -> dict[str, Any]:
    return {
        "yes_outcome": None, "tournament": None, "game": None, "sport": None,
        "participants": None, "map_number": None, "contract_type": None,
        "threshold": None, "extra_info": {},
    }


# ---------------------------------------------------------------------------
# Title parser — fallback when rules_primary is insufficient
# ---------------------------------------------------------------------------


def parse_title(title: str) -> dict[str, Any]:
    """Parse a Kalshi market title into structured fields.

    Used as a fallback when rules_primary is empty or yields no contract_type.
    Title parsing is less rich than rules_primary parsing (no tournament, no
    yes_outcome) but is sufficient to classify contract_type, map_number,
    and participants for common patterns.

    Contract type can be known while game/sport remain unknown — game
    identification is a separate step using ticker prefix, rules_primary,
    and event metadata.

    Patterns handled:
      - "Will {TEAM} win map {N} in the {A} vs. {B} match?"  → map_winner
      - "Will {TEAM} win the {A} vs. {B} {GAME} match?"      → match_winner
      - "Will {PLAYER} win set {N} in the {A} vs {B} match"   → set_winner
      - "Will {PLAYER} win the {A} vs {B}: ... match?"        → match_winner
      - "{PLAYER}: {N}+ {STAT}?"                               → player_prop
      - "Will over {N} goals be scored?"                       → total_goals

    Args:
        title: The market title string.

    Returns:
        Dict with contract_type, map_number, participants, and threshold.
        Fields are None if not detected from the title.
    """
    if not title or not title.strip():
        return {
            "contract_type": None, "map_number": None,
            "participants": None, "threshold": None,
        }

    t = title.strip()

    # ── Map winner: "Will X win map N in the A vs. B match?" ──
    m = re.match(
        r"^Will (.+?) win map (\d+) in the (.+?) vs\.? (.+?) match\?$",
        t, _F,
    )
    if m:
        return {
            "contract_type": ContractType.MAP_WINNER.value,
            "map_number": int(m.group(2)),
            "participants": [m.group(3).strip(), m.group(4).strip()],
            "threshold": None,
        }

    # ── Set winner: "Will X win set N in the A vs B match" ──
    m = re.match(
        r"^Will (.+?) win set (\d+) in the (.+?) vs\.? (.+?) match",
        t, _F,
    )
    if m:
        return {
            "contract_type": ContractType.SET_WINNER.value,
            "map_number": int(m.group(2)),
            "participants": [m.group(3).strip(), m.group(4).strip()],
            "threshold": None,
        }

    # ── Match winner (esports): "Will X win the A vs. B League of Legends match?" ──
    m = re.match(
        r"^Will (.+?) win the (.+?) vs\.? (.+?) (League of Legends|Dota 2|CS2|Valorant) match\?$",
        t, _F,
    )
    if m:
        return {
            "contract_type": ContractType.MATCH_WINNER.value,
            "map_number": None,
            "participants": [m.group(2).strip(), m.group(3).strip()],
            "threshold": None,
        }

    # ── Tennis match (colon separator): "Will X win the A vs B: Tournament Round match?" ──
    # Must come BEFORE generic match winner to avoid capturing the colon as
    # part of the team name.
    m = re.match(
        r"^Will (.+?) win the (.+?) vs\.? (.+?): .+ match\?$",
        t, _F,
    )
    if m:
        return {
            "contract_type": ContractType.MATCH_WINNER.value,
            "map_number": None,
            "participants": [m.group(2).strip(), m.group(3).strip()],
            "threshold": None,
        }

    # ── Match winner (generic): "Will X win the A vs. B match?" ──
    # (without game name — works for CS2, some esports, etc.)
    m = re.match(
        r"^Will (.+?) win the (.+?) vs\.? (.+?) match\?$",
        t, _F,
    )
    if m:
        return {
            "contract_type": ContractType.MATCH_WINNER.value,
            "map_number": None,
            "participants": [m.group(2).strip(), m.group(3).strip()],
            "threshold": None,
        }

    # ── Player prop: "{PLAYER}: {N}+ {STAT}?" ──
    m = re.match(
        r"^(.+?): (\d+)\+ (?:RBIs|home runs?|hits|strikeouts?|stolen bases?|total bases?|"
        r"hits \+ runs \+ RBIs|Outs Recorded)\?$",
        t, _F,
    )
    if m:
        return {
            "contract_type": ContractType.PLAYER_PROP.value,
            "map_number": None,
            "participants": None,  # no team info in title
            "threshold": float(m.group(2)),
        }

    # ── Soccer totals: "Will over N.N goals be scored?" ──
    m = re.match(r"^Will over ([\d.]+) goals be scored\?$", t, _F)
    if m:
        return {
            "contract_type": ContractType.TOTAL_GOALS.value,
            "map_number": None,
            "participants": None,
            "threshold": float(m.group(1)),
        }

    # ── "Over N.N goals scored?" ──
    m = re.match(r"^Over ([\d.]+) .* goals scored\?$", t, _F)
    if m:
        return {
            "contract_type": ContractType.TOTAL_GOALS.value,
            "map_number": None,
            "participants": None,
            "threshold": float(m.group(1)),
        }

    return {
        "contract_type": None, "map_number": None,
        "participants": None, "threshold": None,
    }


# ---------------------------------------------------------------------------
# yes_outcome extraction
# ---------------------------------------------------------------------------


def _extract_yes_outcome(text: str) -> str | None:
    if not text.lower().startswith("if "):
        return None
    inner = text[3:]

    earliest_end = len(inner)
    for boundary_pat in _YES_OUTCOME_BOUNDARIES:
        m = re.search(boundary_pat, inner, _F)
        if m and m.start() < earliest_end:
            earliest_end = m.start()

    outcome = inner[:earliest_end].strip()
    outcome = _apply_yes_outcome_cleanup(outcome)

    if not outcome:
        return None
    return outcome


# ---------------------------------------------------------------------------
# Sport classification
# ---------------------------------------------------------------------------


def _classify_sport(text: str) -> str | None:
    text_lower = text.lower()

    if re.search(
        r"\b(?:league of legends|league of legend|dota\s*2|counter.?strike|"
        r"valorant|overwatch|rainbow\s*six|rocket\s*league|call of duty|"
        r"apex\s*legends|esports?|e-sports?)\b", text_lower,
    ):
        return Sport.ESPORTS.value

    if re.search(
        r"\b(?:soccer|club friendl|conmebol|both score a goal"
        r"|liga de exp|czefl|dimayor|ekstraklasa|eliteserien"
        r"|hnl|perliga|scottish prem|ucl\b|uecl|ury pd"
        r"|bt ts)\b", text_lower,
    ):
        return Sport.SOCCER.value

    if re.search(r"\b(?:basketball|nba|wnba|pro basketball)\b", text_lower):
        return Sport.BASKETBALL.value

    if re.search(r"\b(?:football|nfl)\b", text_lower) and "soccer" not in text_lower:
        return Sport.FOOTBALL.value

    if re.search(
        r"\b(?:baseball|mlb|npb|kbo|lmb|rbi\b|home runs?\b|strikeouts?\b|"
        r"stolen bases?\b|total bases?\b|hits \+ runs|college baseball)\b",
        text_lower,
    ):
        return Sport.BASEBALL.value

    if re.search(r"\b(?:hockey|nhl)\b", text_lower):
        return Sport.HOCKEY.value

    if re.search(r"\b(?:tennis|atp|wta|itf)\b", text_lower):
        return Sport.TENNIS.value

    if re.search(r"\b(?:mma|ufc|mixed martial arts)\b", text_lower):
        return Sport.MMA.value

    return None


# ---------------------------------------------------------------------------
# Game extraction (esports)
# ---------------------------------------------------------------------------


def _extract_game(text: str, sport: str | None) -> str | None:
    if sport != Sport.ESPORTS.value:
        return None
    text_lower = text.lower()
    for slug, pattern in [
        ("league-of-legends", r"\bleague of legends\b"),
        ("dota2", r"\bdota\s*2\b"),
        ("cs2", r"\bcounter.?strike\b"),
        ("valorant", r"\bvalorant\b"),
        ("overwatch", r"\boverwatch\b"),
        ("rainbow-six", r"\brainbow\s*six\b"),
        ("rocket-league", r"\brocket\s*league\b"),
        ("call-of-duty", r"\bcall of duty\b"),
        ("apex-legends", r"\bapex\s*legends\b"),
    ]:
        if re.search(pattern, text_lower):
            return slug
    from prediction_bot.kalshi.discovery import classify_game
    return classify_game(text)


# ---------------------------------------------------------------------------
# Tournament extraction
# ---------------------------------------------------------------------------


def _extract_tournament(text: str) -> str | None:
    # Pattern 1: Esports colon — "in the <Tournament>: <teams>"
    m = re.search(r"in the (.+?):\s*(?:.+)", text)
    if m:
        candidate = m.group(1).strip()
        if _is_valid_tournament(candidate):
            return candidate

    # Pattern 1b: Esports match winner — "wins the <Tournament>: <teams>"
    m = re.search(r"wins the (.+?):\s*(?:.+)", text)
    if m:
        candidate = m.group(1).strip()
        if _is_valid_tournament(candidate):
            return candidate

    # Pattern 1c: Esports match winner — "wins <Tournament>: <teams>" (no "the")
    # Matches Dota 2 BLAST patterns: "If OG wins BLAST Slam 2026: OG vs LGD..."
    m = re.search(r"wins ([A-Z][\w\s]+?\d{4}):\s*(?:.+)", text)
    if m:
        candidate = m.group(1).strip()
        if _is_valid_tournament(candidate):
            return candidate

    # Pattern 2: "professional <Tournament> <sport>"
    m = re.search(
        r"professional (.+?) (?:soccer|basketball|football|baseball|hockey|tennis)\s",
        text, _F,
    )
    if m:
        candidate = m.group(1).strip()
        if len(candidate) > 2:
            return candidate

    # Pattern 3: "in the <Tournament> <sport/league>"
    m = re.search(
        r"in the (.+?) (?:League of Legends|soccer|basketball|football|"
        r"Japan NPB|Korea KBO|Mexico LMB|women's Pro Basketball|"
        r"professional|College Baseball)\b",
        text, _F,
    )
    if m:
        candidate = m.group(1).strip()
        if len(candidate) > 2 and _is_valid_tournament(candidate):
            return candidate

    # Pattern 4: "in the <Year> <Tournament>" (tennis)
    m = re.search(r"in the (\d{4} .+?) (?:Round|professional tennis)", text)
    if m:
        candidate = m.group(1).strip()
        if len(candidate) > 2:
            return candidate

    return None


def _is_valid_tournament(candidate: str) -> bool:
    if len(candidate) <= 3:
        return False
    team_prefixes = (
        r"^(?:the\s+)?(?:Chelsea|Western|AZ|Mental|T1\b|Gen\b|Dplus|KT\b|Hanwha|DRX|NS\b|"
        r"BRO|FearX|OK\b|G2\b|Fnatic|MAD|Cloud9|Liquid|FaZe|Navi|Vitality|Spirit|"
        r"RBIs\b|Seattle|Milwaukee|Texas|Tampa|Toronto|Washington|Arizona|Pittsburgh|"
        r"Atlanta|New York|Philadelphia|Miami|Houston|Los Angeles|San Francisco|"
        r"Essen|Ennepetal|York|Peterborough|Bushido|SU\b|BoostGate|PCIFIC|MVK|Team Secret|"
        r"Bilibili|Team WE|Shopify|Rebellion|Contra|2GAME|OLDBOYS|Fortress|NAVI|"
        r"usst\b|Midas|PlayTime|Rune|Leicester|Manchester|Birmingham|Bromley|QPR|"
        r"Southport|Wigan|Caracas|Independ|O.Higgins|Boca)"
    )
    return not re.search(team_prefixes, candidate, _F)


# ---------------------------------------------------------------------------
# Participant extraction
# ---------------------------------------------------------------------------


def _extract_participants(text: str) -> list[str] | None:
    # Strategy 1: "X vs Y" after colon (esports)
    m_colon = re.search(
        r":\s*(.+?vs\..+?)(?:\s+(?:League of Legends|Dota\s*2|CS2|Valorant|"
        r"Counter.?Strike|match|game|professional|soccer|originally))",
        text, _F,
    )
    if m_colon:
        result = _extract_vs(m_colon.group(1))
        if result:
            return result

    # Strategy 2: "in (the) X vs Y" — anchored
    m_in_vs = re.search(
        r"\bin\s+(?:the\s+)?(\w[\w\s.&'/\-]+?)\s+vs\.?\s+(\w[\w\s.&'/\-]+?)\s+professional\s+",
        text, _F,
    )
    if m_in_vs:
        a, b = m_in_vs.group(1).strip(), m_in_vs.group(2).strip()
        if _is_team_name(a) and _is_team_name(b):
            return [a, b]

    # Strategy 3: "wins the X vs Y" for match winners
    m_wins_vs = re.search(
        r"\bwins the (\w[\w\s.&'/\-]+?)\s+vs\.?\s+(\w[\w\s.&'/\-]+?)\s+"
        r"(?:professional|Japan NPB|Korea KBO|Mexico LMB|women's Pro Basketball)\b",
        text, _F,
    )
    if m_wins_vs:
        a, b = m_wins_vs.group(1).strip(), m_wins_vs.group(2).strip()
        if _is_team_name(a) and _is_team_name(b):
            return [a, b]

    # Strategy 4: Tennis — "X vs Y professional tennis match"
    m_tennis = re.search(
        r"(\w[\w\s./'\-]+?)\s+vs\.?\s+(\w[\w\s./'\-]+?)\s+professional\s+tennis\s+match",
        text, _F,
    )
    if m_tennis:
        a, b = m_tennis.group(1).strip(), m_tennis.group(2).strip()
        if _is_participant_name(a) and _is_participant_name(b):
            return [a, b]

    # Strategy 5: "X and Y" pattern for totals/BTTS
    m_and = re.search(
        r"(\w[\w\s.&'/\-]+?)\s+and\s+(\w[\w\s.&'/\-]+?)\s+(?:collectively|both)\s",
        text, _F,
    )
    if m_and:
        a, b = m_and.group(1).strip(), m_and.group(2).strip()
        if _is_team_name(a) and _is_team_name(b) and a != b:
            return [a, b]

    # Strategy 6: Esports/Asian baseball near game/match boundary
    for pat in [
        r"(\w[\w\s.&'/\-]+?)\s+vs\.?\s+(\w[\w\s.&'/\-]+?)\s+(?:League of Legends|"
        r"Dota\s*2|CS2|Valorant|Japan NPB|Korea KBO|Mexico LMB|women's Pro Basketball)\b",
        r"(\w[\w\s.&'/\-]+?)\s+vs\.?\s+(\w[\w\s.&'/\-]+?)\s+(?:game|match)\b",
    ]:
        m = re.search(pat, text, _F)
        if m:
            a, b = m.group(1).strip(), m.group(2).strip()
            if _is_team_name(a) and _is_team_name(b):
                return [a, b]

    return None


def _extract_vs(section: str) -> list[str] | None:
    m = re.search(r"(.+?)\s+vs\.?\s+(.+?)$", section, _F)
    if m:
        a, b = m.group(1).strip(), m.group(2).strip()
        if 1 <= len(a) < 60 and 1 <= len(b) < 60:
            return [a, b]
    return None


def _is_team_name(name: str) -> bool:
    if not name or len(name) < 2 or len(name) > 60:
        return False
    return not re.search(r"\b(?:RBIs|runs|stolen|hits|strikeouts?|total bases)\b", name, _F)


def _is_participant_name(name: str) -> bool:
    if not name or len(name) < 2 or len(name) > 80:
        return False
    garbage = (
        r"^(?:over|under|more than|less than|at least|in|the|a|an|"
        r"professional|originally|scheduled|after|then|records?|"
        r"scored?|played?|resolves?|if|wins?)\b"
    )
    return not re.search(garbage, name, _F)


# ---------------------------------------------------------------------------
# Contract type classification
# ---------------------------------------------------------------------------


def _classify_contract_type(yes_outcome: str, full_text: str) -> str:
    """Classify what kind of contract this is from the yes_outcome text."""
    combined = (yes_outcome + " " + full_text).lower()

    # Map/set winner (most specific)
    if re.search(r"wins?\s+map\s+\d+", combined, _F):
        return ContractType.MAP_WINNER.value
    if re.search(r"wins?\s+set\s+\d+", combined, _F):
        return ContractType.SET_WINNER.value

    # Totals
    if re.search(r"over\s+[\d.]+\s+(?:goals|points|runs)\s+(?:are|is)\s+scored", combined, _F):
        return ContractType.TOTAL_GOALS.value
    if re.search(r"over\s+[\d.]+\s+maps?\s+(?:are|is)\s+played", combined, _F):
        return ContractType.TOTAL_MAPS.value
    if re.search(r"(?:number of completed games|above\s+[\d.]+\s+games)\b", combined, _F):
        return ContractType.TOTAL_GAMES.value
    if re.search(r"collectively score more than [\d.]+", combined, _F):
        return ContractType.TOTAL_RUNS.value

    # Soccer match winner
    if re.search(
        r"wins?\s+the\s+.+?vs\s+.+?\s+professional\s+.+?\s+"
        r"(?:soccer|basketball|football|baseball|hockey)\s+game",
        combined, _F,
    ):
        return ContractType.MATCH_WINNER.value

    # Tie/Draw
    if re.search(
        r"(?:Tie|Draw)\s+is\s+the\s+result\s+of\s+the\s+.+?vs\s+.+?\s+professional",
        combined, _F,
    ):
        return ContractType.MATCH_WINNER.value

    # Esports match winner
    if re.search(
        r"wins?\s+the\s+\w.+?:\s+\w.+?\b(?:League of Legends|Dota\s*2|CS2|Valorant)\b",
        combined, _F,
    ):
        return ContractType.MATCH_WINNER.value

    # Esports double colon
    if re.search(
        r"wins?\s+the\s+\w.+?: .+?: \w.+?\b(?:Valorant|League of Legends|CS2)\b",
        combined, _F,
    ):
        return ContractType.MATCH_WINNER.value

    # Dota2 no-"the"
    if re.search(r"wins?\s+\w+\s+\w+\s+\d{4}:\s+\w.+?\bDota\s*2\b", combined, _F):
        return ContractType.MATCH_WINNER.value

    # Asian baseball
    if re.search(
        r"wins?\s+the\s+.+?vs\s+.+?\s+"
        r"(?:Japan NPB|Korea KBO|Mexico LMB|women's Pro Basketball)\b",
        combined, _F,
    ):
        return ContractType.MATCH_WINNER.value

    # Tennis
    if re.search(
        r"wins?\s+the\s+.+?vs\s+.+?\s+professional\s+tennis\s+match",
        combined, _F,
    ):
        return ContractType.MATCH_WINNER.value

    # Generic "wins the match"
    if re.search(r"wins?\s+(?:the\s+)?match\b", combined, _F):
        return ContractType.MATCH_WINNER.value

    # Tournament winner
    if re.search(
        r"wins?\s+the\s+\d{4}\s+\w+\s+professional\s+tennis\s+tournament",
        combined, _F,
    ):
        return ContractType.TOURNAMENT_WINNER.value
    if re.search(r"wins?\s+(?:the\s+)?tournament", combined, _F):
        return ContractType.TOURNAMENT_WINNER.value
    if re.search(r"wins?\s+(?:the\s+)?series", combined, _F):
        return ContractType.SERIES_WINNER.value

    # Player props (baseball)
    if re.search(
        r"records?\s+\d+[+]\s+(?:RBIs|home\s+runs?|hits|strikeouts?|stolen\s+bases?|"
        r"total\s+bases?|total\s+hits\s*\+\s*runs)",
        combined, _F,
    ):
        return ContractType.PLAYER_PROP.value

    # Both teams to score
    if re.search(r"both\s+score\s+a\s+goal", combined, _F):
        return ContractType.BTTS.value

    # Spread / handicap
    if re.search(r"win\s+by\s+more\s+than\s+[\d.]+\s+runs?", combined, _F):
        return ContractType.SPREAD.value
    if re.search(
        r"game\s+differential\s+in\s+favor\s+of\s+.+?\s+is\s+above\s+[\d.]+",
        combined, _F,
    ):
        return ContractType.SPREAD.value
    if re.search(r"(?:handicap|spread)", combined, _F):
        return ContractType.SPREAD.value

    # Generic Tie/Draw at start
    if re.search(r"^(?:Tie|Draw)\s+is\s+the\s+result", combined, _F):
        return ContractType.MATCH_WINNER.value

    return ContractType.OTHER.value


# ---------------------------------------------------------------------------
# Threshold extraction
# ---------------------------------------------------------------------------


def _extract_threshold(yes_outcome: str, full_text: str) -> float | None:
    """Extract numeric threshold from totals/spreads."""
    combined = yes_outcome + " " + full_text

    m = re.search(
        r"over\s+([\d.]+)\s+(?:goals|points|maps|games|runs)\s+(?:are|is)\s+(?:scored|played)",
        combined, _F,
    )
    if m:
        return float(m.group(1))

    m = re.search(r"collectively score more than ([\d.]+)\s+runs?", combined, _F)
    if m:
        return float(m.group(1))

    m = re.search(r"win\s+by\s+more\s+than\s+([\d.]+)\s+runs?", combined, _F)
    if m:
        return float(m.group(1))

    m = re.search(r"above\s+([\d.]+)\s+games", combined, _F)
    if m:
        return float(m.group(1))

    m = re.search(r"above\s+([\d.]+)\s+in\s+the", combined, _F)
    if m:
        return float(m.group(1))

    m = re.search(r"(?:handicap|spread)\s*[:\s]+([+-]?[\d.]+)", combined, _F)
    if m:
        return float(m.group(1))

    m = re.search(
        r"records?\s+(\d+)\+\s+(?:RBIs|home\s+runs?|hits|strikeouts?|stolen\s+bases?|"
        r"total\s+bases?)",
        combined, _F,
    )
    if m:
        return float(m.group(1))

    return None


# ---------------------------------------------------------------------------
# Normalized schemas
# ---------------------------------------------------------------------------


class NormalizedContract(BaseModel):
    """A single Kalshi market contract, parsed from rules_primary."""

    ticker: str = Field(..., description="Kalshi market ticker")
    event_ticker: str = Field(..., description="Kalshi event ticker")
    contract_type: str = Field(
        default=ContractType.OTHER.value,
        description="What kind of contract: map_winner, match_winner, etc.",
    )
    sport: str | None = Field(default=None)
    game: str | None = Field(default=None)
    yes_outcome: str | None = Field(default=None)
    tournament: str | None = Field(default=None)
    participants: list[str] | None = Field(default=None)
    map_number: int | None = Field(default=None)
    threshold: float | None = Field(default=None)
    rules_primary: str | None = Field(default=None)
    title: str | None = Field(default=None)
    yes_sub_title: str | None = Field(default=None)
    no_sub_title: str | None = Field(default=None)
    close_time: datetime | None = Field(default=None)


class UnderlyingEvent(BaseModel):
    """The underlying event that one or more contracts reference."""

    event_id: str = Field(...)
    sport: str | None = Field(default=None)
    game: str | None = Field(default=None)
    tournament: str | None = Field(default=None)
    participants: list[str] = Field(default_factory=list)
    start_time: datetime | None = Field(default=None)
    contract_types: list[str] = Field(default_factory=list)

    @field_validator("participants")
    @classmethod
    def participants_not_empty(cls, v: list[str]) -> list[str]:
        stripped = [p.strip() for p in v if p.strip()]
        if not stripped:
            raise ValueError("participants must contain at least one non-empty entry")
        return stripped

    @property
    def team_a(self) -> str:
        return self.participants[0] if self.participants else ""

    @property
    def team_b(self) -> str:
        return self.participants[1] if len(self.participants) > 1 else ""


# ---------------------------------------------------------------------------
# Normalizer
# ---------------------------------------------------------------------------


def normalize_contract(raw: dict[str, Any]) -> NormalizedContract:
    """Normalize a raw Kalshi market dict into a NormalizedContract.

    Parsing priority:
      1. ticker prefix — primary source for contract_type, sport, game
      2. rules_primary — authoritative for yes_outcome, tournament,
         participants; fallback for contract_type/sport/game
      3. title — fallback for contract_type, map_number, participants
      4. yes_sub_title / no_sub_title — supplementary outcome descriptions

    Contract type can be known while other fields remain unknown.
    """
    ticker = raw.get("ticker", "") or ""
    rules = raw.get("rules_primary", "") or ""
    title = raw.get("title", "") or ""

    # ── Tier 1: Ticker prefix (100% reliable, machine-generated) ──
    ticker_parsed = parse_ticker(ticker)

    # ── Tier 2: rules_primary (authoritative human description) ──
    rp_parsed = parse_rules_primary(rules)

    # ── Tier 3: Title (user-visible fallback) ──
    title_parsed = parse_title(title)

    # Merge with priority: ticker > rules_primary > title
    contract_type = (
        ticker_parsed["contract_type"]
        or rp_parsed.get("contract_type")
        or title_parsed.get("contract_type")
    )
    sport = (
        ticker_parsed["sport"]
        or rp_parsed.get("sport")
    )
    game = (
        ticker_parsed["game"]
        or rp_parsed.get("game")
    )
    # Detail fields: rules_primary is authoritative, title fills gaps
    yes_outcome = rp_parsed.get("yes_outcome")
    tournament = rp_parsed.get("tournament")
    map_number = rp_parsed.get("map_number") or title_parsed.get("map_number")
    participants = rp_parsed.get("participants") or title_parsed.get("participants")
    threshold = rp_parsed.get("threshold") or title_parsed.get("threshold")

    close_time = None
    raw_close = raw.get("close_time")
    if raw_close:
        close_time = _parse_iso_datetime(raw_close)
    return NormalizedContract(
        ticker=ticker,
        event_ticker=raw.get("event_ticker", ""),
        contract_type=contract_type or ContractType.OTHER.value,
        sport=sport,
        game=game,
        yes_outcome=yes_outcome,
        tournament=tournament,
        participants=participants,
        map_number=map_number,
        threshold=threshold,
        rules_primary=rules or None,
        title=title or None,
        yes_sub_title=raw.get("yes_sub_title"),
        no_sub_title=raw.get("no_sub_title"),
        close_time=close_time,
    )


def build_event(contracts: list[NormalizedContract]) -> UnderlyingEvent | None:
    if not contracts:
        return None
    event_ids = {c.event_ticker for c in contracts}
    if len(event_ids) != 1:
        raise ValueError(f"All contracts must share the same event_ticker, got: {event_ids}")
    first = contracts[0]
    participants: list[str] = []
    for c in contracts:
        if c.participants:
            for p in c.participants:
                if p not in participants:
                    participants.append(p)
    contract_types: list[str] = []
    for c in contracts:
        ct = c.contract_type
        if ct and ct not in contract_types:
            contract_types.append(ct)
    return UnderlyingEvent(
        event_id=first.event_ticker,
        sport=first.sport,
        game=first.game,
        tournament=first.tournament,
        participants=participants,
        start_time=first.close_time,
        contract_types=contract_types,
    )


# ---------------------------------------------------------------------------
# Prediction schemas
# ---------------------------------------------------------------------------


class PredictionRequest(BaseModel):
    event_id: str = Field(...)
    game: str | None = Field(default=None)
    tournament: str | None = Field(default=None)
    participants: list[str] = Field(default_factory=list)
    contract_types: list[str] = Field(default_factory=list)
    start_time: datetime | None = Field(default=None)
    available_information: dict[str, Any] = Field(default_factory=dict)

    @property
    def team_a(self) -> str:
        return self.participants[0] if self.participants else ""

    @property
    def team_b(self) -> str:
        return self.participants[1] if len(self.participants) > 1 else ""

    def to_research_prompt(self) -> str:
        return build_research_prompt(self)


class PredictionResponse(BaseModel):
    event_id: str = Field(...)
    predicted_winner: str = Field(...)
    team_a_probability: float = Field(..., ge=0.0, le=1.0)
    team_b_probability: float = Field(..., ge=0.0, le=1.0)
    confidence: PredictionConfidence = Field(...)
    abstain: bool = False
    reasoning_summary: str = Field(...)
    key_factors: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)

    @field_validator("team_a_probability", "team_b_probability")
    @classmethod
    def probabilities_must_be_valid(cls, v: float) -> float:
        if v < 0.0 or v > 1.0:
            raise ValueError(f"Probability must be between 0 and 1, got {v}")
        return v

    @field_validator("team_b_probability")
    @classmethod
    def probabilities_sum_to_one(cls, v: float, info: Any) -> float:
        prob_a = info.data.get("team_a_probability")
        if prob_a is not None and abs(prob_a + v - 1.0) > 0.001:
            raise ValueError(
                f"Probabilities must sum to approximately 1.0, got {prob_a} + {v}"
            )
        return v

    @model_validator(mode="after")
    def validate_consistency(self) -> PredictionResponse:
        if self.abstain:
            if self.predicted_winner.lower() != "abstain":
                raise ValueError("When abstain=True, predicted_winner must be 'abstain'")
            if self.confidence != PredictionConfidence.LOW:
                raise ValueError("When abstain=True, confidence must be 'low'")
            if abs(self.team_a_probability - 0.5) > 0.01:
                raise ValueError("When abstain=True, team_a_probability ~0.5")
            if abs(self.team_b_probability - 0.5) > 0.01:
                raise ValueError("When abstain=True, team_b_probability ~0.5")
        elif self.predicted_winner.lower() == "abstain":
            raise ValueError("predicted_winner='abstain' but abstain=False")
        return self


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def build_research_prompt(request: PredictionRequest) -> str:
    game_str = request.game or "Unknown"
    tournament_str = request.tournament or "Unknown"
    start_str = request.start_time.isoformat() if request.start_time else "Unknown"
    team_a = request.team_a or "Team A"
    team_b = request.team_b or "Team B"

    info_lines: list[str] = []
    if request.available_information:
        info_lines.append("")
        info_lines.append("## Available Information")
        info_lines.append("")
        for key, value in request.available_information.items():
            info_lines.append(f"- **{key}**: {value}")

    return f"""You are an independent esports analyst estimating win probability.

## Task
Estimate the probability that each team wins this match. Your output must be a
valid JSON object matching the PredictionResponse schema.

## Important Rules
- Estimate probability, do NOT give betting advice.
- Consider: team strength, recent performance, roster stability, tournament
  importance, match format, historical matchup results, and the
  quality/quantity of available information.
- Do NOT fabricate statistics. If you don't know a fact, work with what you have.
- Separate known facts from assumptions.
- If information is severely insufficient, set abstain=true, confidence=low,
  and assign 0.5/0.5 probabilities.
- Probabilities must sum to 1.0.

## Match Details
- **Event ID**: {request.event_id}
- **Game**: {game_str}
- **Tournament**: {tournament_str}
- **Teams**: {team_a} vs {team_b}
- **Start Time**: {start_str}
- **Contract Types**: {', '.join(request.contract_types) if request.contract_types else 'Unknown'}
{chr(10).join(info_lines)}

## Required Output Format
Respond with ONLY a valid JSON object (no markdown fences, no surrounding text):

{{
  "event_id": "{request.event_id}",
  "predicted_winner": "<team name or 'abstain'>",
  "team_a_probability": <float 0.0-1.0>,
  "team_b_probability": <float 0.0-1.0>,
  "confidence": "low" | "medium" | "high",
  "abstain": true | false,
  "reasoning_summary": "<brief summary>",
  "key_factors": ["<factor 1>", "<factor 2>", ...],
  "risk_flags": ["<risk 1>", "<risk 2>", ...]
}}
"""


# ---------------------------------------------------------------------------
# Shared util
# ---------------------------------------------------------------------------


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        from datetime import timezone
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None
