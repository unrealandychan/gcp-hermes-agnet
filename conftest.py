"""Root conftest — ensure project root is importable and fix eval package resolution."""
import importlib
import importlib.util
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

# Force the 'eval' name in sys.modules to point to our eval package,
# not tests/eval which pytest may cache first.
_eval_init = os.path.join(_root, "eval", "__init__.py")
_spec = importlib.util.spec_from_file_location("eval", _eval_init,
    submodule_search_locations=[os.path.join(_root, "eval")])
_eval_mod = importlib.util.module_from_spec(_spec)
sys.modules["eval"] = _eval_mod
_spec.loader.exec_module(_eval_mod)
