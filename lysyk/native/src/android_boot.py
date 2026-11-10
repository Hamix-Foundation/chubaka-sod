import os
import sys
import traceback

root = os.environ["LYSYK_ROOT"]
sys.path.insert(0, os.path.join(root, "app"))
try:
    import _native
    sys.modules["lysyk.engine._native"] = _native
    from chubaka.android import run
    run()
except BaseException:
    traceback.print_exc()
    raise
