"""Prediction workflow: contract normalisation, event building, and response parsing.

Phase 1 redesign pipeline:
  RawMarket → normalize_contract() → NormalizedContract
  [NormalizedContract, ...] → build_event() → UnderlyingEvent
  UnderlyingEvent → PredictionRequest → research prompt → Hermes → PredictionResponse
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from prediction_bot.agents.schema import (
    NormalizedContract,
    PredictionRequest,
    PredictionResponse,
    UnderlyingEvent,
    build_event,
    normalize_contract,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# High-level pipeline
# ---------------------------------------------------------------------------


def normalize_kalshi_market(market_raw: dict[str, Any]) -> NormalizedContract:
    """Normalize a raw Kalshi market dict into a NormalizedContract.

    Delegates to normalize_contract which parses rules_primary as the
    authoritative source.

    Args:
        market_raw: Raw Kalshi market dict from the API.

    Returns:
        A NormalizedContract.
    """
    return normalize_contract(market_raw)


def build_event_from_contracts(
    contracts: list[NormalizedContract],
) -> UnderlyingEvent | None:
    """Build an UnderlyingEvent from contracts sharing the same event_ticker.

    Args:
        contracts: List of NormalizedContract objects.

    Returns:
        UnderlyingEvent, or None if no contracts.
    """
    return build_event(contracts)


def normalize_kalshi_event(market_raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a single Kalshi market into contract and derived event.

    Single-market convenience function. For proper event construction,
    use normalize_contract() + build_event() with all contracts for
    the same event_ticker.

    Args:
        market_raw: Raw Kalshi market dict.

    Returns:
        Dict with 'contract' (NormalizedContract) and 'event' (UnderlyingEvent).
    """
    contract = normalize_contract(market_raw)
    event = build_event([contract])
    return {
        "contract": contract,
        "event": event.model_dump() if event else None,
    }


def build_prediction_request(event: UnderlyingEvent) -> PredictionRequest:
    """Build a PredictionRequest from an UnderlyingEvent.

    Args:
        event: The underlying event.

    Returns:
        A PredictionRequest ready for Hermes.
    """
    return PredictionRequest(
        event_id=event.event_id,
        game=event.game,
        tournament=event.tournament,
        participants=event.participants,
        contract_types=event.contract_types,
        start_time=event.start_time,
        available_information={},
    )


def build_research_prompt(request: PredictionRequest) -> str:
    """Build the natural-language research prompt for Hermes."""
    return request.to_research_prompt()


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def parse_prediction_response(
    raw_text: str,
    event_id: str | None = None,
    participants: list[str] | None = None,
) -> PredictionResponse:
    """Parse a Hermes prediction response into a validated PredictionResponse.

    Handles common formatting issues: markdown code fences, surrounding text.

    Args:
        raw_text: The raw text output from Hermes.
        event_id: Expected event ID for cross-validation (optional).
        participants: Expected participants for cross-validation (optional).

    Returns:
        A validated PredictionResponse.

    Raises:
        ValueError: If the response cannot be parsed or fails validation.
    """
    # Step 1: Extract JSON from the text
    json_str = _extract_json(raw_text)

    # Step 2: Parse JSON
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Failed to parse prediction response as JSON: {e}\n\nRaw text:\n{raw_text[:500]}"
        ) from e

    # Step 3: Validate with Pydantic
    try:
        response = PredictionResponse(**data)
    except Exception as e:
        raise ValueError(
            f"Prediction response failed validation: {e}\n\n"
            f"Parsed data:\n{json.dumps(data, indent=2)}"
        ) from e

    # Step 4: Cross-validate event_id if provided
    if event_id and response.event_id != event_id:
        raise ValueError(
            f"Event ID mismatch: expected '{event_id}', got '{response.event_id}'"
        )

    # Step 5: Cross-validate participants if provided
    if not response.abstain and participants and len(participants) >= 2:
        winner = response.predicted_winner.lower()
        valid = [p.lower() for p in participants]
        if winner not in valid:
            raise ValueError(
                f"Predicted winner '{response.predicted_winner}' is not one of "
                f"the participants: {participants}"
            )

    return response


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> str:
    """Extract a JSON object from text that may contain markdown fences or prose."""
    text = text.strip()

    # Already clean JSON
    if text.startswith("{") and text.endswith("}"):
        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            pass

    # Try ```json fence
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        candidate = m.group(1).strip()
        if candidate.startswith("{"):
            return candidate

    # Find outermost braces
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return text[first_brace : last_brace + 1]

    raise ValueError("Could not locate a JSON object in the response text")
