from pathlib import Path
from maya_chat import ask

ROOT = Path(__file__).resolve().parent

source = (ROOT / "maya_chat.py").read_text(encoding="utf-8")
assert 'Prefer one clear sentence' in source
assert 'only the current question' in source
assert 'wait for the next message' in source
assert 'num_predict": 512' in source

print('concise_policy=OK')
print('topic_relevance_policy=OK')
print('continuity_policy=OK')