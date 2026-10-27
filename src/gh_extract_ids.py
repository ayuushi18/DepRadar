import argparse
import json
from datetime import date
from pathlib import Path

from google.cloud import bigquery

from gh_backfill import LEDGER, load_ledger, months, spent_this_month
from gh_extract import EVENT_TYPES, NO_ACTOR_TYPES, PROJECT_ID

REPO_IDS = Path('data/raw/repo_ids.json')
OUT_DIR = Path('data/raw/gh_id')
GIB = 1024 ** 3

SQL = """
SELECT
  repo.id AS repo_id,
  type AS event_type,
  IF(type IN UNNEST(@no_actor_types), NULL, actor.login) AS actor_login,
  COUNT(*) AS events,
  MAX(created_at) AS last_event
FROM `githubarchive.month.{period}`
WHERE repo.id IN UNNEST(@ids)
  AND type IN UNNEST(@event_types)
  AND NOT ENDS_WITH(actor.login, '[bot]')
GROUP BY 1, 2, 3
"""


def load_ids():
    data = json.loads(REPO_IDS.read_text(encoding='utf-8'))
    return sorted({v['id'] for v in data.values() if 'id' in v and not v['fork']})


def make_config(ids, dry_run, max_gb):
    return bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter('ids', 'INT64', ids),
            bigquery.ArrayQueryParameter('event_types', 'STRING', EVENT_TYPES),
            bigquery.ArrayQueryParameter('no_actor_types', 'STRING', NO_ACTOR_TYPES),
        ],
        dry_run=dry_run,
        use_query_cache=False,
        maximum_bytes_billed=int(max_gb * GIB),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', default='202111')
    parser.add_argument('--end', default='202504')
    parser.add_argument('--budget-gb', type=float, default=880.0)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    ids = load_ids()
    print(f'Repo ids in the list: {len(ids)}')
    client = bigquery.Client(project=PROJECT_ID)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ledger = load_ledger()

    if args.dry_run:
        total = 0.0
        for period in months(args.start, args.end):
            sql = SQL.format(period=period)
            job = client.query(sql, job_config=make_config(ids, True, 1000))
            gb = job.total_bytes_processed / GIB
            total += gb
            print(f'{period}: {gb:.2f} GB')
        print(f'Total for the range: {total:.1f} GB')
        print(f'Ledger already shows {spent_this_month(ledger):.0f} GB this month '
              f'(plus about 65 GB of coverage runs that are not in the ledger)')
        return

    for period in months(args.start, args.end):
        out = OUT_DIR / f'month_{period}.parquet'
        if out.exists():
            print(f'{period}: already saved, skipping')
            continue

        sql = SQL.format(period=period)
        dry = client.query(sql, job_config=make_config(ids, True, 1000))
        estimate = dry.total_bytes_processed / GIB

        spent = spent_this_month(ledger)
        if spent + estimate > args.budget_gb:
            print(f'{period}: stopping. {spent:.0f} GB already used this month and '
                  f'this query needs {estimate:.1f} GB (budget {args.budget_gb:.0f} GB).')
            break

        job = client.query(sql, job_config=make_config(ids, False, estimate * 1.2))
        df = job.to_dataframe()
        df.to_parquet(out, index=False)
        billed = job.total_bytes_billed / GIB
        ledger.append({
            'period': period,
            'gb': round(billed, 2),
            'rows': int(len(df)),
            'kind': 'by_id',
            'run_month': date.today().strftime('%Y-%m'),
        })
        LEDGER.write_text(json.dumps(ledger, indent=1), encoding='utf-8')
        print(f'{period}: {len(df)} rows, billed {billed:.2f} GB, '
              f'total this month {spent + billed:.0f} GB')


if __name__ == '__main__':
    main()