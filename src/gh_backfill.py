import argparse
import json
from datetime import date
from pathlib import Path

from google.cloud import bigquery

from gh_extract import OUT_DIR, PROJECT_ID, SQL, load_repos, make_config

LEDGER = OUT_DIR / 'ledger.json'
GIB = 1024 ** 3


def months(start, end):
    year, month = int(start[:4]), int(start[4:])
    last = (int(end[:4]), int(end[4:]))
    while (year, month) <= last:
        yield f'{year}{month:02d}'
        month += 1
        if month == 13:
            year += 1
            month = 1


def load_ledger():
    if LEDGER.exists():
        return json.loads(LEDGER.read_text(encoding='utf-8'))
    return []


def spent_this_month(ledger):
    key = date.today().strftime('%Y-%m')
    return sum(item['gb'] for item in ledger if item['run_month'] == key)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', default='202001')
    parser.add_argument('--end', default='202406')
    parser.add_argument('--budget-gb', type=float, default=600.0)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    repos = load_repos()
    client = bigquery.Client(project=PROJECT_ID)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ledger = load_ledger()

    if args.dry_run:
        total = 0.0
        for period in months(args.start, args.end):
            sql = SQL.format(kind='month', period=period)
            job = client.query(sql, job_config=make_config(repos, True, 1000))
            gb = job.total_bytes_processed / GIB
            total += gb
            print(f'{period}: {gb:.2f} GB')
        print(f'Total for the range: {total:.1f} GB')
        return

    for period in months(args.start, args.end):
        out = OUT_DIR / f'month_{period}.parquet'
        if out.exists():
            print(f'{period}: already saved, skipping')
            continue

        sql = SQL.format(kind='month', period=period)
        dry = client.query(sql, job_config=make_config(repos, True, 1000))
        estimate = dry.total_bytes_processed / GIB

        spent = spent_this_month(ledger)
        if spent + estimate > args.budget_gb:
            print(f'{period}: stopping. {spent:.0f} GB already used this month and '
                  f'this query needs {estimate:.1f} GB (budget {args.budget_gb:.0f} GB).')
            break

        job = client.query(sql, job_config=make_config(repos, False, estimate * 1.2))
        df = job.to_dataframe()
        df.to_parquet(out, index=False)
        billed = job.total_bytes_billed / GIB
        ledger.append({
            'period': period,
            'gb': round(billed, 2),
            'rows': int(len(df)),
            'run_month': date.today().strftime('%Y-%m'),
        })
        LEDGER.write_text(json.dumps(ledger, indent=1), encoding='utf-8')
        print(f'{period}: {len(df)} rows, billed {billed:.2f} GB, '
              f'total this month {spent + billed:.0f} GB')


if __name__ == '__main__':
    main()