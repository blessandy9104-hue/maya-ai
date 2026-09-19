import subprocess,sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
print("Starting template evolution cycle...")
subprocess.run([sys.executable, str(ROOT / "cycle.py")], check=True)
subprocess.run([sys.executable, str(ROOT / "generate_template.py")], check=True)
print("Template evolution cycle complete")