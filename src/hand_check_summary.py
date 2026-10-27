import pandas as pd

review = pd.read_csv('data/processed/hand_check.csv')
review['category'] = review['category'].fillna('').astype(str).str.strip().str.lower()
done = review[review['category'] != '']
n = len(done)
print(f'Reviewed {n} of {len(review)}')


def wilson(k, total, z=1.96):
    p = k / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    margin = z * ((p * (1 - p) / total + z * z / (4 * total * total)) ** 0.5) / denom
    return max(0, centre - margin), min(1, centre + margin)


for category, count in done['category'].value_counts().items():
    low, high = wilson(count, n)
    print(f'  {category:<8} {count:>3}  ({100 * count / n:.0f}%, range {100 * low:.0f}-{100 * high:.0f}%)')

labels = pd.read_parquet('data/processed/labels.parquet')
snap = labels[labels['snapshot'] == '2023-05'][['package', 'released_later', 'archived']]
merged = done.merge(snap, on='package')
print()
print('Your category vs. "released again on PyPI in months 13-24":')
print(pd.crosstab(merged['category'], merged['released_later']))