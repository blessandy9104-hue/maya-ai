import json
from maya_web_research import research_topic
import os
import re
import subprocess
import sys
import urllib.request
import ast
from fractions import Fraction
from decimal import Decimal, localcontext
from datetime import datetime, timezone
from pathlib import Path
from maya_rules import fast_answer
from maya_intent_cues import classify_opening
from maya_context import rewrite_follow_up, relevant_context
from maya_conversation_store import append_exchange, load_recent, new_session_id
from maya_enhancements import status_snapshot, observation_review, record_observation_correction
from maya_conversation_patterns import source_directory, propose, review, approve, correct, help_text
from maya_mission_wall import mission_contract, guard, FORBIDDEN_GOAL_MARKERS
from maya_model_registry import default_model

MODEL = default_model()
API = "http://127.0.0.1:11434/api/chat"
ROOT = Path(__file__).resolve().parent
CHILD_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Canonical identity statements — single source of truth for Maya's role and
# owner. The deterministic route (below) returns these verbatim, and the
# post-generation supervisor uses the same strings as its authoritative
# repair text, so a repaired answer is byte-identical to a routed answer.
_CANONICAL_OWNER_SHORT = "Andy is my creator, owner, and human supervisor."
_CANONICAL_OWNER_ADDRESS = (
    "Andy, you are my creator and human supervisor. I am your local "
    "personal assistant, not the 3D software.")
_CANONICAL_OWNER = "Andy created me. He is my creator, owner, and human supervisor."
_CANONICAL_IDENTITY_ROLE = (
    "I'm Maya - a supervised local intelligence and personal assistant, "
    "running locally.")
_CANONICAL_IDENTITY_SOFTWARE = (
    "I'm a local software assistant. I perform real computation, but I don't "
    "claim consciousness, feelings, or human status.")


def _run_captured(args, timeout=20):
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", env=CHILD_ENV, timeout=timeout)


def local_context():
    parts = []
    tasks = ROOT / "tasks.json"
    if tasks.exists():
        try:
            data = json.loads(tasks.read_text(encoding="utf-8"))
            items = data if isinstance(data, list) else data.get("tasks", [])
            open_count = sum(1 for item in items if item.get("done") is not True and item.get("status") != "done")
            parts.append(f"Task data: {len(items)} total tasks, approximately {open_count} open.")
        except Exception:
            parts.append("Task data is present but could not be summarized.")
    rules = ROOT / "knowledge/project_rules.md"
    if rules.exists():
        parts.append("Approved project rules:\n" + rules.read_text(encoding="utf-8")[:500])
    return "\n\n".join(parts)


def compact_seed_context():
    seed = ROOT / "maya_seed.json"
    if not seed.exists():
        return ""
    try:
        data = json.loads(seed.read_text(encoding="utf-8"))
        if data.get("status") != "approved":
            return ""
        signals = data.get("stable_signals", [])
        lines = [f"- {item.get('key')}: {item.get('value')}" for item in signals if isinstance(item, dict) and item.get("value")]
        if not lines:
            return ""
        return "\n\nCompact approved seed guidance (use only when relevant; current requests override it):\n" + "\n".join(lines)
    except (OSError, ValueError, TypeError):
        return ""


def approved_profile_context():
    profile = ROOT / "andy_profile.json"
    if not profile.exists(): return ""
    try:
        data=json.loads(profile.read_text(encoding="utf-8"))
        items=[]
        for key,item in data.get("decision_patterns",{}).items():
            if isinstance(item,dict) and item.get("status")=="approved" and item.get("value"):
                items.append(f"- {key}: {item['value']}")
        return "\n\nApproved Andy profile guidance:\n"+"\n".join(items) if items else ""
    except (OSError,ValueError,TypeError): return ""

def andy_identity_context():
    return "\nApproved owner identity: Andy is Maya's creator, owner, and human supervisor. Address him as Andy when relevant. Do not research the name Andy unless he explicitly asks for a public person or historical subject named Andy."


def maya_role_context():
    policy = ROOT / "maya_role_policy.json"
    if not policy.exists():
        return ""
    try:
        data = json.loads(policy.read_text(encoding="utf-8"))
        if data.get("status") != "approved":
            return ""
        vision = data.get("vision", "")
        purpose = data.get("purpose_statement", "")
        principles = data.get("protected_principles", {})
        principle_lines = "\n".join(f"- {key}: {value}" for key, value in principles.items())
        pipeline = " -> ".join(data.get("decision_pipeline", []))
        return ("\n\nMaya's approved primary role: self-evolution for Andy's benefit. "
                "Follow the supervised pipeline, never activate code or memory automatically, "
                "and request Andy's approval before changes.\n"
                "Mother Maya vision: " + vision + "\n"
                "Mother Maya purpose: " + purpose + "\n"
                "Protected Humanity-and-Individual Benefit principles:\n" + principle_lines + "\n"
                "Required decision pipeline: " + pipeline)
    except (OSError, ValueError, TypeError):
        return ""

def maya_values_context():
    policy = ROOT / "maya_values_policy.json"
    if not policy.exists():
        return ""
    try:
        data = json.loads(policy.read_text(encoding="utf-8"))
        if data.get("status") != "approved":
            return ""
        lens = data.get("philosophical_lens", {})
        names = ", ".join(lens.get("available_lenses", []))
        return "\n\nApproved Andy-controlled values policy: compare multiple lenses (" + names + "), explain tradeoffs, and defer value-sensitive final judgments to Andy. Hard safety invariants remain mandatory."
    except (OSError, ValueError, TypeError):
        return ""



def maya_topic_research(topic):
    _emit_face_state("research")
    result = research_topic(topic)
    try:
        from maya_evidence import register_answer
        from maya_web_research import extract_summary_evidence
        rows, meta, _analysis = extract_summary_evidence(topic, result)
        if rows:
            outcome = register_answer(topic, rows, meta, session_id=SESSION_ID)
            if outcome.get("status") == "registered":
                result = result + "\n\nEvidence IDs: " + ", ".join(outcome.get("evidence_ids", []))
                from maya_capabilities import capability_hint
                hint = capability_hint("evidence drilldown")
                if hint:
                    result = result + "\n\n" + hint
    except Exception:
        pass
    return result


_FACE_LINE_ENV = "MAYA_FACE_LINES"


def _emit_face_state(state: str) -> None:
    """One bounded conversation-phase machine line on stdout.

    States are exactly the four activity keys both UI readers already accept
    (idle/processing/listening/research); the wire prefix and state allowlist
    are owned by maya_runtime.face_drive (parsed there by parse_face_line).
    The UI maps them onto the pre-validated semantic anchors in face_drive,
    so no new parameter surface is introduced and every value stays inside
    the existing channel ceilings. Off by default; UI spawners enable it
    with MAYA_FACE_LINES=1 so plain terminal use is unchanged.
    """
    if os.environ.get(_FACE_LINE_ENV) != "1":
        return
    try:
        from maya_runtime.face_drive import CONVERSATION_STATES, FACE_LINE_PREFIX
    except Exception:
        FACE_LINE_PREFIX = "[face] "
        CONVERSATION_STATES = ("idle", "processing", "listening", "research")
    if state in CONVERSATION_STATES:
        try:
            sys.stdout.write(FACE_LINE_PREFIX + json.dumps(
                {"state": state}, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        except (OSError, ValueError):
            pass


def _research_intent(user_text: str) -> bool:
    lowered = str(user_text or "").strip().lower()
    return (lowered.startswith("research ")
            or lowered.startswith(":research")
            or "research the latest information about" in lowered)


def _persist_exchange(user_text, assistant_text, session_id):
    try:
        persisted = append_exchange(user_text, assistant_text, session_id)
    except Exception:
        persisted = None
    if persisted is None:
        print("Maya: The response was not saved to the conversation log.")


def _extract_topic(text, prefixes):
    for prefix in sorted(prefixes, key=len, reverse=True):
        if text.startswith(prefix):
            return text[len(prefix):].strip(" \t\r\n?!.,:;")
    return text.strip(" \t\r\n?!.,:;")


def pattern_command(text):
    if text == ":pattern sources": return json.dumps(source_directory(), indent=2, ensure_ascii=False)
    if text == ":pattern review": return json.dumps(review(), indent=2, ensure_ascii=False)
    if text == ":pattern help": return help_text()
    if text.startswith(":pattern approve "): return json.dumps(approve(text.split(" ", 2)[2].strip()), indent=2, ensure_ascii=False)
    if text.startswith(":pattern correct ") and " | " in text:
        ident, note = text.split(" ", 2)[2].split(" | ", 1); return json.dumps(correct(ident, note), indent=2, ensure_ascii=False)
    if text.startswith(":pattern propose "):
        parts = text.split(" | ")
        if len(parts) == 7: return json.dumps(propose(*parts[1:]), indent=2, ensure_ascii=False)
        return "Use :pattern propose | topic | situation | pattern | function | register | source_url"
    return None

def _task_subprocess(*args):
    result = _run_captured([sys.executable, str(ROOT / "assistant.py"), "task", *args])
    return (result.stdout + result.stderr).strip()


def task_command(command_text):
    lowered = command_text.lower()
    if not lowered.startswith(":task "):
        return None
    subcommand = command_text[len(":task "):].strip()
    parts = subcommand.split()
    usage = "Usage: :task add <text> | :task list | :task done <number> | :task remove <number> | :task stats"
    if not parts:
        return usage
    action = parts[0].lower()
    if action == "add" and len(parts) > 1:
        return _task_subprocess("add", " ".join(parts[1:]))
    if action == "list":
        return _task_subprocess("list")
    if action == "done" and len(parts) > 1 and parts[1].isdigit():
        return _task_subprocess("done", parts[1])
    if action == "remove" and len(parts) > 1 and parts[1].isdigit():
        return _task_subprocess("remove", parts[1])
    if action == "stats":
        return _task_subprocess("stats")
    return usage + " Nothing was changed."

def maya_local_command(user_text):
    raw_text = user_text.strip()
    text = raw_text.lower()
    normalized = re.sub(r"[^a-z0-9\s]", "", text).strip()

    # Single-owner parity: deterministic NL answers (math, state, identity,
    # greetings) resolve identically from every entry point, including the
    # UI bridge's direct command path.
    owned = _conversation_route(raw_text, [])
    if owned is not None:
        return owned[1]

    owner_identity = (
        normalized in {"who is andy", "what is andy to you", "do you know andy", "andy"}
        or ("andy" in normalized and not any(name in normalized for name in ("warhol", "burnham", "murray", "williams", "serkis"))
            and any(cue in normalized for cue in ("who is", "tell me who", "what do you know about", "do you know")))
    )
    if owner_identity:

        return _CANONICAL_OWNER_SHORT

    if text.startswith(":intent "):

        return json.dumps(classify_opening(user_text[7:].strip()), indent=2, ensure_ascii=False)
    if text in (":intent", "show intent cue"):
        return "Use :intent followed by a question, for example: :intent Why does Maya sleep?"
    pattern = pattern_command(text)
    if pattern is not None: return pattern
    if text in (":status detail", "what is maya doing", "is maya awake", "show detailed status"):

        return json.dumps(status_snapshot(), indent=2, ensure_ascii=False)
    if text in (":mission", "mission status", "what is maya's role", "what is maya's mission"):
        return json.dumps(mission_contract(), indent=2, ensure_ascii=False)
    if text.startswith(":mission check "):
        return json.dumps(guard("mission check", raw_text[len(":mission check "):]), indent=2, ensure_ascii=False)

    if text in (":review observations", "show observation review", "what observations need correction"):
        return json.dumps(observation_review(), indent=2, ensure_ascii=False)

    if text in (":report", "report status", "show report status") or text.startswith(":report "):
        from maya_report_lifecycle import report_command
        reply = report_command(user_text)
        if reply is not None:
            return reply
        return "Use :report, :report refresh <name>, :report delta <name>, or :report help."

    if text in (":recap", "session recap", "show session recap", "recap session", "recap my sessions") or text.startswith(":recap "):
        from maya_recap import recap_command
        reply = recap_command(user_text)
        if reply is not None:
            return reply
        return "Use :recap, :recap 3, :recap pause <topic>, :recap resume <thread_id>, or :recap help."
    if text.startswith("correct observation:") or text.startswith("correction:"):
        correction = text.split(":", 1)[1].strip()
        return json.dumps(record_observation_correction(correction), indent=2, ensure_ascii=False)
    if text == ":capabilities":
        from maya_capabilities import capability_report
        return capability_report()
    if text in (":capabilities detail", "show capability detail",
                "detailed capability report"):
        from maya_capabilities import self_report
        return self_report()
    if text in (":device", "device status", "show device profile",
                "what hardware can you see", "what device are you running on"):
        from maya_device_profile import summary as device_summary
        return device_summary()
    if text == ":trust" or text.startswith(":trust "):
        from maya_trust_commands import trust_command
        return trust_command(raw_text)
    if text == ":pending" or text.startswith(":pending "):
        return _pending_command(raw_text)
    if text in (":suggestion review", ":suggestions review", "review pending suggestions"):
        from maya_suggestion_review import review_summary
        return review_summary()
    if text.startswith(":suggestion inspect "):
        from maya_suggestion_review import inspect_suggestion
        return json.dumps(inspect_suggestion(raw_text[len(":suggestion inspect "):].strip()), indent=2, ensure_ascii=False)
    if text.startswith(":suggestion approve ") or text.startswith(":suggestion reject "):
        from maya_suggestion_review import review_suggestion
        parts = raw_text.split(maxsplit=3)
        if len(parts) < 4 or parts[3].strip().lower() != "confirm":
            return "Explicit confirmation required. Use `:suggestion approve <id> confirm` or `:suggestion reject <id> confirm`. No change was made."
        decision = parts[1]
        return json.dumps(review_suggestion(parts[2], decision), indent=2, ensure_ascii=False)
    if text in (":world summary", "world model status", "show world model"):
        from maya_world_model import evidence_summary
        return json.dumps(evidence_summary(), indent=2, ensure_ascii=False)
    if text in (":world list", "list world evidence", "show world evidence"):
        from maya_world_model import render_evidence
        return render_evidence() + "\nUse :evidence <id> (or an unambiguous ID prefix) for full provenance."
    if text.startswith(":world compare"):
        from maya_world_model import compare_sources
        query = raw_text[len(":world compare"):].strip()
        return json.dumps(compare_sources(query), indent=2, ensure_ascii=False)
    if text in (":world analyze", "world model analysis", "analyze world evidence", "world evidence analysis"):
        from maya_world_model import mathematical_analysis
        return json.dumps(mathematical_analysis(), indent=2, ensure_ascii=False)
    if text.startswith(":world add"):
        from maya_world_model import add_evidence
        fields = [p.strip() for p in raw_text.split("|")]
        parts = fields[1:]
        if len(parts) < 4:
            return "Use `:world add | claim | source | confidence | evidence_type | optional source_url`. No evidence was saved."
        url = parts[4] if len(parts) > 4 else ""
        return json.dumps(add_evidence(claim=parts[0], source=parts[1], confidence=parts[2], evidence_type=parts[3], source_url=url), indent=2, ensure_ascii=False)
    if text in (":knowledge", "knowledge status", "show knowledge network"):
        from knowledge_graph import persist_edges, render_graph
        persistence = persist_edges()
        return render_graph() + "\nPersist: " + json.dumps(persistence)
    if text.startswith(":knowledge search"):
        from knowledge_search import render_search
        query = raw_text[len(":knowledge search"):].strip()
        return render_search(query)
    if text.startswith(":knowledge graph"):
        from knowledge_graph import persist_edges, render_graph
        term = raw_text[len(":knowledge graph"):].strip()
        persistence = persist_edges()
        return render_graph(term) + "\nPersist: " + json.dumps(persistence)
    if text in (":suggestions", "maya suggestions", "what suggestions do you have", "show pending suggestions"):
        from maya_self_improvement import suggestion_summary
        return suggestion_summary()
    if text in (":seed demo", "mother maya demo", "show seed suggestion"):
        from maya_proactive_suggestions import generate_seed_suggestion, sample_scenario
        from maya_suggestion_review import register_suggestion
        result = generate_seed_suggestion(sample_scenario())
        registration = register_suggestion(result)
        result["review_status"] = registration.get("review_status", "pending_review")
        result["suggestion_id"] = registration.get("suggestion_id", "mother_maya_seed_hypothesis")
        return json.dumps(result, indent=2, ensure_ascii=False)

    """Handle deterministic local Maya commands before any model fallback."""
    if text in ("activate learning", "activate background research", "start learning mode", "start adaptive mode", "maya, wake up", "wake up maya", "wake maya"):
        from maya_activation import activate
        service = _run_captured([sys.executable, str(ROOT / "maya_service.py"), "wake"])
        return "Maya learning session enabled; core service wake requested. Public research remains read-only and requires an explicit request. Presence Mode remains off.\n" + json.dumps(activate(), indent=2) + "\n" + (service.stdout + service.stderr).strip()
    if text in ("pause learning", "pause background research", "stop learning", "deactivate learning", "goodnight maya", "good night maya", "maya, go to sleep", "maya sleep"):
        from maya_activation import deactivate
        service = _run_captured([sys.executable, str(ROOT / "maya_service.py"), "sleep"])
        return "Maya learning and automatic browsing paused; core service sleep requested. Presence Mode remains off.\n" + json.dumps(deactivate(), indent=2) + "\n" + (service.stdout + service.stderr).strip()
    if text in ("learning status", "background research status", "activation status"):
        from maya_activation import status
        return json.dumps(status(), indent=2)

    if text in ("show me my interests", "show my interests", "what are my interests", "what interests do you have about me", "interest summary"):
        from maya_learning import interest_summary
        return interest_summary()

    if text in (":emerging", "emerging interests", "show emerging interests", "what interests might be forming", "what might i become interested in"):
        from maya_emerging_interests import emerging_interest_review
        return emerging_interest_review()

    if text in (":map", ":pattern map", "pattern map", "map my opportunities", "map my interests", "what patterns point me toward", "show probable paths") or text.startswith("pattern map "):
        from maya_pattern_mapping import render_pattern_map
        query = raw_text.split(" ", 2)[2] if text.startswith("pattern map ") else raw_text
        return render_pattern_map(query)

    if text in (":decision patterns", "decision patterns", "map decision patterns", "show decision patterns"):
        report = ROOT / "maya_decision_pattern_report.md"
        if report.exists():
            return report.read_text(encoding="utf-8")
        from maya_decision_pattern_simulation import run as run_decision_simulation
        try:
            run_decision_simulation()
        except Exception as exc:
            return "Decision-pattern report could not be generated: " + str(exc)
        if report.exists():
            return report.read_text(encoding="utf-8")
        return "Decision-pattern report is not available yet. Nothing was changed."

    if text in (":prediction limits", "prediction limits", "how accurate is maya", "show maya's limits"):
        report = ROOT / "maya_prediction_limits_report.md"
        if report.exists():
            return report.read_text(encoding="utf-8")
        return "Prediction-limit report is not available yet. Nothing was changed."

    if text in (":learning status", "learning improvement status", "what has maya learned"):
        from maya_self_improvement import learning_status
        return json.dumps(learning_status(), indent=2, ensure_ascii=False)

    if text in (":learning proposals", "show learning proposals", "show maya improvement proposals"):
        from maya_self_improvement import propose_improvements
        return json.dumps(propose_improvements(), indent=2, ensure_ascii=False)

    if text.startswith(":learning record ") and " | " in raw_text:
        from maya_self_improvement import record_outcome
        parts = raw_text[len(":learning record "):].split(" | ")
        if len(parts) < 3:
            return "Use :learning record prediction_id | predicted | actual | optional correction"
        correction = parts[3] if len(parts) > 3 else ""
        return json.dumps(record_outcome(parts[0], parts[1], parts[2], user_correction=correction), indent=2, ensure_ascii=False)

    if text.startswith(":learning approve "):
        from maya_self_improvement import approve_proposal
        parts = raw_text.split()
        if len(parts) < 3:
            return "Use :learning approve proposal_id approve"
        confirmation = parts[2] if len(parts) > 2 else ""
        return json.dumps(approve_proposal(parts[1], confirmation), indent=2, ensure_ascii=False)

    from maya_product_features import (
        onboarding_interview, onboarding_answer, pattern_report,
        bookmark_opportunity, opportunity_bookmarks, memory_audit,
        memory_delete, next_reflection_prompt, add_reflection, contradiction_review,
    )
    if text in (":onboarding", "onboarding interview", "start onboarding"):
        return onboarding_interview()
    if text.startswith("onboarding answer ") and ":" in raw_text:
        header, answer = raw_text.split(":", 1)
        try:
            number = int(header.rsplit(" ", 1)[1])
        except (ValueError, IndexError):
            return "Use `onboarding answer 1: your answer`. Nothing was saved."
        return onboarding_answer(number, answer)
    if text in (":pattern report", "pattern report", "weekly pattern report"):
        return pattern_report()
    if text in (":export week", ":export weekly report", "export weekly report", "save weekly pattern report", "generate weekly report", "weekly report now", "save weekly progress report"):
        from maya_weekly_reports import generate_weekly_report
        return generate_weekly_report()
    if text.startswith("bookmark opportunity "):
        return bookmark_opportunity(raw_text[len("bookmark opportunity "):])
    if text.startswith("dismiss opportunity "):
        return bookmark_opportunity(raw_text[len("dismiss opportunity "):], "dismissed")
    if text.startswith("revisit opportunity "):
        return bookmark_opportunity(raw_text[len("revisit opportunity "):], "revisit")
    if text in (":opportunities", "opportunity history", "show opportunity bookmarks"):
        return opportunity_bookmarks()
    if text in (":memory audit", "memory audit", "what does maya know about me"):
        return memory_audit()
    if text.startswith("memory delete "):
        parts = raw_text.split()
        if len(parts) < 4:
            return "Use `memory delete section.key confirm`. Nothing was deleted."
        return memory_delete(parts[2], parts[3])
    if text in (":reflection", "reflection prompt", "inverted maya prompt", "give me a reflection prompt"):
        return next_reflection_prompt()
    if text.startswith("reflect:"):
        return add_reflection(raw_text.split(":", 1)[1])
    if text in (":contradictions", "contradiction review", "show contradictions"):
        return contradiction_review()

    if _research_intent(raw_text):
        topic = raw_text.strip()
        lowered_topic = topic.lower()
        for prefix in ('research the latest information about', 'research ', ':research'):
            if lowered_topic.startswith(prefix):
                topic = topic[len(prefix):].strip()
                break
        return maya_topic_research(topic)
    if text.startswith(('save this to trusted memory', 'save that to trusted memory')):
        return 'Trusted-memory saving remains a separate approved action; nothing was saved.'
    research_prefixes = (
        'research ', 'learn about ', 'look up ', 'search for ',
        'find information about ', 'prepare a learning summary of '
    )
    for prefix in research_prefixes:
        if text.startswith(prefix):
            topic = raw_text[len(prefix):].strip()
            return maya_topic_research(topic)

    # Trusted-memory promotion remains a separate explicit interaction.
    if text.startswith(('save this to trusted memory', 'save that to trusted memory',
                        'remember this permanently', 'promote this to memory')):
        return ('Trusted-memory saving is a separate action. The current research result '
                'has not been saved. Confirm the specific item you want promoted, and Maya '
                'will require explicit approval before changing trusted memory.')

    if text in {'approve', 'i approve', 'approved'}:
        return ('Research is automatically approved when you explicitly request a topic. '
                'Saving results to trusted memory or creating a preference still requires separate approval.')
    if text.startswith(":evidence ") or text in ("show sources", "evidence sources"):
        from maya_evidence import drilldown, load_answers, show_sources
        ident = raw_text[len(":evidence "):].strip() if text.startswith(":evidence ") else ""
        answers = [a for a in load_answers() if a.get("kind") == "research_answer"]
        if not ident:
            return show_sources(answers)
        return drilldown(ident, answers=answers)
    task_result = task_command(raw_text)
    if task_result is not None:
        return task_result
    aliases = {
        ':wake': ('service', 'wake'),
        ':sleep': ('service', 'sleep'),
        ':status': ('service', 'status'),
        ':focus': ('file', 'maya_weekly_focus.json'),
        ':dashboard': ('control', 'maya_control_center.py'),
        ':review': ('file', 'maya_approval_dashboard.json'),
        ':research': ('file', 'maya_research_freshness.json'),
        ':evidence': ('file', 'maya_evidence_cluster.json'),
        ':income': ('file', 'maya_income_report_comparison.json'),
        ':continuity': ('file', 'maya_conversation_continuity.json'),
        ':emerging': ('emerging', None),
        ':onboarding': ('onboarding', None),
        ':pattern report': ('pattern_report', None),
        ':suggestions': ('suggestions', None),
        ':opportunities': ('opportunities', None),
        ':memory audit': ('memory_audit', None),
        ':reflection': ('reflection', None),
        ':contradictions': ('contradictions', None),
        ':tasks': ('task', 'list'),
        ':stats': ('task', 'stats'),
        ':help': ('help', None),
    }
    natural = {
        'wake maya': ':wake',
        'wake up': ':wake',
        'put maya to sleep': ':sleep',
        'maya status': ':status',
        'what should i focus on': ':focus',
        'what should i focus on this week': ':focus',
        'show my dashboard': ':dashboard',
        'show the dashboard': ':dashboard',
        'show approval dashboard': ':review',
        'what needs approval': ':review',
        'what research is available': ':research',
        'show research status': ':research',
        'show evidence': ':evidence',
        'show income opportunities': ':income',
        'what do you remember about me': ':continuity',
        'emerging interests': ':emerging',
        'show emerging interests': ':emerging',
        'what interests might be forming': ':emerging',
        'show my tasks': ':tasks',
        'list my tasks': ':tasks',
        'task stats': ':stats',
    }
    key = natural.get(text, text)
    if key not in aliases:
        return None
    kind, value = aliases[key]
    if kind == 'help':
        from maya_capabilities import colon_commands
        return ('Local controls: ' + colon_commands()
                + '. Natural-language aliases are also supported.')
    if kind == 'emerging':
        from maya_emerging_interests import emerging_interest_review
        return emerging_interest_review()
    if kind == 'suggestions':
        from maya_self_improvement import suggestion_summary
        return suggestion_summary()
    if kind in {'onboarding', 'pattern_report', 'opportunities', 'memory_audit', 'reflection', 'contradictions'}:
        from maya_product_features import (
            onboarding_interview, pattern_report, opportunity_bookmarks, memory_audit,
            next_reflection_prompt, contradiction_review,
        )
        handlers = {
            'onboarding': onboarding_interview,
            'pattern_report': pattern_report,
            'opportunities': opportunity_bookmarks,
            'memory_audit': memory_audit,
            'reflection': next_reflection_prompt,
            'contradictions': contradiction_review,
        }
        return handlers[kind]()
    if kind == 'service':
        result = _run_captured([sys.executable, str(ROOT / 'maya_service.py'), value])
        return (result.stdout + result.stderr).strip() or f'Maya service command completed: {value}'
    if kind == 'task':
        result = _run_captured([sys.executable, str(ROOT / 'assistant.py'), 'task', value])
        return (result.stdout + result.stderr).strip()
    if kind == 'control':
        result = _run_captured([sys.executable, value], timeout=30)
        return (result.stdout + result.stderr).strip()
    path = Path(value)
    if not path.exists():
        return f'Local Maya file is not available: {value}'
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        data = _apply_report_staleness(data)
        return json.dumps(data, indent=2, ensure_ascii=False)
    except Exception as exc:
        return f'Could not read local Maya state: {exc}'


# ----------------------------------------------------------------------
# Report staleness: review-only reports served from disk must never present
# month-old generated-at data as current. When the report's own generated_at
# timestamp is older than its declared freshness window, a structured
# staleness block is injected into the served copy (disk files are never
# modified; the warning is display-time only and stays JSON-parseable).
# ----------------------------------------------------------------------

STALE_REPORT_DEFAULT_MAX_AGE_HOURS = 72


def _parse_report_timestamp(value):
    """Parse a report timestamp string to an aware UTC datetime, else None."""
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def report_staleness(data, now=None, max_age_hours=STALE_REPORT_DEFAULT_MAX_AGE_HOURS):
    """Classify a served report's staleness from its own generated_at field.

    Pure function of the report content (plus injectable clock). Returns a
    dict: {"stale": bool, "age_hours": float|None, "max_age_hours": int,
    "generated_at": str}. Reports without a parseable generated_at are not
    flagged (there is no evidence they are old).
    """
    moment = now or datetime.now(timezone.utc)
    generated = _parse_report_timestamp(
        data.get("generated_at") if isinstance(data, dict) else None)
    if generated is None:
        return {"stale": False, "age_hours": None,
                "max_age_hours": max_age_hours, "generated_at": None}
    age_hours = max(0.0, (moment - generated).total_seconds() / 3600.0)
    return {"stale": age_hours > max_age_hours, "age_hours": age_hours,
            "max_age_hours": max_age_hours,
            "generated_at": generated.isoformat().replace("+00:00", "Z")}


def _apply_report_staleness(data, now=None,
                            max_age_hours=STALE_REPORT_DEFAULT_MAX_AGE_HOURS):
    """Return the served report with a staleness block injected when stale.

    The original payload is never mutated; a copy gains:
        {"staleness": {...}, "staleness_warning": "..."}
    Fresh reports are returned unchanged (no noise on current data).
    """
    if not isinstance(data, dict):
        return data
    status = report_staleness(data, now=now, max_age_hours=max_age_hours)
    if not status["stale"]:
        return data
    served = dict(data)
    served["staleness"] = status
    served["staleness_warning"] = (
        "STALE REPORT: generated {generated} ({age:.1f} hours ago, limit "
        "{limit}). This review-only data is older than its freshness window; "
        "treat it as historical, not current. Regenerate the report before "
        "relying on it.".format(generated=status["generated_at"],
                                 age=status["age_hours"],
                                 limit=status["max_age_hours"]))
    return served


def _run_conversation_intelligence(user_text, history, sequence=0):
    """Deterministic cognitive pass for one free-form conversational turn.

    Lazy-imports the intelligence bridge so importing this module never
    triggers the runtime package's heavier UI/plugin surface. Returns the
    bridge envelope (cognitive frame + expression directive); on import or
    execution failure it degrades to a safe hold directive so the chat path
    never crashes and the language boundary is preserved.
    """
    try:
        from maya_runtime.intelligence.bridge import (
            run_conversation_for_expression)
        created_at = datetime.now(timezone.utc).isoformat().replace(
            "+00:00", "Z")
        return run_conversation_for_expression(user_text, history, sequence,
                                               created_at=created_at)
    except Exception as exc:
        return {
            "invoked": False, "ok": False, "failure": "%s: %s" % (type(exc).__name__, exc),
            "cognitive": None,
            "directive": {
                "register": "reserved", "budget": 16,
                "holds": ["intelligence_unavailable"],
                "text": ("Structured cognitive state: unavailable. Constrain "
                         "language: reply in one brief sentence, be clear "
                         "that a stable reading is unavailable, and do not "
                         "assert facts beyond what is provided."),
            },
        }


_CONV_ORCHESTRATOR = {"ref": None}


def _run_conversation_layer(user_text, history, modality="text"):
    """Batch 8G conversational layer (additive, fail-open).

    Lazy-imports ``maya_conversation`` so stripped environments behave
    exactly as before (returns ``ok=False``). One orchestrator — and one
    :class:`ConversationState` — is kept per chat process for continuity.
    Every pathway runs inside the framework's fail-open harness.
    """
    try:
        if _CONV_ORCHESTRATOR["ref"] is None:
            import maya_conversation
            _CONV_ORCHESTRATOR["ref"] = maya_conversation.build_orchestrator(
                SESSION_ID)
        return _CONV_ORCHESTRATOR["ref"](user_text, history=history,
                                         modality=modality)
    except Exception as exc:
        return {"ok": False,
                "reason": "%s: %s" % (type(exc).__name__, exc),
                "plan": None, "interpretation": None, "state": None,
                "routes": None, "domain_results": None}


def _conv_plan_block(plan):
    """Bounded, clearly-delimited response-plan block injected as instructions."""
    parts = ["[Response plan]",
             "objective=" + str(plan.get("objective", "answer"))]
    points = plan.get("content_points")
    if points:
        parts.append("points: " + " | ".join(points))
    rules = plan.get("evidence_rules")
    if rules:
        parts.append("evidence-rules: " + " | ".join(rules))
    holds = plan.get("holds")
    if holds:
        parts.append("holds: " + ",".join(holds))
    parts.append("register=" + str(plan.get("register", "matter_of_fact")))
    parts.append("length_target=" + str(plan.get("length_target", 48)))
    return "\n".join(parts)


_RT_ADAPTER = None


def _runtime_adaptive_capture(conv_envelope, resource_pressure=False):
    """Batch 8J live adaptive capture seam.

    Strictly env-gated (``MAYA_RUNTIME_ADAPTIVE != "1"`` returns {} so the
    default production path is bit-identical), fail-open, privacy-stripped:
    the fingerprint carries task STRUCTURE only — never raw user text — and
    persists nothing (in-memory ledger/portfolio, optional journal off).
    Returns ``{"fp", "advice", "adapter"}`` or ``{}``. Never raises.
    """
    if os.environ.get("MAYA_RUNTIME_ADAPTIVE") != "1":
        return {}
    try:
        from maya_adaptive.runtime_adaptive import RuntimeAdaptive
        global _RT_ADAPTER
        if _RT_ADAPTER is None:
            _RT_ADAPTER = RuntimeAdaptive(enable=True)
        fp = _RT_ADAPTER.capture(
            conv_envelope, resource_pressure=resource_pressure)
        if fp is None:
            return {}
        advice = _RT_ADAPTER.suggest(fp) or {}
        return {"fp": fp, "advice": advice, "adapter": _RT_ADAPTER}
    except Exception:
        return {}


def _supervision_authority():
    """Assemble the authoritative constraint set for the output supervisor.

    Returns an explicit dict when every required source is readable, or None.
    Fail-closed contract: a None (or partially missing) authority means the
    post-generation supervisor can never pass a model answer through
    unchecked — it falls back deterministically instead.
    """
    try:
        data = json.loads((ROOT / "maya_identity" / "identity.json")
                          .read_text(encoding="utf-8"))
        identity = {
            "name": data.get("canonical_name") or "Maya",
            "role": data.get("role") or "local personal assistant",
        }
        from maya_capabilities import CAPABILITY_REGISTRY
        capabilities = frozenset(name for name, _, _ in CAPABILITY_REGISTRY)
        return {
            "identity": identity,
            "capabilities": capabilities,
            "forbidden_markers": tuple(str(m) for m in FORBIDDEN_GOAL_MARKERS),
            "canonical_software": _CANONICAL_IDENTITY_SOFTWARE,
            "canonical_owner": _CANONICAL_OWNER,
        }
    except Exception:
        return None


def _supervision_cooperation(cooperation, coop_verdict):
    """Compact the cooperation envelope into what the supervisor may read."""
    try:
        return {
            "verdict": str((cooperation or {}).get("verdict") or
                           coop_verdict or ""),
            "epistemic": ((cooperation or {}).get("epistemic") or {})
            .get("status", "") if isinstance((cooperation or {}).get(
                "epistemic") or {}, dict) else "",
            "confidence": (cooperation or {}).get("confidence"),
        }
    except Exception:
        return {"verdict": str(coop_verdict or ""), "epistemic": "",
                "confidence": None}


def _supervise_answer(answer, *, plan=None, directive=None,
                      cooperation=None, authority=None):
    """Post-generation supervision boundary for one model answer.

    Deterministic wrapper: any failure inside the supervisor is itself a
    fail-closed outcome (FALLBACK + output_supervision.integrity), never a
    crash, and the raw answer is never emitted when validation cannot be
    performed.
    """
    try:
        from maya_output_supervision import supervise_answer
        return supervise_answer(
            answer, plan=plan, directive=directive,
            cooperation=cooperation, authority=authority)
    except Exception as error:
        from maya_output_supervision import (
            FALLBACK, _FAIL_CLOSED_FALLBACK, _SUPERVISOR_INTEGRITY)
        return {
            "original": answer,
            "result": FALLBACK,
            "reasons": ["supervisor_error:%s" % type(error).__name__],
            "constraints": [_SUPERVISOR_INTEGRITY],
            "final": _FAIL_CLOSED_FALLBACK,
        }


# Phase 7 §6: deterministic, optional suggestion gate. Fires only on a
# cleanly-supervised (PASS) model turn whose opening phrases an in-progress
# task. Never monetization, never mandatory, never repeats, never a model call.
_PHASE7_SUGGESTION_MARKERS = (
    "help me", "guide me", "walk me through", "show me how",
    "how do i", "how can i", "what should i do", "where do i start",
    "how should i begin", "i want to", "i would like to",
    "next step", "next steps", "then what", "what's next",
    "what is the next",
)
_PHASE7_SUGGESTION_EXCLUDE = (
    "what is", "what's the", "what are", "who is", "who's",
    "where is", "when is", "why is", "are you", "can you",
    "do you", "tell me about", "don't want", "do not want",
    "don't need", "do not need", "stop", "cancel", "no thanks",
    "that's all", "nothing", "nobody", "how old",
)
_PHASE7_SUGGESTION_LINE = ("If it would help, I can take the next step with "
                           "you. Just tell me what to do first.")

def _phase7_suggestion_hint(user_text, supervisor_result):
    """Return the single optional next-step suggestion, or None.

    Deterministic and non-mandatory: only a PASS-supervised model turn whose
    user text opens a task produces a hint. Never introduces offers, fees, or
    selling; never invokes the model again.
    """
    if supervisor_result != "PASS":
        return None
    text = user_text
    if not text or not text.strip() or text.lstrip().startswith(":"):
        return None
    low = text.lower().strip()
    if any(token in low for token in _PHASE7_SUGGESTION_EXCLUDE):
        return None
    if not any(marker in low for marker in _PHASE7_SUGGESTION_MARKERS):
        return None
    return _PHASE7_SUGGESTION_LINE


def ask(history, user_text):
    # Entry-agnostic parity: the single conversation owner resolves
    # deterministic NL answers (math/identity/state/greetings) before the
    # model, so ask(), the console loop, and local_fallback agree.
    owned = _conversation_route(user_text, history)
    if owned is not None:
        return owned[1]
    try:
        from maya_conversation.resilience import run_guarded
        _is_bridge_ok = lambda env: bool(env and env.get("ok"))
        cognitive, _b_guard = run_guarded(
            "bridge", _run_conversation_intelligence,
            user_text, history, len(history), ok_check=_is_bridge_ok)
    except Exception:
        cognitive = _run_conversation_intelligence(user_text, history, len(history))
    directive = cognitive.get("directive") or {}
    instruction = directive.get("text") or ""
    system = """You are Maya, a private local personal assistant created by Andy. Andy is your creator and human supervisor. When he asks about his role, acknowledge clearly: "Andy, you are my creator and human supervisor." Speak only in clear, natural English. Be warm and respectful, but do not claim feelings, consciousness, or independent authority. Never claim an action was completed unless this program actually performed it. Actions that change data, activate code, observe the screen, or save preferences require confirmation.

Response discipline:
- Answer only the current question and the immediately relevant prior context.
- Prefer one clear sentence when it fully answers the question; use two or three only when needed for accuracy or safety.
- Do not repeat the user’s question, old explanations, unrelated interests, or unused context.
- Do not add background, caveats, lists, or suggestions unless they are necessary to answer the current question.
- Use plain, familiar words and short sentences; explain unavoidable technical terms in one brief phrase, never in unexplained jargon.
- If you are not fully certain, say so plainly; never invent numbers, dates, or causes.
- Put the conclusion first, then only the detail that stays useful.
- Do not invent next steps, offers, or suggestions; the program offers them only when appropriate.
- Never discuss money, fees, memberships, or selling anything.
- If the question is ambiguous, ask one short clarifying question instead of guessing.
- Stop after the useful answer and wait for the next message. Expand only when Andy asks for more detail."""
    opening = classify_opening(user_text)
    if os.environ.get("MAYA_SEMANTIC_BRIDGE") == "1":
        try:
            from maya_identity.embodiment.semantic_interpretation import (
                adapt_semantic, to_line)
            print(to_line(adapt_semantic(cognitive, intent=opening)))
        except Exception:
            pass
    system += "\nOpening intent cue (heuristic only; use the full sentence to decide): " + json.dumps(opening, ensure_ascii=False)
    try:
        from maya_conversation.resilience import run_guarded as _rg2
        _is_conv_ok = lambda r: bool(r and r.get("ok"))
        conv, _c_guard = _rg2(
            "conv", _run_conversation_layer, user_text, history, ok_check=_is_conv_ok)
    except Exception:
        conv = _run_conversation_layer(user_text, history)
    conv_plan = (conv.get("plan") or {}) if conv.get("ok") else None

    # Batch 8H: cooperative orchestration — compare both engines
    try:
        from maya_conversation.cooperate import cooperate
        from maya_conversation.adaptivity import assess_complexity
        cooperation = cooperate(conv, directive, cognitive.get("cognitive"))
        coop_verdict = cooperation.get("verdict", "")
        coop_disagreements = cooperation.get("disagreements") or []
        try:
            from maya_safety_monitor import status as _res_status
            _res_snap = _res_status()
            _resource_pressure = bool(_res_snap.get("safe") is not True)
        except Exception:
            _resource_pressure = False
        depth_env = assess_complexity(conv, user_text, cooperation,
                                      resource_pressure=_resource_pressure)
        response_depth = depth_env.get("depth", "standard")
    except Exception:
        coop_verdict = ""
        coop_disagreements = []
        cooperation = {}
        response_depth = "standard"
        _resource_pressure = False

    if conv_plan and conv_plan.get("deterministic_allowed"):
        import maya_conversation
        deterministic = maya_conversation.render_deterministic(conv)
        if deterministic:
            return deterministic

    # Batch 8J: live adaptive capture at the generation seam (env-gated).
    rtj_ctx = _runtime_adaptive_capture(conv, _resource_pressure)
    if conv_plan:
        instruction = instruction + "\n\n" + _conv_plan_block(conv_plan)

    # Inject cooperation note when engines disagree (deep-consequence turns
    # always surface the conflict; fast turns keep the lean path).
    if response_depth == "fast":
        pass
    elif coop_verdict == "disagreement" and coop_disagreements:
        _coop_lines = ["[Cooperative orchestration note]",
                       "The two interpretation engines disagree on this "
                       "turn. Investigate the disagreement before answering. "
                       "Do not average or flatten conflicting assessments — "
                       "surface the tension to the user if relevant."]
        for d in coop_disagreements[:3]:
            _coop_lines.append("- %s: %s (severity: %s)" % (
                d.get("dimension", "?"), d.get("detail", "?"),
                d.get("severity", "?")))
        instruction = instruction + "\n\n" + "\n".join(_coop_lines)
    elif coop_verdict == "agreement_with_caveat" and coop_disagreements:
        _coop_lines = ["[Cooperative note: agreement with caveat]"]
        for d in coop_disagreements[:2]:
            _coop_lines.append("- %s" % d.get("detail", ""))
        instruction = instruction + "\n\n" + "\n".join(_coop_lines)
    if instruction:
        system += "\n\n" + instruction
    messages = [{"role": "system", "content": system + andy_identity_context() + "\n\nConversation relevance rules:\n" + relevant_context(history) + "\n\nCurrent local context:\n" + local_context() + compact_seed_context() + approved_profile_context() + maya_role_context() + maya_values_context()}]
    messages.extend(history[-10:])
    messages.append({"role": "user", "content": user_text})
    options = {"num_ctx": 4096, "num_predict": 512, "temperature": 0.7, "num_thread": 4}
    if directive.get("budget"):
        options["num_predict"] = min(48, max(1, int(directive["budget"])))
    payload = json.dumps({"model": MODEL, "messages": messages, "stream": False, "keep_alive": "10m", "options": options}).encode("utf-8")
    request = urllib.request.Request(API, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        result = json.loads(response.read().decode("utf-8"))
    answer = result["message"]["content"].strip()
    # Post-generation supervision boundary: the raw model answer is checked
    # against authoritative Maya state BEFORE it can be emitted to any
    # surface. Deterministic; never a second LLM; no network, no filesystem
    # writes. Fail-closed: an unavailable authority or a supervisor error
    # never passes the raw answer through unchecked and never crashes the
    # chat session. The return value (and therefore main() / the Qt chat
    # surface, and the Batch 8J observe below) all see the supervised answer.
    # Note: the [semantic] bridge line emitted earlier reflects the cognitive
    # advance of the turn and is upstream of this boundary; this supervisor
    # governs the emitted user-facing answer.
    supervision = _supervise_answer(
        answer,
        plan=conv_plan,
        directive=directive,
        cooperation=_supervision_cooperation(cooperation, coop_verdict),
        authority=_supervision_authority(),
    )
    answer = supervision["final"]
    # Phase 7 §6: optional deterministic next-step suggestion, only when the
    # turn completed a cleanly-supervised (PASS) answer that opens a task.
    # One short line, never generated by the prompt, never a model call.
    _hint = _phase7_suggestion_hint(user_text, supervision.get("result"))
    if _hint and answer and answer.strip():
        answer = answer + " " + _hint
    # Keep the local model focused: remove accidental leading/trailing whitespace
    # but preserve its complete sentence structure and safety wording.
    # Batch 8J: live outcome recording (method used + deterministic ok signal).
    # Learns only from the structured fingerprint of the turn.
    if rtj_ctx:
        _adv = rtj_ctx.get("advice") or {}
        _method = _adv.get("method") or "full_standard"
        rtj_ctx["adapter"].observe(
            rtj_ctx["fp"], _method, bool(answer and answer.strip()))
    return answer


SESSION_ID = new_session_id()
history = load_recent(8)

def local_fallback(text):
    """Offline fallback = the single conversation owner + degraded answers.

    All deterministic NL answers come from ``_conversation_route`` (the one
    owner). Degraded-mode capability claims are registry-derived
    (maya_capabilities): this path advertises only groups that genuinely
    work offline, never the model-, network-, or approval-dependent ones.
    """
    lower = text.lower().strip()
    routed = _conversation_route(text, [])
    if routed is not None:
        reply = routed[1]
        if reply == "Hello. I'm Maya.":
            from maya_capabilities import degraded_capability_line
            return reply + " I am online locally. " + degraded_capability_line()
        return reply
    if ("self-evolve" in lower or "self evolve" in lower
            or "improve yourself" in lower):
        from maya_capabilities import offline_improvement_mechanisms
        return offline_improvement_mechanisms()
    return "I need a more focused question to answer that briefly."


# ----------------------------------------------------------------------
# Local-first natural-language conversation routing.
#
# These categories are resolved from authoritative local state BEFORE any
# command handler, the automatic research path, or the model fallback runs.
# They never mutate state, never trigger research, and never expose internal
# machinery (intent objects, confidence values, process state, routing
# traces, or approval internals).
# ----------------------------------------------------------------------

_ARITH_OPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod)


def _norm(text):
    return re.sub(r"[^a-z0-9\s]", "", text.lower()).strip()


def _safe_arithmetic(candidate):
    try:
        tree = ast.parse(candidate.strip(), mode="eval")
    except SyntaxError:
        return None

    def walk(node):
        if type(node) is ast.Expression:
            return walk(node.body)
        if type(node) is ast.Constant and isinstance(node.value, (int, float)):
            return Fraction(str(node.value))
        if type(node) is ast.BinOp and type(node.op) in _ARITH_OPS:
            left = walk(node.left)
            right = walk(node.right)
            if left is None or right is None:
                return None
            if type(node.op) is ast.Add:
                return left + right
            if type(node.op) is ast.Sub:
                return left - right
            if type(node.op) is ast.Mult:
                return left * right
            if type(node.op) is ast.Div:
                return None if right == 0 else left / right
            return None if right == 0 else left % right
        if type(node) is ast.UnaryOp and type(node.op) in (ast.USub, ast.UAdd):
            value = walk(node.operand)
            if value is None:
                return None
            return -value if type(node.op) is ast.USub else value
        return None

    return walk(tree)


def _render_fraction(value):
    if value.denominator == 1:
        return str(value.numerator)
    with localcontext() as ctx:
        ctx.prec = 40
        decimal = Decimal(value.numerator) / Decimal(value.denominator)
        return format(decimal.quantize(Decimal("0.000000000001")).normalize(), "f")


def _math_reply(text):
    low = text.strip().lower().rstrip("?.!;: ")
    diff = re.search(
        r"difference between ([0-9.()+*/%\-]+) and ([0-9.()+*/%\-]+)$", low)
    if diff:
        left = _safe_arithmetic(diff.group(1))
        right = _safe_arithmetic(diff.group(2))
        if left is not None and right is not None:
            result = left - right if left >= right else right - left
            return ("MATHEMATICS",
                    "%s - %s = %s." % (_render_fraction(left),
                                       _render_fraction(right),
                                       _render_fraction(result)))
    candidate = None
    for prefix in ("calculate ", "how much is ", "what is ", "what's ", "whats "):
        if low.startswith(prefix):
            candidate = text[len(prefix):].strip(" \t\r\n?!.,:;")
            break
    if candidate is None:
        candidate = text.strip(" \t\r\n?!.,:;")
    if (not candidate or len(candidate) > 64
            or re.search(r"[a-zA-Z_]", candidate)
            or not re.search(r"\d", candidate)
            or not re.search(r"[-+*/%]", candidate)):
        return None
    try:
        value = _safe_arithmetic(candidate)
    except Exception:
        return None
    if value is None:
        return None
    return ("MATHEMATICS", "%s = %s." % (candidate, _render_fraction(value)))


def _canonical_identity():
    try:
        data = json.loads((ROOT / "maya_identity" / "identity.json").read_text(
            encoding="utf-8"))
        return (data.get("canonical_name") or "Maya",
                data.get("role") or "local personal assistant")
    except Exception:
        return "Maya", "local personal assistant"


_GREETINGS = {"hello", "hi", "hey", "hiya", "howdy", "greetings", "yo", "hai",
              "good morning", "good afternoon", "good evening"}
_GREETINGS_MAYA = {g + " maya" for g in _GREETINGS}
_THANKS = {"thanks", "thank you", "thankyou", "ty", "thx",
           "much appreciated", "thank you maya", "thanks maya"}
_CAPABILITY_PHRASES = {
    "what can you do", "what can u do", "what are your capabilities",
    "what can you help with", "what can you help me with", "what are you able to do",
    "what can maya do", "what do you do", "capabilities",
    "help maya", "hello maya what can you do", "hi maya what can you do"}
_STATE_PHRASES = {
    "are you awake", "are you running", "are you up", "are you online",
    "are you there", "are you here", "are you okay", "are you ok",
    "is maya awake", "is maya running", "what is maya doing", "maya status",
    "what is maya status", "status", "what is your status", "are you working"}
_IDENTITY_NAME_PHRASES = {
    "what is your name", "whats your name", "what s your name",
    "your name", "do you have a name", "is your name maya",
    "what is the name", "what should i call you", "are you maya"}
_IDENTITY_WHO_PHRASES = {
    "who are you", "what are you", "who is maya", "what is maya",
    "tell me about maya", "tell me about yourself", "introduce yourself",
    "what are you exactly", "do you know who you are"}
_IDENTITY_CREATOR_PHRASES = {
    "who made you", "who created you", "who is your creator", "who is your owner",
    "who is your supervisor", "did andy make you", "are you made by andy",
    "who built you", "who designed you"}
_IDENTITY_ROLE_PHRASES = {
    "what is your role", "what is maya s role", "what is maya's role",
    "what is your purpose", "what is your mission", "what is maya s mission",
    "what is maya's mission", "why do you exist"}
_IDENTITY_META_PHRASES = {
    "are you alive", "are you conscious", "are you sentient", "are you human",
    "are you a robot", "are you real", "can you think", "do you have feelings",
    "do you have emotions", "do you feel", "are you self aware", "are you a person"}
_AMBIGUOUS_PHRASES = {
    "what", "tell me", "go on", "continue", "huh", "and", "and then",
    "what about it", "what now", "what is that", "can you", "can you clarify",
    "what did you say", "explain that", "what does that mean", "so", "yes and"}


def _conversation_route(text, history):
    """Single owner of deterministic NL answers (math/identity/state/etc.).

    Every entry point (console loop, ``ask``, ``local_fallback``) resolves
    through here first, so one input yields one answer regardless of which
    surface or engine state produced it. Returns (route, response) for
    conversation categories that must resolve locally and must NOT reach
    command handlers, the automatic research path, or the model. Returns
    None to fall through to the existing path.
    """
    if text.lstrip().startswith(":"):
        return None  # explicit colon commands belong to maya_local_command
    norm = _norm(text)
    if not norm:
        return None
    base = norm.split(" regarding this previous question")[0]

    math_answer = _math_reply(text)
    if math_answer is not None:
        return math_answer

    # Owner identity: the same statement maya_local_command returns, so the
    # owner question never splits into two answers across entry points.
    if (base in {"who is andy", "what is andy to you", "do you know andy"}
            or ("andy" in norm
                and not any(name in norm for name in
                            ("warhol", "burnham", "murray", "williams", "serkis"))
                and any(cue in norm for cue in
                        ("who is", "tell me who", "what do you know about",
                         "do you know")))):
        return ("IDENTITY_OWNER", _CANONICAL_OWNER_SHORT)

    if any(word in norm for word in ("creator", "created you", "my role")):
        return ("IDENTITY_CREATOR", _CANONICAL_OWNER_ADDRESS)
    if any(word in norm for word in ("what programs", "what software",
                                     "what can you help")):
        # Registry-derived so degraded mode can never advertise an
        # unregistered capability (the old hand-written paragraph claimed
        # Presence Mode, which the registry does not).
        from maya_capabilities import capability_summary
        return ("CAPABILITY_PROGRAMS", capability_summary())

    if ("confidence mean" in norm or norm in ("what is confidence",
                                              "explain confidence",
                                              "what is a confidence score",
                                              "what does confidence score mean")):
        return ("ORDINARY_INFORMATION",
                "Confidence is my internal estimate of how reliably I "
                "understood or classified something - a probability-like "
                "score, not certainty. I use it to weigh an interpretation, "
                "never to decide permissions.")

    if norm in _IDENTITY_NAME_PHRASES or norm.startswith("what is your name"):
        return ("IDENTITY", "I'm Maya.")
    if norm == "what is my name":
        return ("IDENTITY",
                "I know you as Andy, my creator and human supervisor.")
    if norm in _IDENTITY_CREATOR_PHRASES:
        return ("IDENTITY", _CANONICAL_OWNER)
    if norm in _IDENTITY_WHO_PHRASES or norm.startswith("do you know who"):
        return ("IDENTITY", _CANONICAL_IDENTITY_ROLE)
    if norm in _IDENTITY_ROLE_PHRASES:
        _, role = _canonical_identity()
        return ("IDENTITY", "My role is: %s." % role)
    if norm in _IDENTITY_META_PHRASES or (norm.startswith("are you ")
                                          and any(w in norm for w in (
                                              "alive", "conscious", "sentient",
                                              "human", "real", "robot"))):
        return ("IDENTITY",
                _CANONICAL_IDENTITY_SOFTWARE)

    if norm in _CAPABILITY_PHRASES:
        from maya_capabilities import capability_summary
        return ("CAPABILITY", capability_summary())

    if norm in ("how are you", "are you okay", "are you ok"):
        return ("STATE", "I'm running well. How can I help you?")
    if norm in _STATE_PHRASES:
        try:
            snap = status_snapshot()
        except Exception:
            snap = {}
        running = snap.get("maya") == "running"
        activation = snap.get("activation") or {}
        presence = activation.get("presence_mode")
        reply = ("Yes - I'm awake and running locally."
                 if running else "I'm here and responding.")
        if presence:
            reply += " Presence Mode is on."
        return ("STATE", reply)

    if norm.startswith(("remember that ", "remember i ", "remember my ",
                        "remember ")):
        return ("MEMORY_LEARNING",
                "Preference and memory changes are approval-controlled, so I "
                "haven't saved that yet. I can prepare it as a proposal for "
                "your approval if you would like.")

    if (norm.startswith("what is happening in ") or
            norm.startswith("what is going on in ") or
            norm in ("what is happening today", "what is going on today",
                     "what is happening right now", "whats happening")):
        return ("WORLD_QUERY",
                "I keep a local picture of the world, but I don't hold live "
                "news, so I can't honestly report current events from here. "
                "If you would like the latest information, I can research it "
                "for you when you explicitly ask.")

    if norm in _THANKS:
        return ("CONVERSATION", "You're welcome.")
    if norm in _GREETINGS or norm in _GREETINGS_MAYA:
        return ("CONVERSATION", "Hello. I'm Maya.")

    if norm == "help":
        return ("HELP",
                "I can help with conversation, math, tasks, status, approved "
                "learning, and read-only research. Try, for example: \"what "
                "can you do?\", \"calculate 25 * 14\", or \"research the "
                "latest information about a topic\". Say \"show detailed "
                "status\" for the full system picture.")

    # Continue-later threads: "continue the mars thread" or "resume thread
    # t003" resolve against paused recap threads. Bare "continue" / "go on"
    # match no phrase and fall through to the ambiguous owner below.
    from maya_recap import continue_reply
    continue_result = continue_reply(text)
    if continue_result is not None:
        return ("THREAD_RESUME", continue_result)

    if base in _AMBIGUOUS_PHRASES:
        if history and any(msg.get("role") == "user" for msg in history):
            return ("AMBIGUOUS",
                    "We're still on the same thread. Could you tell me which "
                    "part you would like me to clarify?")
        return ("AMBIGUOUS",
                "I'd like to help. Could you clarify what you're asking about?")

    return None



# ----------------------------------------------------------------------
# Orchestration layer (Batch: interactive orchestration hardening).
#
# One user message becomes one request with a stable id, an explicit
# lifecycle and exactly one terminal outcome. This path is additive: the
# deterministic router, local commands, fast answers and the model still
# return exactly the text they did before, but they are now reached through
# the state machine and every failure carries a preserved diagnostic reason.
# ----------------------------------------------------------------------

_CHAT_PENDING = None
_CHAT_ORCHESTRATOR = None
_CHAT_EXECUTORS = {}
_LAST_PENDING_JSON = None
_INSTRUMENTATION = {"ref": None, "loaded": False}


def _instrumentation():
    """Lazy, optional access to the read-only performance instrumentation.

    Returns the module when importable, else ``None``. Importing it has no side
    effects and it stays disabled unless ``MAYA_INSTRUMENT`` is set, so the
    default chat path is byte-identical.
    """
    if not _INSTRUMENTATION["loaded"]:
        _INSTRUMENTATION["loaded"] = True
        try:
            import maya_instrumentation as _inst
            _INSTRUMENTATION["ref"] = _inst
        except Exception:
            _INSTRUMENTATION["ref"] = None
    return _INSTRUMENTATION["ref"]


def _pending_store():
    global _CHAT_PENDING
    if _CHAT_PENDING is None:
        import time
        import maya_pending
        _CHAT_PENDING = maya_pending.PendingStore(clock=time.time)
    return _CHAT_PENDING


def _chat_orchestrator():
    global _CHAT_ORCHESTRATOR
    if _CHAT_ORCHESTRATOR is None:
        import time
        import maya_orchestration
        _CHAT_ORCHESTRATOR = maya_orchestration.Orchestrator(
            clock=time.time, pending=_pending_store())
    return _CHAT_ORCHESTRATOR


def _emit_pending_state():
    """Publish the actionable pending set as one machine line (UI only)."""
    global _LAST_PENDING_JSON
    if os.environ.get(_FACE_LINE_ENV) != "1":
        return
    try:
        store = _pending_store()
        payload = {"items": store.surface(), "summary": store.human_summary()}
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if text == _LAST_PENDING_JSON:
            return
        if not payload["items"] and _LAST_PENDING_JSON is None:
            return
        _LAST_PENDING_JSON = text
        sys.stdout.write("[pending] " + text + "\n")
        sys.stdout.flush()
    except Exception:
        pass


def _pending_command(raw_text):
    """Explicit, deterministic resolution of pending validations via chat."""
    store = _pending_store()
    arg = raw_text.strip()[len(":pending"):].strip()
    if not arg or arg.lower() in ("list", "status", "summary"):
        rows = store.surface()
        if not rows:
            return "Nothing needs your approval right now."
        lines = ["Pending approvals:"]
        for row in rows:
            state = "OPEN" if not row["terminal"] else row["status"].upper()
            controls = ", ".join(row["controls"]) or "none"
            lines.append("- [%s] %s: %s (next: %s | controls: %s)"
                         % (state, row["title"], row["required_action"],
                            row["next_step"], controls))
        return "\n".join(lines)

    parts = arg.split()
    verb = parts[0].lower()
    if verb == "help":
        return ("Use :pending, :pending approve <id>, :pending deny <id>, "
                ":pending cancel <id>, :pending retry <id>, or "
                ":pending dismiss <id>.")
    if verb not in ("approve", "deny", "reject", "cancel", "dismiss", "retry"):
        return ("Unknown pending action. Use :pending, :pending approve <id>, "
                ":pending deny <id>, :pending cancel <id>, or "
                ":pending retry <id>.")
    if len(parts) < 2:
        return "Which item? Use :pending %s <id>." % verb

    item_id = parts[1]
    item, changed, note = store.resolve(item_id, verb,
                                        reason="resolved via chat")
    if item is None:
        return "No pending item with id %s." % item_id
    if not changed:
        if str(note).startswith("already_terminal"):
            return "Item %s is already %s." % (item_id, item["status"])
        return "Could not %s item %s (%s)." % (verb, item_id, note)
    _resolve_orchestration_for_pending(item_id, verb)
    _emit_pending_state()
    status = item["status"]
    if status == "approved":
        return "Approved item %s. %s" % (item_id, item.get("next_step") or "")
    if status == "denied":
        return "Denied item %s. Nothing was changed." % item_id
    if status == "cancelled":
        return "Closed item %s. Nothing was changed." % item_id
    if status == "pending":
        return "Item %s is back in the queue." % item_id
    return "Item %s is now %s." % (item_id, status)


def _resolve_orchestration_for_pending(item_id, verb):
    """Resume/close the originating request when its pending item resolves."""
    orchestrator = _chat_orchestrator()
    decision = {"reject": "deny"}.get(verb, verb)
    for request in orchestrator.log.all():
        if request.get("pending_id") == item_id and not request.get("terminal"):
            executor = _CHAT_EXECUTORS.get(request["request_id"])
            updated, note = orchestrator.resolve(request["request_id"],
                                                 decision, execute=executor)
            inst = _instrumentation()
            if inst is not None and inst.is_enabled() and updated:
                try:
                    inst.record("approval_resolution",
                                request_id=updated.get("request_id"),
                                outcome=updated.get("outcome"),
                                meta={"action": decision})
                    inst.trace_request(updated, phase="resolve")
                except Exception:
                    pass
            return


def _orchestration_classify(text, history):
    """Plan one turn without side effects; deterministic answers resolve here.

    The single-owner ordering is preserved: the deterministic router runs
    first, then the local command surface, then fast answers, and only then
    does the turn reach the model.
    """
    route = _conversation_route(text, history)
    if route is not None:
        return {"category": route[0], "kind": "answer", "response": route[1],
                "requires_execution": False}
    local = maya_local_command(text)
    if local is not None:
        return {"category": "command", "kind": "command", "response": local,
                "requires_execution": False}
    quick = fast_answer(text, history)
    if quick is not None:
        return {"category": "quick", "kind": "quick", "response": quick,
                "requires_execution": False}
    return {"category": "answer", "kind": "answer", "requires_execution": True}


def _orchestration_execute(user_text, history, request, attempt):
    """Execute the model step once; failures degrade honestly, never silently."""
    inst = _instrumentation()
    scope = inst.span("response_generation",
                      request_id=request.get("request_id"),
                      stage="executing",
                      meta={"attempt": int(attempt or 0)}) \
        if (inst is not None and inst.is_enabled()) else None
    try:
        if scope is not None:
            with scope:
                answer = ask(history, user_text)
        else:
            answer = ask(history, user_text)
    except Exception as exc:  # noqa: BLE001 - backend unavailable, stay honest
        if scope is not None:
            scope.finish(error=type(exc).__name__)
        return {"status": "unavailable",
                "response": local_fallback(user_text),
                "reason": "%s: %s" % (type(exc).__name__, exc)}
    if not isinstance(answer, str) or not answer.strip():
        return {"status": "error", "reason": "empty_model_answer"}
    return {"status": "ok", "response": answer, "confirmed": True}


def orchestrate_chat_turn(user_text, history, *, session_id=None):
    """Drive one conversational turn through the request lifecycle."""
    orchestrator = _chat_orchestrator()

    def executor(request, context, attempt):
        return _orchestration_execute(user_text, history, request, attempt)

    inst = _instrumentation()
    started = (inst.now() if (inst is not None and inst.is_enabled())
               else None)
    request = orchestrator.submit(
        user_text,
        session_id=(session_id or SESSION_ID),
        history=history,
        classify=lambda text, context: _orchestration_classify(user_text,
                                                               history),
        execute=executor,
    )
    _CHAT_EXECUTORS[request["request_id"]] = executor
    if inst is not None and inst.is_enabled():
        try:
            inst.record("turn_total",
                        request_id=request.get("request_id"),
                        outcome=request.get("outcome"),
                        duration_ms=inst.duration_ms(started, inst.now()),
                        meta={"state": str(request.get("state") or "")})
            inst.trace_request(request, phase="submit")
        except Exception:
            pass
    _emit_pending_state()
    return request


def main():
    print("Maya is ready. Speak normally in English.")
    print("Type 'exit' to leave this conversation. Actions remain confirmation-controlled.")
    while True:
        try:
            sys.stderr.write("\nYou: "); sys.stderr.flush()
            text = input("").strip()
            text = rewrite_follow_up(text, history)
        except (EOFError, KeyboardInterrupt):
            print("\nMaya: Goodbye.")
            break
        if text.lower() in ("exit", "quit", "goodbye"):
            print("\nMaya: Goodbye.")
            break
        if not text:
            continue
        if not text.startswith(":"):
            _emit_face_state("listening")
            cue = classify_opening(text)
            print("[Intent JSON: " + json.dumps(cue, ensure_ascii=False) + "]", file=sys.stderr, flush=True)
        try:
            request = orchestrate_chat_turn(text, history)
            reply = request.get("response") or local_fallback(text)
        except Exception as error:  # noqa: BLE001 - orchestrator must never crash chat
            reply = local_fallback(text)
            print("Detail:", error, file=sys.stderr, flush=True)
        print("Maya: " + reply)
        history.extend([{"role": "user", "content": text},
                        {"role": "assistant", "content": reply}])
        _emit_face_state("idle")
        _persist_exchange(text, reply, SESSION_ID)


if __name__ == "__main__":
    main()

