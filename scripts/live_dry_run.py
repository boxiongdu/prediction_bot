"""First live trade dry-run — scan, filter, predict, propose."""
import logging

logging.basicConfig(level=logging.WARNING)

from prediction_bot.trading.strategy import build_team_elo_lookup, hermes_review, predict_match
from prediction_bot.trading.filter import filter_markets
from prediction_bot.trading.strategy_rules import EligibilityRule, SizingRule, StrategyConfig
from prediction_bot.trading.order_client import generate_proposal
from prediction_bot.agents.schema import normalize_contract
from prediction_bot.data.schema import _parse_price_dollars
import requests

print("Step 1: Scanning KXLOLGAME markets...")
url = (
    "https://external-api.kalshi.com/trade-api/v2/markets"
    "?status=open&limit=100&series_ticker=KXLOLGAME&mve_filter=exclude"
)
resp = requests.get(url, timeout=30)
resp.raise_for_status()
markets = resp.json().get("markets", [])
print(f"  Found {len(markets)} KXLOLGAME markets")

print("Step 2: Filtering...")
results = filter_markets(markets, tier1_only=True, scan_id="live-test", query_params="")
print(f"  Tier 1 passed: {len(results)}")

if not results:
    print("  No Tier 1 matches — showing best available.")
    results = filter_markets(markets, tier1_only=False, scan_id="live-test", query_params="")
    print(f"  All passed: {len(results)}")

print("Step 3: Building Elo + predicting...")
elo = build_team_elo_lookup()

strategy = StrategyConfig(
    eligibility=EligibilityRule(prob_lo=0.62, prob_hi=0.85, min_edge=0.03),
    sizing=SizingRule(method="fixed", fixed_size=25.0),
    name="live-0.62-0.85",
)

proposals = []
for fr in results:
    raw = next(m for m in markets if m.get("ticker") == fr.ticker)
    ta, tb = fr.team_a, fr.team_b
    if not ta or not tb:
        continue
    pred = predict_match(ta, tb, elo)
    nc = normalize_contract(raw)
    yo = (nc.yes_outcome or "").lower()
    if ta.lower() in yo:
        prob = pred["probability"]
        winner = ta
    elif tb.lower() in yo:
        prob = 1 - pred["probability"]
        winner = tb
    else:
        continue

    review = hermes_review(ta, tb, prob, elo, tournament=fr.tournament)
    if review["decision"] != "APPROVE":
        continue

    ask = float(_parse_price_dollars(raw.get("yes_ask_dollars")) or 0)
    edge = prob - ask if ask > 0 else None

    decision = strategy.evaluate_trade(
        prob=prob, edge=edge if edge else None,
        hermes_approved=True, both_known=True,
    )
    if not decision["trade"]:
        continue

    proposal = generate_proposal(
        ticker=fr.ticker, team_a=ta, team_b=tb,
        predicted_winner=winner, prob=prob,
        market_ask=ask if ask > 0 else None,
        size=25.0,
    )
    proposals.append(proposal)

print(f"  Qualified trades: {len(proposals)}")

if proposals:
    print()
    print("=" * 60)
    print("  LIVE TRADE PROPOSALS (APPROVAL MODE)")
    print("=" * 60)
    for i, p in enumerate(proposals, 1):
        print(f"  #{i}: {p.ticker}")
        print(f"       Match:    {p.team} vs {p.opponent}")
        print(f"       Bet:      YES on {p.team}")
        print(f"       Prob:     {p.probability:.1%}")
        ask_str = f"${p.market_price:.4f}" if p.market_price else "N/A"
        print(f"       Ask:      {ask_str}")
        edge_str = f"{p.edge:+.1%}" if p.edge else "N/A"
        print(f"       Edge:     {edge_str}")
        print(f"       Size:     ${p.size:.0f}")
        print()

print("-" * 60)
print("  SAFETY CONFIG (ENABLE_LIVE_TRADING=false)")
print("-" * 60)
from prediction_bot.trading.safety import (
    ENABLE_LIVE_TRADING,
    LIVE_TRADING_MODE,
    MAX_DAILY_LOSS,
    MAX_POSITION_PER_TRADE,
    MAX_TOTAL_OPEN_EXPOSURE,
    MAX_TRADES_PER_DAY,
)
print(f"  Mode:                  {LIVE_TRADING_MODE}")
print(f"  Live trading:          {ENABLE_LIVE_TRADING}")
print(f"  Max position/trade:    ${MAX_POSITION_PER_TRADE:.0f}")
print(f"  Max open exposure:     ${MAX_TOTAL_OPEN_EXPOSURE:.0f}")
print(f"  Max daily loss:        ${MAX_DAILY_LOSS:.0f}")
print(f"  Max trades/day:        {MAX_TRADES_PER_DAY}")
print(f"  Require approval:      {LIVE_TRADING_MODE == 'APPROVAL'}")
print(f"  Emergency shutdown:    unset ENABLE_LIVE_TRADING or set to false")
