import json
import re
import time
from pathlib import Path

import requests

PACKAGES = Path('data/raw/top_packages.json')
OUT = Path('data/raw/repo_map.json')
GITHUB = re.compile(r'github\.com[/:]([\w.-]+)/([\w.-]+)', re.IGNORECASE)
NOT_REPOS = {'sponsors', 'orgs', 'topics', 'features', 'marketplace'}


def find_repo(info):
    urls = list((info.get('project_urls') or {}).values())
    urls.append(info.get('home_page') or '')
    for url in urls:
        match = GITHUB.search(url or '')
        if not match:
            continue
        owner, name = match.group(1), match.group(2)
        if owner.lower() in NOT_REPOS:
            continue
        if name.endswith('.git'):
            name = name[:-4]
        return f'{owner}/{name}'
    return None


def main():
    rows = json.loads(PACKAGES.read_text(encoding='utf-8'))
    packages = [row['project'] for row in rows]
    done = json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {}
    session = requests.Session()

    for i, name in enumerate(packages, start=1):
        if name in done:
            continue
        try:
            response = session.get(f'https://pypi.org/pypi/{name}/json', timeout=20)
            if response.status_code == 404:
                done[name] = {'repo': None, 'note': 'not found'}
            else:
                response.raise_for_status()
                info = response.json()['info']
                done[name] = {'repo': find_repo(info), 'latest_version': info.get('version')}
        except requests.RequestException as error:
            print(f'{name}: {error}')
            continue
        if i % 50 == 0:
            OUT.write_text(json.dumps(done, indent=1), encoding='utf-8')
            print(f'{i}/{len(packages)} done')
        time.sleep(0.05)

    OUT.write_text(json.dumps(done, indent=1), encoding='utf-8')
    mapped = sum(1 for value in done.values() if value.get('repo'))
    print(f'Mapped {mapped} of {len(done)} packages to a GitHub repo')


if __name__ == '__main__':
    main()