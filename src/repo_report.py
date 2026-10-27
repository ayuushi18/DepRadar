import json
from pathlib import Path

import pandas as pd

repo_map = json.loads(Path('data/raw/repo_map.json').read_text(encoding='utf-8'))
repo_ids = json.loads(Path('data/raw/repo_ids.json').read_text(encoding='utf-8'))

rows = []
for package, value in repo_map.items():
    repo = value.get('repo')
    if not repo:
        continue
    info = repo_ids.get(repo, {})
    rows.append({
        'package': package,
        'repo': repo,
        'repo_id': info.get('id'),
        'current_name': info.get('full_name'),
        'fork': info.get('fork'),
        'archived': info.get('archived'),
    })

table = pd.DataFrame(rows)
missing = table[table['repo_id'].isna()]
print('Not found:')
print(missing[['package', 'repo']].to_string(index=False))
print()
print('Forks:', table[table['fork'] == True]['package'].tolist())
print()
print('Archived (first 15):', table[table['archived'] == True]['package'].head(15).tolist())

keep = table[table['repo_id'].notna() & (table['fork'] != True)].copy()
keep['repo_id'] = keep['repo_id'].astype('int64')
Path('data/processed').mkdir(parents=True, exist_ok=True)
keep.to_csv('data/processed/package_ids.csv', index=False)
print()
print(f'Kept {len(keep)} packages, {keep["repo_id"].nunique()} unique repo ids')