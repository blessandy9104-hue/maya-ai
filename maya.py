import subprocess,sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
print("Maya ready")
subprocess.run([sys.executable, str(ROOT / "assistant.py")]+sys.argv[1:])