import hashlib
import json
import random
from pathlib import Path

import pandas as pd
import requests

from gh_recent import get, make_session

PACKAGE_IDS = Path('data/processed/package_ids.csv')
OUT = Path('data/raw/gh_overlap.json')
SAMPLE_SIZE = 300
SINCE = '2024-10-01T00:00:00Z'
UNTIL = '2025-05-01T00:00:00Z'
MAX_PAGES = 3


def collect(session, repo):
    commits = []
    truncated = False
    for page in range(1, MAX_PAGES + 1):
        response = get(session, f'https://api.github.com/repos/{repo}/commits',
                       params={'since': SINCE, 'until': UNTIL,
                               'per_page': 100, 'page': page})
        if response.status_code == 409:
            break
        if response.status_code != 200:
            return {'status': response.status_code}
        items = response.json()
        for item in items:
            commit = item['commit']
            source = commit.get('committer') or commit.get('author') or {}
            stamp = source.get('date')
            if not stamp:
                continue
            author = item.get('author') or {}
            email = ((commit.get('author') or {}).get('email') or '').lower()
            who = author.get('login') or hashlib.sha1(email.encode()).hexdigest()[:12]
            is_bot = author.get('type') == 'Bot' or who.endswith('[bot]')
            commits.append([stamp, who, is_bot])
        if len(items) < 100:
            break
        if page == MAX_PAGES:
            truncated = True
    return {'status': 200, 'commits': commits, 'truncated': truncated}


def main():
    table = pd.read_csv(PACKAGE_IDS)
    repos = sorted(table['current_name'].dropna().unique())
    sample = sorted(random.Random(7).sample(repos, SAMPLE_SIZE))
    done = json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {}
    session = make_session()
    fetched = 0
    try:
        for repo in sample:
            if repo in done:
                continue
            try:
                done[repo] = collect(session, repo)
            except requests.RequestException as error:
                print(f'{repo}: {error} (will retry next run)', flush=True)
                continue
            fetched += 1
            if fetched % 25 == 0:
                OUT.write_text(json.dumps(done), encoding='utf-8')
                print(f'{len(done)} of {len(sample)} repos stored', flush=True)
    finally:
        OUT.write_text(json.dumps(done), encoding='utf-8')

    ok = [v for v in done.values() if v.get('status') == 200]
    print(f'Repos stored: {len(done)} of {len(sample)}, with data: {len(ok)}')
    print(f'Truncated (more than 300 commits in the window): '
          f'{sum(1 for v in ok if v["truncated"])}')


if __name__ == '__main__':
    main()