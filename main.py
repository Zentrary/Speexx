"""Entry point for Speexx Exercise Assistant (`python main.py` / `run.bat`)."""

from playwright.sync_api import sync_playwright

from speexx_bot import (
    ACTION_SETTLE_SECONDS,
    EXERCISE_STEP_PAUSE_SECONDS,
    FAST_ACTION_SETTLE_SECONDS,
    HAS_COLOR,
    MAIN_SCRIPT_PATH,
    PROJECT_ROOT,
    TRANSLATIONS,
    UNSUPPORTED_TYPES,
    AnswerSolver,
    BaseSolver,
    DragDropSolver,
    ExerciseEngine,
    Fore,
    MarkTextSolver,
    MultipleChoiceSolver,
    PictureChoiceSolver,
    PronunciationSolver,
    ScrambledSentenceSolver,
    ScrambledTableSolver,
    SingleChoiceSolver,
    SpeexxBotCLI,
    Style,
    TeeLogger,
    ToggleSolutionSolver,
    VideoSolver,
    _ANSI_ESCAPE_RE,
    _TeeLogHandler,
    _char_display_width,
    display_width,
    pad_display,
    run_cli,
    truncate_display,
)

if __name__ == "__main__":
    run_cli()
