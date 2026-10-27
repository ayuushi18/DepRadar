import argparse
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

from gh_extract import PROJECT_ID

GIB = 1024 ** 3


def build_sql(first, last):
    return f"""
SELECT DATE(created_at) AS day, COUNT(*) AS events
FROM `githubarchive.month.20*`
WHERE _TABLE_SUFFIX BETWEEN '{first}' AND '{last}'
GROUP BY day
ORDER BY day
"""


def fetch(first, last, dry_run):
    client = bigquery.Client(project=PROJECT_ID)
    config = bigquery.QueryJobConfig(
        dry_run=dry_run,
        use_query_cache=False,
        maximum_bytes_billed=80 * GIB,
    )
    job = client.query(build_sql(first, last), job_config=config)
    if dry_run:
        print(f'Dry run: this would process {job.total_bytes_processed / GIB:.1f} GB')
        return None
    df = job.to_dataframe()
    print(f'Processed {job.total_bytes_processed / GIB:.1f} GB, {len(df)} days returned')
    return df


def find_gaps(df, threshold):
    df = df.copy()
    df['day'] = pd.to_datetime(df['day'].astype(str))
    full = pd.date_range(df['day'].min(), df['day'].max(), freq='D')
    events = df.set_index('day')['events'].astype('float').reindex(full)
    missing = int(events.isna().sum())
    typical = events.rolling(91, center=True, min_periods=30).median()
    ratio = (events / typical).fillna(0)
    bad = ratio < threshold

    print(f'Days covered: {len(full)}, days with no rows at all: {missing}, '
          f'flagged: {int(bad.sum())}')
    start = None
    for day, flag in bad.items():
        if flag and start is None:
            start = day
        if (not flag or day == full[-1]) and start is not None:
            end = day if flag else day - pd.Timedelta(days=1)
            window = ratio[start:end]
            print(f'{start.date()} to {end.date()}: {len(window)} days, '
                  f'lowest ratio {window.min():.2f}')
            start = None

    monthly = events.resample('MS').sum() / 1e6
    print('Events per month (millions):')
    for month, value in monthly.items():
        print(f'  {month.strftime("%Y-%m")}: {value:.0f}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--first', default='2407', help='first month as YYMM')
    parser.add_argument('--last', default='2609', help='last month as YYMM')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--threshold', type=float, default=0.6)
    args = parser.parse_args()

    if args.dry_run:
        fetch(args.first, args.last, True)
    else:
        out = Path(f'data/raw/daily_coverage_{args.first}_{args.last}.parquet')
        if out.exists():
            df = pd.read_parquet(out)
            print('Using saved', out)
        else:
            df = fetch(args.first, args.last, False)
            df.to_parquet(out, index=False)
        find_gaps(df, args.threshold)