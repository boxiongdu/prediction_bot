"""Tests for production trading safety and order client."""

from __future__ import annotations

from prediction_bot.trading.safety import (
    MAX_POSITION_PER_TRADE,
    MAX_TRADES_PER_DAY,
    ProductionSafety,
)
from prediction_bot.trading.order_client import (
    KalshiOrderClient,
    TradeProposal,
    generate_proposal,
)


class TestSafetyChecks:
    """Production safety guard tests."""

    def test_duplicate_prevention(self, tmp_path) -> None:
        db = str(tmp_path / "checkpoint.json")
        safety = ProductionSafety(checkpoint_path=db)
        safety.mark_executed("TEST-01", "YES")
        check = safety.check_trade("TEST-01", "YES", 100.0)
        assert not check.passed
        assert check.duplicate

    def test_different_side_allowed(self, tmp_path) -> None:
        db = str(tmp_path / "checkpoint.json")
        safety = ProductionSafety(checkpoint_path=db)
        safety.mark_executed("TEST-01", "YES")
        check = safety.check_trade("TEST-01", "NO", 100.0)
        # Different side — not a duplicate
        assert check.duplicate is False

    def test_position_size_limit(self, tmp_path) -> None:
        db = str(tmp_path / "checkpoint.json")
        safety = ProductionSafety(checkpoint_path=db)
        check = safety.check_trade("TEST-01", "YES", 9999.0)
        assert not check.passed
        assert check.exceeds_position_limit

    def test_daily_trade_limit(self, tmp_path) -> None:
        db = str(tmp_path / "checkpoint.json")
        safety = ProductionSafety(checkpoint_path=db)
        safety._daily_state["daily_trades"] = MAX_TRADES_PER_DAY
        check = safety.check_trade("TEST-01", "YES", 50.0)
        assert not check.passed
        assert check.exceeds_trade_count

    def test_exposure_limit(self, tmp_path) -> None:
        db = str(tmp_path / "checkpoint.json")
        safety = ProductionSafety(checkpoint_path=db)
        safety._daily_state["open_exposure"] = 490.0
        check = safety.check_trade("TEST-01", "YES", 50.0)
        assert not check.passed
        assert check.exceeds_exposure


class TestOrderClient:
    """Order client tests."""

    def test_paper_mode_rejects(self) -> None:
        client = KalshiOrderClient(mode="PAPER")
        assert client.is_paper
        assert not client.can_submit
        try:
            client.approve(TradeProposal(
                ticker="TEST", team="A", opponent="B",
                probability=0.70, market_price=0.65,
                edge=0.05, size=100.0, reason="test",
            ))
            assert False, "Should have raised"
        except RuntimeError:
            pass

    def test_approval_mode_simulates_without_live(self) -> None:
        client = KalshiOrderClient(mode="APPROVAL")
        assert not client.is_paper
        result = client.approve(TradeProposal(
            ticker="TEST", team="A", opponent="B",
            probability=0.70, market_price=0.65,
            edge=0.05, size=100.0, reason="test",
        ))
        assert result.status == "simulated"

    def test_generate_proposal(self) -> None:
        proposal = generate_proposal(
            ticker="KXLOLGAME-TEST",
            team_a="T1",
            team_b="Gen.G",
            predicted_winner="T1",
            prob=0.72,
            market_ask=0.65,
            size=100.0,
        )
        assert proposal.ticker == "KXLOLGAME-TEST"
        assert proposal.team == "T1"
        assert abs(proposal.edge - 0.07) < 0.001
        assert proposal.size == 100.0
        d = proposal.to_dict()
        assert d["probability"] == 0.72
        assert abs(d["edge"] - 0.07) < 0.001
