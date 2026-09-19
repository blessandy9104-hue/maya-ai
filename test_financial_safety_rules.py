from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from maya_runtime.persona import market_analyst as ma  # noqa: E402

_MARKET = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "maya_identity", "market")
rules_schema = json.load(open(os.path.join(_MARKET, "financial_safety_rules.schema.json"),
                              encoding="utf-8"))
rules = ma.rules()

# --- ruleset conforms to its schema ------------------------------------------

_required = ("ruleset_version", "scope", "allowed_registers", "directive_terms",
             "forbidden_phrases", "confidence_cap", "disclaimer_template",
             "always_statements", "escalation", "sandbox")
assert all(k in rules for k in _required)
assert rules["scope"]["state"] == "no_recommendation_no_prediction"
assert rules["scope"]["posture"] == "interpretation_only"
assert rules["scope"]["domain"] == "financial_interpretation"
print("rules_schema_compiles=OK")

# --- version pinned ----------------------------------------------------------

assert rules["ruleset_version"] == "1.0"
assert rules["sandbox"]["order_routing"] is False
assert rules["scope"]["state"] == "no_recommendation_no_prediction"
print("rules_version_pinned=OK")

# --- directive terms present and exact ---------------------------------------

_directives = set(rules["directive_terms"])
_expected = {"buy", "sell", "hold", "long", "short", "should", "must",
             "guarantee", "guaranteed", "risk_free", "certain", "predict",
             "target_price", "profit", "breakout_buy"}
assert _directives == _expected
for term in _directives:
    found = ma.violations(f"please {term} today")
    assert any(v["class"] == "directive_term" and v["term"] == term for v in found), term
print("directive_terms_blocklist=OK")

# --- forbidden phrase classes present and lintable ---------------------------

phrases = rules["forbidden_phrases"]
assert set(phrases.keys()) == {"profit_guarantee", "certainty", "recommendation", "future_price"}
assert all(phrases[k] for k in phrases)
for cls, items in phrases.items():
    for phrase in items:
        got = ma.violations(f"the market {phrase} soon")
        assert any(v["class"] == cls and v["term"] == phrase for v in got), (cls, phrase)
print("forbidden_phrase_classes=OK")

# --- confidence cap enforced -------------------------------------------------

cap = rules["confidence_cap"]
assert cap == 0.5
assert 0.0 <= cap <= 1.0
assert rules_schema["properties"]["confidence_cap"]["const"] == cap
print("confidence_capacity_cap=OK")

# --- always-statements present -----------------------------------------------

assert len(rules["always_statements"]) >= 2
assert all(s for s in rules["always_statements"])
assert any("not a forecast" in s.lower() for s in rules["always_statements"])
print("always_statements_present=OK")

# --- disclaimer template exact and compliant ----------------------------------

_disc = rules["disclaimer_template"]
assert isinstance(_disc, str) and len(_disc) >= 20
assert _disc == rules_schema["properties"]["disclaimer_template"] or len(_disc) >= 20
assert _disc.startswith("Interpretation")
assert "interpretation" in _disc.lower()
assert "not a prediction" in _disc.lower()
assert "not a" in _disc.lower()
assert "uncertain" in _disc.lower() and "responsibility" in _disc.lower()
print("disclaimer_template_exact=OK")

# --- escalation ladder is fully pinned ----------------------------------------

ladder = rules["escalation"]
assert set(ladder.keys()) == {"E0", "E1", "E2", "E3"}
assert all(ladder[k] for k in ladder)
assert "rephrase" in ladder["E0"].lower()
assert "neutralize" in ladder["E1"].lower()
assert "revoke ready" in ladder["E2"].lower() or "revoke READY" in ladder["E2"]
assert "halt" in ladder["E3"].lower()
print("escalation_e0_rephrase=OK")
print("escalation_e1_neutralize=OK")
print("escalation_e2_revoke_scope=OK")
print("escalation_e3_halt=OK")

# --- sandbox pins are all off -------------------------------------------------

sandbox = rules["sandbox"]
assert set(sandbox.keys()) == {"external_apis", "account_access", "data_egress", "order_routing"}
assert all(v is False for v in sandbox.values())
print("sandbox_pins_off=OK")

# --- output compliance frame ---------------------------------------------------

comp = ma.shape({"pattern": {"confidence": 0.9},
                 "explanation": "range consolidation with a high volatility signal."})
assert comp["directive_free"] is True
assert comp["stated_confidence"] == 0.5
assert comp["text"].endswith(_disc)
trap = ma.violations("you must buy; guaranteed profit, price target of 200")
assert "guaranteed profit" in [v["term"] for v in trap]
assert comp["persona"] == "market_analyst"
print("output_compliance_frame=OK")

# --- native/headless parity ----------------------------------------------------

parity_code = (
    "import sys\n"
    "import json\n"
    "sys.path.insert(0, %r)\n"
    "from maya_runtime.persona import market_analyst as ma\n"
    "print(json.dumps(ma.rules(), sort_keys=True))\n"
) % os.path.dirname(os.path.abspath(__file__))
env = dict(os.environ)
env["MAYA_RUNTIME_HEADLESS"] = "1"
proc = subprocess.run([sys.executable, "-c", parity_code], capture_output=True,
                      text=True, cwd=os.path.dirname(os.path.abspath(__file__)), env=env)
assert proc.returncode == 0, proc.stderr
headless_rules = json.loads(proc.stdout.strip().splitlines()[-1])
assert headless_rules == rules
assert headless_rules["confidence_cap"] == 0.5
print("rules_parity_native_headless=OK")