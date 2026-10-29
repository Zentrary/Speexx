"""Solver for type-toggle-solution exercises."""

import time

from .base import BaseSolver


class ToggleSolutionSolver(BaseSolver):
    MAX_ITERATIONS = 6
    MAX_TOGGLE_CYCLES = 14

    def extract_current_state_answers(self, verified=True):
        self.capture_initial_context()
        vals = self.extract_correct_answers()
        has_any = bool(vals and any(v != "" for v in vals))
        return self.record_answer(
            "toggle-solution", vals, verified=(verified and has_any)
        )

    def solve(self):
        self.logger.info("=== Toggle Solution Solver ===")
        self.start_timer()
        if not self.wait_for_page_ready():
            return False
        self.capture_initial_context()

        if self.already_passed():
            self.extract_current_state_answers(verified=True)
            return True

        cached = self._find_cached_answer(expected_type="toggle-solution")
        cached_answers = cached.get("answers") if isinstance(cached, dict) else None
        if cached_answers:
            self.step(f"[CACHE] Using saved toggle-solution answers ({len(cached_answers)} gaps)")
            self.set_all_gaps(cached_answers)
            self.click_correction()
            score = self.get_result_score()
            if score >= self.PASS_LINE:
                self.verify_step("ตรวจคะแนน Toggle Solution (Cache)", True, f"ได้คะแนน {score}/100")
                self.record_answer("toggle-solution", cached_answers, verified=True)
                return True
            self.step("[CACHE] Cached toggle-solution failed — falling back to solve")
            self.click_repeat()

        self.click_correction()
        if not self.click_solution():
            self.report_problem("toggle_solution_no_solution")
            self.extract_current_state_answers(verified=False)
            return False

        correct_answers = self.extract_correct_answers()
        if not correct_answers or all(a == "" for a in correct_answers):
            self.report_problem("toggle_solution_extract_empty")
            self.extract_current_state_answers(verified=False)
            return False

        self.record_answer("toggle-solution", correct_answers, verified=True)
        self.verify_step("บันทึกเฉลย Toggle Solution ลงฐานข้อมูล", True, f"{len(correct_answers)} จุด")

        self.click_repeat()
        for iteration in range(self.MAX_ITERATIONS):
            self.set_all_gaps(correct_answers)
            self.click_correction()
            score = self.get_result_score()
            if score >= self.PASS_LINE:
                self.verify_step("ตรวจคะแนน Toggle Solution", True, f"ได้คะแนน {score}/100")
                return True
            if iteration + 1 < self.MAX_ITERATIONS:
                self.click_repeat()
        final_sc = self.get_result_score()
        ok = final_sc >= self.PASS_LINE
        self.verify_step("ตรวจคะแนน Toggle Solution", ok, f"ได้คะแนน {final_sc}/100")
        return ok

    def _norm(self, s):
        return (s or "").replace("\xa0", " ").strip()

    def extract_correct_answers(self):
        try:
            return self.page.evaluate("""
                () => Array.from(document.querySelectorAll('.exercise-items .gap'))
                    .map(g => (g.innerText || g.textContent || '').replace(/\\u00a0/g, ' ').trim())
            """) or []
        except Exception:
            return []

    def set_all_gaps(self, answers):
        expected = sum(1 for a in answers if a)
        if expected == 0:
            return
        try:
            # Fast single-JS cycle pass across all toggle gaps
            self.page.evaluate(
                """
                ([ansList, maxCycles]) => {
                    const norm = s => (s || '').replace(/\\u00a0/g, ' ').trim();
                    for (let i = 0; i < ansList.length; i++) {
                        const wanted = norm(ansList[i]);
                        if (!wanted) continue;
                        for (let c = 0; c < maxCycles; c++) {
                            const gaps = document.querySelectorAll('.exercise-items .gap');
                            if (i >= gaps.length) break;
                            const g = gaps[i];
                            if (norm(g.innerText || g.textContent) === wanted) break;
                            const cont = g.closest('.gap-container') || g.parentElement;
                            const btn = cont ? cont.querySelector('button') : null;
                            if (!btn) break;
                            try { btn.click(); } catch (e) { break; }
                        }
                    }
                }
                """,
                [list(answers), self.MAX_TOGGLE_CYCLES],
            )

            # Verify every single gap; repair any stubborn gap via Playwright click
            cur_vals = self.extract_correct_answers()
            for i, ans in enumerate(answers):
                wanted = self._norm(ans)
                if not wanted:
                    continue
                if i < len(cur_vals) and cur_vals[i] == wanted:
                    continue
                for _ in range(self.MAX_TOGGLE_CYCLES):
                    gap = self.page.locator(".exercise-items .gap").nth(i)
                    if gap.count() == 0:
                        break
                    if self._norm(gap.inner_text()) == wanted:
                        break
                    container = gap.locator(
                        "xpath=ancestor::div[contains(@class,'gap-container')]"
                    ).first
                    toggle = container.locator("button").first if container.count() > 0 else None
                    if toggle is None or toggle.count() == 0:
                        break
                    try:
                        toggle.click(timeout=1500)
                        time.sleep(0.04)
                    except Exception:
                        break

            final_vals = self.extract_correct_answers()
            matched = sum(
                1 for i, ans in enumerate(answers)
                if self._norm(ans) and i < len(final_vals) and final_vals[i] == self._norm(ans)
            )
            self.verify_step(
                "ตั้งค่าตัวเลือก Toggle ครบทุกจุด",
                matched == expected,
                f"ครบ {matched}/{expected} จุด",
            )
        except Exception as e:
            self.logger.error(f"set_all_gaps error: {e}")
