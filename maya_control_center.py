import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def read_json(name, default=None):
    path = ROOT / name
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default

def task_command(*args):
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / 'assistant.py'), *args],
            cwd=ROOT, text=True, capture_output=True, timeout=20
        )
        return {'returncode': result.returncode, 'output': (result.stdout + result.stderr).strip()}
    except Exception as exc:
        return {'returncode': None, 'output': f'unavailable: {exc}'}

def main():
    dashboard = read_json('maya_approval_dashboard.json', {})
    focus = read_json('maya_weekly_focus.json', {})
    freshness = read_json('maya_research_freshness.json', {})
    learning = read_json('maya_supervised_research_learning.json', {})
    evidence = read_json('maya_evidence_cluster.json', {})
    income = read_json('maya_income_report_comparison.json', {})

    result = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'status': 'review_only',
        'title': 'Maya Control Center',
        'sections': {
            'weekly_focus': {
                'open_task_count': focus.get('open_task_count'),
                'focus_tasks': focus.get('focus_tasks', []),
            },
            'tasks': {
                'stats': task_command('task', 'stats'),
                'list': task_command('task', 'list'),
            },
            'approvals': {
                'pending_review_entries': dashboard.get('summary', {}).get('candidate_or_proposal_files'),
                'tracked_files': dashboard.get('summary', {}).get('other_tracked_files'),
                'audit_events_loaded': dashboard.get('summary', {}).get('audit_events_loaded'),
            },
            'research': {
                'learning_state': learning.get('learning_state'),
                'freshness_state': freshness.get('learning_state'),
                'research_like_records': freshness.get('research_like_records'),
                'network_mode': freshness.get('network_mode'),
                'allowed_hosts': freshness.get('allowed_hosts', []),
            },
            'evidence': {
                'record_count': evidence.get('record_count'),
                'cluster_count': evidence.get('cluster_count'),
            },
            'income_research': {
                'opportunity_count': income.get('opportunity_count'),
                'status': income.get('status'),
            },
        },
        'controls': {
            'read_only': True,
            'task_changes_executed': False,
            'approval_actions_executed': False,
            'memory_modified': False,
            'network_access': False,
            'writes_only_to_stdout': True,
            'explicit_Andy_approval_required_for_actions': True,
        },
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == '__main__':
    main()
