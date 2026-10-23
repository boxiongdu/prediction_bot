"""Deterministic, as-of soccer forecasts. No LLM-generated probabilities or orders."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

LABELS = ['H', 'D', 'A']
FEATURES = ['home_attack', 'home_defense', 'away_attack', 'away_defense']
PROMOTION_FACTOR = .85
PRIOR_GAMES = 8.0
GOAL_PRIOR = 1.4


def elo_probabilities(home_rating, away_rating, draw_rate=.26, home_advantage=60):
    """Davidson three-outcome mapping, ordered H,D,A; draw_rate at equal strength."""
    z = np.clip((np.asarray(home_rating)-np.asarray(away_rating)+home_advantage) * np.log(10)/400, -30, 30)
    a = np.exp(z / 2)
    b = np.exp(-z / 2)
    nu = 2 * draw_rate / (1-draw_rate)
    den = a+b+nu
    return np.stack([a/den, np.ones_like(a)*nu/den, b/den], axis=-1)


def _new_team(division):
    return dict(elo=1500.0 if division == 'E0' else 1350.0, gf=0., ga=0., n=0., division=division)


def _translate(team, division):
    """Translate observed goal rates once on a division transition, never infer offset."""
    t = dict(team)
    if t['division'] != division:
        factor = PROMOTION_FACTOR if division == 'E0' else 1/PROMOTION_FACTOR
        t['gf'] *= factor
        t['ga'] /= factor
        t['division'] = division
    return t


def build_features(matches, k=20, decay=.95, fixtures=None):
    """Replay only results whose available_utc is at/before each forecast cutoff.

    Optional fixtures have kickoff_utc, forecast_utc, division, season and team names;
    their outcomes are never required. Match results are consumed in availability order.
    """
    if not 0 < decay <= 1 or k <= 0:
        raise ValueError('Invalid state-update parameters')
    source = matches.copy()
    for c in ['kickoff_utc', 'forecast_utc', 'available_utc']:
        source[c] = pd.to_datetime(source[c], utc=True)
    if (source.available_utc < source.kickoff_utc).any():
        raise ValueError('Result availability precedes kickoff')
    targets = source.copy() if fixtures is None else fixtures.copy()
    targets['kickoff_utc'] = pd.to_datetime(targets.kickoff_utc, utc=True)
    if 'forecast_utc' not in targets:
        targets['forecast_utc'] = targets.kickoff_utc - pd.Timedelta(hours=2)
    targets['forecast_utc'] = pd.to_datetime(targets.forecast_utc, utc=True)
    if (targets.forecast_utc > targets.kickoff_utc - pd.Timedelta(hours=2)).any():
        raise ValueError('Forecast violates two-hour cutoff')
    source = source.sort_values(['available_utc', 'kickoff_utc', 'home_team', 'away_team'])
    events = list(source.to_dict('records'))
    state, out, pos, last = {}, [], 0, pd.NaT
    def get(name, division):
        return _translate(state.get(name, _new_team(division)), division)
    def update(row):
        h, a = get(row['home_team'], row['division']), get(row['away_team'], row['division'])
        p = elo_probabilities(h['elo'], a['elo'])
        observed = 1. if row['home_goals'] > row['away_goals'] else .5 if row['home_goals'] == row['away_goals'] else 0.
        delta = k * (observed - (p[0]+.5*p[1]))
        h['elo'] += delta
        a['elo'] -= delta
        for t, gf, ga in [(h,row['home_goals'],row['away_goals']), (a,row['away_goals'],row['home_goals'])]:
            t['gf'] = decay*t['gf']+gf
            t['ga'] = decay*t['ga']+ga
            t['n'] = decay*t['n']+1
        state[row['home_team']], state[row['away_team']] = h, a
    for row in targets.sort_values(['forecast_utc','home_team','away_team']).to_dict('records'):
        while pos < len(events) and events[pos]['available_utc'] <= row['forecast_utc']:
            update(events[pos]); last = events[pos]['available_utc']; pos += 1
        h, a = get(row['home_team'],row['division']), get(row['away_team'],row['division'])
        for prefix, t in [('home',h),('away',a)]:
            row[prefix+'_attack'] = float(np.log((t['gf']+PRIOR_GAMES*GOAL_PRIOR)/(t['n']+PRIOR_GAMES)/GOAL_PRIOR))
            row[prefix+'_defense'] = float(-np.log((t['ga']+PRIOR_GAMES*GOAL_PRIOR)/(t['n']+PRIOR_GAMES)/GOAL_PRIOR))
            row['elo_'+prefix] = t['elo']
        row['feature_last_available_utc'] = last
        out.append(row)
    return pd.DataFrame(out)


def _fit(frame, c):
    if len(frame) == 0 or set(frame.result) != set(LABELS):
        raise ValueError('Training data must contain all H/D/A outcomes')
    model = make_pipeline(StandardScaler(), LogisticRegression(C=c, max_iter=2000, random_state=0))
    model.fit(frame[FEATURES], frame.result)
    return model


def _predict(config, train, target):
    if config['kind'] == 'elo':
        return elo_probabilities(target.elo_home.to_numpy(),target.elo_away.to_numpy(),config['draw_rate'])
    model = _fit(train, config['C'])
    p = model.predict_proba(target[FEATURES])
    return p[:,[list(model.classes_).index(x) for x in LABELS]]


def metrics(actual, probabilities):
    p = np.asarray(probabilities, dtype=float)
    y = np.asarray([LABELS.index(x) for x in actual])
    if not len(y):
        raise ValueError('No outcomes to evaluate')
    if p.shape != (len(y),3) or not np.isfinite(p).all() or (p < 0).any() or not np.allclose(p.sum(1),1):
        raise ValueError('Invalid probability matrix')
    onehot = np.eye(3)[y]
    calibration = {}
    for j,label in enumerate(LABELS):
        buckets=[]
        for b in range(10):
            mask = (p[:,j]>=b/10) & ((p[:,j]<(b+1)/10) if b<9 else (p[:,j]<=1))
            if mask.any():
                buckets.append(dict(lower=b/10,upper=(b+1)/10,n=int(mask.sum()),mean_probability=float(p[mask,j].mean()),frequency=float(onehot[mask,j].mean())))
        calibration[label]=buckets
    return dict(n=len(y),log_loss=float(-np.log(np.clip(p[np.arange(len(y)),y],1e-15,1)).mean()),brier=float(((p-onehot)**2).sum(1).mean()),accuracy=float((p.argmax(1)==y).mean()),calibration=calibration)


def _records(frame,p,model_id):
    cols=['season','division','kickoff_utc','forecast_utc','home_team','away_team','result','feature_last_available_utc']
    ans=frame[[c for c in cols if c in frame]].copy()
    for i,label in enumerate(LABELS): ans['p_'+label]=p[:,i]
    ans['model_id']=model_id
    return ans


def _hash(frame):
    cols=['season','division','kickoff_utc','forecast_utc','available_utc','home_team','away_team','home_goals','away_goals','result']
    text=frame[cols].sort_values(['kickoff_utc','home_team','away_team']).to_csv(index=False)
    return hashlib.sha256(text.encode()).hexdigest()


def run_experiment(matches, output_dir, evaluate_test=False):
    """Select with 2324->2425. Test only a previously frozen selection, no retuning.

    Calling once without evaluate_test freezes selection.json. A later explicit test run
    reuses that file and rejects changed development inputs. Team states update online;
    logistic coefficients remain frozen throughout each evaluated season.
    """
    output_dir=Path(output_dir); output_dir.mkdir(parents=True,exist_ok=True)
    data=matches.copy(); data['season']=data.season.astype(str)
    dev=data[data.season.isin(['2223','2324','2425'])].copy()
    for season in ['2223','2324','2425']:
        if not ((dev.season==season)&(dev.division=='E0')).any(): raise ValueError('Missing EPL season '+season)
    fingerprint=_hash(dev)
    lock=output_dir/'selection.json'
    if evaluate_test and not lock.exists():
        raise ValueError('First run without evaluate_test to freeze the selection before opening holdout')
    existing=json.loads(lock.read_text()) if lock.exists() else None
    if existing and existing['development_sha256']!=fingerprint:
        raise ValueError('Development data changed; use a new experiment directory')
    code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if existing and existing.get('model_code_sha256') != code_sha256:
        raise ValueError('Model code changed; use a new experiment directory')
    if evaluate_test:
        if (output_dir/'test_metrics.json').exists() or (output_dir/'test.csv').exists():
            raise ValueError('Holdout already evaluated; do not repeatedly inspect or overwrite it')
        if not ((data.season=='2526')&(data.division=='E0')).any():
            raise ValueError('No EPL 2526 holdout')
        cfg=existing['config']
        through_test=data[data.season.isin(['2223','2324','2425','2526'])]
        f=build_features(through_test,k=cfg['k'],decay=cfg['decay'])
        train=f[f.season.isin(['2324','2425'])&(f.division=='E0')]
        test=f[(f.season=='2526')&(f.division=='E0')]
        p=_predict(cfg,train,test)
        summary=dict(selection=existing,test=metrics(test.result,p),test_evaluated=True,holdout_sha256=_hash(through_test[through_test.season=='2526']))
        _records(test,p,cfg['id']).to_csv(output_dir/'test.csv',index=False)
        (output_dir/'test_metrics.json').write_text(json.dumps(summary,indent=2)+'\n')
        return summary
    candidates=[]
    for k in [20,40]:
        for d in [.24,.30]: candidates.append(dict(id=f'elo_k{k}_d{d}',kind='elo',k=k,draw_rate=d,decay=.95))
    for decay in [.90,.97]:
        for c in [.1,1.]: candidates.append(dict(id=f'attack_defense_decay{decay}_C{c}',kind='logistic',k=20,decay=decay,C=c))
    cache={}; results={}; predictions=[]
    for cfg in candidates:
        key=(cfg['k'],cfg['decay'])
        if key not in cache: cache[key]=build_features(dev,k=key[0],decay=key[1])
        f=cache[key]; train=f[(f.season=='2324')&(f.division=='E0')]; val=f[(f.season=='2425')&(f.division=='E0')]
        p=_predict(cfg,train,val)
        results[cfg['id']]=metrics(val.result,p)
        predictions.append(_records(val,p,cfg['id']))
    counts=train.result.value_counts(); baseline=np.array([counts.get(x,0)/len(train) for x in LABELS])
    results['historical_frequencies']=metrics(val.result,np.tile(baseline,(len(val),1)))
    winner=min(candidates,key=lambda cfg:(results[cfg['id']]['log_loss'],cfg['id']))
    selection=dict(version=1,model_code_sha256=code_sha256,config=winner,development_sha256=fingerprint,selection_metric='2425 log loss',features=FEATURES,holdout_season='2526',coefficient_policy='Frozen per evaluated season; refit on all earlier modeling seasons before next season',promotion_factor=PROMOTION_FACTOR,championship_initial_elo=1350,home_advantage=60)
    if existing:
        if existing!=selection: raise ValueError('Locked selection differs; do not overwrite experiment')
    else: lock.write_text(json.dumps(selection,indent=2)+'\n')
    pd.concat(predictions).to_csv(output_dir/'validation.csv',index=False)
    summary=dict(selection=selection,validation=results,test_evaluated=False)
    (output_dir/('test_metrics.json' if evaluate_test else 'metrics.json')).write_text(json.dumps(summary,indent=2)+'\n')
    return summary


def predict_fixtures(matches, fixtures, selection):
    """Forecast requested fixtures, fitting coefficients on completed earlier seasons.

    Every forecast uses its own two-hour cutoff, including for coefficient fitting.
    Current-season results update team strengths, while coefficients stay season-frozen.
    """
    if selection.get('model_code_sha256') != hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
        raise ValueError('Forecast selection belongs to different model code')
    required={'season','division','kickoff_utc','home_team','away_team'}
    if not required.issubset(fixtures.columns):
        raise ValueError('Fixture columns missing')
    fixtures=fixtures.copy(); fixtures['season']=fixtures.season.astype(str)
    if not fixtures.division.eq('E0').all() or not fixtures.season.str.fullmatch(r'\d{4}').all():
        raise ValueError('Forecasts require EPL division E0 and four-digit season')
    if any(fixtures[c].isna().any() or fixtures[c].astype(str).str.strip().eq('').any() for c in ['home_team','away_team']):
        raise ValueError('Fixture team names must be nonblank')
    if fixtures.home_team.eq(fixtures.away_team).any() or fixtures.duplicated(['kickoff_utc','home_team','away_team']).any():
        raise ValueError('Invalid or duplicate fixture')
    cfg=selection['config']; data=matches.copy(); data['season']=data.season.astype(str)
    outputs=[]
    for row in fixtures.to_dict('records'):
        kickoff=pd.to_datetime(row['kickoff_utc'],utc=True); cutoff=kickoff-pd.Timedelta(hours=2)
        if 'forecast_utc' in row and pd.to_datetime(row['forecast_utc'],utc=True)!=cutoff:
            raise ValueError('Expected exactly two-hour fixture cutoff')
        row['forecast_utc']=cutoff
        past=data[pd.to_datetime(data.available_utc,utc=True)<=cutoff].copy()
        known=set(past.home_team)|set(past.away_team)
        if row['home_team'] not in known or row['away_team'] not in known:
            raise ValueError('Unknown fixture team; verify canonical names and history')
        train=build_features(past,k=cfg['k'],decay=cfg['decay'])
        train=train[(train.division=='E0')&(train.season!='2223')&(train.season.astype(int)<int(row['season']))]
        target=build_features(past,k=cfg['k'],decay=cfg['decay'],fixtures=pd.DataFrame([row]))
        p=_predict(cfg,train,target)
        result=_records(target,p,cfg['id'])
        known=set(past.home_team)|set(past.away_team)
        result['prior_only_home']=row['home_team'] not in known
        result['prior_only_away']=row['away_team'] not in known
        outputs.append(result)
    return pd.concat(outputs,ignore_index=True) if outputs else pd.DataFrame()
