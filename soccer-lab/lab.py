"""CLI for the bounded three-role research workflow."""
import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, default=str, allow_nan=False)+'\n')

def provenance():
    import importlib.metadata
    return {'python':sys.version, 'source_sha256':{
        p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob('*.py')},
        'packages':{p:importlib.metadata.version(p) for p in ['numpy','pandas','scipy','scikit-learn']}}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    run = sub.add_parser('run', help='Audit and compare models on development seasons only')
    run.add_argument('--data', default='data/raw')
    run.add_argument('--out', required=True, help='New run directory; existing runs never overwritten')
    run.add_argument('--astra', action='store_true', help='Make up to three paid API calls for role memos')
    test = sub.add_parser('test', help='Explicit one-time test evaluation using an existing frozen run')
    test.add_argument('--data', default='data/raw')
    test.add_argument('--run', required=True)
    forecast = sub.add_parser('forecast', help='Forecast timestamped fixtures with frozen selection')
    forecast.add_argument('--data', default='data/raw')
    forecast.add_argument('--run', required=True)
    forecast.add_argument('--fixtures', required=True)
    forecast.add_argument('--out', required=True)
    forecast.add_argument('--retrospective', action='store_true', help='Explicit historical as-of simulation, not an on-time forecast')
    args = parser.parse_args()
    from data import load_matches
    from modeling import run_experiment, predict_fixtures
    if args.command == 'run':
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=False)
        write_json(out/'provenance.json', provenance())
        # Source files for the test season are not even loaded on this path.
        matches = load_matches(args.data, seasons=['2223','2324','2425'])
        audit = {'rows':len(matches), 'counts':{
            f'{s}/{d}':int(n) for (s,d),n in matches.groupby(['season','division']).size().items()},
            'cutoff':'kickoff minus two hours; historical availability conservatively approximated',
            'limitations':['Retrospective CSVs are not point-in-time publication archives.',
                'Paper replication pending accessible full method.',
                'No odds benchmark or portfolio results in this phase.']}
        audit['source_files']=matches.attrs.get('provenance',[])
        write_json(out/'data_audit.json', audit)
        summary = run_experiment(matches, out)
        write_json(out/'experiment_summary.json', summary)
        check = subprocess.run([sys.executable,'-m','unittest','discover','-s',str(ROOT/'tests'),'-v'],
            cwd=ROOT, capture_output=True, text=True)
        (out/'validation_tests.txt').write_text(check.stdout+'\n'+check.stderr)
        if check.returncode:
            raise RuntimeError('Independent tests failed; run is blocked. Inspect validation_tests.txt.')
        record={'time':datetime.now(timezone.utc).isoformat(),
            'executed':['data validation','predeclared model comparison','independent offline checks'],
            'not_executed':['test-season evaluation','paper replication','trading','deployment'],
            'model_changes':'Selection only; no agent-authored code changes are executed.'}
        write_json(out/'change_log.json',record)
        if args.astra:
            from agents import run_reviews
            compact_summary=json.loads(json.dumps(summary))
            for item in compact_summary.get('validation',{}).values():
                item.pop('calibration',None)
            run_reviews({'data_audit':audit,'experiment':compact_summary,'changes':record,
                'test_status':'independent offline checks passed; held-out season not evaluated'},out/'reviews')
        else:
            report='# Supervisor report — deterministic/offline\n\n'
            report+='Pipeline completed; Astra role reviews were not called.\n\n'
            report+='| Model | Log loss | Brier | Accuracy | Matches |\n|---|---:|---:|---:|---:|\n'
            for name,m in summary.get('validation',{}).items():
                report+=f"| {name} | {m['log_loss']:.4f} | {m['brier']:.4f} | {m['accuracy']:.1%} | {m['n']} |\n"
            report+='\nValidation-selected candidate: '+summary['selection']['config']['id']+'.\n\n'
            report+=('Lower log loss and Brier are better. Selection is conditional on this validation season; '
                'the test season has not been evaluated.\n\n'
                'See experiment_summary.json for measured validation performance, data_audit.json for '
                'coverage, validation_tests.txt for checks, and change_log.json for executed changes.\n\n'
                '2025–26 remains unexamined. Model selection is provisional, not evidence of trading profitability.\n')
            (out/'SUPERVISOR.md').write_text(report)
        print(out / ('reviews/SUPERVISOR.md' if args.astra else 'SUPERVISOR.md'))
    elif args.command == 'test':
        out=Path(args.run)
        before=json.loads((out/'provenance.json').read_text())
        if before != provenance():
            raise RuntimeError('Source/runtime differs from frozen run. Do not silently change the test protocol.')
        if (out/'TEST_OPENED.json').exists():
            raise RuntimeError('Test already opened for this run. Preserve it; subsequent changes need a new future test.')
        if not (out/'selection.json').exists():
            raise RuntimeError('No frozen selection found.')
        write_json(out/'TEST_OPENED.json',{'time':datetime.now(timezone.utc).isoformat(),
            'note':'Test opened; failures do not restore untouched status.'})
        matches=load_matches(args.data,seasons=['2223','2324','2425','2526'])
        summary=run_experiment(matches,out,evaluate_test=True)
        write_json(out/'test_summary.json',summary)
        print(out/'test_summary.json')
    else:
        import pandas as pd
        fixtures=pd.read_csv(args.fixtures)
        required={'kickoff_utc','home_team','away_team','division','season'}
        if not required.issubset(fixtures):
            raise ValueError('Fixture CSV requires '+', '.join(sorted(required)))
        fixtures['kickoff_utc']=pd.to_datetime(fixtures['kickoff_utc'],utc=True)
        if 'forecast_utc' not in fixtures:
            fixtures['forecast_utc']=fixtures['kickoff_utc']-pd.Timedelta(hours=2)
        else:
            fixtures['forecast_utc']=pd.to_datetime(fixtures['forecast_utc'],utc=True)
        issued_at=pd.Timestamp.now(tz='UTC')
        if (fixtures['forecast_utc']>issued_at).any():
            raise ValueError('Forecast cutoff has not arrived. Run at the requested two-hour cutoff.')
        if not args.retrospective and ((issued_at-fixtures['forecast_utc'])>pd.Timedelta(minutes=5)).any():
            raise ValueError('Missed two-hour forecast window (5-minute tolerance). Use --retrospective only for labeled simulation.')
        matches=load_matches(args.data,seasons=['2223','2324','2425','2526','2627'])
        selection=json.loads((Path(args.run)/'selection.json').read_text())
        result=predict_fixtures(matches,fixtures,selection)
        result['issued_at_utc']=issued_at
        result['mode']='retrospective_simulation' if args.retrospective else 'scheduled_forecast'
        target=Path(args.out)
        with target.open('x') as f:
            result.to_csv(f,index=False)
        print(target)

if __name__=='__main__':
    main()
