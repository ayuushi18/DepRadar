import pandas as pd

labels = pd.read_parquet('data/processed/labels.parquet')
pool = labels[(labels['snapshot'] == '2023-05') & labels['abandoned']
              & ~labels['suspect_history']]
sample = pool.sample(n=50, random_state=7).sort_values('package')

out = pd.DataFrame({
    'package': sample['package'].values,
    'github': 'https://github.com/' + sample['repo'].values,
    'pypi': 'https://pypi.org/project/' + sample['package'].values + '/',
    'category': '',
    'note': '',
})
out.to_csv('data/processed/hand_check.csv', index=False)
print(f'Wrote {len(out)} rows to data/processed/hand_check.csv')