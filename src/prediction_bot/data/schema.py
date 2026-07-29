"""Core data schemas for the prediction_bot system.

All schemas use Pydantic for validation and serialization.
Timestamps are timezone-aware UTC datetime objects.

Price fields (probabilities) use Decimal for exact arithmetic.
Quantity fields (volume, open interest, sizes) use Decimal.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TournamentTier(str, Enum):
    """Competition tier classification."""
    S = "S"
    A = "A"
    B = "B"
    C = "C"
    UNKNOWN = "unknown"


class MatchFormat(str, Enum):
    """Series format for a match."""
    BO1 = "BO1"
    BO3 = "BO3"
    BO5 = "BO5"
    UNKNOWN = "unknown"


class PlayerRole(str, Enum):
    """League of Legends position."""
    TOP = "top"
    JUNGLE = "jungle"
    MID = "mid"
    ADC = "adc"
    SUPPORT = "support"
    UNKNOWN = "unknown"


class GameSide(str, Enum):
    """Which side a team played on."""
    BLUE = "blue"
    RED = "red"


class MarketSide(str, Enum):
    """Which side of a binary contract."""
    YES = "yes"
    NO = "no"


class DecisionStatus(str, Enum):
    """Hermes review decision."""
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    FLAG = "FLAG"


class TradeStatus(str, Enum):
    """Paper trade lifecycle states."""
    OPEN = "open"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"
    VOID = "void"


class ResolutionOutcome(str, Enum):
    """Trade resolution result."""
    WON = "won"
    LOST = "lost"
    VOID = "void"


class MatchConfidence(str, Enum):
    """Confidence level for event matching."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


# ---------------------------------------------------------------------------
# Esports domain schemas
# ---------------------------------------------------------------------------

class Team(BaseModel):
    """A competitive esports team."""
    team_id: str = Field(..., description="Canonical slug, e.g. 't1', 'g2-esports'")
    name: str = Field(..., description="Display name")
    region: str | None = Field(default=None, description="LCK, LPL, LEC, LCS, etc.")
    aliases: list[str] = Field(default_factory=list, description="Known alternative names")


class Player(BaseModel):
    """A professional esports player."""
    player_id: str = Field(..., description="Canonical slug")
    name: str = Field(..., description="Display name")
    role: PlayerRole = Field(default=PlayerRole.UNKNOWN)
    aliases: list[str] = Field(default_factory=list)


class Roster(BaseModel):
    """A team roster at a point in time."""
    roster_id: int | None = None
    team_id: str
    players: list[str] = Field(default_factory=list, description="List of player_ids")
    effective_from: datetime
    effective_to: datetime | None = None

    @field_validator("effective_to")
    @classmethod
    def effective_to_after_from(cls, v: datetime | None, info: Any) -> datetime | None:
        effective_from = info.data.get("effective_from")
        if v is not None and effective_from is not None and v <= effective_from:
            raise ValueError("effective_to must be after effective_from")
        return v


class Tournament(BaseModel):
    """An esports tournament or league."""
    tournament_id: str = Field(..., description="Canonical ID")
    name: str
    tier: TournamentTier = TournamentTier.UNKNOWN
    region: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None


class MatchResult(BaseModel):
    """A completed or upcoming esports match."""
    match_id: str = Field(..., description="Canonical match identifier")
    tournament_id: str | None = None
    team_a_id: str
    team_b_id: str
    format: MatchFormat = MatchFormat.UNKNOWN
    patch: str | None = Field(default=None, description="e.g. '14.12'")
    scheduled_time: datetime
    actual_start_time: datetime | None = None
    winner: str | None = Field(default=None, description="team_id of winner; null if unplayed")
    cancelled: bool = False

    @field_validator("winner")
    @classmethod
    def winner_must_be_participant(cls, v: str | None, info: Any) -> str | None:
        if v is not None:
            team_a = info.data.get("team_a_id")
            team_b = info.data.get("team_b_id")
            if v not in (team_a, team_b):
                raise ValueError(f"Winner '{v}' must be one of the participating teams")
        return v


class EsportsEvent(BaseModel):
    """A scheduled or completed esports event (match + context)."""
    match: MatchResult
    tournament: Tournament | None = None
    team_a: Team | None = None
    team_b: Team | None = None


# ---------------------------------------------------------------------------
# Kalshi schemas
# ---------------------------------------------------------------------------

def _parse_price_dollars(raw: Any) -> Decimal | None:
    """Parse a Kalshi *_dollars field into a Decimal probability (0-1).

    New API fields like yes_bid_dollars are already in 0-1 range.
    """
    if raw is None:
        return None
    return Decimal(str(raw))


def _parse_price_cents(raw: Any) -> Decimal | None:
    """Parse an old-style cent-based price field.

    Values > 1 are assumed to be cents and divided by 100.
    Values in [0, 1] are used directly.
    """
    if raw is None:
        return None
    val = Decimal(str(raw))
    if val > 1:
        return val / 100
    return val


def _parse_fp_quantity(raw: Any) -> Decimal | None:
    """Parse a Kalshi *_fp fixed-point quantity field."""
    if raw is None:
        return None
    return Decimal(str(raw))


class KalshiMarket(BaseModel):
    """A Kalshi prediction market.

    Uses Decimal for all price and quantity fields to avoid
    floating-point rounding errors in bid/ask arithmetic.

    New API fields (*_dollars, *_fp) are preferred. Old cent-based
    fields are supported as fallbacks.
    """

    ticker: str = Field(..., description="Market ticker symbol")
    event_ticker: str = Field(..., description="Parent event ticker")
    title: str = Field(..., description="Market title/description")
    subtitle: str | None = Field(default=None, description="Market subtitle")
    yes_sub_title: str | None = Field(default=None, description="YES outcome description")
    no_sub_title: str | None = Field(default=None, description="NO outcome description")
    category: str | None = Field(default=None, description="Market category")
    rules_primary: str | None = Field(default=None, description="Primary contract rule text")
    close_time: datetime | None = Field(default=None, description="When the market closes")
    status: str | None = Field(default=None, description="Market status")

    # Prices (probabilities 0-1), parsed from *_dollars fields preferentially
    yes_bid: Decimal | None = Field(default=None, description="Best bid for YES")
    yes_ask: Decimal | None = Field(default=None, description="Best ask for YES")
    no_bid: Decimal | None = Field(default=None, description="Best bid for NO")
    no_ask: Decimal | None = Field(default=None, description="Best ask for NO")
    last_price: Decimal | None = Field(default=None, description="Last traded price")

    # Quantities (contracts / shares), parsed from *_fp fields
    volume: Decimal | None = Field(default=None, description="Total volume traded")
    volume_24h: Decimal | None = Field(default=None, description="24h volume")
    open_interest: Decimal | None = Field(default=None, description="Number of open contracts")
    yes_bid_size: Decimal | None = Field(default=None, description="Size at best YES bid")
    yes_ask_size: Decimal | None = Field(default=None, description="Size at best YES ask")

    # Liquidity
    liquidity: Decimal | None = Field(default=None, description="Liquidity in dollars")

    # Matching metadata
    matched_match_id: str | None = Field(default=None, description="Internal match_id if matched")
    matched_team: str | None = Field(default=None, description="Which team this side represents")
    match_confidence: MatchConfidence = Field(default=MatchConfidence.NONE)
    estimated_game: str | None = Field(default=None, description="Classified esport game")

    @property
    def spread(self) -> Decimal | None:
        """Computed bid-ask spread (ask - bid), or None if either side missing."""
        if self.yes_bid is not None and self.yes_ask is not None:
            return self.yes_ask - self.yes_bid
        return None

    @property
    def midpoint(self) -> Decimal | None:
        """Midpoint price: (bid + ask) / 2, or None if either side missing."""
        if self.yes_bid is not None and self.yes_ask is not None:
            return (self.yes_bid + self.yes_ask) / 2
        return None


class KalshiOrderBookSnapshot(BaseModel):
    """A point-in-time snapshot of a Kalshi order book."""

    market_ticker: str
    captured_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    best_bid: Decimal | None = None
    best_ask: Decimal | None = None
    bid_depth: Decimal | None = Field(default=None, description="Volume at best bid")
    ask_depth: Decimal | None = Field(default=None, description="Volume at best ask")
    spread: Decimal | None = Field(default=None, description="ask - bid")
    midpoint: Decimal | None = Field(default=None, description="(bid + ask) / 2")
    last_price: Decimal | None = None

    def model_post_init(self, __context: Any) -> None:
        """Compute derived fields if not explicitly set."""
        if self.spread is None and self.best_bid is not None and self.best_ask is not None:
            self.spread = self.best_ask - self.best_bid
        if self.midpoint is None and self.best_bid is not None and self.best_ask is not None:
            self.midpoint = (self.best_bid + self.best_ask) / 2

    def executable_price_yes(self) -> Decimal | None:
        """Price to buy YES: the best ask."""
        return self.best_ask

    def executable_price_no(self) -> Decimal | None:
        """Price to buy NO: 1 - best_bid."""
        if self.best_bid is not None:
            return Decimal("1") - self.best_bid
        return None

    def executable_price_for_side(self, side: MarketSide) -> Decimal | None:
        """Executable price for a given side."""
        if side == MarketSide.YES:
            return self.executable_price_yes()
        return self.executable_price_no()


# ---------------------------------------------------------------------------
# Model and prediction schemas
# ---------------------------------------------------------------------------

class ModelPrediction(BaseModel):
    """A model's probability prediction for a match."""
    prediction_id: int | None = None
    match_id: str
    model_version: str = Field(..., description="Hash or version tag")
    as_of_time: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    prob_team_a: float = Field(..., ge=0.0, le=1.0, description="Calibrated probability for team A")
    prob_team_b: float = Field(..., ge=0.0, le=1.0, description="Calibrated probability for team B")
    uncertainty: float | None = Field(default=None, ge=0.0, description="Model uncertainty estimate")
    is_ood: bool = Field(default=False, description="Out-of-distribution flag")

    @field_validator("prob_team_b")
    @classmethod
    def probabilities_sum_to_one(cls, v: float, info: Any) -> float:
        prob_a = info.data.get("prob_team_a")
        if prob_a is not None and abs(prob_a + v - 1.0) > 0.001:
            raise ValueError("prob_team_a + prob_team_b must sum to approximately 1.0")
        return v


# ---------------------------------------------------------------------------
# Paper trading schemas
# ---------------------------------------------------------------------------

class PaperTradeDecision(BaseModel):
    """A paper trade decision produced by the strategy/hermes layer."""
    trade_id: int | None = None
    recommendation_id: str | None = None
    match_id: str
    market_ticker: str
    side: MarketSide
    entry_price: float = Field(..., gt=0.0, le=1.0, description="Executable price at which position was taken")
    quantity: int = Field(..., gt=0, description="Number of contracts")
    notional: float = Field(..., gt=0, description="quantity * entry_price")
    placed_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    status: TradeStatus = TradeStatus.OPEN
    decision: DecisionStatus = Field(..., description="Hermes review decision")
    p_model: float = Field(..., ge=0.0, le=1.0, description="Model probability at entry")
    p_conservative: float = Field(..., ge=0.0, le=1.0, description="Uncertainty-adjusted probability at entry")
    raw_edge: float = Field(..., description="p_conservative - p_market")
    net_edge: float = Field(..., description="raw_edge minus costs")
    hermes_version: str | None = None


# ---------------------------------------------------------------------------
# Audit report schemas
# ---------------------------------------------------------------------------

class MetadataGap(str, Enum):
    """Categories of missing or problematic metadata in a market."""
    UNCLASSIFIED_CONTRACT_TYPE = "unclassified_contract_type"
    UNCLASSIFIED_GAME = "unclassified_game"
    UNCLASSIFIED_SPORT = "unclassified_sport"
    MISSING_BID = "missing_bid"
    MISSING_ASK = "missing_ask"
    ZERO_VOLUME = "zero_volume"
    ZERO_OPEN_INTEREST = "zero_open_interest"
    MISSING_CLOSE_TIME = "missing_close_time"
    MISSING_CATEGORY = "missing_category"
    AMBIGUOUS_TITLE = "ambiguous_title"


class EsportsMarketAuditEntry(BaseModel):
    """A single row in the esports market audit report."""

    title: str
    ticker: str
    event_ticker: str
    yes_sub_title: str | None = None
    no_sub_title: str | None = None
    # ── Normalized fields (from normalize_contract) ──
    contract_type: str | None = Field(
        default=None,
        description="Contract type from ticker/rules_primary/title: map_winner, match_winner, etc.",
    )
    sport: str | None = Field(
        default=None,
        description="Sport classification: esports, soccer, baseball, etc.",
    )
    game: str | None = Field(
        default=None,
        description="Esports game slug, or None for traditional sports",
    )
    # ── Legacy / raw fields ──
    estimated_game: str | None = Field(
        default=None,
        description="DEPRECATED: use 'game' field instead. Kept for backward compat.",
    )
    category: str | None = None
    close_time: datetime | None = None
    volume: Decimal | None = None
    open_interest: Decimal | None = None
    yes_bid: Decimal | None = None
    yes_ask: Decimal | None = None
    no_bid: Decimal | None = None
    no_ask: Decimal | None = None
    spread: Decimal | None = None
    last_price: Decimal | None = None
    bid_size: Decimal | None = Field(default=None, description="Size at best YES bid")
    ask_size: Decimal | None = Field(default=None, description="Size at best YES ask")
    liquidity: Decimal | None = None
    status: str | None = None
    snapshot_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    metadata_gaps: list[str] = Field(
        default_factory=list,
        description="Specific metadata gap categories (see MetadataGap enum)",
    )


class FeasibilityReport(BaseModel):
    """Summary report of the esports market feasibility audit."""

    total_markets: int = 0
    total_sports_markets: int = 0
    # ── Normalized breakdowns ──
    markets_by_game: dict[str, int] = Field(default_factory=dict)
    markets_by_contract_type: dict[str, int] = Field(default_factory=dict)
    markets_by_sport: dict[str, int] = Field(default_factory=dict)
    # ── Legacy (kept for backward compat) ──
    total_esports_markets: int = 0
    markets_by_category: dict[str, int] = Field(default_factory=dict)
    # ── Quality ──
    markets_with_missing_metadata: int = 0
    gap_counts: dict[str, int] = Field(
        default_factory=dict,
        description="Count of markets per MetadataGap category",
    )
    spread_stats: dict[str, float] = Field(default_factory=dict)
    volume_stats: dict[str, float] = Field(default_factory=dict)
    open_interest_stats: dict[str, float] = Field(default_factory=dict)
    markets_with_ambiguous_title: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    raw_entries: list[EsportsMarketAuditEntry] = Field(default_factory=list)
