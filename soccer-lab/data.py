"""Football-Data ingestion. No bookmaker fields enter the modeling interface."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import urllib.request
import pandas as pd

SEASONS = ('2223', '2324', '2425', '2526', '2627')
DIVISIONS = ('E0', 'E1')
REQUIRED = ('Div', 'Date', 'Time', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG', 'FTR')
STAT_MAP = {'HS':'home_shots','AS':'away_shots','HST':'home_sot','AST':'away_sot'}


def normalize_matches(raw: pd.DataFrame, season: str, division: str, source_timezone: str = 'Europe/London') -> pd.DataFrame:
    """Validate complete results; fail closed on ambiguous timestamps or bad labels.

    Source notes do not document a timezone. Europe/London is an explicit,
    configurable assumption for English fixtures. available_utc is a 24-hour
    publication proxy, NOT observed historical availability.
    """
    missing = set(REQUIRED) - set(raw.columns)
    if missing:
        raise ValueError(f'Missing required columns: {sorted(missing)}')
    raw = raw.dropna(how='all').copy()
    if raw.empty:
        raise ValueError('Empty match file')
    if not raw.Div.eq(division).all():
        raise ValueError('Division mismatch')
    label_cols = ['FTHG','FTAG','FTR']
    partial = raw[label_cols].notna().sum(axis=1).isin([1,2])
    if partial.any():
        raise ValueError('Partially populated result')
    # Unplayed fixtures never acquire synthetic zero-goal labels.
    raw = raw.loc[raw[label_cols].notna().all(axis=1)].copy()
    for column in ('HomeTeam','AwayTeam','Date','Time'):
        if raw[column].isna().any() or raw[column].astype(str).str.strip().eq('').any():
            raise ValueError(f'Missing {column}')
    for column in ('FTHG','FTAG'):
        n = pd.to_numeric(raw[column], errors='raise')
        if ((n < 0) | (n % 1 != 0)).any():
            raise ValueError('Goals must be nonnegative integers')
        raw[column] = n.astype(int)
    expected = raw.apply(lambda r: 'H' if r.FTHG > r.FTAG else 'A' if r.FTHG < r.FTAG else 'D', axis=1)
    if not raw.FTR.eq(expected).all():
        raise ValueError('Result inconsistent with goals')
    # Explicit formats avoid pandas mixed-date inference changing across versions.
    def parse_date(value):
        for fmt in ('%d/%m/%Y','%d/%m/%y'):
            try:
                return datetime.strptime(str(value),fmt)
            except ValueError:
                pass
        raise ValueError(f'Invalid date: {value}')
    naive = pd.Series([datetime.combine(parse_date(d).date(), datetime.strptime(str(t),'%H:%M').time())
                       for d,t in zip(raw.Date,raw.Time)], index=raw.index, dtype='datetime64[ns]')
    kickoff = naive.dt.tz_localize(source_timezone, ambiguous='raise', nonexistent='raise').dt.tz_convert('UTC')
    out = pd.DataFrame({
        'season': str(season), 'division': division,
        'home_team': raw.HomeTeam.astype(str).str.strip(),
        'away_team': raw.AwayTeam.astype(str).str.strip(),
        'kickoff_utc': kickoff, 'forecast_utc': kickoff-pd.Timedelta(hours=2),
        'available_utc': kickoff+pd.Timedelta(hours=24),
        'home_goals': raw.FTHG, 'away_goals': raw.FTAG, 'result': raw.FTR,
    })
    if out.home_team.eq(out.away_team).any():
        raise ValueError('Team cannot play itself')
    if out.duplicated(['season','division','home_team','away_team']).any():
        raise ValueError('Duplicate fixture; source correction or replay needs manual review')
    for source, target in STAT_MAP.items():
        values = pd.to_numeric(raw[source], errors='raise') if source in raw else pd.Series(float('nan'),index=raw.index)
        if ((values.dropna() < 0) | (values.dropna() % 1 != 0)).any():
            raise ValueError(f'Invalid nonnegative count {source}')
        out[target] = values
    for team in ('home','away'):
        bad = out[f'{team}_sot'] > out[f'{team}_shots']
        out[f'{team}_shots_invalid'] = bad
        # Quarantine optional contradictory observations, preserving valid goals.
        out.loc[bad, [f'{team}_sot', f'{team}_shots']] = float('nan')
    return out.sort_values(['kickoff_utc','division','home_team']).reset_index(drop=True)


def load_matches(data_dir: str | Path, seasons=None, source_timezone='Europe/London') -> pd.DataFrame:
    """Load exact requested seasons, both leagues. Missing files are errors."""
    data_dir = Path(data_dir)
    requested = list(SEASONS if seasons is None else map(str,seasons))
    tables = []
    provenance = []
    for season in requested:
        if not re.fullmatch(r'\d{4}',season):
            raise ValueError('Season must be a four-digit string')
        for division in DIVISIONS:
            path = data_dir/f'{season}_{division}.csv'
            content = path.read_bytes()
            tables.append(normalize_matches(pd.read_csv(io.BytesIO(content)), season, division, source_timezone))
            provenance.append({'path':str(path),'sha256':hashlib.sha256(content).hexdigest()})
    if not tables:
        raise ValueError('No seasons selected')
    matches = pd.concat(tables,ignore_index=True).sort_values(['kickoff_utc','division','home_team']).reset_index(drop=True)
    matches.attrs['provenance'] = provenance
    matches.attrs['timing_assumption'] = 'Europe/London source timezone; kickoff+24h availability proxy; not point-in-time verified'
    return matches


def download(data_dir: str | Path, seasons=SEASONS):
    """Download raw source snapshots, preserving immutable content-addressed copies."""
    dest = Path(data_dir)
    dest.mkdir(parents=True, exist_ok=True)
    snapshots = dest/'snapshots'
    snapshots.mkdir(exist_ok=True)
    def fetch(pair):
        season, division = pair
        if not re.fullmatch(r'\d{4}',str(season)) or division not in DIVISIONS:
            raise ValueError('Invalid source identifier')
        url = f'https://www.football-data.co.uk/mmz4281/{season}/{division}.csv'
        req = urllib.request.Request(url,headers={'User-Agent':'soccer-research-baseline/1.0'})
        with urllib.request.urlopen(req,timeout=40) as response:
            content = response.read()
        # Validate before replacing latest. Odds retained only in original raw bytes.
        frame = normalize_matches(pd.read_csv(io.BytesIO(content)),str(season),division)
        digest = hashlib.sha256(content).hexdigest()
        filename = f'{season}_{division}.csv'
        (snapshots/f'{season}_{division}_{digest[:16]}.csv').write_bytes(content)
        temp = dest/(filename+'.tmp')
        temp.write_bytes(content)
        temp.replace(dest/filename)
        return {'file':filename,'url':url,'retrieved_utc':datetime.now(timezone.utc).isoformat(),
                'sha256':digest,'completed_rows':len(frame),'season':str(season),'division':division,
                'source_timezone_assumption':'Europe/London','availability_proxy_hours':24,
                'missing_stats':{c:int(frame[c].isna().sum()) for c in STAT_MAP.values()},
                'quarantined_shot_rows':int((frame.home_shots_invalid | frame.away_shots_invalid).sum())}
    pairs = [(str(s),d) for s in seasons for d in DIVISIONS]
    entries, failures = [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [(pair,pool.submit(fetch,pair)) for pair in pairs]
        for pair,future in futures:
            try:
                entries.append(future.result())
            except Exception as exc:
                failures.append({'season':pair[0],'division':pair[1],'error':str(exc)})
    prior_path = dest/'manifest.json'
    prior = json.loads(prior_path.read_text()) if prior_path.exists() else {}
    indexed = {x['file']:x for x in prior.get('sources',[])}
    indexed.update({x['file']:x for x in entries})
    failed = {(x['season'],x['division']):x for x in prior.get('failures',[])}
    for item in entries:
        failed.pop((item['season'],item['division']),None)
    failed.update({(x['season'],x['division']):x for x in failures})
    manifest = {'sources':list(indexed.values()),'failures':list(failed.values()),'schema_version':1}
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    (dest/f'manifest_{stamp}.json').write_text(json.dumps(manifest,indent=2))
    (dest/'manifest.json').write_text(json.dumps(manifest,indent=2))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['download','audit'])
    parser.add_argument('--data-dir',default='data/raw')
    parser.add_argument('--seasons',nargs='+',default=list(SEASONS))
    args = parser.parse_args()
    if args.command == 'download':
        manifest = download(args.data_dir,args.seasons)
        print(json.dumps(manifest,indent=2))
        if manifest['failures']:
            raise SystemExit(1)
    else:
        matches = load_matches(args.data_dir,args.seasons)
        # Schema/coverage audit only, no held-out performance or outcome inspection.
        print(matches.groupby(['season','division']).size().to_string())
        print('Odds excluded; cutoff is two hours before kickoff; availability is an unverified +24h proxy.')

if __name__ == '__main__':
    main()
