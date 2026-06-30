from pathlib import Path
import subprocess
import sys


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    raise SystemExit(subprocess.call([sys.executable, "-m", "streamlit", "run", str(root / "app.py")], cwd=root))
