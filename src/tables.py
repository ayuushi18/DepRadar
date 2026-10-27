import json
from pathlib import Path

import pandas as pd

GH_DIR = Path('data/raw/gh_id')
PACKAGE_IDS = Path('data/processed/package_ids.csv')
RELEASES = Path('data/raw/pypi_releases.json')

FIRST_MONTH = '2021-11'
LAST_MONTH = '2025-04'
MONTHS = [str(p) for p in pd.period_range(FIRST_MONTH, LAST_MONTH, freq='M')]


def months_between(start, end):
    return [str(p) for p in pd.period_range(start, end, freq='M')]


def package_table():
    table = pd.read_csv(PACKAGE_IDS)
    table['repo_id'] = table['repo_id'].astype('int64')
    return table.set_index('package')


def build_activity():
    frames = []
    for path in sorted(GH_DIR.glob('month_*.parquet')):
        period = path.stem.split('_')[1]
        month = f'{period[:4]}-{period[4:]}'
        if month < FIRST_MONTH or month > LAST_MONTH:
            continue
        df = pd.read_parquet(path, columns=['repo_id', 'event_type', 'events'])
        df['month'] = month
        frames.append(df)
    data = pd.concat(frames, ignore_index=True)
    data['events'] = data['events'].astype('int64')
    data['repo_id'] = data['repo_id'].astype('int64')

    pushes = (data[data['event_type'] == 'PushEvent']
              .pivot_table(index='repo_id', columns='month', values='events',
                           aggfunc='sum', fill_value=0)
              .reindex(columns=MONTHS, fill_value=0))
    everything = (data.pivot_table(index='repo_id', columns='month', values='events',
                                   aggfunc='sum', fill_value=0)
                  .reindex(columns=MONTHS, fill_value=0))
    return pushes, everything


def build_releases(months=MONTHS):
    raw = json.loads(RELEASES.read_text(encoding='utf-8'))
    rows = []
    first = {}
    for package, value in raw.items():
        releases = value.get('releases') or {}
        stamps = [info['first_upload'][:7] for info in releases.values()]
        if stamps:
            first[package] = min(stamps)
        for info in releases.values():
            if not info['yanked']:
                rows.append((package, info['first_upload'][:7], 1))
    df = pd.DataFrame(rows, columns=['package', 'month', 'n'])
    table = (df.pivot_table(index='package', columns='month', values='n',
                            aggfunc='sum', fill_value=0)
             .reindex(columns=months, fill_value=0))
    return table, pd.Series(first)