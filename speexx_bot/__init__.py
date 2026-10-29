"""Speexx Exercise Assistant modular package."""

from .cli import SpeexxBotCLI, run_cli
from .constants import (
    ACTION_SETTLE_SECONDS,
    EXERCISE_STEP_PAUSE_SECONDS,
    FAST_ACTION_SETTLE_SECONDS,
    MAIN_SCRIPT_PATH,
    PROJECT_ROOT,
    UNSUPPORTED_TYPES,
)
from .speed_config import get as get_speed, get_all as get_all_speeds, set_value as set_speed, reset_defaults as reset_speed_defaults  # noqa: F401
from .self_healing import SelfHealingEngine
from .anti_flaky import AntiFlakyDetector
from .logging_utils import TeeLogger, _TeeLogHandler
from .solvers import (
    AnswerSolver,
    BaseSolver,
    DragDropSolver,
    ExerciseEngine,
    MarkTextSolver,
    MultipleChoiceSolver,
    PictureChoiceSolver,
    PronunciationSolver,
    ScrambledSentenceSolver,
    ScrambledTableSolver,
    SingleChoiceSolver,
    ToggleSolutionSolver,
    VideoSolver,
)
from .translations import TRANSLATIONS
from .ui_utils import (
    Fore,
    HAS_COLOR,
    Style,
    _ANSI_ESCAPE_RE,
    _char_display_width,
    display_width,
    pad_display,
    truncate_display,
)

__all__ = [
    "ACTION_SETTLE_SECONDS",
    "EXERCISE_STEP_PAUSE_SECONDS",
    "FAST_ACTION_SETTLE_SECONDS",
    "PROJECT_ROOT",
    "MAIN_SCRIPT_PATH",
    "UNSUPPORTED_TYPES",
    "get_speed",
    "get_all_speeds",
    "set_speed",
    "reset_speed_defaults",
    "SelfHealingEngine",
    "AntiFlakyDetector",
    "TRANSLATIONS",
    "Fore",
    "Style",
    "HAS_COLOR",
    "_ANSI_ESCAPE_RE",
    "_char_display_width",
    "display_width",
    "truncate_display",
    "pad_display",
    "TeeLogger",
    "_TeeLogHandler",
    "BaseSolver",
    "DragDropSolver",
    "VideoSolver",
    "AnswerSolver",
    "ScrambledSentenceSolver",
    "ScrambledTableSolver",
    "SingleChoiceSolver",
    "MultipleChoiceSolver",
    "PictureChoiceSolver",
    "ToggleSolutionSolver",
    "MarkTextSolver",
    "PronunciationSolver",
    "ExerciseEngine",
    "SpeexxBotCLI",
    "run_cli",
]
