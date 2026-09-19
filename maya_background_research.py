import json, time
try:
    import fcntl
except ImportError:
    fcntl = None
from datetime import datetime, timezone
from pathlib import Path
from maya_web_research import research_topic

ROOT = Path(__file__).resolve().parent
STATE = ROOT / 'maya_activation_state.json'
PROFILE = ROOT / 'maya_interest_profile.json'
LOG = ROOT / 'knowledge' / 'background_research_events.jsonl'
LOCK = ROOT / 'maya_background_research.lock'


def topics():
    if not PROFILE.exists(): return []
    data = json.loads(PROFILE.read_text(encoding='utf-8'))
    return [item for group in data.get('interests', {}).values() for item in group]


def main():
    with LOCK.open('w', encoding='utf-8') as lock_handle:
        try:
            if fcntl is not None:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        seen = set()
        _run_loop(seen)


def _run_loop(seen):
    while True:
        try:
            state = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {}
            if not state.get('active') or not state.get('automatic_browsing') or not state.get('automatic_learning'):
                break
            for topic in topics():
                key = topic.strip().lower()
                if not key or key in seen: continue
                result = research_topic(topic)
                LOG.parent.mkdir(parents=True, exist_ok=True)
                with LOG.open('a', encoding='utf-8') as f:
                    f.write(json.dumps({'timestamp': datetime.now(timezone.utc).isoformat(), 'event': 'background_research', 'topic': topic, 'memory_update': 'not_performed', 'result_preview': result[:400]}, ensure_ascii=False) + '\n')
                seen.add(key)
            time.sleep(900)
        except Exception as exc:
            LOG.parent.mkdir(parents=True, exist_ok=True)
            with LOG.open('a', encoding='utf-8') as f:
                f.write(json.dumps({'timestamp': datetime.now(timezone.utc).isoformat(), 'event': 'background_research_error', 'detail': str(exc)[:300]}) + '\n')
            time.sleep(60)

if __name__ == '__main__': main()


