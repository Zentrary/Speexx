"""Solver for type-answer (fill in the blanks) exercises."""

from .base import BaseSolver


class AnswerSolver(BaseSolver):
    MAX_ITERATIONS = 5

    ANSWER_INPUT_SELECTOR = (
        "input.answer, input.answer-gap, "
        ".exercise-items input:not([type='radio']):not([type='checkbox']):not([type='hidden'])"
    )

    def extract_current_state_answers(self, verified=True):
        self.capture_initial_context()
        vals = self.extract_answers_from_solution()
        has_any = bool(vals and any(v != "" for v in vals))
        return self.record_answer("answer", vals, verified=(verified and has_any))

    def solve(self):
        self.logger.info("=== Answer Solver ===")
        self.start_timer()
        if not self.wait_for_page_ready():
            return False
        self.capture_initial_context()

        if self.already_passed():
            self.extract_current_state_answers(verified=True)
            return True

        if self.has_start_button():
            self.click_start()

        cached = self._find_cached_answer(expected_type="answer")
        cached_answers = cached.get("answers") if isinstance(cached, dict) else None
        if cached_answers:
            self.step(f"[CACHE] Using saved fill-in answers ({len(cached_answers)} blanks)")
            self.fill_blanks(cached_answers)
            self.click_correction()
            score = self.get_result_score()
            if score >= self.PASS_LINE:
                self.verify_step("ตรวจคะแนนเติมคำ (Cache)", True, f"ได้คะแนน {score}/100")
                self.record_answer("answer", cached_answers, verified=True)
                return True
            self.step("[CACHE] Cached fill-in answers failed — falling back to solve")
            self.click_repeat()

        self.click_correction()
        if not self.click_solution():
            self.report_problem("answer_no_solution_button")
            self.extract_current_state_answers(verified=False)
            return False

        correct_answers = self.extract_answers_from_solution()
        if not correct_answers or all(a == "" for a in correct_answers):
            self.report_problem("answer_extract_empty")
            self.extract_current_state_answers(verified=False)
            return False

        non_empty_expected = sum(1 for a in correct_answers if a != "")
        self.record_answer("answer", correct_answers, verified=True)
        self.verify_step("บันทึกเฉลยเติมคำลงฐานข้อมูล", True, f"ครบ {non_empty_expected} จุด")

        self.click_repeat()

        for iteration in range(self.MAX_ITERATIONS):
            if self.has_start_button():
                self.click_start()
            self.fill_blanks(correct_answers)
            self.click_correction()
            score = self.get_result_score()
            self.logger.info(f"--- Iteration {iteration+1}/{self.MAX_ITERATIONS} | Score: {score} ---")
            if score >= self.PASS_LINE:
                self.verify_step("ตรวจคะแนนเติมคำ", True, f"ได้คะแนน {score}/100")
                return True
            if iteration + 1 < self.MAX_ITERATIONS:
                self.click_repeat()
        final_sc = self.get_result_score()
        ok = final_sc >= self.PASS_LINE
        self.verify_step("ตรวจคะแนนเติมคำ", ok, f"ได้คะแนน {final_sc}/100")
        return ok

    def extract_answers_from_solution(self):
        try:
            return self.page.evaluate(
                """
                (sel) => Array.from(document.querySelectorAll(sel)).map(inp => (inp.value || '').trim())
                """,
                self.ANSWER_INPUT_SELECTOR,
            ) or []
        except Exception as e:
            self.logger.error(f"Extract error: {str(e)}")
            return []

    def fill_blanks(self, answers):
        expected = sum(1 for a in answers if a)
        if expected == 0:
            return
        try:
            self._wait_until_js(
                """
                () => {
                    const inputs = Array.from(document.querySelectorAll('input.answer, input.answer-gap'));
                    return inputs.length > 0 && inputs.every(inp => !inp.disabled && !inp.readOnly);
                }
                """,
                timeout=1.5,
                interval=0.04,
            )

            inputs_loc = self.page.locator(self.ANSWER_INPUT_SELECTOR).all()
            for i, ans in enumerate(answers):
                if not ans or i >= len(inputs_loc):
                    continue
                try:
                    inputs_loc[i].fill(ans, timeout=2000)
                except Exception:
                    try:
                        inputs_loc[i].evaluate(
                            """(inp, val) => {
                                inp.focus();
                                inp.value = val;
                                inp.dispatchEvent(new Event('input', { bubbles: true }));
                                inp.dispatchEvent(new Event('change', { bubbles: true }));
                            }""",
                            ans,
                        )
                    except Exception:
                        pass

            # Trigger AngularJS / jQuery change + blur across all inputs so ngModel commits immediately
            self.page.evaluate(
                """
                (sel) => {
                    document.querySelectorAll(sel).forEach(inp => {
                        try {
                            if (window.jQuery) {
                                window.jQuery(inp).trigger('input').trigger('change').trigger('blur');
                            }
                            inp.dispatchEvent(new Event('input', { bubbles: true }));
                            inp.dispatchEvent(new Event('change', { bubbles: true }));
                            inp.blur();
                        } catch (e) {}
                    });
                }
                """,
                self.ANSWER_INPUT_SELECTOR,
            )

            verified_vals = self.extract_answers_from_solution()
            matched = sum(
                1 for i, ans in enumerate(answers)
                if ans and i < len(verified_vals) and verified_vals[i] == ans
            )
            self.verify_step(
                "กรอกคำตอบลงช่องว่างครบทุกจุด",
                matched == expected,
                f"ครบ {matched}/{expected} จุด",
            )
        except Exception as e:
            self.logger.error(f"fill_blanks error: {e}")
