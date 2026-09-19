import json
from pathlib import Path
from maya_chat import maya_local_command, local_fallback
from maya_context import rewrite_follow_up
from maya_voice_startup import status

root = Path(__file__).parent


def stable_snapshot(root_path, names):
    snapshot = {}
    for name in names:
        path = root_path / name
        if not path.exists():
            continue
        if name == "maya_service_state.json":
            data = json.loads(path.read_text(encoding="utf-8"))
            data.pop("pid", None)
            data.pop("updated_at", None)
            snapshot[name] = data
        else:
            snapshot[name] = path.read_bytes()
    return snapshot


tracked_files = ("andy_profile.json", "maya_service_state.json")
before = stable_snapshot(root, tracked_files)

assert maya_local_command("Who is Andy?") == "Andy is my creator, owner, and human supervisor."
assert maya_local_command("Tell me who Andy is.") == "Andy is my creator, owner, and human supervisor."
warhol_answer = maya_local_command("Who is Andy Warhol?") or local_fallback("Who is Andy Warhol?")
assert "creator, owner, and human supervisor" not in warhol_answer.lower()
assert "focused question" in local_fallback("What is the smallest useful version of Maya?")

history = [
    {"role": "user", "content": "I want to improve my coding skills."},
    {"role": "assistant", "content": "What outcome matters most?"},
]
follow_up = rewrite_follow_up("A paid project within six months.", history)
assert "paid project" in follow_up.lower()
assert "status" in maya_local_command(":status").lower()
assert status()["microphone_listening_enabled"] is False

after = stable_snapshot(root, tracked_files)
assert after == before

print("owner_identity=OK")
print("topic_isolation=OK")
print("concise_fallback=OK")
print("conversation_continuity=OK")
print("useful_status_command=OK")
print("no_state_change=OK")
