import argparse
import json
from pathlib import Path

from google.cloud import bigquery

PROJECT_ID = 'depradar-512014'
REPO_MAP = Path('data/raw/repo_map.json')
OUT_DIR = Path('data/raw/gh')

EVENT_TYPES = [
    'PushEvent', 'PullRequestEvent', 'IssuesEvent', 'IssueCommentEvent',
    'ReleaseEvent', 'PullRequestReviewEvent', 'PullRequestReviewCommentEvent',
    'WatchEvent', 'ForkEvent',
]
NO_ACTOR_TYPES = ['WatchEvent', 'ForkEvent']

SQL = """
SELECT
  LOWER(repo.name) AS repo_name,
  type AS event_type,
  IF(type IN UNNEST(@no_actor_types), NULL, actor.login) AS actor_login,
  COUNT(*) AS events,
  MAX(created_at) AS last_event
FROM `githubarchive.{kind}.{period}`
WHERE LOWER(repo.name) IN UNNEST(@repos)
  AND type IN UNNEST(@event_types)
  AND NOT ENDS_WITH(actor.login, '[bot]')
GROUP BY 1, 2, 3
"""


def load_repos():
    repo_map = json.loads(REPO_MAP.read_text(encoding='utf-8'))
    repos = {value['repo'].lower() for value in repo_map.values() if value.get('repo')}
    return sorted(repos)


def make_config(repos, dry_run, max_gb):
    return bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter('repos', 'STRING', repos),
            bigquery.ArrayQueryParameter('event_types', 'STRING', EVENT_TYPES),
            bigquery.ArrayQueryParameter('no_actor_types', 'STRING', NO_ACTOR_TYPES),
        ],
        dry_run=dry_run,
        use_query_cache=False,
        maximum_bytes_billed=int(max_gb * 1024 ** 3),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--kind', choices=['day', 'month'], default='day')
    parser.add_argument('--period', default='20240615', help='YYYYMMDD for day, YYYYMM for month')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--max-gb', type=float, default=1.0)
    args = parser.parse_args()

    repos = load_repos()
    print(f'Repos in the list: {len(repos)}')

    client = bigquery.Client(project=PROJECT_ID)
    sql = SQL.format(kind=args.kind, period=args.period)
    job = client.query(sql, job_config=make_config(repos, args.dry_run, args.max_gb))

    if args.dry_run:
        print(f'Dry run: this would process {job.total_bytes_processed / 1024 ** 3:.2f} GB')
        return

    df = job.to_dataframe()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f'{args.kind}_{args.period}.parquet'
    df.to_parquet(out, index=False)
    print(f'Processed {job.total_bytes_processed / 1024 ** 3:.2f} GB, saved {len(df)} rows to {out}')


if __name__ == '__main__':
    main()