"""Core timing constants, paths, and unsupported exercise definitions."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAIN_SCRIPT_PATH = str(PROJECT_ROOT / "main.py")

try:
    from .speed_config import get as _speed_get, DEFAULTS as _SPEED_DEFAULTS
    ACTION_SETTLE_SECONDS = _speed_get("ACTION_SETTLE_SECONDS")
    EXERCISE_STEP_PAUSE_SECONDS = _speed_get("EXERCISE_STEP_PAUSE_SECONDS")
    FAST_ACTION_SETTLE_SECONDS = _speed_get("FAST_ACTION_SETTLE_SECONDS")
except Exception:
    ACTION_SETTLE_SECONDS = 0.9
    EXERCISE_STEP_PAUSE_SECONDS = 0.55
    FAST_ACTION_SETTLE_SECONDS = 0.45
    _speed_get = lambda k, d=None: d
    _SPEED_DEFAULTS = {}

UNSUPPORTED_TYPES = {
    "type-intro": "introductory page",
}
