#!/usr/bin/env python3
"""
assistant.py — Andy's personal assistant: file organizing + task tracking.

This is the single source of truth for task data. maya_chat.py imports
functions directly from this file so there's only ever one task list.

Usage:
    python3 assistant.py organize [folder]
    python3 assistant.py task add "buy milk"
    python3 assistant.py task list
    python3 assistant.py task done 2
    python3 assistant.py task remove 2
    python3 assistant.py task stats

    Or just talk naturally:
    python3 assistant.py "remind me to buy milk"
    python3 assistant.py "what's on my list"
"""

import sys
import os
import re
import shutil
import json
from pathlib import Path
from datetime import datetime

DEFAULT_ORGANIZE_FOLDER = str(Path.home() / "Downloads")
TASKS_FILE = str(Path(__file__).resolve().parent / "tasks.json")

FILE_CATEGORIES = {
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp"],
    "Documents": [".pdf", ".doc", ".docx", ".txt", ".odt", ".rtf"],
    "Spreadsheets": [".xlsx", ".xls", ".csv"],
    "Archives": [".zip", ".rar", ".7z", ".tar", ".gz"],
    "Videos": [".mp4", ".mkv", ".avi", ".mov", ".webm"],
    "Audio": [".mp3", ".wav", ".flac", ".m4a"],
    "Scripts": [".py", ".sh", ".js"],
}


def categorize_file(extension):
    ext = extension.lower()
    for category, extensions in FILE_CATEGORIES.items():
        if ext in extensions:
            return category
    return "Other"


def organize_folder(folder_path):
    folder = Path(folder_path)
    if not folder.exists():
        print(f"❌ Folder not found: {folder}")
        return

    moved_count = 0
    for item in folder.iterdir():
        if item.is_file():
            category = categorize_file(item.suffix)
            dest_folder = folder / category
            dest_folder.mkdir(exist_ok=True)

            dest_path = dest_folder / item.name
            counter = 1
            while dest_path.exists():
                dest_path = dest_folder / f"{item.stem}_{counter}{item.suffix}"
                counter += 1

            shutil.move(str(item), str(dest_path))
            print(f"  {item.name}  →  {category}/")
            moved_count += 1

    if moved_count == 0:
        print("Nothing to organize — folder is already tidy (or empty).")
    else:
        print(f"\n✅ Organized {moved_count} file(s) in {folder}")


def load_tasks():
    path = Path(TASKS_FILE)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("tasks", [])
    except Exception:
        pass
    return []


def save_tasks(tasks):
    Path(TASKS_FILE).write_text(json.dumps(tasks, indent=2), encoding="utf-8")


def task_is_done(task):
    return task.get("done") is True or str(task.get("status", "")).lower() == "done"


def task_add(text):
    tasks = load_tasks()
    tasks.append({
        "text": text,
        "done": False,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    save_tasks(tasks)
    print(f"✅ Added: {text}")
    return True


def task_list():
    tasks = load_tasks()
    if not tasks:
        print("No tasks yet. Add one with: assistant.py task add \"something\"")
        return
    print("\nYour tasks:")
    for i, t in enumerate(tasks, start=1):
        status = "✔" if task_is_done(t) else " "
        print(f"  [{status}] {i}. {t.get('text', 'Untitled task')}")
    print()


def task_done(index):
    tasks = load_tasks()
    if 1 <= index <= len(tasks):
        tasks[index - 1]["done"] = True
        save_tasks(tasks)
        print(f"✅ Marked done: {tasks[index - 1].get('text', 'Untitled task')}")
        return True
    print(f"❌ No task #{index}")
    return False


def task_remove(index):
    tasks = load_tasks()
    if 1 <= index <= len(tasks):
        removed = tasks.pop(index - 1)
        save_tasks(tasks)
        print(f"🗑️  Removed: {removed.get('text', 'Untitled task')}")
        return True
    print(f"❌ No task #{index}")
    return False


def task_stats():
    tasks = load_tasks()
    total = len(tasks)
    done = sum(1 for t in tasks if task_is_done(t))
    return total, total - done, done


def print_task_stats():
    total, open_count, done = task_stats()
    print(f"Total: {total}  Open: {open_count}  Done: {done}")


def print_usage():
    print(__doc__)


def try_natural_language(text):
    lower = text.lower()

    add_triggers = ["remind me to", "add task", "i need to", "todo:", "add:"]
    for trigger in add_triggers:
        if trigger in lower:
            task_text = lower.split(trigger, 1)[1].strip()
            if task_text:
                task_add(task_text)
                return True

    list_triggers = ["what's on my list", "show my tasks", "list tasks",
                      "my tasks", "show tasks", "what do i need to do"]
    if any(trigger in lower for trigger in list_triggers):
        task_list()
        return True

    organize_triggers = ["organize", "clean up", "sort my files", "tidy"]
    if any(trigger in lower for trigger in organize_triggers):
        print(f"Organizing: {DEFAULT_ORGANIZE_FOLDER}\n")
        organize_folder(DEFAULT_ORGANIZE_FOLDER)
        return True

    done_match = re.search(r"(?:mark task|finish task|done with|complete task)\D*(\d+)", lower)
    if done_match:
        task_done(int(done_match.group(1)))
        return True

    remove_match = re.search(r"(?:remove task|delete task)\D*(\d+)", lower)
    if remove_match:
        task_remove(int(remove_match.group(1)))
        return True

    return False


def main():
    if len(sys.argv) < 2:
        print_usage()
        return

    command = sys.argv[1]
    known_commands = {"organize", "task"}

    if command not in known_commands:
        full_text = " ".join(sys.argv[1:])
        if try_natural_language(full_text):
            return
        print("🤔 I didn't understand that. Try phrasing it differently, or:")
        print_usage()
        return

    if command == "organize":
        folder = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_ORGANIZE_FOLDER
        print(f"Organizing: {folder}\n")
        organize_folder(folder)

    elif command == "task":
        if len(sys.argv) < 3:
            print_usage()
            return
        subcommand = sys.argv[2]

        if subcommand == "add" and len(sys.argv) > 3:
            task_add(" ".join(sys.argv[3:]))
        elif subcommand == "list":
            task_list()
        elif subcommand == "done" and len(sys.argv) > 3:
            task_done(int(sys.argv[3]))
        elif subcommand == "remove" and len(sys.argv) > 3:
            task_remove(int(sys.argv[3]))
        elif subcommand == "stats":
            print_task_stats()
        else:
            print_usage()
    else:
        print_usage()


if __name__ == "__main__":
    main()

