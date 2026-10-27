import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()
TOKEN = os.getenv('GITHUB_TOKEN')
PACKAGE_IDS = Path('data/processed/package_ids.csv')
OUT = Path('data/raw/gh_recent.json')
DAYS = 400
MAX_PAGES = 3


def make_session():
    session = requests.Session()
    retry = Retry(total=5, connect=5, read=5, backoff_factor=2,
                  status_forcelist=[500, 502, 503, 504],
                  allowed_methods=['GET'])
    session.mount('https://', HTTPAdapter(max_retries=retry))
    session.headers.update({
        'Authorization': f'Bearer {TOKEN}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    })
    return session


def wait_until(reset_epoch):
    pause = max(5, int(reset_epoch) - int(time.time()) + 5)
    print(f'Waiting {pause // 60} min {pause % 60} s for the GitHub rate limit to reset...',
          flush=True)
    time.sleep(pause)


def get(session, url, params=None):
    response = None
    for _ in range(4):
        response = session.get(url, params=params, timeout=(10, 40))
        if response.status_code in (403, 429):
            retry_after = response.headers.get('retry-after')
            if retry_after:
                print(f'GitHub asked us to wait {retry_after} s...', flush=True)
                time.sleep(int(retry_after) + 2)
                continue
            if response.headers.get('x-ratelimit-remaining') == '0':
                wait_until(response.headers.get('x-ratelimit-reset', time.time() + 60))
                continue
        remaining = int(response.headers.get('x-ratelimit-remaining', 100))
        if remaining < 20:
            wait_until(response.headers.get('x-ratelimit-reset', time.time() + 60))
        return response
    return response


def collect(session, repo, since):
    info_response = get(session, f'https://api.github.com/repos/{repo}')
    if info_response.status_code != 200:
        return {'status': info_response.status_code}
    info = info_response.json()
    result = {
        'status': 200,
        'archived': info['archived'],
        'pushed_at': info['pushed_at'],
        'open_issues': info['open_issues_count'],
        'stars': info['stargazers_count'],
        'forks': info['forks_count'],
        'default_branch': info['default_branch'],
        'commits': [],
        'truncated': False,
    }
    for page in range(1, MAX_PAGES + 1):
        response = get(session, f'https://api.github.com/repos/{repo}/commits',
                       params={'since': since, 'per_page': 100, 'page': page})
        if response.status_code == 409:
            break
        if response.status_code != 200:
            result['commit_status'] = response.status_code
            break
        items = response.json()
        for item in items:
            commit = item['commit']
            stamp_source = commit.get('committer') or commit.get('author') or {}
            stamp = stamp_source.get('date')
            if not stamp:
                continue
            author = item.get('author') or {}
            email = ((commit.get('author') or {}).get('email') or '').lower()
            who = author.get('login') or hashlib.sha1(email.encode()).hexdigest()[:12]
            is_bot = author.get('type') == 'Bot' or who.endswith('[bot]')
            result['commits'].append([stamp, who, is_bot])
        if len(items) < 100:
            break
        if page == MAX_PAGES:
            result['truncated'] = True
    return result


def main():
    if not TOKEN:
        raise SystemExit('Put GITHUB_TOKEN=... in the .env file first')

    table = pd.read_csv(PACKAGE_IDS)
    repos = sorted(table['current_name'].dropna().unique())
    done = json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {}
    if '__meta__' not in done:
        since = (datetime.now(timezone.utc) - timedelta(days=DAYS)).strftime('%Y-%m-%dT%H:%M:%SZ')
        done['__meta__'] = {'since': since, 'collected': datetime.now(timezone.utc).isoformat()}
    since = done['__meta__']['since']

    session = make_session()
    fetched = 0
    try:
        for repo in repos:
            if repo in done:
                continue
            try:
                done[repo] = collect(session, repo, since)
            except requests.RequestException as error:
                print(f'{repo}: {error} (will retry next run)', flush=True)
                continue
            fetched += 1
            if fetched % 25 == 0:
                OUT.write_text(json.dumps(done), encoding='utf-8')
                print(f'{len(done) - 1} of {len(repos)} repos stored', flush=True)
    finally:
        OUT.write_text(json.dumps(done), encoding='utf-8')

    ok = {r: v for r, v in done.items() if r != '__meta__' and v.get('status') == 200}
    human = {r: [c for c in v['commits'] if not c[2]] for r, v in ok.items()}
    print(f'Repos stored: {len(done) - 1} of {len(repos)}')
    print(f'Repos collected with data: {len(ok)}')
    print(f'With at least one human commit since {since[:10]}: '
          f'{sum(1 for c in human.values() if c)}')
    print(f'Truncated (more than 300 commits): {sum(1 for v in ok.values() if v["truncated"])}')
    print(f'Archived: {sum(1 for v in ok.values() if v["archived"])}')


if __name__ == '__main__':
    main()