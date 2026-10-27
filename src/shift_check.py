from pathlib import Path

import pandas as pd

frames = []
for path in sorted(Path('data/raw/gh').glob('month_*.parquet')):
    period = path.stem.split('_')[1]
    if not ('202403' <= period <= '202607'):
        continue
    df = pd.read_parquet(path)
    df['period'] = period
    frames.append(df)

data = pd.concat(frames)
by_type = data.pivot_table(index='period', columns='event_type', values='events',
                           aggfunc='sum', fill_value=0)
by_type['TOTAL'] = by_type.sum(axis=1)
by_type['repos_active'] = data.groupby('period')['repo_name'].nunique()

pd.set_option('display.width', 250)
pd.set_option('display.max_columns', 20)
print(by_type)