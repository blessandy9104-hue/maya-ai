import json,sys,shutil,subprocess
from pathlib import Path
BASE = Path(__file__).resolve().parent
R = BASE / "evolution"
S = R / "state.json"
s = json.loads(S.read_text())
src = str(BASE / "assistant.py")
a = sys.argv[1:]
if a[:1]==["status"]:
    print(json.dumps(s,indent=2))
elif a[:1]==["candidate"]:
    n=s["last_candidate"]+1; d=R/"candidates"/f"v{n}"; d.mkdir(parents=True); shutil.copy(src, str(d/"assistant.py")); s["last_candidate"]=n; S.write_text(json.dumps(s,indent=2)); print("Candidate",n,"created at",d)
elif a[:1]==["test"] and len(a)>1:
    d=R/"candidates"/f"v{a[1]}"; r=subprocess.run([sys.executable,"-m","py_compile",str(d/"assistant.py")]); print("Candidate passed syntax test" if r.returncode==0 else "Candidate failed")
else: print("Usage: python3 evolve.py status|candidate|test NUMBER")