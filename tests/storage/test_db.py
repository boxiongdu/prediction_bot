"""Tests for PredictionStore and PredictionRecord."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from prediction_bot.storage import PredictionRecord, PredictionStore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_db() -> Path:
    """Create a temporary SQLite database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db", prefix="test_preds_")
    os.close(fd)
    yield Path(path)
    # Cleanup
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def store(temp_db: Path) -> PredictionStore:
    """Create a PredictionStore backed by a temp database."""
    return PredictionStore(db_path=temp_db)


@pytest.fixture
def sample_record() -> PredictionRecord:
    return PredictionRecord(
        event_id="evt-test-1",
        team_a="T1",
        team_b="Gen.G",
        predicted_winner="T1",
        team_a_probability=0.62,
        team_b_probability=0.38,
        confidence="medium",
        abstain=False,
        reasoning_summary="T1 has stronger roster and better recent form.",
        key_factors=["roster strength", "recent form"],
        risk_flags=["new patch"],
        model_name="hermes+deepseek",
        model_version="0.1.0",
    )


# ---------------------------------------------------------------------------
# PredictionRecord
# ---------------------------------------------------------------------------


class TestPredictionRecord:
    def test_defaults(self) -> None:
        rec = PredictionRecord()
        assert rec.event_id == ""
        assert rec.team_a_probability == 0.5
        assert rec.team_b_probability == 0.5
        assert rec.abstain is False
        assert rec.key_factors == []
        assert rec.risk_flags == []

    def test_to_params(self, sample_record: PredictionRecord) -> None:
        params = sample_record.to_params()
        assert params["event_id"] == "evt-test-1"
        assert params["team_a_probability"] == 0.62
        assert params["abstain"] == 0  # int
        # JSON fields
        assert "roster strength" in params["key_factors"]

    def test_to_params_roundtrip(self, sample_record: PredictionRecord) -> None:
        """to_params().key_factors should be valid JSON that loads back."""
        import json
        factors = json.loads(sample_record.to_params()["key_factors"])
        assert factors == sample_record.key_factors


# ---------------------------------------------------------------------------
# PredictionStore — CRUD
# ---------------------------------------------------------------------------


class TestPredictionStoreCRUD:
    def test_insert_and_get(self, store: PredictionStore, sample_record: PredictionRecord) -> None:
        pid = store.insert(sample_record)
        assert pid > 0

        loaded = store.get_by_id(pid)
        assert loaded is not None
        assert loaded.event_id == "evt-test-1"
        assert loaded.predicted_winner == "T1"
        assert loaded.team_a_probability == 0.62
        assert loaded.confidence == "medium"
        assert loaded.model_name == "hermes+deepseek"

    def test_get_nonexistent(self, store: PredictionStore) -> None:
        assert store.get_by_id(99999) is None

    def test_multiple_inserts(self, store: PredictionStore) -> None:
        ids = []
        for i in range(5):
            rec = PredictionRecord(
                event_id=f"evt-{i}",
                team_a="A",
                team_b="B",
                predicted_winner="A",
                team_a_probability=0.6,
                team_b_probability=0.4,
                confidence="low",
                reasoning_summary=f"prediction {i}",
            )
            ids.append(store.insert(rec))

        assert len(set(ids)) == 5  # all unique
        assert store.count() == 5

    def test_update_result(self, store: PredictionStore, sample_record: PredictionRecord) -> None:
        pid = store.insert(sample_record)
        store.update_result(pid, "T1", True)

        loaded = store.get_by_id(pid)
        assert loaded is not None
        assert loaded.actual_result == "T1"
        assert loaded.correct_prediction is True

    def test_update_result_incorrect(self, store: PredictionStore, sample_record: PredictionRecord) -> None:
        pid = store.insert(sample_record)
        store.update_result(pid, "Gen.G", False)

        loaded = store.get_by_id(pid)
        assert loaded is not None
        assert loaded.actual_result == "Gen.G"
        assert loaded.correct_prediction is False

    def test_get_by_event(self, store: PredictionStore) -> None:
        for i in range(3):
            rec = PredictionRecord(
                event_id="evt-same",
                team_a="A",
                team_b="B",
                predicted_winner="A",
                team_a_probability=0.6,
                team_b_probability=0.4,
                confidence="low",
                reasoning_summary=f"v{i}",
            )
            store.insert(rec)

        results = store.get_by_event("evt-same")
        assert len(results) == 3

        results_other = store.get_by_event("nonexistent")
        assert results_other == []


# ---------------------------------------------------------------------------
# PredictionStore — iteration
# ---------------------------------------------------------------------------


class TestPredictionStoreIteration:
    def test_iter_all_empty(self, store: PredictionStore) -> None:
        assert list(store.iter_all()) == []

    def test_iter_all(self, store: PredictionStore) -> None:
        for i in range(3):
            rec = PredictionRecord(
                event_id=f"evt-{i}",
                team_a="A", team_b="B",
                predicted_winner="A",
                team_a_probability=0.6, team_b_probability=0.4,
                confidence="low",
                reasoning_summary=f"p{i}",
            )
            store.insert(rec)

        all_records = list(store.iter_all())
        assert len(all_records) == 3

    def test_iter_unsettled(self, store: PredictionStore) -> None:
        for i in range(3):
            rec = PredictionRecord(
                event_id=f"evt-{i}",
                team_a="A", team_b="B",
                predicted_winner="A",
                team_a_probability=0.6, team_b_probability=0.4,
                confidence="low",
                reasoning_summary=f"p{i}",
            )
            pid = store.insert(rec)
            if i == 0:
                store.update_result(pid, "A", True)

        unsettled = list(store.iter_unsettled())
        assert len(unsettled) == 2

    def test_iter_settled(self, store: PredictionStore) -> None:
        for i in range(3):
            rec = PredictionRecord(
                event_id=f"evt-{i}",
                team_a="A", team_b="B",
                predicted_winner="A",
                team_a_probability=0.6, team_b_probability=0.4,
                confidence="low",
                reasoning_summary=f"p{i}",
            )
            pid = store.insert(rec)
            store.update_result(pid, "A", True)

        settled = list(store.iter_settled())
        assert len(settled) == 3

    def test_iter_by_confidence(self, store: PredictionStore) -> None:
        for i, conf in enumerate(["low", "medium", "high", "low", "medium"]):
            rec = PredictionRecord(
                event_id=f"evt-{i}",
                team_a="A", team_b="B",
                predicted_winner="A",
                team_a_probability=0.6, team_b_probability=0.4,
                confidence=conf,
                reasoning_summary=f"p{i}",
            )
            pid = store.insert(rec)
            store.update_result(pid, "A", True)

        high = list(store.iter_by_confidence("high"))
        assert len(high) == 1

        low = list(store.iter_by_confidence("low"))
        assert len(low) == 2


# ---------------------------------------------------------------------------
# PredictionStore — stats
# ---------------------------------------------------------------------------


class TestPredictionStoreStats:
    def test_count_empty(self, store: PredictionStore) -> None:
        assert store.count() == 0
        assert len(store) == 0

    def test_count(self, store: PredictionStore) -> None:
        for i in range(4):
            rec = PredictionRecord(
                event_id=f"evt-{i}",
                team_a="A", team_b="B",
                predicted_winner="A",
                team_a_probability=0.6, team_b_probability=0.4,
                confidence="low",
                reasoning_summary=f"p{i}",
            )
            store.insert(rec)

        assert store.count() == 4
        assert len(store) == 4

    def test_count_settled(self, store: PredictionStore) -> None:
        for i in range(5):
            rec = PredictionRecord(
                event_id=f"evt-{i}",
                team_a="A", team_b="B",
                predicted_winner="A",
                team_a_probability=0.6, team_b_probability=0.4,
                confidence="low",
                reasoning_summary=f"p{i}",
            )
            pid = store.insert(rec)
            if i < 3:
                store.update_result(pid, "A", True)

        assert store.count_settled() == 3

    def test_repr(self, store: PredictionStore) -> None:
        r = repr(store)
        assert "PredictionStore" in r


# ---------------------------------------------------------------------------
# PredictionRecord — from_row
# ---------------------------------------------------------------------------


class TestPredictionRecordFromRow:
    def test_roundtrip(self, store: PredictionStore, sample_record: PredictionRecord) -> None:
        """Insert a record, retrieve it, check it matches."""
        pid = store.insert(sample_record)
        loaded = store.get_by_id(pid)
        assert loaded is not None
        assert loaded.event_id == sample_record.event_id
        assert loaded.predicted_winner == sample_record.predicted_winner
        assert loaded.team_a_probability == sample_record.team_a_probability
        assert loaded.key_factors == sample_record.key_factors
        assert loaded.risk_flags == sample_record.risk_flags

    def test_key_factors_json_roundtrip(self, store: PredictionStore) -> None:
        rec = PredictionRecord(
            event_id="evt-json",
            team_a="A", team_b="B",
            predicted_winner="A",
            team_a_probability=0.6, team_b_probability=0.4,
            confidence="low",
            reasoning_summary="test",
            key_factors=["factor 1", "factor 2", "multi-word factor"],
            risk_flags=["risk A", "risk B"],
        )
        pid = store.insert(rec)
        loaded = store.get_by_id(pid)
        assert loaded is not None
        assert loaded.key_factors == ["factor 1", "factor 2", "multi-word factor"]
        assert loaded.risk_flags == ["risk A", "risk B"]

    def test_abstain_record(self, store: PredictionStore) -> None:
        rec = PredictionRecord(
            event_id="evt-abstain",
            team_a="A", team_b="B",
            predicted_winner="abstain",
            team_a_probability=0.5, team_b_probability=0.5,
            confidence="low",
            abstain=True,
            reasoning_summary="not enough info",
        )
        pid = store.insert(rec)
        loaded = store.get_by_id(pid)
        assert loaded is not None
        assert loaded.abstain is True
        assert loaded.predicted_winner == "abstain"
