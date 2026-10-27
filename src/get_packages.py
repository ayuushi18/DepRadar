import json
from pathlib import Path

import requests

URLS = [
    'https://hugovk.github.io/top-pypi-packages/top-pypi-packages-30-days.min.json',
    'https://hugovk.github.io/top-pypi-packages/top-pypi-packages.min.json',
]
TOP_N = 3000
OUT = Path('data/raw/top_packages.json')


def download():
    for url in URLS:
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            rows = response.json()['rows']
            print(f'Got {len(rows)} packages from {url}')
            return rows
        except (requests.RequestException, ValueError, KeyError) as error:
            print(f'Failed {url}: {error}')
    raise SystemExit('Could not download the package list')


if __name__ == '__main__':
    rows = download()[:TOP_N]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows), encoding='utf-8')
    print(f'Saved {len(rows)} packages to {OUT}')
    print('First five:', [row['project'] for row in rows[:5]])