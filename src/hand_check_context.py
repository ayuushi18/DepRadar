import json
import os
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('GITHUB_TOKEN')

review = pd.read_csv('data/processed/hand_check.csv')
review['category'] = review['category'].fillna('')
review['note'] = review['note'].fillna('')
releases = json.loads(Path('data/raw/pypi_releases.json').read_text(encoding='utf-8'))

session = requests.Session()
session.headers.update({
    'Authorization': f'Bearer {TOKEN}',
    'Accept': 'application/vnd.github+json',
})

last_release, pushed, issues, archived = [], [], [], []
for _, row in review.iterrows():
    info = releases.get(row['package'], {}).get('releases') or {}
    stamps = [item['first_upload'][:10] for item in info.values() if not item['yanked']]
    last_release.append(max(stamps) if stamps else '')

    repo = row['github'].replace('https://github.com/', '')
    response = session.get(f'https://api.github.com/repos/{repo}', timeout=20)
    if response.status_code == 200:
        data = response.json()
        pushed.append(data['pushed_at'][:10])
        issues.append(data['open_issues_count'])
        archived.append(data['archived'])
    else:
        pushed.append('')
        issues.append('')
        archived.append('')

review['last_release'] = last_release
review['pushed_at'] = pushed
review['open_issues'] = issues
review['archived'] = archived

columns = ['package', 'github', 'pypi', 'last_release', 'pushed_at',
           'open_issues', 'archived', 'category', 'note']
review[columns].to_csv('data/processed/hand_check.csv', index=False)
print('Added context columns to data/processed/hand_check.csv')