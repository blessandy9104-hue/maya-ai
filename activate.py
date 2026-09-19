import json,sys,shutil
from pathlib import Path
BASE = Path(__file__).resolve().parent
R = BASE / "evolution"
S = R / "state.json"
s = json.loads(S.read_text())
src = str(BASE / "assistant.py")
a = sys.argv[1:]
if a[:1]==["approve"] and len(a)>1:
    n=int(a[1]); s.setdefault("approved",[]).append(n); S.write_text(json.dumps(s,indent=2)); print("Approved candidate",n)
elif a[:1]==["activate"] and len(a)>1:
    n=int(a[1])
    if n not in s.get("approved",[]): print("Candidate is not approved")
    else:
        shutil.copy(src, str(R/"versions"/f"before_v{n}.py"))
        shutil.copy(str(R/"candidates"/f"v{n}"/"assistant.py"), src)
        s["active"]=f"candidate_v{n}"; S.write_text(json.dumps(s,indent=2)); print("Activated candidate",n)
elif a[:1]==["rollback"]:
    backups=sorted((R/"versions").glob("before_v*.py"))
    if backups:
        shutil.copy(str(backups[-1]), src)
        print("Rollback complete")
    else:
        print("No activation backup found")
else: print("Usage: python3 activate.py approve NUMBER|activate NUMBER|rollback")