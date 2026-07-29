"""
Monte Carlo simulation for paper trading bankroll analysis.

Simulates different trade orderings, position arrival patterns,
and computes capital requirements to survive drawdowns.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SimulatedTrade:
    """A single trade in the Monte Carlo simulation."""

    prob: float
    correct: bool | None = None  # None = not yet settled
    size: float = 100.0
    sequence: int = 0


def generate_trade_set(
    n_trades: int,
    prob_dist: list[float] | None = None,
    empirical_wr: dict[str, float] | None = None,
    seed: int | None = None,
) -> list[SimulatedTrade]:
    """Generate a set of trades matching historical calibration.

    Args:
        n_trades: Number of trades to generate.
        prob_dist: Distribution of model probabilities (sampled from).
        empirical_wr: Dict mapping prob_bin → win_rate (e.g., {'0.6-0.7': 0.72}).
        seed: Random seed.

    Uses historical calibration: 0.60-0.70: 72%, 0.70-0.80: 78%, 0.80-0.85: 85%.
    """
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)

    # Default: sample from historical distribution in 0.62-0.85 band
    if prob_dist is None:
        prob_dist = (
            [0.65] * 25 + [0.68] * 20 + [0.72] * 15 +
            [0.75] * 15 + [0.78] * 10 + [0.82] * 10 + [0.84] * 5
        )

    if empirical_wr is None:
        empirical_wr = {
            "0.60-0.70": 0.72,
            "0.70-0.80": 0.78,
            "0.80-0.85": 0.85,
        }

    trades: list[SimulatedTrade] = []
    for i in range(n_trades):
        prob = random.choice(prob_dist)

        # Determine win rate for this prob bin
        if prob < 0.70:
            wr = empirical_wr.get("0.60-0.70", 0.72)
        elif prob < 0.80:
            wr = empirical_wr.get("0.70-0.80", 0.78)
        else:
            wr = empirical_wr.get("0.80-0.85", 0.85)

        correct = random.random() < wr
        trades.append(SimulatedTrade(prob=prob, correct=correct, sequence=i))

    return trades


def simulate_session(
    trades: list[SimulatedTrade],
    initial_bankroll: float = 2000.0,
    fixed_size: float = 100.0,
    max_concurrent: int = 5,
    settle_delay: int = 3,
    max_utilization: float = 0.50,
) -> dict[str, Any]:
    """Simulate a trading session with concurrent positions.

    Positions take `settle_delay` trades before settling (simulating
    time-to-maturity). New trades are rejected if committed capital
    exceeds max_utilization * bankroll.

    Returns dict with PnL path, drawdown, final bankroll, rejections.
    """
    bankroll = initial_bankroll
    open_positions: list[SimulatedTrade] = []
    pnl_path: list[float] = [0.0]
    bankroll_path: list[float] = [initial_bankroll]
    rejected = 0
    executed = 0

    for trade in trades:
        # Settle old positions
        while len(open_positions) >= max_concurrent:
            settled = open_positions.pop(0)
            if settled.correct:
                pnl = settled.size * (1.0 - settled.prob)
            else:
                pnl = -settled.size * settled.prob
            bankroll += pnl
            pnl_path.append(pnl)
            bankroll_path.append(bankroll)

        # Check capital utilization
        committed = sum(p.size for p in open_positions)
        if committed + fixed_size > bankroll * max_utilization:
            rejected += 1
            continue

        # Open new position
        trade.size = fixed_size
        open_positions.append(trade)
        executed += 1

    # Settle remaining
    for settled in open_positions:
        if settled.correct:
            pnl = settled.size * (1.0 - settled.prob)
        else:
            pnl = -settled.size * settled.prob
        bankroll += pnl
        pnl_path.append(pnl)
        bankroll_path.append(bankroll)

    pnls = np.array(pnl_path)
    cumsum = np.cumsum(pnls)
    max_dd = float(np.min(cumsum - np.maximum.accumulate(cumsum)))
    sharpe = (
        float(np.mean(pnls) / np.std(pnls) * np.sqrt(len(pnls)))
        if len(pnls) > 1 and np.std(pnls) > 0
        else 0.0
    )

    return {
        "initial_bankroll": initial_bankroll,
        "final_bankroll": float(bankroll),
        "total_pnl": float(bankroll - initial_bankroll),
        "roi": float((bankroll - initial_bankroll) / initial_bankroll),
        "max_drawdown": max_dd,
        "max_drawdown_pct": float(max_dd / initial_bankroll),
        "sharpe": sharpe,
        "trades_executed": executed,
        "trades_rejected": rejected,
        "bankroll_path": [float(x) for x in bankroll_path],
        "pnl_path": [float(x) for x in pnl_path],
    }


def run_monte_carlo(
    n_scenarios: int = 1000,
    n_trades: int = 50,
    initial_bankroll: float = 2000.0,
    fixed_size: float = 100.0,
    max_concurrent: int = 5,
    max_utilization: float = 0.50,
    seed: int = 42,
) -> dict[str, Any]:
    """Run Monte Carlo simulation across many scenarios.

    Returns aggregate statistics: mean/median/P5/P95 outcomes,
    ruin probability, capital requirement.
    """
    results: list[dict[str, Any]] = []
    ruin_count = 0
    ruin_threshold = 0.5 * initial_bankroll  # "ruin" = 50% capital loss

    for i in range(n_scenarios):
        trades = generate_trade_set(n_trades, seed=seed + i)
        result = simulate_session(
            trades,
            initial_bankroll=initial_bankroll,
            fixed_size=fixed_size,
            max_concurrent=max_concurrent,
            max_utilization=max_utilization,
        )
        results.append(result)
        if result["final_bankroll"] < ruin_threshold:
            ruin_count += 1

    final_values = [r["final_bankroll"] for r in results]
    max_dds = [r["max_drawdown_pct"] for r in results]
    rois = [r["roi"] for r in results]

    return {
        "scenarios": n_scenarios,
        "trades_per_scenario": n_trades,
        "initial_bankroll": initial_bankroll,
        "fixed_size": fixed_size,
        "mean_final": float(np.mean(final_values)),
        "median_final": float(np.median(final_values)),
        "p5_final": float(np.percentile(final_values, 5)),
        "p95_final": float(np.percentile(final_values, 95)),
        "min_final": float(np.min(final_values)),
        "max_final": float(np.max(final_values)),
        "mean_roi": float(np.mean(rois)),
        "median_roi": float(np.median(rois)),
        "mean_max_dd_pct": float(np.mean(max_dds)),
        "p5_max_dd_pct": float(np.percentile(max_dds, 5)),
        "worst_dd_pct": float(np.min(max_dds)),
        "ruin_probability": ruin_count / n_scenarios,
        "ruin_threshold": ruin_threshold,
        "capital_requirement_95": max(
            initial_bankroll - float(np.percentile(final_values, 5)),
            abs(float(np.percentile(max_dds, 5)) * initial_bankroll),
        ),
    }


def print_monte_carlo_report(result: dict[str, Any]) -> None:
    """Print a human-readable Monte Carlo report."""
    print()
    print("=" * 60)
    print("  MONTE CARLO BANKROLL ANALYSIS")
    print("=" * 60)
    print(f"  Scenarios:          {result['scenarios']}")
    print(f"  Trades/scenario:    {result['trades_per_scenario']}")
    print(f"  Initial bankroll:   ${result['initial_bankroll']:,.0f}")
    print(f"  Fixed size:         ${result['fixed_size']:.0f}")
    print()
    print("  Outcomes:")
    print(f"    Mean final:       ${result['mean_final']:,.0f}")
    print(f"    Median final:     ${result['median_final']:,.0f}")
    print(f"    P5 (worst 5%):    ${result['p5_final']:,.0f}")
    print(f"    P95 (best 5%):    ${result['p95_final']:,.0f}")
    print(f"    Min/Max:          ${result['min_final']:,.0f} / ${result['max_final']:,.0f}")
    print()
    print("  Risk:")
    print(f"    Mean ROI:         {result['mean_roi']:+.1%}")
    print(f"    Mean max DD:      {result['mean_max_dd_pct']:+.1%}")
    print(f"    P5 max DD:        {result['p5_max_dd_pct']:+.1%}")
    print(f"    Ruin prob (<50%):  {result['ruin_probability']:.1%}")
    print()
    print(f"  Capital req (95% confidence): ${result['capital_requirement_95']:,.0f}")
    print()
