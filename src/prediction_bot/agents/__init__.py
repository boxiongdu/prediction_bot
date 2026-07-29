"""Hermes prediction agent — schema, workflow, and evaluation.

This package defines the interface between the prediction_bot infrastructure
(Kalshi data fetching, normalisation, storage) and the Hermes reasoning engine.

Hermes is the analyst — this package provides the tools, schemas, and prompts
that let Hermes produce structured, machine-readable predictions.
"""

from prediction_bot.agents.schema import (
    ContractType,
    NormalizedContract,
    PredictionConfidence,
    PredictionRequest,
    PredictionResponse,
    Sport,
    UnderlyingEvent,
    build_event,
    normalize_contract,
    parse_rules_primary,
)
from prediction_bot.agents.workflow import (
    build_event_from_contracts,
    build_prediction_request,
    build_research_prompt,
    normalize_kalshi_event,
    normalize_kalshi_market,
    parse_prediction_response,
)

__all__ = [
    "ContractType",
    "NormalizedContract",
    "PredictionConfidence",
    "PredictionRequest",
    "PredictionResponse",
    "Sport",
    "UnderlyingEvent",
    "build_event",
    "build_event_from_contracts",
    "build_prediction_request",
    "build_research_prompt",
    "normalize_contract",
    "normalize_kalshi_event",
    "normalize_kalshi_market",
    "parse_prediction_response",
    "parse_rules_primary",
]
