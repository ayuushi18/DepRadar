import numpy as np
import pandas as pd
import pytest

import core

REQ = '\n'.join([
    '# a comment',
    'requests==2.31.0  # inline comment',
    'Flask[async]>=2.0,<3',
    'pywin32; sys_platform == "win32"',
    'Typing_Extensions',
    'numpy==1.26.0 \\',
    '    --hash=sha256:abc123',
    '-r other.txt',
    '-e .',
    'git+https://github.com/example/project.git',
    './local/path',
    'https://example.com/pkg.whl',
    'not a valid ((( line',
    'requests>=2.0',
])


def fixture_scores():
    rows = [
        ('alpha', 'o/alpha', '1 High', 0.40, 'quiet', True, 30, 1, True),
        ('bravo', 'o/bravo', '1 High', 0.60, 'quiet', False, 40, 1, True),
        ('charlie', 'o/charlie', '1 High', 0.30, 'quiet', False, 20, 2, True),
        ('delta', 'o/delta', '2 Elevated', 0.15, 'some', False, 10, 5, True),
        ('echo', 'o/echo', '3 Lower', 0.01, 'none', False, 2, 12, True),
        ('foxtrot', 'o/foxtrot', 'Already silent', np.nan, 'silent', False, 33, 0, False),
        ('golf', 'o/golf', 'Already silent', np.nan, 'silent', False, 50, 0, False),
    ]
    df = pd.DataFrame(rows, columns=['package', 'repo_name', 'tier', 'score', 'signals',
                                     'archived', 'months_since_last_release',
                                     'active_months_12', 'alive'])
    df['key'] = df['package']
    return df.set_index('key')


def fixture_stats():
    return pd.DataFrame({
        'tier': ['1 High', '2 Elevated', '3 Lower'],
        'went_silent_pct': [31.0, 17.4, 2.1],
        'range_low_pct': [26.0, 14.0, 2.0],
        'range_high_pct': [37.0, 21.0, 3.0],
    })


def deps_for(names):
    return [{'name': n, 'display': n, 'spec': ''} for n in names]


def test_normalize():
    assert core.normalize('Typing_Extensions') == 'typing-extensions'
    assert core.normalize('zope.interface') == 'zope-interface'
    assert core.normalize('A--B__C') == 'a-b-c'


def test_parse_handles_messy_input():
    deps, skipped = core.parse_requirements(REQ)
    assert [d['name'] for d in deps] == [
        'requests', 'flask', 'pywin32', 'typing-extensions', 'numpy']
    assert deps[0]['spec'] == '==2.31.0'
    assert len(skipped) == 6


def test_assess_orders_by_urgency():
    result = core.assess(
        deps_for(['echo', 'bravo', 'missing-pkg', 'alpha', 'golf',
                  'charlie', 'delta', 'foxtrot']),
        fixture_scores())
    assert list(result['package']) == [
        'alpha', 'golf', 'foxtrot', 'bravo', 'charlie', 'delta', 'echo', 'missing-pkg']
    assert result.loc[0, 'status'] == 'Archived by owner'
    assert result.iloc[-1]['status'] == 'Not covered'


def test_summarize_counts_and_coverage():
    result = core.assess(deps_for(['alpha', 'bravo', 'echo', 'nope']), fixture_scores())
    summary = core.summarize(result, [('-r x', 'option')])
    assert summary['total'] == 4
    assert summary['covered'] == 3
    assert summary['skipped'] == 1
    assert summary['counts']['High'] == 1
    assert summary['counts']['Archived by owner'] == 1
    assert summary['counts']['Not covered'] == 1


def test_explain_uses_measured_numbers():
    stats = fixture_stats()
    text = core.explain('High', stats)
    assert '31%' in text and '26 to 37%' in text
    assert 'not the same as dead' in text
    assert 'archived' in core.explain('Archived by owner', stats)


@pytest.mark.skipif(not (core.DATA_DIR / 'risk_scores.csv').exists(),
                    reason='data files not present')
def test_real_data_contract():
    scores, stats = core.load_data()
    assert len(scores) == 2667
    assert set(scores['tier']) == {'1 High', '2 Elevated', '3 Lower', 'Already silent'}
    alive = scores[scores['alive']]
    assert alive['score'].between(0, 1).all()
    assert scores[~scores['alive']]['score'].isna().all()
    assert (scores[~scores['alive']]['tier'] == 'Already silent').all()
    assert set(stats['tier']) == {'1 High', '2 Elevated', '3 Lower'}
    result = core.assess(deps_for(list(scores.index[:50])), scores)
    assert (result['status'] != 'Not covered').all()