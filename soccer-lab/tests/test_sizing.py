"""Independent sizing audit. Every probability, quote, fee and outcome is synthetic."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

from sizing import PaperLedger, POLICY_PATH, size_order

NOW = datetime(2026, 10, 9, 22, 0, tzinfo=timezone.utc)


def policy(method='fixed'):
    return dict(json.loads(POLICY_PATH.read_text()), method=method)


def request(fixture='synthetic-1', now=NOW, **changes):
    row = dict(fixture_id=fixture, ticker='SYNTHETIC', probabilities={'H': '.70', 'D': '.20', 'A': '.10'},
               outcome='H', side='yes', limit_price='.50', available_contracts=100,
               fee_totals={str(i): '0' for i in range(1, 101)}, fee_source='synthetic test assumptions',
               quote_at=now.isoformat(), kickoff=(now+timedelta(hours=1)).isoformat(),
               forecast_cutoff=(now-timedelta(hours=1)).isoformat())
    row.update(changes)
    return row


def snapshot(**changes):
    row = dict(cash='500', bankroll='500', open_risk='0', daily_losses='0', seen_fixture_ids=[])
    row.update(changes)
    return row


class SizingTests(unittest.TestCase):
    def test_approved_policy_caps_and_clock_cannot_be_relaxed(self):
        for key,value in [('day_timezone','UTC'),('max_match_loss','10.01'),
                          ('max_open_risk','50.01'),('daily_loss_budget','50.01'),
                          ('initial_bankroll','501'),('kelly_fraction','.5'),('mode','live')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                size_order(request(), snapshot(), dict(policy(),**{key:value}), NOW)

    def test_fixed_stake_and_no_complement(self):
        yes = size_order(request(), snapshot(), policy(), NOW)
        self.assertEqual((yes['quantity'], yes['total_cost']), (10, '5.00'))
        no = size_order(request(outcome='A', side='no'), snapshot(), policy(), NOW)
        self.assertEqual(Decimal(no['probability']), Decimal('.90'))
        rejected = size_order(request(side='no'), snapshot(), policy(), NOW)
        self.assertEqual(rejected['quantity'], 0)

    def test_fee_rounding_explicit_table_and_positive_edge(self):
        answer = size_order(request(fee_totals={'9': '.001', '10': '.001'}), snapshot(), policy(), NOW)
        self.assertEqual(answer['quantity'], 9)
        self.assertEqual(answer['total_cost'], '4.51')
        self.assertEqual(size_order(request(fee_totals={}), snapshot(), policy(), NOW)['quantity'], 0)
        self.assertEqual(size_order(request(fee_totals={'1': '.21'}), snapshot(), policy(), NOW)['quantity'], 0)
        with self.assertRaises(ValueError):
            size_order(request(fee_totals={'1': '-.01'}), snapshot(), policy(), NOW)

    def test_quarter_kelly_and_bankroll_cap(self):
        r = request(probabilities={'H':'.52', 'D':'.28', 'A':'.20'})
        answer = size_order(r, snapshot(), policy('quarter_kelly'), NOW)
        self.assertEqual((answer['quantity'], answer['total_cost']), (10, '5.00'))
        capped = size_order(r, snapshot(cash='1000', bankroll='1000'), policy('quarter_kelly'), NOW)
        self.assertEqual(capped['quantity'], 10)
        reduced = size_order(r, snapshot(cash='250', bankroll='250'), policy('quarter_kelly'), NOW)
        self.assertEqual((reduced['quantity'], reduced['total_cost']), (5, '2.50'))
        event = size_order(request(), snapshot(), policy('quarter_kelly'), NOW)
        self.assertEqual(event['total_cost'], '10.00')

    def test_cash_depth_daily_and_open_risk_caps(self):
        cases = [(snapshot(cash='1.25'), request(), 2),
                 (snapshot(open_risk='49.50'), request(), 1),
                 (snapshot(open_risk='40', daily_losses='9.50'), request(), 1),
                 (snapshot(open_risk='40', daily_losses='10'), request(), 0),
                 (snapshot(), request(available_contracts=3), 3)]
        for state, req, expected in cases:
            self.assertEqual(size_order(req, state, policy(), NOW)['quantity'], expected)

    def test_freshness_cutoff_and_input_fail_closed(self):
        for update in [dict(quote_at=(NOW-timedelta(seconds=31)).isoformat()),
                       dict(quote_at=(NOW+timedelta(seconds=1)).isoformat()),
                       dict(forecast_cutoff=NOW.isoformat()),
                       dict(kickoff=NOW.isoformat(),forecast_cutoff=(NOW-timedelta(hours=2)).isoformat())]:
            self.assertEqual(size_order(request(**update), snapshot(), policy(), NOW)['quantity'], 0)
        for update in [dict(probabilities={'H':'.8','D':'.3','A':'.1'}),
                       dict(limit_price='nan'), dict(available_contracts=True),dict(fee_source='')]:
            with self.assertRaises(ValueError):
                size_order(request(**update), snapshot(), policy(), NOW)
        self.assertEqual(size_order(request(), snapshot(seen_fixture_ids=['synthetic-1']), policy(), NOW)['quantity'],0)

    def test_concurrent_same_fixture_cannot_reserve_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = PaperLedger(Path(directory)/'paper.sqlite', policy())
            with ThreadPoolExecutor(max_workers=8) as workers:
                results = list(workers.map(lambda _: ledger.reserve(request(), NOW), range(16)))
            self.assertEqual(sum(r['quantity'] > 0 for r in results), 1)
            self.assertEqual(Decimal(ledger.snapshot(NOW)['open_risk']), Decimal('5'))

    def test_concurrent_different_fixtures_enforce_global_caps(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = PaperLedger(Path(directory)/'paper.sqlite', policy())
            with ThreadPoolExecutor(max_workers=8) as workers:
                results = list(workers.map(lambda i: ledger.reserve(request(f'synthetic-{i}'), NOW), range(20)))
            self.assertEqual(sum(r['quantity'] > 0 for r in results), 10)
            state = ledger.snapshot(NOW)
            self.assertEqual(Decimal(state['open_risk']), Decimal('50'))
            self.assertEqual(Decimal(state['cash']), Decimal('450'))

    def test_restart_gross_losses_and_no_reentry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'paper.sqlite'
            ledger = PaperLedger(path, policy())
            loss = ledger.reserve(request('loser'), NOW)
            win = ledger.reserve(request('winner'), NOW)
            settled = NOW+timedelta(hours=3)
            ledger.settle(loss['reservation_id'], False, settled)
            state = ledger.settle(win['reservation_id'], True, settled)
            self.assertEqual(Decimal(state['cash']), Decimal('500'))
            self.assertEqual(Decimal(state['daily_losses']), Decimal('5'))
            restarted = PaperLedger(path, policy())
            self.assertEqual(restarted.snapshot(settled), state)
            self.assertEqual(restarted.reserve(request('loser', settled), settled)['quantity'], 0)
            with self.assertRaises(ValueError):
                restarted.settle(loss['reservation_id'], False, settled)
            with self.assertRaises(ValueError):
                PaperLedger(path, policy('quarter_kelly'))

    def test_pending_survives_chicago_midnight(self):
        # In October Chicago midnight is 05:00 UTC, not 00:00 UTC.
        before = datetime(2026,10,10,4,59,tzinfo=timezone.utc)
        after = before+timedelta(minutes=2)
        with tempfile.TemporaryDirectory() as directory:
            ledger=PaperLedger(Path(directory)/'paper.sqlite', policy())
            for i in range(10):
                ledger.reserve(request(f'pending-{i}', before), before)
            self.assertEqual(Decimal(ledger.snapshot(after)['open_risk']), Decimal('50'))
            self.assertEqual(ledger.reserve(request('new-day', after), after)['quantity'],0)

    def test_losses_reset_at_local_midnight_only(self):
        entry=datetime(2026,10,10,0,0,tzinfo=timezone.utc)
        settled=datetime(2026,10,10,3,0,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            ledger=PaperLedger(Path(directory)/'paper.sqlite', policy())
            reservation=ledger.reserve(request(now=entry),entry)
            ledger.settle(reservation['reservation_id'],False,settled)
            self.assertEqual(Decimal(ledger.snapshot(datetime(2026,10,10,4,59,tzinfo=timezone.utc))['daily_losses']),Decimal('5'))
            self.assertEqual(Decimal(ledger.snapshot(datetime(2026,10,10,5,0,tzinfo=timezone.utc))['daily_losses']),Decimal('0'))


if __name__ == '__main__':
    unittest.main()
