from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

_source = Path(__file__).with_name("09_question_generator_supabase.py")
_spec = spec_from_file_location("_qg_supabase_impl", _source)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Could not load generator implementation from {_source}")
_module = module_from_spec(_spec)
# Ensure module exists in sys.modules for dataclass/type resolution.
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)

QuestionGeneratorSupabase = _module.QuestionGeneratorSupabase
SupabaseConnection = _module.SupabaseConnection
UsageStats = _module.UsageStats
