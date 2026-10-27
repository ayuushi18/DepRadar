import json
from pathlib import Path

import pandas as pd

MONTHS = ['2024-11', '2024-12', '2025-01', '2025-02', '2025-03', '2025-04']

ids = pd.read_csv('data/processed/package_ids.csv')
name_to_id = dict(zip(ids['current_name'], ids['repo_id']))

overlap = json.loads(Path('data/raw/gh_overlap.json').read_text(encoding='utf-8'))
ok = {repo: value for repo, value in overlap.items() if value.get('status') == 200}

series = []
for month in MONTHS:
    df = pd.read_parquet(f'data/raw/gh_id/month_{month.replace("-", "")}.parquet',
                         columns=['repo_id', 'event_type', 'events'])
    pushes = df[df['event_type'] == 'PushEvent'].groupby('repo_id')['events'].sum()
    series.append(pushes.rename(month))
archive = pd.concat(series, axis=1).fillna(0)

rows = []
for repo, value in ok.items():
    repo_id = name_to_id.get(repo)
    if repo_id is None:
        continue
    everything = value['commits']
    human = [c for c in everything if not c[2]]
    api_months = set(pd.to_datetime([c[0] for c in human], utc=True).strftime('%Y-%m')) \
        if human else set()
    oldest = None
    if value['truncated'] and everything:
        oldest = pd.to_datetime([c[0] for c in everything], utc=True).min().strftime('%Y-%m')
    for month in MONTHS:
        if oldest and month < oldest:
            continue
        in_archive = repo_id in archive.index and archive.loc[repo_id, month] > 0
        rows.append({'repo': repo, 'month': month,
                     'archive': bool(in_archive), 'api': month in api_months})

cells = pd.DataFrame(rows)
print('repo-months compared:', len(cells), 'across', cells['repo'].nunique(), 'repos')
print()
print('Active months, archive (rows) versus API (columns):')
print(pd.crosstab(cells['archive'], cells['api']))

po = (cells['archive'] == cells['api']).mean()
pa, pb = cells['archive'].mean(), cells['api'].mean()
pe = pa * pb + (1 - pa) * (1 - pb)
print()
print(f'agreement: {100 * po:.1f}%   kappa: {(po - pe) / (1 - pe):.2f}')
print('active in the archive only:', int((cells['archive'] & ~cells['api']).sum()),
      '| active in the API only:', int((~cells['archive'] & cells['api']).sum()))

per_repo = cells.groupby('repo').agg(months=('month', 'size'),
                                     archive=('archive', 'sum'),
                                     api=('api', 'sum'))
full = per_repo[per_repo['months'] == len(MONTHS)].copy()
full['gap'] = (full['archive'] - full['api']).abs()
print()
print(f'Active months out of 6, per repo ({len(full)} repos with all 6 months known):')
print('  exact match:', f'{100 * (full["gap"] == 0).mean():.0f}%',
      '| within one month:', f'{100 * (full["gap"] <= 1).mean():.0f}%',
      '| rank correlation:', f'{full["archive"].corr(full["api"], method="spearman"):.2f}')
print()
print('Largest disagreements:')
print(full.sort_values('gap', ascending=False).head(10).to_string())