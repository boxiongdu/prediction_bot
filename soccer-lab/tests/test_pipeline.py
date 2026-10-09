"""Independent contract tests. Synthetic matches test invariants, not model skill."""
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


def matches_fixture():
    rows = []
    for i in range(16):
        kickoff = pd.Timestamp('2023-08-01 14:00', tz='UTC') + pd.Timedelta(days=i * 4)
        hg, ag = [(2, 0), (1, 1), (0, 2)][i % 3]
        rows.append(dict(season='2324', division='E0', home_team='Alpha' if i % 2 == 0 else 'Beta',
                         away_team='Beta' if i % 2 == 0 else 'Alpha', kickoff_utc=kickoff,
                         forecast_utc=kickoff-pd.Timedelta(hours=2), available_utc=kickoff+pd.Timedelta(hours=24),
                         home_goals=hg, away_goals=ag, result='H' if hg > ag else 'A' if hg < ag else 'D',
                         home_shots=12., away_shots=9., home_sot=5., away_sot=3.))
    return pd.DataFrame(rows)


FEATURES = ['home_attack', 'home_defense', 'away_attack', 'away_defense', 'elo_home', 'elo_away']


class PipelineTests(unittest.TestCase):
    def test_forecast_contract_and_frozen_code(self):
        import hashlib
        import modeling
        data = matches_fixture()
        selection = dict(model_code_sha256=hashlib.sha256(Path(modeling.__file__).read_bytes()).hexdigest(),
                         config=dict(kind='elo', id='test_elo', k=20, decay=.95, draw_rate=.26))
        fixture = pd.DataFrame([dict(season='2324', division='E0', kickoff_utc=pd.Timestamp('2023-11-01 15:00', tz='UTC'), home_team='Alpha', away_team='Beta')])
        result = modeling.predict_fixtures(data, fixture, selection)
        self.assertAlmostEqual(result[['p_H', 'p_D', 'p_A']].to_numpy().sum(), 1.)
        self.assertEqual(result.loc[0, 'forecast_utc'], pd.Timestamp('2023-11-01 13:00', tz='UTC'))
        for column, value in [('division', 'E1'), ('season', 'invalid'), ('home_team', ''), ('home_team', 'Unknown'), ('home_team', 'Beta'), ('forecast_utc', pd.Timestamp('2023-11-01 14:00', tz='UTC'))]:
            invalid = fixture.copy()
            invalid[column] = value
            with self.subTest(column=column, value=value), self.assertRaises(ValueError):
                modeling.predict_fixtures(data, invalid, selection)
        with self.assertRaises(ValueError):
            modeling.predict_fixtures(data, pd.concat([fixture, fixture]), selection)
        with self.assertRaises(ValueError):
            modeling.predict_fixtures(data, fixture, dict(selection, model_code_sha256='wrong'))

    def test_holdout_is_not_used_for_selection_and_is_single_use(self):
        from modeling import run_experiment
        seasons = []
        for year, season in ((2022, '2223'), (2023, '2324'), (2024, '2425'), (2025, '2526')):
            frame = matches_fixture()
            shift = pd.DateOffset(years=year-2023)
            for column in ['kickoff_utc', 'forecast_utc', 'available_utc']:
                frame[column] = frame[column] + shift
            frame['season'] = season
            seasons.append(frame)
        data = pd.concat(seasons, ignore_index=True)
        changed = data.copy()
        changed.loc[changed.season == '2526', ['home_goals', 'away_goals', 'result']] = [9, 0, 'H']
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            with self.assertRaises(ValueError):
                run_experiment(data, one, evaluate_test=True)
            first = run_experiment(data, one)
            second = run_experiment(changed, two)
            self.assertEqual(first['selection'], second['selection'])
            self.assertEqual(first['validation'], second['validation'])
            self.assertFalse(Path(one, 'test_metrics.json').exists())
            opened = run_experiment(data, one, evaluate_test=True)
            self.assertTrue(opened['test_evaluated'])
            with self.assertRaises(ValueError):
                run_experiment(data, one, evaluate_test=True)
            changed_dev = data.copy()
            changed_dev.loc[0, 'home_goals'] = 15
            with self.assertRaises(ValueError):
                run_experiment(changed_dev, one)

    def test_contradictory_optional_shots_are_quarantined(self):
        from data import normalize_matches
        raw = pd.DataFrame([dict(Div='E0', Date='01/08/2023', Time='15:00', HomeTeam='A', AwayTeam='B', FTHG=2, FTAG=0, FTR='H', HS=2, HST=7, AS=9, AST=3)])
        clean = normalize_matches(raw, '2324', 'E0')
        self.assertTrue(clean.loc[0, 'home_shots_invalid'])
        self.assertTrue(pd.isna(clean.loc[0, 'home_shots']))
        self.assertTrue(pd.isna(clean.loc[0, 'home_sot']))
        self.assertEqual(clean.loc[0, 'home_goals'], 2)
        self.assertEqual(clean.loc[0, 'away_shots'], 9)

    def test_ingestion_excludes_odds_and_preserves_cutoff(self):
        from data import normalize_matches
        raw = pd.DataFrame([dict(Div='E0', Date='01/08/2023', Time='15:00', HomeTeam='A', AwayTeam='B', FTHG=2, FTAG=0, FTR='H', B365H=1.01, B365D=50., B365A=100.)])
        clean = normalize_matches(raw, '2324', 'E0')
        self.assertFalse(any('B365' in c or 'odds' in c.lower() for c in clean))
        self.assertEqual(clean.loc[0, 'kickoff_utc'] - clean.loc[0, 'forecast_utc'], pd.Timedelta(hours=2))
        self.assertEqual(clean.loc[0, 'kickoff_utc'], pd.Timestamp('2023-08-01 14:00', tz='UTC'))

    def test_invalid_label_and_duplicate_fail_closed(self):
        from data import normalize_matches
        raw = pd.DataFrame([dict(Div='E0', Date='01/08/2023', Time='15:00', HomeTeam='A', AwayTeam='B', FTHG=2, FTAG=0, FTR='A')])
        with self.assertRaises(ValueError):
            normalize_matches(raw, '2324', 'E0')
        raw.loc[0, 'FTR'] = 'H'
        with self.assertRaises(ValueError):
            normalize_matches(pd.concat([raw, raw]), '2324', 'E0')

    def test_current_and_future_results_cannot_change_current_features(self):
        from modeling import build_features
        matches = matches_fixture()
        reference = build_features(matches)
        changed = matches.copy()
        changed.loc[8:, ['home_goals', 'away_goals', 'home_shots', 'away_shots', 'home_sot', 'away_sot']] = [9, 0, 40, 1, 20, 0]
        changed.loc[8:, 'result'] = 'H'
        actual = build_features(changed)
        np.testing.assert_allclose(reference.loc[:8, FEATURES], actual.loc[:8, FEATURES], atol=0, rtol=0)

    def test_previous_available_result_does_change_later_features(self):
        from modeling import build_features
        matches = matches_fixture()
        reference = build_features(matches)
        changed = matches.copy()
        changed.loc[0, ['home_goals', 'away_goals', 'result']] = [0, 8, 'A']
        actual = build_features(changed)
        self.assertFalse(np.allclose(reference.loc[1, FEATURES].astype(float), actual.loc[1, FEATURES].astype(float)))

    def test_same_day_unavailable_result_is_excluded(self):
        from modeling import build_features
        matches = matches_fixture().iloc[:3].copy()
        for i in (1, 2):
            matches.loc[i, 'kickoff_utc'] = matches.loc[0, 'kickoff_utc'] + pd.Timedelta(hours=i * 3)
            matches.loc[i, 'forecast_utc'] = matches.loc[i, 'kickoff_utc'] - pd.Timedelta(hours=2)
            matches.loc[i, 'available_utc'] = matches.loc[i, 'kickoff_utc'] + pd.Timedelta(hours=24)
        reference = build_features(matches)
        changed = matches.copy()
        changed.loc[0, ['home_goals', 'away_goals', 'result']] = [0, 8, 'A']
        actual = build_features(changed)
        np.testing.assert_allclose(reference[FEATURES], actual[FEATURES], atol=0, rtol=0)

    def test_probability_domain_and_normalization(self):
        from modeling import elo_probabilities
        for a, b in ((1500, 1500), (500, 2200), (2200, 500)):
            p = elo_probabilities(a, b)
            self.assertEqual(len(p), 3)
            self.assertTrue(np.isfinite(p).all())
            self.assertTrue((p >= 0).all() and (p <= 1).all())
            self.assertAlmostEqual(float(p.sum()), 1.)

    def test_features_reproducible(self):
        from modeling import build_features
        matches = matches_fixture()
        first = build_features(matches)
        second = build_features(matches.copy(deep=True))
        pd.testing.assert_frame_equal(first, second)

    def test_promoted_team_retains_history_with_translation(self):
        from modeling import build_features
        promoted = matches_fixture()
        promoted.loc[:7, 'division'] = 'E1'
        f = build_features(promoted)
        # Championship performances must matter, rather than every entrant being reset.
        changed = promoted.copy()
        changed.loc[:7, ['home_goals', 'away_goals', 'result']] = [5, 0, 'H']
        altered = build_features(changed)
        self.assertFalse(np.allclose(f.loc[8, FEATURES].astype(float), altered.loc[8, FEATURES].astype(float)))
        self.assertTrue(np.isfinite(f.loc[8, FEATURES].astype(float)).all())

    def test_no_feature_timestamp_after_cutoff(self):
        from modeling import build_features
        f = build_features(matches_fixture())
        values = pd.to_datetime(f['feature_last_available_utc'], utc=True)
        cutoff = pd.to_datetime(f['forecast_utc'], utc=True)
        self.assertTrue(((values <= cutoff) | values.isna()).all())


if __name__ == '__main__':
    unittest.main()
