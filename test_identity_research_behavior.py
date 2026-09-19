from pathlib import Path
from maya_chat import maya_local_command, local_fallback

ROOT = Path(__file__).resolve().parent

assert maya_local_command('Who is Andy') == 'Andy is my creator, owner, and human supervisor.'
assert local_fallback('Who is Andy') == 'Andy is my creator, owner, and human supervisor.'
source = (ROOT / 'maya_web_research.py').read_text(encoding='utf-8')
assert 'Brief research summary' in source
assert 'Relevant points only' in source
assert 'No trusted memory update occurred.' in source
assert 'score_relevance' in source
print('andy_identity=OK')
print('concise_research_policy=OK')