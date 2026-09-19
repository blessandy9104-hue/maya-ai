"""Independent external-source verification for Maya's readiness decision.

The deploy verifier never trusts one Python runner as the sole source of
truth. This module runs the same verification targets through genuinely
independent observers and requires cross-source agreement before READY may
be printed:

- every usable Python interpreter on the machine runs a deterministic subset
- Windows PowerShell and cmd.exe observe process exit codes, stdout
  presence, ``=OK`` evidence, generated reports and Git working-tree state
  from outside Maya (an observation is never another source's echo)
- a stdlib-only static pass inspects manifest registration, suite presence,
  referenced files, forbidden imports in the protected intelligence scope,
  syntax validity, JSON validity and Git-tracked runtime state without
  importing the runtime
- an external oracle recomputes the launch math from first principles with
  no import of Maya's implementation

Every source records identity, executable/version, command, timestamp, exit
code, observed evidence, anomalies and result. Sources that cannot provide
evidence are recorded as ``unavailable`` and never count as success;
disagreement between required sources, or a missing required source, fails
closed.
"""
from __future__ import annotations

import ast
import datetime as _datetime
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
AUDIT_LOG = PROJECT_ROOT / "maya_identity" / "metadata" / "independent_verification.jsonl"

# Mirrors the internal readiness policy: only the intelligence package is
# protected from nondeterministic/runtime imports (the runtime itself uses
# `time`/`datetime` legitimately elsewhere).
PROTECTED_INTELLIGENCE_DIR = "maya_runtime/intelligence"
FORBIDDEN_IMPORTS = ("random", "time", "datetime", "tkinter", "subprocess",
                     "socket")

# Machine-independent signature: [pattern_state, cosine, stability_std, channel_count]
#   * pattern_state(0.0, 1.0, 0.5) = one exponential-smoothing blend step
#   * cosine_similarity((1,0),(1,0)) = normalized dot product
#   * world_stability([1,1,1,1]) = standard deviation of a constant series
#   * len(CHANNEL_MAX) = declared ceiling count (self-referential, documented)
EXPECTED_SIGNATURES = (0.5, 1.0, 0.0, 4)
EXPECTED_ORACLE_TRIPLE = (0.5, 1.0, 0.0)

# The deterministic subset run by every independent interpreter/shell arm.
# Light enough to repeat across interpreters while carrying contracted
# ``=OK`` evidence (test_readiness.py = 10).
INTERPRETER_SUBSET = ("test_readiness.py",)

# Probe that imports the runtime and prints the signature as JSON. The path is
# enclosed in double quotes so the string is safe to embed in PowerShell
# single-quoted arguments as well as interpreter ``-c`` invocation.
SIGNATURE_CODE = (
    "import json; import sys; "
    "sys.path.insert(0, r\"{root}\"); "
    "import maya_runtime as rt; "
    "a = rt.MATH_AGENT; "
    "sig = ["
    "round(a.pattern_state(0.0, 1.0, 0.5), 15), "
    "round(rt.core.cosine_similarity((1.0, 0.0), (1.0, 0.0)), 15), "
    "round(a.world_stability([1.0, 1.0, 1.0, 1.0], max_std=0.05)['std'], 15), "
    "len(rt.core.CHANNEL_MAX)"
    "]; "
    "print(json.dumps(sig))"
).format(root=PROJECT_ROOT)

# External oracle: recomputed from the mathematical definitions with no Maya
# import, printed as JSON.
ORACLE_CODE = (
    "import json; import math; from decimal import Decimal; "
    "blend = float(Decimal('0.0') + (Decimal('1.0') - Decimal('0.0')) * Decimal('0.5')); "
    "na = math.sqrt(1.0 ** 2 + 0.0 ** 2); "
    "nb = math.sqrt(1.0 ** 2 + 0.0 ** 2); "
    "cosine = (1.0 * 1.0 + 0.0 * 0.0) / (na * nb); "
    "series = [1.0, 1.0, 1.0, 1.0]; "
    "mean = sum(series) / len(series); "
    "var = sum((v - mean) ** 2 for v in series) / len(series); "
    "sd = math.sqrt(var); "
    "print(json.dumps([round(blend, 15), round(cosine, 15), round(sd, 15)]))"
)


def _iso_now():
    return _datetime.datetime.now(_datetime.timezone.utc).isoformat()


def _run(argv, cwd=None, timeout_ms=300000, input_text=None):
    """Run one captured subprocess; never raises on timeout."""
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            cwd=str(cwd or PROJECT_ROOT),
            timeout=max(timeout_ms / 1000.0, 1.0),
            input=input_text,
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "duration_s": round(time.perf_counter() - start, 3),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired:
        return {
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "duration_s": round(time.perf_counter() - start, 3),
            "timed_out": True,
        }


def _base_source(source, identity, tool_version, command):
    return {
        "source": source,
        "identity": identity,
        "tool_version": tool_version,
        "command": command,
        "at": _iso_now(),
        "exit_code": None,
        "observed": {},
        "anomalies": [],
        "result": "pending",
    }


def _finalize_source(base, exit_code, observed, anomalies, optional=False):
    base["exit_code"] = exit_code
    base["observed"] = observed
    base["anomalies"] = anomalies
    base["optional"] = bool(optional)
    base["result"] = ("pass" if not anomalies else "fail")
    return base


# ---------------------------------------------------------------------------
# 1. Interpreter detection and per-interpreter arms
# ---------------------------------------------------------------------------

def _candidate_exes():
    candidates = [sys.executable]
    for token in os.environ.get("PATH", "").split(os.pathsep):
        if not token:
            continue
        for name in ("python.exe", "python3.exe", "py.exe"):
            candidate = pathlib.Path(token) / name
            if candidate.is_file():
                candidates.append(str(candidate))
    extra = (
        r"C:\Program Files\Python313\python.exe",
        r"C:\Program Files\Python314\python.exe",
        r"C:\Program Files\Python312\python.exe",
        r"C:\Users\USER\AppData\Local\Programs\Python\Python313\python.exe",
        r"C:\Users\USER\AppData\Local\Programs\Python\Python314\python.exe",
        r"C:\Users\USER\AppData\Local\Python\pythoncore-3.14-64\python.exe",
    )
    for candidate in extra:
        if pathlib.Path(candidate).is_file():
            candidates.append(candidate)
    return candidates


def resolve_python_interpreters():
    """Every interpreter that can run the verification subset, deduplicated.

    Deduplication keys on the interpreter *actually launched* (``sys.executable``
    as reported by the probe), so ``py.exe`` and Windows app-execution aliases
    collapse onto the underlying interpreter they run.
    """
    found = {}
    for candidate in _candidate_exes():
        probe = _run([candidate, "--version"])
        if probe["returncode"] != 0:
            continue
        version = ".".join(probe["stdout"].strip().split()[-1:]) or "unknown"
        canary = _run([candidate, "-c",
                       "import sys; sys.path.insert(0, r\"{0}\"); "
                       "import maya_runtime; print('ok'); "
                       "print('EXE:', sys.executable)".format(PROJECT_ROOT)])
        usable = canary["returncode"] == 0 and "ok" in canary["stdout"]
        launched = None
        for line in canary["stdout"].splitlines():
            if line.startswith("EXE: "):
                launched = line[len("EXE: "):].strip()
        exe = launched or candidate
        real = os.path.realpath(exe)
        if real in found:
            continue
        found[real] = {
            "exe": exe,
            "realpath": real,
            "version": version,
            "usable": usable,
            "primary": real == os.path.realpath(sys.executable),
        }
    return sorted(found.values(), key=lambda item: (not item["primary"],
                                                    item["version"]))


def battery_interpreter():
    """The most capable interpreter for the full sweep battery.

    The battery's canonical suite requires PIL (the visual-validation
    dependency manifests expect it). Choose the first detected interpreter
    that satisfies the runtime *and* PIL; fall back to this process's
    interpreter when none is certified.
    """
    for info in resolve_python_interpreters():
        probe = _run([info["exe"], "-c", "import PIL; print('pil ok')"])
        if probe["returncode"] == 0:
            return info["exe"]
    return sys.executable


def interpreter_arm(info, suites=INTERPRETER_SUBSET, root=None):
    root = pathlib.Path(root or PROJECT_ROOT)
    from .manifest import SUITE_CONTRACTS  # local import: static-free manifest

    command = [[info["exe"], "--version"]]
    observed = {"interpreter_exe": info["exe"],
                "interpreter_version": info["version"]}
    anomalies = []
    suite_results = {}
    for suite in suites:
        args = [info["exe"], str(root / suite)]
        command.append(args)
        result = _run(args, cwd=root)
        observed_res = {"returncode": result["returncode"],
                        "ok_labels": 0,
                        "duration_s": result["duration_s"]}
        ok_labels = sum(1 for line in result["stdout"].splitlines()
                        if line.strip().endswith("=OK"))
        observed_res["ok_labels"] = ok_labels
        suite_results[suite] = observed_res
        expected = SUITE_CONTRACTS.get(suite, {}).get("expected_ok")
        if result["returncode"] != 0:
            anomalies.append(f"{suite}: interpreter exited "
                             f"{result['returncode']}")
        if expected is not None and ok_labels != expected:
            anomalies.append(
                f"{suite}: ok evidence {ok_labels} != contracted {expected}")
        if result["returncode"] != 0 and "Traceback" in result["stderr"]:
            anomalies.append(f"{suite}: traceback in stderr")
    observed["suite_results"] = suite_results

    sig_args = [info["exe"], "-c", SIGNATURE_CODE]
    command.append(sig_args)
    sig_run = _run(sig_args, cwd=root)
    signatures = None
    if sig_run["returncode"] == 0 and sig_run["stdout"].strip():
        try:
            signatures = tuple(json.loads(
                sig_run["stdout"].strip().splitlines()[-1]))
        except (ValueError, TypeError):
            anomalies.append(f"signature unparsable: {sig_run['stdout']!r}")
    else:
        anomalies.append(f"signature process failed ({sig_run['stderr'][:200]!r})")
    observed["signatures"] = signatures
    if sig_run["timed_out"]:
        anomalies.append("signature process timed out")

    oracle_args = [info["exe"], "-c", ORACLE_CODE]
    command.append(oracle_args)
    oracle_run = _run(oracle_args, cwd=root)
    oracle = None
    if oracle_run["returncode"] == 0 and oracle_run["stdout"].strip():
        try:
            oracle = tuple(json.loads(
                oracle_run["stdout"].strip().splitlines()[-1]))
        except (ValueError, TypeError):
            anomalies.append(f"oracle unparsable: {oracle_run['stdout']!r}")
    else:
        anomalies.append("oracle process failed")
    observed["oracle"] = oracle

    if signatures is not None and not _sig_consistent(signatures, oracle):
        anomalies.append(_sig_inconsistency_detail(signatures, oracle))

    base = _base_source("python-interpreter",
                        f"Python {info['version']} @ {info['exe']}",
                        info["version"], command)
    return _finalize_source(base, sig_run["returncode"], observed, anomalies)


def _sig_consistent(signatures, oracle):
    sig_ok = (isinstance(signatures, tuple)
              and len(signatures) == 4
              and list(signatures) == list(EXPECTED_SIGNATURES))
    oracle_ok = oracle is None or list(oracle) == list(EXPECTED_ORACLE_TRIPLE)
    agree = oracle is None or list(signatures[:3]) == list(oracle)
    return bool(sig_ok and oracle_ok and agree)


def _sig_inconsistency_detail(signatures, oracle):
    return (f"signature/oracle inconsistency: runtime={signatures} "
            f"oracle={oracle} expected={EXPECTED_SIGNATURES}")


# ---------------------------------------------------------------------------
# 2. Shell-level independence (PowerShell, then cmd)
# ---------------------------------------------------------------------------

_POWERSHELL_SCRIPT = r"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Continue"
$root = "ROOT"
$facts = @{}
$py = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
if (-not $py) {
    $facts.python = "missing"
} else {
    $facts.python = $py
    $sigOut = Join-Path $env:TEMP ("ps_sig_" + [guid]::NewGuid().ToString("N") + ".out")
    & $py -c 'SIGNATURE_CODE' *> $sigOut
    $facts.sig_exit = $LASTEXITCODE
    $facts.sig_line = (Get-Content $sigOut -Raw).Trim()
    Remove-Item $sigOut -ErrorAction SilentlyContinue

    $suiteOut = Join-Path $env:TEMP ("ps_suite_" + [guid]::NewGuid().ToString("N") + ".out")
    & $py "$root\test_readiness.py" *> $suiteOut
    $facts.suite_exit = $LASTEXITCODE
    $lines = @(Get-Content $suiteOut)
    $facts.stdout_present = ($lines.Count -gt 0)
    $ok = @($lines | Where-Object { $_ -match "=OK$" })
    $facts.ok_count = $ok.Count
    Remove-Item $suiteOut -ErrorAction SilentlyContinue
}
$report = Join-Path $root "maya_identity\metadata\verification.jsonl"
if (Test-Path $report) {
    $facts.report_exists = $true
    $last = (Get-Content $report -Tail 1) | ConvertFrom-Json
    $facts.report_last_kind = $last.kind
} else {
    $facts.report_exists = $false
    $facts.report_last_kind = "none"
}
$git = (Get-Command git.exe -ErrorAction SilentlyContinue).Source
$facts.git = $git
if ($git) {
    $st = @(& $git -C $root status --porcelain --untracked-files=all 2>&1)
    $facts.git_porcelain_lines = $st.Count
    $facts.git_metadata_listed = (@($st | Where-Object {
        $_ -match "maya_identity\\metadata" }).Count -gt 0)
} else {
    $facts.git_porcelain_lines = -1
    $facts.git_metadata_listed = $true
}
$facts | ConvertTo-Json -Compress
"""


def powershell_arm(root=None):
    root = pathlib.Path(root or PROJECT_ROOT)
    powershell = shutil.which("powershell.exe") or (
        r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
    script = (_POWERSHELL_SCRIPT
              .replace("ROOT", str(root).replace("\\", "/"))
              .replace("SIGNATURE_CODE", SIGNATURE_CODE))
    command = [powershell, "-NoProfile", "-NonInteractive",
               "-ExecutionPolicy", "Bypass", "-Command", "-"]
    base = _base_source("powershell", f"Windows PowerShell @ {powershell}",
                        "5.1", command)
    if not pathlib.Path(powershell).exists():
        return _unavailable(base, "powershell.exe not present")
    result = _run(command, cwd=root, input_text=script)
    anomalies = []
    if result["returncode"] != 0:
        anomalies.append(f"powershell exited {result['returncode']}: "
                         f"{result['stderr'][:300]!r}")
    observed = {}
    if result["stdout"].strip():
        try:
            observed = json.loads(result["stdout"].strip().splitlines()[-1])
        except (ValueError, TypeError):
            anomalies.append(f"powershell JSON unparsable: "
                             f"{result['stdout'][:300]!r}")
    if observed.get("python") == "missing":
        anomalies.append("no python.exe on PATH for the shell arm")
    if observed.get("suite_exit") not in (None, 0):
        anomalies.append(f"shell observed nonzero suite exit "
                         f"{observed.get('suite_exit')}")
    return _finalize_source(base, result["returncode"], observed, anomalies)


def cmd_arm(root=None, keep=False):
    """Optional cmd.exe observer. Provides its own exit/count observations."""
    root = pathlib.Path(root or PROJECT_ROOT)
    cmd = shutil.which("cmd.exe") or os.path.join(
        os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe")
    base = _base_source("cmd", f"Windows Command Prompt @ {cmd}", "cmd.exe",
                        [cmd, "/d", "/q", "/c", "<probe batch>"])
    if not pathlib.Path(cmd).exists():
        return _unavailable(base, "cmd.exe not present")
    probe = (SIGNATURE_CODE + "\n")
    with _TempDir(prefix="cmd_arm_") as scratch:
        probe_path = scratch.path / "sig_probe.py"
        probe_path.write_text(probe, encoding="utf-8")
        batch = scratch.path / "arm.cmd"
        batch.write_text(_CMD_BATCH.format(root=root, probe=probe_path),
                         encoding="utf-8")
        result = _run([cmd, "/d", "/q", "/c", str(batch)], cwd=root)
    anomalies = []
    observed = {}
    if result["returncode"] != 0:
        anomalies.append(f"cmd exited {result['returncode']}")
    for line in result["stdout"].splitlines():
        line = line.strip()
        if line.startswith("CMDARM "):
            try:
                _kv = dict(part.split("=", 1) for part in
                           line[len("CMDARM "):].split())
                observed = {k: (int(v) if v.lstrip("-").isdigit() else v)
                            for k, v in _kv.items()}
            except ValueError:
                anomalies.append(f"cmd ARM line unparsable: {line!r}")
    if not observed:
        anomalies.append("cmd arm produced no CMDARM observations")
    if str(observed.get("sig_exit")) not in ("0", "None"):
        anomalies.append(f"cmd signature probe failed (exit "
                         f"{observed.get('sig_exit')})")
    return _finalize_source(base, observed.get("suite_exit"), observed,
                            anomalies, optional=True)


_CMD_BATCH = """\
@echo off
setlocal
set "PY=python"
set "ROOT={root}"
set "PROBE={probe}"
set "TMPOUT=%TEMP%\\cmda_sig.out"
"%PY%" "%PROBE%" > "%TMPOUT%" 2>&1
set SIGEXIT=%ERRORLEVEL%
"%PY%" "%ROOT%\\test_readiness.py" > "%TEMP%\\cmda_suite.out" 2>&1
set SUITEEXIT=%ERRORLEVEL%
set /a OKCOUNT=0
for /f "delims=" %%i in ('findstr /c:"=OK" "%TEMP%\\cmda_suite.out" ^| find /c "=OK"') do set OKCOUNT=%%i
echo CMDARM sig_exit=%SIGEXIT% suite_exit=%SUITEEXIT% ok_count=%OKCOUNT%
endlocal
"""


class _TempDir:
    def __init__(self, prefix="tmp_"):
        import tempfile as _tempfile
        self.path = pathlib.Path(_tempfile.mkdtemp(prefix=prefix))

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        import shutil as _shutil
        _shutil.rmtree(self.path, ignore_errors=True)


# ---------------------------------------------------------------------------
# 3. Static verification (no runtime import)
# ---------------------------------------------------------------------------

def _read_text(path):
    """Read a file, tolerating UTF-8 BOM and UTF-16 documents (which exist in
    the repo's generated benchmark outputs) without misreporting them.""" 
    data = pathlib.Path(path).read_bytes()
    for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "utf-16-be"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    raise UnicodeDecodeError("utf-8", data, 0, 1, "no supported encoding")


def scan_forbidden_imports(paths):
    """AST scan of a list of files for forbidden top-level imports.

    Returns ``(ok, reports)``; reports are one-line descriptions of each
    offending import. Pure static: no module is imported or executed.
    """
    reports = []
    for path in paths:
        try:
            tree = ast.parse(_read_text(path))
        except (OSError, SyntaxError) as exc:
            reports.append(f"{path}: unparsable ({exc!r})")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                roots = [node.module.split(".")[0]] if node.module else []
            else:
                continue
            for root in roots:
                if root in FORBIDDEN_IMPORTS:
                    reports.append(f"{path}: line {node.lineno} imports {root}")
    return not reports, reports


def static_checks(root=None):
    root = pathlib.Path(root or PROJECT_ROOT)
    checks = {}

    # manifest registration
    manifest_path = root / "verification" / "manifest.py"
    suites = contracts = controlled = ()
    try:
        tree = ast.parse(manifest_path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id == "SUITES":
                    suites = ast.literal_eval(node.value)
                elif target.id == "SUITE_CONTRACTS":
                    contracts = ast.literal_eval(node.value)
                elif target.id == "CONTROLLED_RUNTIME":
                    controlled = ast.literal_eval(node.value)
        aligned = (isinstance(suites, (tuple, list)) and bool(suites)
                   and isinstance(contracts, dict)
                   and all(name in contracts for name in suites)
                   and isinstance(controlled, dict))
        checks["manifest_registration"] = _check(
            aligned, f"SUITES/SUITE_CONTRACTS/CONTROLLED_RUNTIME aligned "
                     f"({len(suites)} suites, {len(contracts)} contracts)")
    except Exception as exc:
        checks["manifest_registration"] = _check(False, f"unparsable: {exc!r}")

    # suite presence
    missing = [name for name in suites if not (root / name).exists()]
    checks["suite_presence"] = _check(
        not missing, "all registered suites exist"
        if not missing else f"missing: {missing}")

    # referenced runtime files
    module = (controlled or {}).get("module")
    runtime_present = bool(module) and (root / module / "__init__.py").is_file()
    checks["runtime_module_present"] = _check(
        runtime_present, f"{module}.__init__ exists")

    # forbidden imports in the protected intelligence scope
    intel_dir = root / PROTECTED_INTELLIGENCE_DIR
    intel_files = sorted(intel_dir.glob("*.py")) if intel_dir.is_dir() else []
    ok, reports = scan_forbidden_imports(intel_files)
    checks["forbidden_imports"] = _check(
        ok, "intelligence free of forbidden imports"
        if ok else reports[:5])

    # syntax validity
    bad_syntax = []
    for py_file in _iter_project_py(root):
        try:
            compile(_read_text(py_file), str(py_file), "exec")
        except SyntaxError as exc:
            bad_syntax.append(f"{py_file.name}:{exc.lineno}")
    checks["syntax_validity"] = _check(
        not bad_syntax, "all project Python compiles"
        if not bad_syntax else bad_syntax[:5])

    # json validity (sanctioned configuration layer; generated benchmark and
    # browser-profile outputs are data artifacts, not configuration)
    bad_json = []
    for json_file in sorted((root / "maya_identity").rglob("*.json")):
        try:
            json.loads(_read_text(json_file))
        except (OSError, ValueError) as exc:
            bad_json.append(f"{json_file.relative_to(root)}: {exc!r}")
    checks["json_validity"] = _check(
        not bad_json, "all configuration JSON parses"
        if not bad_json else bad_json[:5])

    return checks


def _iter_project_py(root):
    for base in ("maya_runtime", "maya_identity", "verification"):
        base_dir = root / base
        if base_dir.is_dir():
            yield from sorted(base_dir.rglob("*.py"))
    yield from sorted(root.glob("test_*.py"))


def _check(ok, detail):
    return {"ok": bool(ok), "detail": detail}


def static_arm(root=None):
    root = pathlib.Path(root or PROJECT_ROOT)
    base = _base_source("static-analysis",
                        "python stdlib static scan (ast/compile/json)",
                        "stdlib", ["<static>", str(root)])
    checks = static_checks(root)
    anomalies = []
    for name, check in checks.items():
        if not check["ok"]:
            anomalies.append(f"{name}: {check['detail']}")
    base["observed"] = {
        "checks": {name: check["ok"] for name, check in checks.items()},
        "details": {name: check["detail"] for name, check in checks.items()},
    }
    return _finalize_source(base, 0, base["observed"], anomalies)


def git_arm(root=None):
    root = pathlib.Path(root or PROJECT_ROOT)
    git = shutil.which("git.exe") or "git"
    base = _base_source("git", f"git {git}", "git", [])
    anomalies = []
    observed = {}
    head = _run([git, "-C", str(root), "rev-parse", "HEAD"])
    observed["head_present"] = head["returncode"] == 0 and bool(head["stdout"].strip())
    if observed["head_present"]:
        observed["head_short"] = head["stdout"].strip()[:8]
    status = _run([git, "-C", str(root), "status", "--porcelain",
                   "--untracked-files=all"])
    if status["returncode"] != 0:
        anomalies.append(f"git status failed ({status['stderr'][:200]!r})")
    porcelain = [line for line in status["stdout"].splitlines() if line.strip()]
    observed["porcelain_lines"] = len(porcelain)
    observed["metadata_listed"] = any("maya_identity\\metadata" in line
                                      for line in porcelain)
    tracked = _run([git, "-C", str(root), "ls-files"])
    tracked_files = [line for line in tracked["stdout"].splitlines() if line.strip()]
    observed["tracked_files"] = len(tracked_files)
    observed["tracked_runtime_state"] = [
        name for name in tracked_files if name.endswith(".jsonl")]
    base["command"] = [git, "-C", str(root), "status", "--porcelain"]
    if not observed["head_present"]:
        anomalies.append("repository has no HEAD commit")
    if observed["tracked_runtime_state"]:
        anomalies.append(f"runtime state tracked: {observed['tracked_runtime_state']}")
    if observed["metadata_listed"]:
        anomalies.append("runtime metadata appears in git working-tree status")
    return _finalize_source(base, head["returncode"], observed, anomalies)


def _unavailable(base, reason):
    base["anomalies"] = [reason]
    base["result"] = "unavailable"
    return base


# ---------------------------------------------------------------------------
# 4. Cross-source consensus and final verdict
# ---------------------------------------------------------------------------

def _arm_oracle_consistent(arm):
    sig = arm["observed"].get("signatures")
    oracle = arm["observed"].get("oracle")
    if sig is None:
        return False
    try:
        return _sig_consistent(tuple(sig), None if oracle is None else tuple(oracle))
    except TypeError:
        return False


def cross_agreement(interpreter_arms, shell_arms):
    """Independently observed facts must agree; returns (agreed, reports)."""
    reports = []
    sigs = [arm["observed"].get("signatures") for arm in interpreter_arms]
    clean_sigs = [tuple(s) for s in sigs if s is not None]
    if len(clean_sigs) > 1 and any(s != clean_sigs[0] for s in clean_sigs[1:]):
        reports.append(f"interpreter signature disagreement: {clean_sigs}")

    ok_maps = []
    for arm in interpreter_arms:
        evidence = {}
        for suite, details in (arm["observed"].get("suite_results") or {}).items():
            evidence[suite] = {"returncode": details["returncode"],
                               "ok_labels": details["ok_labels"]}
        ok_maps.append(evidence)
    if len(ok_maps) > 1 and any(m != ok_maps[0] for m in ok_maps[1:]):
        reports.append(f"interpreter suite evidence disagreement: {ok_maps}")

    for shell in shell_arms:
        obs = shell.get("observed", {})
        ref_suite = "test_readiness.py"
        refs = [arm["observed"]["suite_results"][ref_suite]["ok_labels"]
                for arm in interpreter_arms
                if arm["observed"].get("suite_results", {}).get(ref_suite)]
        if obs.get("ok_count") is not None and refs:
            if obs["ok_count"] != refs[0]:
                reports.append(
                    f"{shell['source']} ok_count {obs['ok_count']} != "
                    f"interpreter {refs[0]}")
        if obs.get("suite_exit") is not None and refs:
            if obs["suite_exit"] != 0:
                reports.append(
                    f"{shell['source']} observed nonzero suite exit "
                    f"{obs['suite_exit']} while report would be clean")

    return not reports, reports


def consensus(sources):
    required = [s for s in sources if not s.get("optional")]
    passing = [s for s in sources if s["result"] == "pass"]
    unavailable = [s for s in sources if s["result"] == "unavailable"]
    required_unavailable = [s for s in required if s["result"] == "unavailable"]
    required_failed = [s for s in required if s["result"] == "fail"]
    required_pass = all(s["result"] == "pass" for s in required)

    interpreter_arms = [s for s in sources if s["source"] == "python-interpreter"]
    shell_arms = [s for s in sources if s["source"] in ("powershell", "cmd")
                  and s["result"] == "pass"]
    oracle_ok = all(_arm_oracle_consistent(s) for s in interpreter_arms
                    if s["result"] == "pass")
    agreed, disagreements = cross_agreement(interpreter_arms, shell_arms)

    ok = (required_pass and not required_unavailable
          and oracle_ok and agreed)
    return {
        "sources": sources,
        "consensus": bool(ok),
        "required_ok": bool(required_pass),
        "required_unavailable": [s["source"] for s in required_unavailable],
        "required_failed": [s["source"] for s in required_failed],
        "optional_unavailable": [s["source"] for s in unavailable
                                 if s.get("optional")],
        "oracle_ok": bool(oracle_ok),
        "cross_agreement": bool(agreed),
        "disagreements": disagreements,
        "passing_sources": [s["source"] for s in passing],
        "source_count": len(sources),
    }


def final_verdict(maya_ready, consensus_result):
    """Final deploy verdict. Maya's own ready string can never be the proof;
    the independent consensus gate decides READY, and a clean consensus never
    overrides a Maya that does not report ready."""
    consensus_ok = bool(consensus_result.get("consensus"))
    if maya_ready and not consensus_ok:
        return {
            "verdict": "NOT READY",
            "maya_reports_ready": True,
            "independent_consensus": False,
            "message": "Maya reports READY, but independent verification "
                       "disagrees.",
        }
    if maya_ready and consensus_ok:
        return {
            "verdict": "READY",
            "maya_reports_ready": True,
            "independent_consensus": True,
            "message": "independent consensus confirms readiness",
        }
    if consensus_ok and not maya_ready:
        return {
            "verdict": "NOT READY",
            "maya_reports_ready": False,
            "independent_consensus": True,
            "message": "independent sources agree, but Maya does not report "
                       "ready: a self-reported ready claim was not present.",
        }
    return {
        "verdict": "NOT READY",
        "maya_reports_ready": False,
        "independent_consensus": False,
        "message": "no readiness basis",
    }


# ---------------------------------------------------------------------------
# 5. Orchestration and auditability
# ---------------------------------------------------------------------------

def _write_audit(records, path=None):
    path = pathlib.Path(path or AUDIT_LOG)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, default=str) + "\n")


def run(root=None, subset=None, include_cmd=True, audit_path=None):
    """Run all independent sources, derive consensus, and audit the outcome."""
    root = pathlib.Path(root or PROJECT_ROOT)
    suites = tuple(subset) if subset else INTERPRETER_SUBSET
    sources = []
    for info in resolve_python_interpreters():
        try:
            if not info["usable"]:
                base = _base_source(
                    "python-interpreter",
                    f"Python {info['version']} @ {info['exe']}",
                    info["version"], [info["exe"], "--version"])
                sources.append(_unavailable(base, "interpreter import probe failed"))
                continue
            sources.append(interpreter_arm(info, suites, root))
        except Exception as exc:  # an arm must never crash the consensus
            base = _base_source("python-interpreter",
                                f"Python {info['version']} @ {info['exe']}",
                                info["version"], ["<interpreter arm>"])
            sources.append(_fail(source=base, reason=repr(exc)))
    try:
        sources.append(powershell_arm(root))
    except Exception as exc:
        sources.append(_fail(
            _base_source("powershell", "powershell.exe", "5.1",
                         ["<powershell arm>"]), repr(exc)))
    if include_cmd:
        try:
            sources.append(cmd_arm(root))
        except Exception as exc:
            sources.append(_fail(
                _base_source("cmd", "cmd.exe", "cmd.exe",
                             ["<cmd arm>"]), repr(exc)))
    try:
        sources.append(static_arm(root))
    except Exception as exc:
        sources.append(_fail(
            _base_source("static-analysis", "stdlib static scan", "stdlib",
                         ["<static arm>"]), repr(exc)))
    try:
        sources.append(git_arm(root))
    except Exception as exc:
        sources.append(_fail(
            _base_source("git", f"git {shutil.which('git') or 'git'}",
                         "git", ["<git arm>"]), repr(exc)))

    result = consensus(sources)
    result["at"] = _iso_now()
    result["root"] = str(root)
    _write_audit([result] + sources, path=audit_path)
    return result


def _fail(base, reason):
    base["anomalies"] = [reason]
    base["result"] = "fail"
    return base