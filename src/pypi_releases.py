import json
import time
from pathlib import Path

import requests
from packaging.utils import parse_sdist_filename, parse_wheel_filename

REPO_MAP = Path('data/raw/repo_map.json')
OUT = Path('data/raw/pypi_releases.json')
HEADERS = {'Accept': 'application/vnd.pypi.simple.v1+json'}


def version_of(filename):
    try:
        if filename.endswith('.whl'):
            return parse_wheel_filename(filename)[1]
        return parse_sdist_filename(filename)[1]
    except Exception:
        return None


def summarize(files):
    releases = {}
    for item in files:
        upload = item.get('upload-time')
        if not upload:
            continue
        version = version_of(item.get('filename', ''))
        if version is None:
            continue
        stamp = upload[:19]
        entry = releases.setdefault(str(version), {
            'first_upload': stamp,
            'prerelease': version.is_prerelease,
            'yanked': True,
        })
        if stamp < entry['first_upload']:
            entry['first_upload'] = stamp
        if not item.get('yanked'):
            entry['yanked'] = False
    return releases


def main():
    repo_map = json.loads(REPO_MAP.read_text(encoding='utf-8'))
    packages = [name for name, value in repo_map.items() if value.get('repo')]
    done = json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {}
    session = requests.Session()
    session.headers.update(HEADERS)

    for i, name in enumerate(packages, start=1):
        if name in done:
            continue
        try:
            response = session.get(f'https://pypi.org/simple/{name}/', timeout=30)
            if response.status_code == 404:
                done[name] = {'error': 'not found'}
            else:
                response.raise_for_status()
                files = response.json().get('files', [])
                done[name] = {'releases': summarize(files)}
        except requests.RequestException as error:
            print(f'{name}: {error}')
            continue
        if i % 50 == 0:
            OUT.write_text(json.dumps(done), encoding='utf-8')
            print(f'{i}/{len(packages)} done')
        time.sleep(0.05)

    OUT.write_text(json.dumps(done), encoding='utf-8')

    with_releases = [n for n, v in done.items() if v.get('releases')]
    empty = [n for n, v in done.items() if 'releases' in v and not v['releases']]
    missing = [n for n, v in done.items() if 'error' in v]
    print(f'Packages processed: {len(done)}')
    print(f'With at least one parsed release: {len(with_releases)}')
    print(f'No parsed release: {len(empty)} (first few: {empty[:5]})')
    print(f'Not found on PyPI: {len(missing)}')

    sample = done.get('requests', {}).get('releases', {})
    latest = sorted(sample.items(), key=lambda kv: kv[1]['first_upload'])[-3:]
    print(f'requests: {len(sample)} releases, latest three:')
    for version, info in latest:
        print(f'  {version}: {info["first_upload"]}')


if __name__ == '__main__':
    main()