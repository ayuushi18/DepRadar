import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('GITHUB_TOKEN')
REPO_MAP = Path('data/raw/repo_map.json')
OUT = Path('data/raw/repo_ids.json')


def main():
    if not TOKEN:
        raise SystemExit('Put GITHUB_TOKEN=... in the .env file first')

    repo_map = json.loads(REPO_MAP.read_text(encoding='utf-8'))
    repos = sorted({value['repo'] for value in repo_map.values() if value.get('repo')})
    done = json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {}

    session = requests.Session()
    session.headers.update({
        'Authorization': f'Bearer {TOKEN}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    })

    for i, repo in enumerate(repos, start=1):
        if repo in done:
            continue
        try:
            response = session.get(f'https://api.github.com/repos/{repo}', timeout=20)
        except requests.RequestException as error:
            print(f'{repo}: {error}')
            continue

        if response.status_code == 200:
            data = response.json()
            done[repo] = {
                'id': data['id'],
                'full_name': data['full_name'].lower(),
                'archived': data['archived'],
                'fork': data['fork'],
            }
        elif response.status_code in (404, 451):
            done[repo] = {'status': response.status_code}
        elif response.status_code in (403, 429):
            print(f'Rate limited at {repo}. Stopping; run again later to resume.')
            break
        else:
            print(f'{repo}: HTTP {response.status_code}')
            continue

        if i % 100 == 0:
            OUT.write_text(json.dumps(done), encoding='utf-8')
            print(f'{i}/{len(repos)} done')
        time.sleep(0.1)

    OUT.write_text(json.dumps(done), encoding='utf-8')
    found = [v for v in done.values() if 'id' in v]
    moved = sum(1 for repo, v in done.items() if 'id' in v and v['full_name'] != repo.lower())
    print(f'Repos looked up: {len(done)} of {len(repos)}')
    print(f'Found: {len(found)}, not found: {len(done) - len(found)}')
    print(f'Name differs from PyPI link (renamed or moved): {moved}')
    print(f'Forks: {sum(v["fork"] for v in found)}, archived: {sum(v["archived"] for v in found)}')


if __name__ == '__main__':
    main()