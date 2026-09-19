"""Final deploy verifier: ``python -m verification``.

Runs Maya's own controlled sweep (recording the external verdict that Maya's
stabilization protocol consumes), then runs every independent external source
of evidence and prints the final verdict. READY is granted only when both the
Maya sweep is clean and the independent sources reach consensus.

If Maya's internal confirmation would say READY but the independent sources
disagree, the verifier revokes the ready state and reports NOT READY -- Maya's
own ``ready=True`` string is never proof by itself.
"""
from __future__ import annotations

import importlib


def main():
    from . import independent
    from maya_identity import stabilization

    sweep_module = importlib.import_module(".sweep", package=__package__)
    battery_python = independent.battery_interpreter()
    print(f"[verify] battery interpreter: {battery_python}")
    maya_ready = sweep_module.main(python=battery_python) == 0
    print()
    print("[verify] independent external-source verification ...")
    consensus_result = independent.run()
    decision = independent.final_verdict(maya_ready, consensus_result)

    print(f"[verify] independent sources: {consensus_result['source_count']}")
    for source in consensus_result["sources"]:
        flag = "OPT" if source.get("optional") else "REQ"
        print(f"  [{flag}] {source['result'].upper():<11} "
              f"{source['source']:<18} {source['identity']}")
        if not source["result"] == "pass" and source["anomalies"]:
            print(f"         -> {source['anomalies'][:3]}")
    print(f"[verify] required sources clean: "
          f"{consensus_result['required_ok']}")
    print(f"[verify] cross-source agreement: "
          f"{consensus_result['cross_agreement']} "
          f"{consensus_result['disagreements'] if consensus_result['disagreements'] else ''}"
          .rstrip())
    print(f"[verify] independent consensus: {consensus_result['consensus']}")
    print(f"[verify] final verdict: {decision['verdict']}")
    if decision["message"]:
        print(f"[verify] {decision['message']}")

    if decision["verdict"] != "READY" and maya_ready:
        stabilization.reset()
        print("[verify] ready state revoked pending independent agreement "
              f"(runtime ready_now={stabilization.is_ready()})")
    return 0 if decision["verdict"] == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())