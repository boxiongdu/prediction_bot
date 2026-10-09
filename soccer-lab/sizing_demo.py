"""Synthetic sizing demonstration. No live market data, credentials, or orders."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
from sizing import PaperLedger, POLICY_PATH


def main():
    now=datetime.now(timezone.utc)
    request={
        'fixture_id':'SYNTHETIC-FIXTURE','ticker':'SYNTHETIC-HOME',
        'probabilities':{'H':'0.55','D':'0.25','A':'0.20'},
        'outcome':'H','side':'yes','limit_price':'0.45','available_contracts':100,
        'fee_totals':{str(n):'0.00' for n in range(1,101)},
        'fee_source':'SYNTHETIC zero-fee assumption, NOT a Kalshi fee quote',
        'quote_at':now.isoformat(),'kickoff':(now+timedelta(hours=2)).isoformat(),
        'forecast_cutoff':now.isoformat()}
    policy=json.loads(POLICY_PATH.read_text())
    with tempfile.TemporaryDirectory() as folder:
        for method in ('fixed','quarter_kelly'):
            book=PaperLedger(Path(folder)/(method+'.sqlite'),dict(policy,method=method))
            print(json.dumps(book.reserve(request,now),indent=2))


if __name__=='__main__':
    main()
