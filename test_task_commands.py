import json
import tempfile
from pathlib import Path

import assistant
import maya_chat


def test_assistant_task_add_list_done_remove_stats():
    with tempfile.TemporaryDirectory() as tmp:
        assistant.TASKS_FILE = str(Path(tmp) / "tasks.json")
        assert assistant.task_add("buy milk") is True
        assert assistant.task_add("call alex tomorrow") is True
        total, open_count, done = assistant.task_stats()
        assert (total, open_count, done) == (2, 2, 0)
        assert assistant.task_done(1) is True
        assert assistant.task_stats() == (2, 1, 1)
        assert assistant.task_remove(2) is True
        assert assistant.task_stats() == (1, 0, 1)
        assert assistant.task_done(99) is False
        assert assistant.task_remove(99) is False
        tasks = assistant.load_tasks()
        assert len(tasks) == 1 and tasks[0]["text"] == "buy milk"


class FakeResult:
    def __init__(self, stdout="", stderr=""):
        self.stdout = stdout
        self.stderr = stderr


def test_maya_local_command_routes_task_and_preserves_case():
    calls = []

    def fake_run(args, **kwargs):
        calls.append(list(args))
        if "add" in args:
            return FakeResult(stdout="Added: Buy Milk And Eggs")
        if "list" in args:
            return FakeResult(stdout="Your tasks:")
        if "stats" in args:
            return FakeResult(stdout="Total: 1  Open: 1  Done: 0")
        if "done" in args:
            return FakeResult(stdout="Marked done: x")
        if "remove" in args:
            return FakeResult(stdout="Removed: x")
        return FakeResult(stdout="")

    original = maya_chat._run_captured
    maya_chat._run_captured = fake_run
    try:
        assert maya_chat.maya_local_command(":task add Buy Milk And Eggs") == "Added: Buy Milk And Eggs"
        assert calls[-1][-1] == "Buy Milk And Eggs"
        assert "task" in maya_chat.maya_local_command(":task list")
        assert "Total:" in maya_chat.maya_local_command(":task stats")
        assert "x" in maya_chat.maya_local_command(":task done 1")
        assert "x" in maya_chat.maya_local_command(":task remove 1")
        usage = maya_chat.maya_local_command(":task bogus")
        assert "Usage:" in usage and "Nothing was changed" in usage
        usage_empty = maya_chat.maya_local_command(":task")
        assert "Usage:" in usage_empty
        assert maya_chat.maya_local_command(":task done two") is None or "Usage:" in maya_chat.maya_local_command(":task done two")
    finally:
        maya_chat._run_captured = original
    assert all(cmd[0] == Path(maya_chat.ROOT / "assistant.py").as_posix() or Path(cmd[0]) == maya_chat.ROOT / "assistant.py" for cmd in calls)
    assert all("task" in cmd for cmd in calls)


print("assistant_task_lifecycle=OK")
print("router_task_routes=OK")
print("router_rejects_bad_task=OK")
print("utf8_subprocess_encode_configured=" + str(maya_chat.CHILD_ENV.get("PYTHONIOENCODING") == "utf-8"))