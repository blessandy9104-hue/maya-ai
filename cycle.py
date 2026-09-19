import subprocess,sys,json
from pathlib import Path
ROOT = Path(__file__).resolve().parent
def run():
    print("Starting evolution cycle...")
    subprocess.run([sys.executable, str(ROOT / "observe.py")])
    subprocess.run([sys.executable, str(ROOT / "cycle_report.py")])
    r=subprocess.run([sys.executable,"-m","py_compile",str(ROOT / "assistant.py")])
    print("Cycle complete. Status:","Tests passed" if r.returncode==0 else "Tests failed")
if __name__=="__main__": run()
