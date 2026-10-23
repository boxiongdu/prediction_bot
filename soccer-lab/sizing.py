"""Deterministic binary-contract sizing and atomic PAPER reservations. No exchange calls."""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid
from zoneinfo import ZoneInfo

D = Decimal
CENT = D('0.01')
POLICY_PATH = Path(__file__).with_name('risk_policy.json')


def decimal(value):
    if isinstance(value, bool):
        raise ValueError('Boolean is not a number')
    n = D(str(value))
    if not n.is_finite():
        raise ValueError('Nonfinite number')
    return n


def timestamp(value):
    t = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace('Z', '+00:00'))
    if t.tzinfo is None:
        raise ValueError('Timezone required')
    return t.astimezone(timezone.utc)


def validate_policy(policy):
    if policy['version'] != 1 or policy['mode'] != 'paper':
        raise ValueError('Only paper policy version 1 is supported')
    if policy['method'] not in ('fixed', 'quarter_kelly'):
        raise ValueError('Unknown sizing method')
    for key in ('initial_bankroll', 'fixed_stake', 'max_match_loss', 'max_open_risk', 'daily_loss_budget'):
        if decimal(policy[key]) <= 0:
            raise ValueError('Positive budget required: '+key)
    if decimal(policy['kelly_fraction']) != D('.25'):
        raise ValueError('V1 challenger is quarter Kelly only')
    # Approved maximums cannot be relaxed by editing JSON alone.
    for key, cap in [('initial_bankroll',500),('max_match_loss',10),('max_open_risk',50),('daily_loss_budget',50),('fixed_stake',5)]:
        if decimal(policy[key]) > cap:
            raise ValueError('Approved cap exceeded: '+key)
    for key in ('max_quote_age_seconds','max_contracts'):
        if type(policy[key]) is not int or policy[key] <= 0:
            raise ValueError('Positive integer required: '+key)
    if policy['max_contracts'] > 1000 or policy['max_quote_age_seconds'] > 30:
        raise ValueError('V1 quote/quantity safety bound exceeded')
    if policy['day_timezone'] != 'America/Chicago':
        raise ValueError('V1 daily risk clock is America/Chicago')
    ZoneInfo(policy['day_timezone'])
    return policy


def policy_hash(policy):
    return hashlib.sha256(json.dumps(policy,sort_keys=True).encode()).hexdigest()


def size_order(request, snapshot, policy, now=None):
    """Pure calculation; use PaperLedger.reserve for serialized durable enforcement.

    Request prices are BUY prices for the chosen yes/no side, never an unconverted
    YES bid for a NO purchase. fee_totals contains explicit dollar fees by quantity.
    Missing required inputs raise; ineligible complete requests return zero quantity.
    """
    validate_policy(policy)
    now = timestamp(now or datetime.now(timezone.utc))
    for field in ('fixture_id','ticker','fee_source'):
        if not isinstance(request[field],str) or not request[field].strip():
            raise ValueError('Missing '+field)
    if request['outcome'] not in ('H','D','A') or request['side'] not in ('yes','no'):
        raise ValueError('Unknown outcome/side')
    probs = {key:decimal(request['probabilities'][key]) for key in ('H','D','A')}
    if any(p<0 or p>1 for p in probs.values()) or abs(sum(probs.values())-1)>D('0.000001'):
        raise ValueError('H/D/A probabilities must sum to one')
    p = probs[request['outcome']]
    if request['side']=='no':
        p = 1-p
    price = decimal(request['limit_price'])
    if not 0 < price < 1:
        raise ValueError('Selected-side limit price must be between zero and one')
    depth = request['available_contracts']
    if type(depth) is not int or depth < 0:
        raise ValueError('Depth must be nonnegative whole contracts')
    fees = {}
    for key,value in request['fee_totals'].items():
        if not str(key).isdigit() or int(key)<1:
            raise ValueError('Fee table keys must be positive quantities')
        fees[int(key)] = decimal(value)
        if fees[int(key)] < 0:
            raise ValueError('Fee rebates unsupported; use a conservative nonnegative bound')
    values = {k:decimal(snapshot[k]) for k in ('cash','bankroll','open_risk','daily_losses')}
    if any(v < 0 for v in values.values()):
        raise ValueError('Negative portfolio input')
    base = {'mode':'paper','quantity':0,'total_cost':'0.00','fee':'0.00',
        'fixture_id':request['fixture_id'],'ticker':request['ticker'],
        'outcome':request['outcome'],'side':request['side'],'probability':str(p),
        'method':policy['method'],'policy_sha256':policy_hash(policy),
        'fee_source':request['fee_source'],'as_of':now.isoformat()}
    def reject(reason):
        return dict(base,reason=reason)
    quote_at = timestamp(request['quote_at'])
    if not 0 <= (now-quote_at).total_seconds() <= policy['max_quote_age_seconds']:
        return reject('stale_or_future_quote')
    kickoff = timestamp(request['kickoff'])
    cutoff = timestamp(request['forecast_cutoff'])
    if cutoff != kickoff-timedelta(hours=2) or cutoff>now:
        return reject('invalid_or_unreached_forecast_cutoff')
    if now>=kickoff:
        return reject('match_started')
    if request['fixture_id'] in snapshot['seen_fixture_ids']:
        return reject('fixture_already_reserved_no_adding_or_reentry')
    budget = max(D(0),min(decimal(policy['max_match_loss']),
        decimal(policy['max_open_risk'])-values['open_risk'],
        decimal(policy['daily_loss_budget'])-values['daily_losses']-values['open_risk'],
        values['cash']))
    base['risk_budget']=str(budget)
    if budget<=0:
        return reject('risk_budget_exhausted')
    if depth==0:
        return reject('no_executable_depth')
    maximum = min(depth,policy['max_contracts'],int(budget/price))
    best = None
    for qty in range(1,maximum+1):
        if qty not in fees:
            continue  # Never silently assume zero fees.
        cost=(price*qty+fees[qty]).quantize(CENT,rounding=ROUND_CEILING)
        unit_cost=cost/qty
        if unit_cost>=1 or p<=unit_cost:
            continue
        full_kelly=(p-unit_cost)/(1-unit_cost)
        stake=(decimal(policy['fixed_stake']) if policy['method']=='fixed' else
            decimal(policy['kelly_fraction'])*min(values['bankroll'],decimal(policy['initial_bankroll']))*full_kelly)
        if cost <= min(budget,stake):
            best=dict(base,quantity=qty,total_cost=str(cost),fee=str(fees[qty]),
                limit_price=str(price),net_edge=str(p-unit_cost),
                full_kelly_fraction=str(full_kelly),strategy_budget=str(stake),reason='eligible')
    return best or reject('no_quantity_with_known_fees_positive_edge_and_budget')


class PaperLedger:
    """Dedicated simulated bankroll. All pending intent counts immediately as risk.

    No broker account reconciliation, cancellation, partial fills, mark-to-market,
    live submission, or live settlement lookup. reserve is intent, not a claimed fill.
    settle is an explicit hypothetical full-fill settlement for paper evaluation.
    """
    def __init__(self,path,policy):
        self.path=str(path)
        self.policy=dict(validate_policy(dict(policy)))
        with self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS reservations (id TEXT PRIMARY KEY,fixture_id TEXT UNIQUE NOT NULL,quantity INTEGER NOT NULL,cost TEXT NOT NULL,kickoff TEXT NOT NULL,created_at TEXT NOT NULL,settled_at TEXT,payout TEXT,request_json TEXT NOT NULL,decision_json TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS audit (created_at TEXT NOT NULL,action TEXT NOT NULL,payload TEXT NOT NULL)')
            db.execute('INSERT OR IGNORE INTO metadata VALUES (?,?)',('policy',json.dumps(self.policy,sort_keys=True)))
            saved=db.execute('SELECT value FROM metadata WHERE key=?',('policy',)).fetchone()[0]
            if json.loads(saved)!=self.policy:
                raise ValueError('Ledger policy is frozen. Compare policies in separate paper ledgers; do not reset live budgets.')

    def _connect(self):
        db=sqlite3.connect(self.path,timeout=15)
        db.row_factory=sqlite3.Row
        return db

    def _snapshot(self,db,now):
        rows=db.execute('SELECT * FROM reservations').fetchall()
        spent=sum((decimal(r['cost']) for r in rows),D(0))
        payouts=sum((decimal(r['payout']) for r in rows if r['payout'] is not None),D(0))
        risk=sum((decimal(r['cost']) for r in rows if r['settled_at'] is None),D(0))
        tz=ZoneInfo(self.policy['day_timezone'])
        today=now.astimezone(tz).date()
        losses=sum((max(D(0),decimal(r['cost'])-decimal(r['payout'])) for r in rows
            if r['settled_at'] is not None and timestamp(r['settled_at']).astimezone(tz).date()==today),D(0))
        cash=decimal(self.policy['initial_bankroll'])-spent+payouts
        return {'cash':str(cash),'bankroll':str(cash+risk),'open_risk':str(risk),
            'daily_losses':str(losses),'seen_fixture_ids':[r['fixture_id'] for r in rows]}

    def snapshot(self,now=None):
        now=timestamp(now or datetime.now(timezone.utc))
        with self._connect() as db:
            return self._snapshot(db,now)

    def reserve(self,request,now=None):
        now=timestamp(now or datetime.now(timezone.utc))
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            decision=size_order(request,self._snapshot(db,now),self.policy,now)
            if decision['quantity']:
                rid=uuid.uuid4().hex
                decision['reservation_id']=rid
                db.execute('INSERT INTO reservations VALUES (?,?,?,?,?,?,NULL,NULL,?,?)',
                    (rid,request['fixture_id'],decision['quantity'],decision['total_cost'],
                     timestamp(request['kickoff']).isoformat(),now.isoformat(),
                     json.dumps(request,default=str,sort_keys=True),json.dumps(decision,sort_keys=True)))
            db.execute('INSERT INTO audit VALUES (?,?,?)',(now.isoformat(),'size_and_reserve',json.dumps(decision,sort_keys=True)))
            return decision

    def settle(self,reservation_id,won,now=None):
        if type(won) is not bool:
            raise ValueError('won must be a boolean outcome for the selected contract side')
        now=timestamp(now or datetime.now(timezone.utc))
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM reservations WHERE id=?',(reservation_id,)).fetchone()
            if row is None or row['settled_at'] is not None:
                raise ValueError('Unknown or already settled reservation')
            if now<timestamp(row['kickoff']):
                raise ValueError('Cannot simulate settlement before kickoff')
            payout=str(row['quantity'] if won else 0)
            db.execute('UPDATE reservations SET payout=?,settled_at=? WHERE id=?',(payout,now.isoformat(),reservation_id))
            db.execute('INSERT INTO audit VALUES (?,?,?)',(now.isoformat(),'hypothetical_full_fill_settlement',
                json.dumps({'reservation_id':reservation_id,'won':won,'payout':payout})))
            return self._snapshot(db,now)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request',required=True,help='JSON request with explicit side, fee quotes and timestamps')
    parser.add_argument('--ledger',required=True,help='Persistent PAPER SQLite path, reuse for every run')
    parser.add_argument('--policy',default=str(POLICY_PATH))
    args=parser.parse_args()
    policy=json.loads(Path(args.policy).read_text())
    request=json.loads(Path(args.request).read_text())
    decision=PaperLedger(args.ledger,policy).reserve(request)
    print(json.dumps(decision,indent=2))


if __name__=='__main__':
    main()
