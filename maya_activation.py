import json
import signal
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / 'maya_activation_state.json'


def _read():
    if not STATE.exists():
        return {'active': False, 'automatic_browsing': False, 'automatic_learning': False, 'presence_mode': False, 'worker_pid': None}
    try:
        return json.loads(STATE.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {'active': False, 'automatic_browsing': False, 'automatic_learning': False, 'presence_mode': False, 'worker_pid': None}


def status():
    return _read()


def activate():
    """Start an explicit learning session without background browsing.

    Public research remains a per-request, read-only operation. This keeps
    activation compatible with the documented approval and resource limits.
    """
    from maya_learning import set_learning_mode
    set_learning_mode('learning')
    state = _read()
    state.update({'active': True, 'automatic_browsing': False, 'automatic_learning': False, 'presence_mode': False, 'worker_pid': None})
    STATE.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')
    return state


def deactivate():
    from maya_learning import set_learning_mode
    set_learning_mode('sleeping')
    state = _read()
    pid = state.get('worker_pid')
    if pid:
        try: os.kill(int(pid), signal.SIGTERM)
        except (OSError, ValueError): pass
    state.update({'active': False, 'automatic_browsing': False, 'automatic_learning': False, 'presence_mode': False, 'worker_pid': None})
    STATE.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')
    return state
