"""Prediction prediction record storage (Phase 1).

Lightweight single-file wrapper that doesn't pull in SQLAlchemy or an ORM —
just const‑correct SQL strings, a few helpers, and a data‑class that knows how
to round‑trip through sqlite3.Row.  This keeps the dependency footprint at zero."""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prediction_bot.config.paths import project_root

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database location
# ---------------------------------------------------------------------------

DEFAULT_DB_PATH: Path = project_root() / "data" / "predictions.db"


def _default_db_path() -> Path:
    DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DEFAULT_DB_PATH


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS predictions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        TEXT    NOT NULL,
    timestamp       TEXT    NOT NULL,
    game            TEXT,
    tournament      TEXT,
    team_a          TEXT    NOT NULL,
    team_b          TEXT    NOT NULL,
    predicted_winner TEXT   NOT NULL,
    team_a_probability REAL  NOT NULL,
    team_b_probability REAL  NOT NULL,
    confidence      TEXT    NOT NULL,
    abstain         INTEGER NOT NULL DEFAULT 0,
    reasoning_summary TEXT  NOT NULL,
    key_factors     TEXT    NOT NULL DEFAULT '[]',
    risk_flags      TEXT    NOT NULL DEFAULT '[]',
    model_name      TEXT    NOT NULL DEFAULT 'hermes+deepseek',
    model_version   TEXT    NOT NULL DEFAULT '',
    actual_result   TEXT,
    correct_prediction INTEGER
);
"""

INSERT_SQL = """
INSERT INTO predictions (
    event_id, timestamp, game, tournament, team_a, team_b,
    predicted_winner, team_a_probability, team_b_probability,
    confidence, abstain, reasoning_summary, key_factors, risk_flags,
    model_name, model_version
) VALUES (
    :event_id, :timestamp, :game, :tournament, :team_a, :team_b,
    :predicted_winner, :team_a_probability, :team_b_probability,
    :confidence, :abstain, :reasoning_summary, :key_factors, :risk_flags,
    :model_name, :model_version
);
"""

SELECT_ALL_SQL = """
SELECT * FROM predictions ORDER BY timestamp DESC;
"""

SELECT_BY_EVENT_SQL = """
SELECT * FROM predictions WHERE event_id = ? ORDER BY timestamp DESC;
"""

SELECT_BY_ID_SQL = """
SELECT * FROM predictions WHERE id = ?;
"""

UPDATE_RESULT_SQL = """
UPDATE predictions
SET actual_result = :actual_result,
    correct_prediction = :correct_prediction
WHERE id = :id;
"""

SELECT_UNSETTLED_SQL = """
SELECT * FROM predictions
WHERE actual_result IS NULL AND abstain = 0
ORDER BY timestamp DESC;
"""

SELECT_SETTLED_SQL = """
SELECT * FROM predictions
WHERE actual_result IS NOT NULL
ORDER BY timestamp DESC;
"""

SELECT_BY_CONFIDENCE_SQL = """
SELECT * FROM predictions
WHERE confidence = ? AND actual_result IS NOT NULL
ORDER BY timestamp DESC;
"""

COUNT_SQL = "SELECT COUNT(*) as cnt FROM predictions;"

COUNT_SETTLED_SQL = "SELECT COUNT(*) as cnt FROM predictions WHERE actual_result IS NOT NULL;"


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass
class PredictionRecord:
    """A single prediction record, stored in and loaded from SQLite."""

    id: int | None = None
    event_id: str = ""
    timestamp: str = ""  # ISO 8601
    game: str | None = None
    tournament: str | None = None
    team_a: str = ""
    team_b: str = ""
    predicted_winner: str = ""
    team_a_probability: float = 0.5
    team_b_probability: float = 0.5
    confidence: str = "low"
    abstain: bool = False
    reasoning_summary: str = ""
    key_factors: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    model_name: str = "hermes+deepseek"
    model_version: str = ""
    actual_result: str | None = None
    correct_prediction: bool | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> PredictionRecord:
        """Build a PredictionRecord from a sqlite3.Row."""
        return cls(
            id=row["id"],
            event_id=row["event_id"],
            timestamp=row["timestamp"],
            game=row["game"],
            tournament=row["tournament"],
            team_a=row["team_a"],
            team_b=row["team_b"],
            predicted_winner=row["predicted_winner"],
            team_a_probability=row["team_a_probability"],
            team_b_probability=row["team_b_probability"],
            confidence=row["confidence"],
            abstain=bool(row["abstain"]),
            reasoning_summary=row["reasoning_summary"],
            key_factors=json.loads(row["key_factors"] or "[]"),
            risk_flags=json.loads(row["risk_flags"] or "[]"),
            model_name=row["model_name"],
            model_version=row["model_version"],
            actual_result=row["actual_result"],
            correct_prediction=(
                bool(row["correct_prediction"])
                if row["correct_prediction"] is not None
                else None
            ),
        )

    def to_params(self) -> dict[str, Any]:
        """Convert to a dict of named parameters for INSERT."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "game": self.game,
            "tournament": self.tournament,
            "team_a": self.team_a,
            "team_b": self.team_b,
            "predicted_winner": self.predicted_winner,
            "team_a_probability": self.team_a_probability,
            "team_b_probability": self.team_b_probability,
            "confidence": self.confidence,
            "abstain": int(self.abstain),
            "reasoning_summary": self.reasoning_summary,
            "key_factors": json.dumps(self.key_factors),
            "risk_flags": json.dumps(self.risk_flags),
            "model_name": self.model_name,
            "model_version": self.model_version,
        }


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class PredictionStore:
    """SQLite-backed storage for prediction records.

    Usage:
        store = PredictionStore()
        store.insert(record)
        for r in store.iter_all():
            print(r.event_id)
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = Path(db_path) if db_path else _default_db_path()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(CREATE_TABLE_SQL)
            conn.commit()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def insert(self, record: PredictionRecord) -> int:
        """Insert a prediction record and return its auto-generated id."""
        if not record.timestamp:
            record.timestamp = datetime.now(timezone.utc).isoformat()

        with self._connect() as conn:
            cursor = conn.execute(INSERT_SQL, record.to_params())
            conn.commit()
            rowid = cursor.lastrowid
            if rowid is None:
                raise RuntimeError("INSERT succeeded but lastrowid is None")
            record.id = rowid
            logger.info("Inserted prediction id=%d event_id=%s", record.id, record.event_id)
            return rowid

    def update_result(
        self,
        prediction_id: int,
        actual_result: str,
        correct_prediction: bool,
    ) -> None:
        """Record the actual outcome for a prediction."""
        with self._connect() as conn:
            conn.execute(
                UPDATE_RESULT_SQL,
                {
                    "id": prediction_id,
                    "actual_result": actual_result,
                    "correct_prediction": int(correct_prediction),
                },
            )
            conn.commit()
            logger.info(
                "Updated prediction id=%d: actual=%s correct=%s",
                prediction_id, actual_result, correct_prediction,
            )

    def get_by_id(self, prediction_id: int) -> PredictionRecord | None:
        """Retrieve a single prediction by its id."""
        with self._connect() as conn:
            row = conn.execute(SELECT_BY_ID_SQL, (prediction_id,)).fetchone()
            if row is None:
                return None
            return PredictionRecord.from_row(row)

    def get_by_event(self, event_id: str) -> list[PredictionRecord]:
        """Retrieve all predictions for a given event_id."""
        with self._connect() as conn:
            rows = conn.execute(SELECT_BY_EVENT_SQL, (event_id,)).fetchall()
            return [PredictionRecord.from_row(r) for r in rows]

    # ------------------------------------------------------------------
    # Iteration
    # ------------------------------------------------------------------

    def iter_all(self) -> Iterator[PredictionRecord]:
        with self._connect() as conn:
            for row in conn.execute(SELECT_ALL_SQL):
                yield PredictionRecord.from_row(row)

    def iter_unsettled(self) -> Iterator[PredictionRecord]:
        with self._connect() as conn:
            for row in conn.execute(SELECT_UNSETTLED_SQL):
                yield PredictionRecord.from_row(row)

    def iter_settled(self) -> Iterator[PredictionRecord]:
        with self._connect() as conn:
            for row in conn.execute(SELECT_SETTLED_SQL):
                yield PredictionRecord.from_row(row)

    def iter_by_confidence(self, confidence: str) -> Iterator[PredictionRecord]:
        with self._connect() as conn:
            for row in conn.execute(SELECT_BY_CONFIDENCE_SQL, (confidence,)):
                yield PredictionRecord.from_row(row)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute(COUNT_SQL).fetchone()
            return row["cnt"]

    def count_settled(self) -> int:
        with self._connect() as conn:
            row = conn.execute(COUNT_SETTLED_SQL).fetchone()
            return row["cnt"]

    def __len__(self) -> int:
        return self.count()

    def __repr__(self) -> str:
        return f"PredictionStore(db_path={self._db_path!r}, count={self.count()})"
