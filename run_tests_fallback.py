"""Only needed if pytest is not installed:  python run_tests_fallback.py"""
import glob, importlib, inspect, os, sys, traceback
sys.path.insert(0, ".")
fails = total = 0
for path in sorted(glob.glob("tests/test_*.py")):
    m = importlib.import_module("tests." + os.path.basename(path)[:-3])
    for n, f in inspect.getmembers(m, inspect.isfunction):
        if not n.startswith("test_") or f.__module__ != m.__name__: continue
        total += 1
        try: f(); print("PASS", m.__name__.split(".")[-1], n)
        except Exception: fails += 1; print("FAIL", m.__name__, n); traceback.print_exc()
print(f"\n{total-fails}/{total} passed"); sys.exit(1 if fails else 0)
