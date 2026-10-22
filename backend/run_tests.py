"""Saare tests ek saath chalata hai.
Chalane ke liye (backend folder se):  python run_tests.py
"""
import glob
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
files = sorted(glob.glob(os.path.join(BASE, "tests", "test_*.py")))
failed = []

for path in files:
    name = os.path.basename(path)
    proc = subprocess.run([sys.executable, path], cwd=BASE, capture_output=True, text=True)
    lines = [l for l in (proc.stdout or "").strip().splitlines() if l.strip()]
    ok = proc.returncode == 0
    print(("PASS  " if ok else "FAIL  ") + name + ("" if ok else "   <- " + (lines[-1] if lines else "no output")))
    if not ok:
        failed.append(name)
        print((proc.stderr or "").strip()[-800:])

print()
print(f"{len(files) - len(failed)} of {len(files)} test files passed")
sys.exit(1 if failed else 0)