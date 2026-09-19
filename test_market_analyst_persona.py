from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from maya_runtime.isolation import (  # noqa: E402
    CHANNEL_MAX,
    PERSONA_CEILINGS,
    SURFACE_WHITELIST,
    PersonaSeal,
)
from maya_runtime.isolation.router import BOUNDARY_TABLE  # noqa: E402
from maya_runtime.persona import market_analyst as ma  # noqa: E402

_MARKET = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "maya_identity", "market")

persona_schema = json.load(open(os.path.join(_MARKET, "market_analyst_persona.schema.json"),
                                encoding="utf-8"))

# --- persona profile conforms to its schema ----------------------------------

_p = ma.profile()
_required = ("schema_kind", "persona_id", "role", "display_name", "tone_profile",
             "channel_ceiling", "cadence", "vocabulary", "expression_rules",
             "hard_rules", "reminder", "stateless", "integration")
assert all(k in _p for k in _required)
assert _p["schema_kind"] == persona_schema["properties"]["schema_kind"]["const"]
assert _p["persona_id"] == "market_analyst"
assert _p["tone_profile"]["default_register"] == "even"
assert _p["tone_profile"]["banned_registers"] == ["lively", "playful"]
assert _p["stateless"] is True
print("persona_schema_compiles=OK")

# --- ceilings lie within CHANNEL_MAX -----------------------------------------

for channel, cap in _p["channel_ceiling"].items():
    assert 0.0 <= cap <= CHANNEL_MAX[channel], channel
assert _p["channel_ceiling"]["expression"] <= 0.5
print("persona_ceiling_within_channel_max=OK")

# --- runtime ceilings match the persona profile ------------------------------

runtime_ceiling = PERSONA_CEILINGS.get("market_analyst") or {}
assert runtime_ceiling["expression"] == _p["channel_ceiling"]["expression"]
assert runtime_ceiling["viseme"] == _p["channel_ceiling"]["viseme"]
assert runtime_ceiling["micro"] == _p["channel_ceiling"]["micro"]
assert ma.ceiling() == runtime_ceiling
print("persona_ceiling_matches_runtime=OK")

# --- allowed registers are all legal and present -----------------------------

allowed = set(_p["tone_profile"]["allowed_registers"])
assert allowed <= {"even", "technical", "warm"}
banned = set(_p["tone_profile"]["banned_registers"])
assert banned <= {"lively", "playful"}
assert not (allowed & banned)
for register in allowed:
    out = ma.shape({"pattern": {"confidence": 0.3}}, register=register)
    assert out["register"] == register
print("persona_registers_allowed=OK")

# --- closed vocabulary: interpretation terms only, no directives -------------

interpretation_terms = set(_p["vocabulary"]["interpretation_terms"])
assert interpretation_terms <= {
    "interpretation", "pattern", "range", "consolidation", "volatility",
    "trend", "momentum", "uncertainty", "risk", "context", "historical",
    "resemblance", "structure", "signal",
}
banned_terms = set(_p["vocabulary"]["banned_directive_terms"])
assert banned_terms <= {"buy", "sell", "hold", "long", "short", "should",
                        "guarantee", "predict"}
assert not (interpretation_terms & banned_terms)
print("persona_closed_vocabulary=OK")

# --- hard rules present, MP01..MP10 ------------------------------------------

rules = _p["hard_rules"]
assert len(rules) == 10
assert all(r["id"] == f"MP{i:02d}" for i, r in zip(range(1, 11), rules))
assert all(r["rule"] for r in rules)
print("persona_hard_rules=OK")

# --- persona bans are a subset of the safety blocklist -----------------------

_rs = ma.rules()
assert banned_terms <= set(_rs["directive_terms"]), banned_terms - set(_rs["directive_terms"])
assert set(_rs["allowed_registers"]) == {"even", "technical", "warm"}
print("persona_rule_subset_of_blocklist=OK")

# --- stateless shaping -------------------------------------------------------

mpm_obj = {"pattern": {"confidence": 0.8},
           "explanation": "breakout structure with an overextension risk flag."}
s1 = ma.shape(mpm_obj)
s2 = ma.shape(mpm_obj)
assert s1 == s2
assert ma.profile() == ma.profile()
print("persona_stateless=OK")

# --- shape output has a closed key set ---------------------------------------

assert set(s1.keys()) == {"persona", "register", "directive_free",
                          "stated_confidence", "disclaimer", "text"}
assert s1["persona"] == "market_analyst"
assert s1["register"] == "even"
assert s1["stated_confidence"] == 0.5  # capped at the safety limit
print("persona_shape_closed_set=OK")

# --- shape uses the allowed register domain ----------------------------------

assert s1["text"].startswith("breakout structure")
assert s1["disclaimer"] == _rs["disclaimer_template"]
assert ma.shape(mpm_obj, register="warm")["register"] == "warm"
try:
    ma.shape(mpm_obj, register="playful")
    raise SystemExit("playful register must be rejected")
except ValueError:
    pass
print("persona_shape_register=OK")

# --- sealing available and tenant-scoped -------------------------------------

seal = ma.seal("tenant-beta")
assert isinstance(seal, PersonaSeal)
assert seal.persona_id == "market_analyst"
assert seal.verify()["tenant_scoped"] is True
assert seal.verify()["cross_tenant_denied"] is True
assert seal.can_access("tenant-beta") is True
assert seal.can_access("other") is False
print("persona_seal_available=OK")

# --- escalation ladder E0..E3 ------------------------------------------------

assert ma.escalate("E0")["verdict"] == "rephrase"
assert ma.escalate("E1")["verdict"] == "neutralize"
assert ma.escalate("E2")["verdict"] == "revoke_ready"
assert ma.escalate("E3")["verdict"] == "halt"
assert ma.escalate(None, {"violation_count": 0})["verdict"] == "pass"
assert ma.escalate(None, {"violation_count": 2})["esc_level"] == "E0"
assert ma.escalate(None, {"violation_count": 5})["esc_level"] == "E1"
assert ma.escalate(None, {"violation_count": 9})["esc_level"] == "E2"
assert ma.escalate(None, {"violation_count": 50})["esc_level"] == "E3"
assert ma.escalate("E2", {"trap_limit_exceeded": True})["verdict"] == "revoke_ready"
for s in ("E0", "E1", "E2", "E3"):
    assert ma.escalate(s, {"violation_count": 0}) == ma.escalate(s, {"violation_count": 0})
print("persona_escalation_ladder=OK")

# --- shaped explanation is neutral and carries the disclaimer ----------------

dirty = ma.violations("you should buy now")
assert dirty, "directive text must surface violations"
assert all(v["severity"] in ("medium", "high") for v in dirty)
clean = ma.violations("range consolidation with medium volatility")
assert clean == []
_body = s1["text"][:-len(s1["disclaimer"])].strip()
assert ma.violations(_body) == []
assert "not a prediction" in _rs["disclaimer_template"].lower()
assert "predict" not in _body.lower()
for banned in ("buy", "sell", "hold", "should"):
    assert banned not in _body.lower(), banned
print("persona_explanation_shaped=OK")

# --- native/headless parity --------------------------------------------------

parity_code = (
    "import sys\n"
    "import json\n"
    "sys.path.insert(0, %r)\n"
    "from maya_runtime.persona import market_analyst as ma\n"
    "o = ma.shape({'pattern': {'confidence': 0.8}, 'explanation': "
    "'breakout structure with an overextension risk flag.'})\n"
    "print(json.dumps({'profile': ma.profile(), 'shape': o}, sort_keys=True))\n"
) % os.path.dirname(os.path.abspath(__file__))
env = dict(os.environ)
env["MAYA_RUNTIME_HEADLESS"] = "1"
proc = subprocess.run([sys.executable, "-c", parity_code], capture_output=True,
                      text=True, cwd=os.path.dirname(os.path.abspath(__file__)), env=env)
assert proc.returncode == 0, proc.stderr
headless = json.loads(proc.stdout.strip().splitlines()[-1])
assert headless["profile"]["persona_id"] == "market_analyst"
assert headless["shape"]["text"] == s1["text"]
assert headless["shape"]["stated_confidence"] == s1["stated_confidence"]
print("persona_parity=OK")