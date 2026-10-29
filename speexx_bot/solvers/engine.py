"""ExerciseEngine: detects current Speexx exercise type and instantiates the matching solver."""

import time

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

    @staticmethod
    def _classify_exercise_class(cls: str) -> str:
        if not cls:
            return ""
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
        if "type-mark-text" in cls or "type-mark-the-text" in cls:
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
        return ""

    def detect_type(self, wait_timeout=6.0):
        start_ts = time.time()
        deadline = start_ts + float(wait_timeout)
        detected = ""

        while time.time() < deadline:
            try:
                probe = self.page.evaluate(
                    """
                    () => {
                        const isVis = (el) => {
                            if (!el) return false;
                            const st = window.getComputedStyle(el);
                            if (!st || st.display === 'none' || st.visibility === 'hidden' || parseFloat(st.opacity || '1') === 0) {
                                return false;
                            }
                            const r = el.getBoundingClientRect();
                            return r.width > 4 && r.height > 4;
                        };

                        const exList = Array.from(document.querySelectorAll('.exercise'));
                        const visEx = exList.find(isVis) || exList[0] || null;
                        const cls = visEx ? (visEx.getAttribute('class') || '') : '';

                        const hasItemsReady = Boolean(
                            document.querySelector(
                                '.exercise-items .item, .exercise-items input, .exercise-items .drag-drop-placeholder, ' +
                                '.exercise-items .drag-drop, .exercise-items .gap, .exercise-items .word, ' +
                                '.draggable-container .drag-drop, button.start-exercise, ' +
                                '[class*="pronunciation"], .exercise-items'
                            )
                        );

                        const realVideos = Array.from(document.querySelectorAll('video')).filter(v => {
                            if (!isVis(v)) return false;
                            const hasSrc = Boolean(
                                v.currentSrc || v.src || v.getAttribute('src') || v.querySelector('source[src]')
                            );
                            return hasSrc || v.readyState > 0;
                        });
                        const anyVisVideoTag = Array.from(document.querySelectorAll('video')).some(isVis);

                        return {
                            cls,
                            hasItemsReady,
                            hasRealVideo: realVideos.length > 0,
                            anyVisVideoTag,
                        };
                    }
                    """
                ) or {}
            except Exception:
                probe = {}

            cls_str = probe.get("cls") or ""
            cand = self._classify_exercise_class(cls_str)
            if cand:
                detected = cand
                if cand in {"type-intro", "type-video"} or probe.get("hasItemsReady"):
                    return cand
                # Wait briefly for child items of this exercise to mount in DOM
                item_deadline = min(deadline, time.time() + 2.0)
                while time.time() < item_deadline:
                    time.sleep(0.1)
                    try:
                        ready_now = self.page.evaluate(
                            """
                            () => Boolean(
                                document.querySelector(
                                    '.exercise-items .item, .exercise-items input, .exercise-items .drag-drop-placeholder, ' +
                                    '.exercise-items .drag-drop, .exercise-items .gap, .exercise-items .word, ' +
                                    '.draggable-container .drag-drop, button.start-exercise'
                                )
                            )
                            """
                        )
                        if ready_now:
                            break
                    except Exception:
                        break
                return cand

            # Only fall back to standalone <video> after giving .exercise time to receive its type-* class,
            # and NEVER treat an empty/hidden .video wrapper div without an actual visible <video> tag as video!
            elapsed = time.time() - start_ts
            if elapsed >= 1.2 and (probe.get("hasRealVideo") or probe.get("anyVisVideoTag")):
                return "type-video"

            time.sleep(0.12)

        if detected:
            return detected

        try:
            has_visible_video = bool(
                self.page.evaluate(
                    """
                    () => Array.from(document.querySelectorAll('video')).some(v => {
                        const st = window.getComputedStyle(v);
                        if (!st || st.display === 'none' || st.visibility === 'hidden') return false;
                        const r = v.getBoundingClientRect();
                        return r.width > 10 && r.height > 10;
                    })
                    """
                )
            )
            if has_visible_video:
                return "type-video"
        except Exception:
            pass

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
