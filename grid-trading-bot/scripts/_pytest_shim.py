"""Minimal stand-in for the bits of pytest these test files use, so the
suite can actually be executed in a sandbox with no internet access to
`pip install pytest`. Not a replacement for real pytest — just enough to
prove the test logic runs and passes.
"""
import math
import re
import sys
import types
import traceback
import inspect
import asyncio


class _Approx:
    def __init__(self, expected, rel=None, abs=None):
        self.expected = expected
        self.rel = rel if rel is not None else 1e-6
        self.abs = abs if abs is not None else 1e-12

    def __eq__(self, other):
        if self.expected == 0:
            return abs(other - self.expected) <= max(self.abs, self.rel)
        return math.isclose(other, self.expected, rel_tol=self.rel, abs_tol=self.abs)

    def __repr__(self):
        return f"approx({self.expected})"


def approx(expected, rel=None, abs=None):
    return _Approx(expected, rel=rel, abs=abs)


class raises:
    def __init__(self, exc_type, match=None):
        self.exc_type = exc_type
        self.match = match

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            raise AssertionError(f"Expected {self.exc_type} to be raised, nothing was")
        if not issubclass(exc_type, self.exc_type):
            return False
        if self.match and not re.search(self.match, str(exc_val)):
            raise AssertionError(f"'{self.match}' not found in exception: {exc_val}")
        return True


class _Mark:
    def asyncio(self, f):
        return f


mark = _Mark()

sys.modules["pytest"] = sys.modules[__name__]


def run_module(path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("test_module", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    passed, failed = 0, 0
    failures = []

    def run_one(name, fn):
        nonlocal passed, failed
        try:
            if inspect.iscoroutinefunction(fn):
                asyncio.run(fn())
            else:
                fn()
            passed += 1
        except Exception as e:  # noqa: BLE001
            failed += 1
            failures.append((name, e, traceback.format_exc()))

    for name in dir(mod):
        obj = getattr(mod, name)
        if name.startswith("test_") and callable(obj):
            run_one(name, obj)
        elif inspect.isclass(obj) and name.startswith("Test"):
            instance = obj()
            for mname in dir(instance):
                if mname.startswith("test_"):
                    m = getattr(instance, mname)
                    run_one(f"{name}.{mname}", m)

    print(f"\n{path}: {passed} passed, {failed} failed")
    for name, e, tb in failures:
        print(f"\nFAILED: {name}\n{tb}")
    return failed == 0


if __name__ == "__main__":
    ok = True
    for path in sys.argv[1:]:
        ok = run_module(path) and ok
    sys.exit(0 if ok else 1)
