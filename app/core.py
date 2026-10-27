import re
from pathlib import Path

import numpy as np
import pandas as pd
from packaging.requirements import InvalidRequirement, Requirement

DATA_DIR = Path(__file__).resolve().parent / 'data'

STATUS_ORDER = ['Archived by owner', 'Already silent', 'High', 'Elevated',
                'Lower', 'Not covered']
TIER_TO_STATUS = {
    '1 High': 'High',
    '2 Elevated': 'Elevated',
    '3 Lower': 'Lower',
    'Already silent': 'Already silent',
}
STATUS_TO_TIER = {'High': '1 High', 'Elevated': '2 Elevated', 'Lower': '3 Lower'}
REQUIRED_COLUMNS = ['package', 'repo_name', 'tier', 'score', 'signals', 'archived',
                    'months_since_last_release', 'active_months_12', 'alive']
RESULT_COLUMNS = ['package', 'key', 'pinned', 'status', 'tier', 'score', 'signals',
                  'repo', 'archived', 'months_since_last_release', 'active_months_12']

MESSAGES = {
    'Archived by owner': ('The owner has archived the repository, which usually means '
                          'the project is finished. Check whether a replacement exists.'),
    'Already silent': ('No human commits and no releases in the last 12 months, so the '
                       'model does not score it. Check whether it is finished or abandoned.'),
    'Not covered': ('Not among the 2,667 packages analysed, so there is no score. '
                    'This is not a sign that it is safe.'),
}


def normalize(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def _clean(line):
    line = line.strip()
    if not line or line.startswith('#'):
        return ''
    line = re.split(r'\s+#', line, maxsplit=1)[0].strip()
    line = re.split(r'\s+--', line, maxsplit=1)[0].strip()
    return line


def parse_requirements(text):
    joined = []
    buffer = ''
    for raw in text.splitlines():
        stripped = raw.rstrip()
        if stripped.endswith('\\'):
            buffer += stripped[:-1] + ' '
            continue
        joined.append(buffer + stripped)
        buffer = ''
    if buffer:
        joined.append(buffer)

    deps, skipped, seen = [], [], set()
    for raw in joined:
        line = _clean(raw)
        if not line:
            continue
        if line.startswith('-'):
            skipped.append((raw.strip(), 'option or include line (not followed)'))
            continue
        if re.match(r'^(git\+|hg\+|svn\+|bzr\+|[a-z][a-z0-9+.-]*://|file:|\.{1,2}[\\/]|/)',
                    line, re.IGNORECASE):
            skipped.append((raw.strip(), 'direct URL or local path'))
            continue
        try:
            req = Requirement(line)
        except InvalidRequirement:
            skipped.append((raw.strip(), 'could not be parsed'))
            continue
        name = normalize(req.name)
        if name in seen:
            continue
        seen.add(name)
        deps.append({'name': name, 'display': req.name, 'spec': str(req.specifier)})
    return deps, skipped


def load_data(data_dir=DATA_DIR):
    data_dir = Path(data_dir)
    scores = pd.read_csv(data_dir / 'risk_scores.csv')
    missing = [c for c in REQUIRED_COLUMNS if c not in scores.columns]
    if missing:
        raise ValueError(f'risk_scores.csv is missing columns: {missing}')
    scores['key'] = scores['package'].map(normalize)
    scores = scores.drop_duplicates('key').set_index('key')
    scores['archived'] = scores['archived'].astype(str).str.lower().isin(['true', '1'])
    scores['alive'] = scores['alive'].astype(str).str.lower().isin(['true', '1'])
    stats = pd.read_csv(data_dir / 'tier_stats.csv')
    return scores, stats


def assess(deps, scores):
    rows = []
    for dep in deps:
        key = dep['name']
        row = {'package': dep['display'], 'key': key, 'pinned': dep['spec']}
        if key not in scores.index:
            row.update({'status': 'Not covered', 'tier': None, 'score': np.nan,
                        'signals': '', 'repo': '', 'archived': False,
                        'months_since_last_release': np.nan,
                        'active_months_12': np.nan})
        else:
            info = scores.loc[key]
            archived = bool(info['archived'])
            status = 'Archived by owner' if archived else TIER_TO_STATUS[info['tier']]
            row.update({'status': status, 'tier': info['tier'],
                        'score': info['score'], 'signals': info['signals'],
                        'repo': info['repo_name'], 'archived': archived,
                        'months_since_last_release': info['months_since_last_release'],
                        'active_months_12': info['active_months_12']})
        rows.append(row)
    if not rows:
        return pd.DataFrame(columns=RESULT_COLUMNS)
    result = pd.DataFrame(rows)
    result['order'] = result['status'].map(STATUS_ORDER.index)
    result = result.sort_values(
        ['order', 'score', 'months_since_last_release', 'package'],
        ascending=[True, False, False, True], na_position='last')
    return result.drop(columns='order').reset_index(drop=True)


def summarize(result, skipped):
    counts = result['status'].value_counts().reindex(STATUS_ORDER, fill_value=0)
    covered = int((result['status'] != 'Not covered').sum())
    return {
        'total': int(len(result)),
        'covered': covered,
        'counts': {k: int(v) for k, v in counts.items()},
        'skipped': int(len(skipped)),
    }


def explain(status, stats):
    if status in STATUS_TO_TIER:
        row = stats[stats['tier'] == STATUS_TO_TIER[status]].iloc[0]
        return (f"In the backtest, about {row['went_silent_pct']:.0f}% of packages in "
                f"this tier (range {row['range_low_pct']:.0f} to "
                f"{row['range_high_pct']:.0f}%) went silent within the next 12 months. "
                "Silent means no commits and no release, which is not the same as dead.")
    return MESSAGES[status]