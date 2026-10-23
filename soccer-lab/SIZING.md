# Deterministic sizing — paper implementation

The user approved a $10 maximum loss per fixture. V1 uses a $500 simulated bankroll,
$5 fixed stake by default, $50 aggregate unresolved exposure and a $50 daily risk
budget. Quarter Kelly is a configurable challenger. Agents do not choose quantities
or override limits. `risk_policy.json` is versioned; `sizing.py` enforces approved
maximums in code. Lower limits are permitted. Increasing caps requires a reviewed
code change as well as configuration. These are application controls, not a security
boundary against an administrator editing code.

## Calculation

For selected contract outcome H/D/A, YES probability is the corresponding model
probability. NO probability is its complement; e.g. NO home includes draw and away.
Prices must be executable BUY prices for the selected side, not last prices or a
YES price reused for NO. Canonical fixture mapping is the caller's responsibility.

For each supported whole-contract quantity q up to executable depth and a 1,000
contract implementation bound:

```
total_cost = ceil_to_cent(q * limit_price + total_entry_fee_for_q)
c = total_cost / q
full_kelly = max(0, (p - c) / (1 - c))
strategy_budget = $5                       # default fixed method
strategy_budget = 0.25 * B * full_kelly     # quarter_kelly challenger
```

Here B is the smaller of $500 and current paper bankroll at cost basis: cash plus
outstanding reservation costs. Profits never raise B above $500; settled losses
reduce it. This is not mark-to-market sizing. The formula assumes a binary contract
pays exactly $1 for the selected side and zero otherwise, with no additional exit
or settlement fees. Products with other payout/fee structures are unsupported.

Choose the largest supported quantity whose total cost fits all budgets:

- strategy budget;
- $10 match-loss cap;
- $50 minus all unresolved risk;
- $50 minus today's gross realized losses minus all unresolved risk;
- remaining paper cash.

Any nonpositive after-fee edge yields no position, including under fixed stakes.
V1 does not invent a probability haircut or extra minimum-edge threshold: these
remain future research parameters. It does not assert the model is sufficiently
calibrated for live Kelly sizing.

## Fees and limit prices

`fee_totals` maps quantity to an explicit total dollar entry-fee quote, e.g.
`{"1":"0.02","2":"0.04"}`. Unsupported quantities cannot be bought; an empty
table produces zero quantity. Fees are included before rounding and sizing. A
nonempty `fee_source` records the source or clearly labeled paper assumption.

No exchange-wide fee rate is hard-coded. Kalshi states that fees can differ by
market: https://help.kalshi.com/en/articles/13823805-fees . The caller must provide
conservative fee bounds appropriate for the market and fill pattern, including
rounding across split fills. The code does not retrieve or verify a fee schedule;
a source string is provenance, not proof of accuracy. Zero fees must be explicit.
The chosen limit price bounds principal; the supplied fee table must bound fees
for every execution allowed by that order. There is no multi-level execution adapter.

## Persistent paper risk

`PaperLedger.reserve()` reads exposure, sizes, and reserves inside one SQLite
`BEGIN IMMEDIATE` transaction. Distinct processes using the same database serialize
against its limits. Every pending intent counts at its full cost immediately. A
unique fixture ID prevents a second contract, opposite side, adding, or re-entry
after settlement. Rejected proposals do not lock a fixture; accepted reservations
do. This policy is stricter than allowing retries after a cancelled entry.

The daily clock uses America/Chicago. Losses are the sum of negative settled net
P&L today; winning settlements do not cancel those losses. All unresolved risk
continues to count after midnight. Policy changes on an existing ledger are rejected.
Use separate ledgers only for explicitly independent paper-policy comparisons, not
to treat one bankroll as several budgets.

`settle(id, won)` is a **hypothetical full-fill paper settlement**, with `won`
referring to the purchased YES or NO side. It does not claim or query a real fill.
The caller supplies the final outcome. The code rejects settlement before kickoff
but cannot verify that the match has finished. There is no cancellation, partial-fill
reconciliation, refund/void handling, early exit, withdrawal, deposit, or live API.
Unresolved reservations remain locked. Production integration will require account
reconciliation and a proper order lifecycle before live sizing is enabled.

The pure `size_order()` function is useful for tests but cannot itself enforce
cross-process budgets. Operational paper callers must use `PaperLedger.reserve()`
with one persistent ledger for the entire experiment. It tracks only that paper
bankroll, not the existing trading system's positions or account balance.

## Interface

Required request fields:

| Field | Meaning |
|---|---|
| fixture_id | Canonical fixture identifier shared across all its markets |
| ticker | Selected contract identifier |
| probabilities | H, D, A probabilities summing to one |
| outcome / side | H/D/A and yes/no |
| limit_price / available_contracts | Selected-side maximum purchase price and observed depth |
| fee_totals / fee_source | Explicit quantity-level total fees and provenance |
| quote_at | Timezone-aware quote timestamp, at most 30 seconds old |
| kickoff / forecast_cutoff | Timezone-aware kickoff and exactly two hours earlier |

The forecast cutoff must have arrived and kickoff must be in the future. The
forecast issue time stays fixed while the executable quote must be fresh at sizing.
The module does not independently confirm fixture/contract identity or source data.

```bash
# Run a clearly synthetic demonstration; no market/network calls:
python sizing_demo.py

# Reserve against a prepared request and one persistent paper database:
python sizing.py --request request.json --ledger runs/paper-risk.sqlite
```

The parent directory must exist. CLI default time is the actual current time, so
old requests fail freshness checks. Database records preserve requests, decisions,
policy fingerprints and explicit simulated settlements for auditing. JSON policy
default `method` is `fixed`; select `quarter_kelly` in a separately named policy
file and separate paper ledger to compare strategies. No LLM credentials are needed.

This module is ready for paper callers to integrate. The forecasting command does
not automatically call it, discover markets, submit orders, or create positions.
