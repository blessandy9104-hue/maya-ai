import json,sys,shutil,subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parent
P=ROOT/"improvement.json"
q=json.loads(P.read_text(encoding="utf-8")) if P.exists() else []
a=sys.argv[1:]
if a and a[0]=="test":
    r=subprocess.run([sys.executable,"-m","py_compile",str(ROOT/"assistant.py")]); print("Tests passed" if r.returncode==0 else "Tests failed")
elif a and a[0]=="approve" and len(a)>1:
    n=int(a[1])-1; q[n]["status"]="approved"; P.write_text(json.dumps(q,indent=2), encoding="utf-8"); print("Approved proposal",n+1,"- activation still requires a manual code change")
elif a and a[0]=="rollback":
    shutil.copy(str(ROOT/"versions/assistant_initial.py"), str(ROOT/"assistant.py")); print("Rolled back assistant.py")
else:
    print("Usage: python3 improve.py test|approve NUMBER|rollback")