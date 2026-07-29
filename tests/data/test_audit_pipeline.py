"""Integration tests: raw Kalshi market → normalize_contract() → audit entry.

Verifies that the audit pipeline consumes NormalizedContract fields
(contract_type, sport, game) and does not bypass normalization.
"""

from __future__ import annotations

from prediction_bot.agents.schema import normalize_contract, ContractType, Sport
from prediction_bot.scripts.audit import _build_audit_entry


# ── Real Kalshi market examples ──


_KXLOLMAP_RAW = {
    "ticker": "KXLOLMAP-26JUL281430AZREMR-2-MR",
    "event_ticker": "KXLOLMAP-26JUL281430AZREMR-2",
    "title": "Will Mental Rush win map 2 in the AZ Rising Eterna vs. Mental Rush match?",
    "yes_sub_title": "Mental Rush",
    "no_sub_title": "Mental Rush",
    "rules_primary": (
        "If Mental Rush wins map 2 in the Equal eSports Cup 2026: "
        "AZ Rising Eterna vs. Mental Rush League of Legends match "
        "originally scheduled for Jul 28, 2026 at 2:30 PM EDT, "
        "then the market resolves to Yes."
    ),
    "yes_bid_dollars": "0.5600",
    "yes_ask_dollars": "0.5900",
    "no_bid_dollars": "0.4000",
    "no_ask_dollars": "0.4300",
    "last_price_dollars": "0.5600",
    "volume_fp": "100.00",
    "open_interest_fp": "40.00",
    "yes_bid_size_fp": "10.00",
    "yes_ask_size_fp": "25.00",
    "liquidity_dollars": "500.00",
    "close_time": "2026-07-30T18:30:00Z",
    "status": "open",
    "category": None,
}

_CS2GAME_RAW = {
    "ticker": "KXCS2GAME-26JUL281430OLDFOR-OLD",
    "event_ticker": "KXCS2GAME-26JUL281430OLDFOR",
    "title": "Will OLDBOYS- win the OLDBOYS- vs. Fortress CS2 match?",
    "yes_sub_title": "OLDBOYS-",
    "no_sub_title": "OLDBOYS-",
    "rules_primary": (
        "If OLDBOYS- wins the ESEA Advanced Europe 2026: "
        "OLDBOYS- vs. Fortress CS2 match "
        "originally scheduled for Jul 28, 2026 at 2:30 PM EDT, "
        "then the market resolves to Yes."
    ),
    "close_time": "2026-07-30T18:30:00Z",
}

_BASEBALL_RBI_RAW = {
    "ticker": "KXMLBRBI-26JUL282210SEALAD-SEARAROZARENA56-2",
    "event_ticker": "KXMLBRBI-26JUL282210SEALAD",
    "title": "Randy Arozarena: 2+ RBIs?",
    "yes_sub_title": "Randy Arozarena: 2+",
    "no_sub_title": "Randy Arozarena: 2+",
    "rules_primary": (
        "If Randy Arozarena records 2+ RBIs in Seattle vs Los Angeles D "
        "professional baseball game originally scheduled for "
        "Jul 28, 2026 at 10:10 PM EDT, "
        "then the market resolves to Yes."
    ),
    "close_time": "2026-07-31T02:10:00Z",
}


class TestNormalizeContractAuditPipeline:
    """verify that normalize_contract() feeds into audit entries correctly."""

    def test_kxlolmap_contract_type(self) -> None:
        """KXLOLMAP ticker → map_winner."""
        nc = normalize_contract(_KXLOLMAP_RAW)
        entry = _build_audit_entry(_KXLOLMAP_RAW, nc)

        assert entry.contract_type == ContractType.MAP_WINNER.value
        assert entry.sport == Sport.ESPORTS.value
        assert entry.game == "league-of-legends"
        assert entry.ticker == "KXLOLMAP-26JUL281430AZREMR-2-MR"

    def test_kxlolmap_has_yes_outcome(self) -> None:
        """rules_primary provides yes_outcome through normalization."""
        nc = normalize_contract(_KXLOLMAP_RAW)
        assert nc.yes_outcome is not None
        assert "Mental Rush" in (nc.yes_outcome or "")
        assert "map 2" in (nc.yes_outcome or "")

    def test_cs2game_contract_type(self) -> None:
        """KXCS2GAME ticker → match_winner with cs2 game."""
        nc = normalize_contract(_CS2GAME_RAW)
        entry = _build_audit_entry(_CS2GAME_RAW, nc)

        assert entry.contract_type == ContractType.MATCH_WINNER.value
        assert entry.sport == Sport.ESPORTS.value
        assert entry.game == "cs2"

    def test_baseball_rbi_contract_type(self) -> None:
        """KXMLBRBI ticker → player_prop with baseball sport."""
        nc = normalize_contract(_BASEBALL_RBI_RAW)
        entry = _build_audit_entry(_BASEBALL_RBI_RAW, nc)

        assert entry.contract_type == ContractType.PLAYER_PROP.value
        assert entry.sport == Sport.BASEBALL.value
        assert entry.game is None  # traditional sport, no game field

    def test_entry_carries_price_fields(self) -> None:
        """Audit entry retains raw price/volume data."""
        nc = normalize_contract(_KXLOLMAP_RAW)
        entry = _build_audit_entry(_KXLOLMAP_RAW, nc)

        assert entry.yes_bid is not None
        assert entry.yes_ask is not None
        assert entry.spread is not None

    def test_metadata_gap_when_no_contract_type(self) -> None:
        """Markets with unknown ticker AND unrecognizable title get gaps."""
        raw = dict(_KXLOLMAP_RAW)
        raw["ticker"] = "KXUNKNOWN-01"
        raw["title"] = "Some completely unrecognizable market title"
        raw["rules_primary"] = "If something happens, then the market resolves to Yes."
        nc = normalize_contract(raw)
        entry = _build_audit_entry(raw, nc)

        assert "unclassified_contract_type" in entry.metadata_gaps

    def test_metadata_gap_when_good_ticker(self) -> None:
        """Known ticker prefix → no unclassified gaps for ct/sport/game."""
        nc = normalize_contract(_KXLOLMAP_RAW)
        entry = _build_audit_entry(_KXLOLMAP_RAW, nc)

        assert "unclassified_contract_type" not in entry.metadata_gaps
        assert "unclassified_sport" not in entry.metadata_gaps
