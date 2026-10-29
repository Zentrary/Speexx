"""Core timing constants, paths, and unsupported exercise definitions."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAIN_SCRIPT_PATH = str(PROJECT_ROOT / "main.py")

ACTION_SETTLE_SECONDS = 0.9
EXERCISE_STEP_PAUSE_SECONDS = 0.55
FAST_ACTION_SETTLE_SECONDS = 0.45

UNSUPPORTED_TYPES = {
    "type-intro": "introductory page",
}
