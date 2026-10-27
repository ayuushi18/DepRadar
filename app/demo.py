import core

SAMPLE = '''
requests==2.31.0
pandas>=2.0
hyperlink
astor==0.8.1
pytest-instafail
typing-inspect
ptyprocess
my-private-library==1.0
-r base.txt
'''

scores, stats = core.load_data()
deps, skipped = core.parse_requirements(SAMPLE)
result = core.assess(deps, scores)

print(core.summarize(result, skipped))
print()
print(result[['package', 'status', 'score', 'signals']].to_string(index=False))
print()
for status in ['High', 'Elevated', 'Lower', 'Already silent',
               'Archived by owner', 'Not covered']:
    print(f'{status}: {core.explain(status, stats)}')