from pathlib import Path

import pandas as pd

from tables import build_activity, build_releases, months_between, package_table

SNAPSHOTS = [str(p) for p in pd.period_range('2022-11', '2024-05', freq='M')]
ALL_MONTHS = [str(p) for p in pd.period_range('2021-11', '2026-10', freq='M')]

pkgs = package_table()
pushes, everything = build_activity()
release_table, first_release = build_releases(ALL_MONTHS)

packages = pkgs.index
ids = pkgs['repo_id'].values

push_by_pkg = pushes.reindex(ids).fillna(0)
push_by_pkg.index = packages
all_by_pkg = everything.reindex(ids).fillna(0)
all_by_pkg.index = packages
release_by_pkg = release_table.reindex(packages).fillna(0)
shared = pkgs['repo_id'].map(pkgs['repo_id'].value_counts())
first = first_release.reindex(packages).fillna('9999-99')

frames = []
for snapshot in SNAPSHOTS:
    start = pd.Period(snapshot, 'M')
    before = months_between(start - 12, start - 1)
    after = months_between(start, start + 11)
    later = months_between(start + 12, start + 23)

    prior_push = push_by_pkg[before].sum(axis=1)
    prior_all = all_by_pkg[before].sum(axis=1)
    prior_rel = release_by_pkg[before].sum(axis=1)
    next_push = push_by_pkg[after].sum(axis=1)
    next_rel = release_by_pkg[after].sum(axis=1)
    later_rel = release_by_pkg[later].sum(axis=1)

    exists = first < snapshot
    alive = exists & ((prior_push > 0) | (prior_rel > 0))
    abandoned = alive & (next_push == 0) & (next_rel == 0)
    suspect = (prior_rel >= 3) & (prior_all == 0)

    frames.append(pd.DataFrame({
        'package': packages,
        'repo': pkgs['current_name'].values,
        'repo_id': ids,
        'repo_packages': shared.values,
        'snapshot': snapshot,
        'alive': alive.values,
        'abandoned': abandoned.values,
        'suspect_history': suspect.values,
        'prior_pushes': prior_push.astype(int).values,
        'prior_releases': prior_rel.astype(int).values,
        'next_pushes': next_push.astype(int).values,
        'next_releases': next_rel.astype(int).values,
        'released_later': (later_rel > 0).values,
        'archived': pkgs['archived'].values,
    }))

labels = pd.concat(frames, ignore_index=True)
Path('data/processed').mkdir(parents=True, exist_ok=True)
labels.to_parquet('data/processed/labels.parquet', index=False)

rows = []
for snapshot, group in labels[labels['alive']].groupby('snapshot'):
    usable = group[~group['suspect_history']]
    rows.append({
        'snapshot': snapshot,
        'alive': len(group),
        'suspect': int(group['suspect_history'].sum()),
        'abandoned': int(usable['abandoned'].sum()),
        'rate_%': round(100 * usable['abandoned'].mean(), 1),
    })
print(pd.DataFrame(rows).to_string(index=False))

print()
print('Does the label agree with independent signals?')
for snapshot in ['2022-11', '2023-05', '2024-05']:
    group = labels[(labels['snapshot'] == snapshot) & labels['alive']
                   & ~labels['suspect_history']]
    dead = group[group['abandoned']]
    rest = group[~group['abandoned']]
    print(f'{snapshot}: abandoned={len(dead)}')
    print(f'   archived on GitHub today: {100 * dead["archived"].mean():.0f}% of abandoned '
          f'vs {100 * rest["archived"].mean():.0f}% of the rest')
    print(f'   released in months 13-24: {100 * dead["released_later"].mean():.0f}% of abandoned '
          f'vs {100 * rest["released_later"].mean():.0f}% of the rest')

print()
print('Examples labeled abandoned at 2023-05:')
sample = labels[(labels['snapshot'] == '2023-05') & labels['abandoned']
                & ~labels['suspect_history']]
print(sample[['package', 'repo', 'archived', 'released_later']].head(15).to_string(index=False))