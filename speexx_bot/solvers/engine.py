"""ExerciseEngine: detects current Speexx exercise type and instantiates the matching solver."""

from .answer import AnswerSolver
from .drag_drop import DragDropSolver
from .mark_text import MarkTextSolver
from .multiple_choice import MultipleChoiceSolver
from .picture_choice import PictureChoiceSolver
from .pronunciation import PronunciationSolver
from .scrambled_sentence import ScrambledSentenceSolver
from .scrambled_table import ScrambledTableSolver
from .single_choice import SingleChoiceSolver
from .toggle_solution import ToggleSolutionSolver
from .video import VideoSolver


class ExerciseEngine:
    def __init__(self, page, logger, answer_db=None, page_answer_index=None, diagnostic_cb=None):
        self.page = page
        self.logger = logger
        self.answer_db = answer_db if answer_db is not None else {}
        self.page_answer_index = page_answer_index if page_answer_index is not None else {}
        self.diagnostic_cb = diagnostic_cb
        self.solvers = {
            "type-drag-drop": DragDropSolver,
            "type-drag-drop-table": DragDropSolver,
            "type-answer": AnswerSolver,
            "type-scrambled-sentence": ScrambledSentenceSolver,
            "type-scrambled-table": ScrambledTableSolver,
            "type-single-choice": SingleChoiceSolver,
            "type-multiple-choice": MultipleChoiceSolver,
            "type-video": VideoSolver,
            "type-picture-choice": PictureChoiceSolver,
            "type-toggle-solution": ToggleSolutionSolver,
            "type-mark-text": MarkTextSolver,
            "type-pronunciation": PronunciationSolver,
            "type-single-item-pronunciation": PronunciationSolver,
            "type-multi-item-pronunciation": PronunciationSolver,
            "type-multiple-item-pronunciation": PronunciationSolver,
        }

    def detect_type(self):
        try:
            exercise_div = self.page.locator(".exercise").first
            video_div = self.page.locator(".video").first
            if exercise_div.count() == 0:
                if video_div.count() > 0 or self.page.locator("video").count() > 0:
                    return "type-video"
                return "unknown"
            cls = exercise_div.get_attribute("class") or ""

            if "type-intro" in cls:
                return "type-intro"

            if "type-video" in cls:
                return "type-video"

            if "type-drag-drop" in cls:
                if "layout-table" in cls or "layout-grid-duo" in cls:
                    return "type-drag-drop-table"
                return "type-drag-drop"

            if "type-scrambled-sentence" in cls:
                return "type-scrambled-sentence"
            if "type-scrambled-table" in cls:
                return "type-scrambled-table"
            if "type-picture-choice" in cls:
                return "type-picture-choice"
            if "type-toggle-solution" in cls:
                return "type-toggle-solution"
            if "type-single-choice" in cls:
                return "type-single-choice"
            if "type-multiple-choice" in cls:
                return "type-multiple-choice"
            if "type-mark-text" in cls:
                return "type-mark-text"
            if "type-single-item-pronunciation" in cls:
                return "type-single-item-pronunciation"
            if "type-multi-item-pronunciation" in cls:
                return "type-multi-item-pronunciation"
            if "type-multiple-item-pronunciation" in cls:
                return "type-multiple-item-pronunciation"
            if "pronunciation" in cls:
                return "type-pronunciation"
            if "type-answer" in cls:
                return "type-answer"
            if video_div.count() > 0 or self.page.locator("video").count() > 0:
                return "type-video"
            return "unknown"
        except Exception:
            return "unknown"

    def get_solver(self, t, force_solve=False, exercise_title="", page_number=0):
        sc = self.solvers.get(t)
        if not sc:
            return None
        solver = sc(
            self.page,
            self.logger,
            answer_db=self.answer_db,
            page_answer_index=self.page_answer_index,
            diagnostic_cb=self.diagnostic_cb,
        )
        solver.force_solve = force_solve
        solver.exercise_title = exercise_title or ""
        solver.page_number = int(page_number or 0)
        return solver
