"""Solver for type-multiple-choice exercises."""

import time

from .base import BaseSolver


class MultipleChoiceSolver(BaseSolver):
    MAX_ITERATIONS = 5

    def extract_current_state_answers(self, verified=True):
        self.capture_initial_context()
        per_item = self._find_correct_per_item_js() or []
        has_any = any(bool(c) for c in per_item)
        return self.record_answer(
            "multiple-choice",
            [list(c) for c in per_item],
            verified=(verified and has_any),
        )

    def _save_multiple_choice_to_db(self, correct_per_item, verified=True):
        try:
            self.record_answer(
                "multiple-choice",
                [list(c) for c in correct_per_item],
                verified=verified,
            )
            self.verify_step("บันทึกเฉลย Multiple Choice ลงฐานข้อมูล", verified, f"{len(correct_per_item)} ข้อ")
        except Exception as e:
            self.logger.error(f"[DB] Save multiple-choice failed: {e}")

    def _select_and_verify_multiple_choices(self, answers):
        try:
            res = self.page.evaluate(
                """
                (ansPerItem) => {
                    const items = Array.from(document.querySelectorAll('.exercise-items .item.choice-item'));
                    if (!items.length) return { matched: 0, expected: 0 };
                    const toggleCheckbox = (inp, wantChecked) => {
                        if (!inp) return false;
                        if (Boolean(inp.checked) !== wantChecked) {
                            try { inp.click(); } catch (e) {}
                        }
                        if (Boolean(inp.checked) !== wantChecked) {
                            const lbl = inp.closest('label, .choice-option');
                            if (lbl) { try { lbl.click(); } catch (e) {} }
                        }
                        if (Boolean(inp.checked) !== wantChecked) {
                            inp.checked = wantChecked;
                            inp.dispatchEvent(new Event('input', { bubbles: true }));
                            inp.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                        return Boolean(inp.checked) === wantChecked;
                    };

                    let matched = 0;
                    const expected = Math.min(ansPerItem.length, items.length);
                    for (let i = 0; i < expected; i++) {
                        const wantedSet = new Set(Array.isArray(ansPerItem[i]) ? ansPerItem[i] : []);
                        const opts = Array.from(items[i].querySelectorAll('input.choice'));
                        let itemOk = true;
                        for (let k = 0; k < opts.length; k++) {
                            if (!toggleCheckbox(opts[k], wantedSet.has(k))) {
                                itemOk = false;
                            }
                        }
                        if (itemOk) matched++;
                    }
                    return { matched, expected };
                }
                """,
                list(answers),
            ) or {"matched": 0, "expected": 0}

            matched = int(res.get("matched", 0))
            expected = int(res.get("expected", 0))

            if matched < expected:
                items = self.page.locator(".exercise-items .item.choice-item").all()
                matched = 0
                for item_idx, correct_indices in enumerate(answers):
                    if item_idx >= len(items):
                        break
                    wanted = set(correct_indices or [])
                    opts = items[item_idx].locator("input.choice").all()
                    item_ok = True
                    for opt_idx, opt in enumerate(opts):
                        try:
                            cur = opt.is_checked()
                            if cur != (opt_idx in wanted):
                                opt.click(force=True, timeout=2000)
                            if opt.is_checked() != (opt_idx in wanted):
                                item_ok = False
                        except Exception:
                            item_ok = False
                    if item_ok:
                        matched += 1

            self.verify_step(
                "เลือกตัวเลือก Multiple Choice ครบทุกข้อ",
                matched == expected and expected > 0,
                f"ครบ {matched}/{expected} ข้อ",
            )
            return expected > 0
        except Exception as e:
            self.logger.error(f"[MULTI] select_and_verify failed: {e}")
            return False

    def _apply_cached_multiple_answers(self, answers):
        return self._select_and_verify_multiple_choices(answers)

    def solve(self):
        self.logger.info("=== Multiple Choice Solver ===")
        self.start_timer()
        if not self.wait_for_page_ready():
            return False
        self.capture_initial_context()

        if self.already_passed():
            self.extract_current_state_answers(verified=True)
            return True

        cached = self._find_cached_answer(expected_type="multiple-choice")
        if cached and cached.get("type") == "multiple-choice":
            answers = cached.get("answers", [])
            if answers:
                self.step(f"[CACHE] Found saved multiple-choice answers: {answers}")
                if self._apply_cached_multiple_answers(answers):
                    self.click_correction()
                    score = self.get_result_score()
                    if score >= self.PASS_LINE:
                        self.verify_step("ตรวจคะแนน Multiple Choice (Cache)", True, f"ได้คะแนน {score}/100")
                        self._save_multiple_choice_to_db(answers, verified=True)
                        return True
                    self.step("[CACHE] Cached multiple-choice answers failed — falling back to solve")
                    self.click_repeat()

        self.click_correction()
        has_solution = self.click_solution()
        try:
            item_count = self.page.locator(".exercise-items .item.choice-item").count()
        except Exception:
            item_count = 0
        if item_count == 0:
            self.extract_current_state_answers(verified=False)
            return False

        correct_per_item = None
        for _ in range(6):
            correct_per_item = self._find_correct_per_item_js()
            if correct_per_item and any(len(c) > 0 for c in correct_per_item):
                break
            time.sleep(0.12)

        if not correct_per_item or all(len(c) == 0 for c in correct_per_item):
            if has_solution:
                self.report_problem("multiple_choice_extract_empty")
                self.extract_current_state_answers(verified=False)
                return False
            self.logger.warning("[MULTI] No revealed solution; falling back to greedy selection")
            return self._solve_without_solution()

        self._save_multiple_choice_to_db(correct_per_item, verified=True)
        self.click_repeat()

        for iteration in range(self.MAX_ITERATIONS):
            self._select_and_verify_multiple_choices(correct_per_item)
            self.click_correction()
            score = self.get_result_score()
            if score >= self.PASS_LINE:
                self.verify_step("ตรวจคะแนน Multiple Choice", True, f"ได้คะแนน {score}/100")
                return True
            if iteration + 1 < self.MAX_ITERATIONS:
                self.click_repeat()
        final_sc = self.get_result_score()
        ok = final_sc >= self.PASS_LINE
        self.verify_step("ตรวจคะแนน Multiple Choice", ok, f"ได้คะแนน {final_sc}/100")
        return ok

    def _solve_without_solution(self):
        try:
            item_count = self.page.locator(".exercise-items .item.choice-item").count()
            if item_count == 0:
                self.extract_current_state_answers(verified=False)
                return False

            self.click_repeat()
            time.sleep(1)
            current_score = self.get_result_score()

            for _ in range(12):
                improved = False
                for item_idx in range(item_count):
                    items_now = self.page.locator(".exercise-items .item.choice-item").all()
                    if item_idx >= len(items_now):
                        break
                    opt_count = items_now[item_idx].locator("input.choice").count()
                    for opt_idx in range(opt_count):
                        try:
                            live_items = self.page.locator(".exercise-items .item.choice-item").all()
                            if item_idx >= len(live_items):
                                break
                            live_opts = live_items[item_idx].locator("input.choice").all()
                            if opt_idx >= len(live_opts):
                                break
                            live_opts[opt_idx].click(force=True, timeout=3000)
                            self.click_correction()
                            time.sleep(0.7)
                            new_score = self.get_result_score()
                            if new_score > current_score:
                                current_score = new_score
                                improved = True
                                if current_score >= self.PASS_LINE:
                                    break
                                continue
                            revert_items = self.page.locator(".exercise-items .item.choice-item").all()
                            if item_idx < len(revert_items):
                                revert_opts = revert_items[item_idx].locator("input.choice").all()
                                if opt_idx < len(revert_opts):
                                    revert_opts[opt_idx].click(force=True, timeout=3000)
                                    self.click_correction()
                                    time.sleep(0.7)
                        except Exception:
                            pass
                    if current_score >= self.PASS_LINE:
                        break
                if current_score >= self.PASS_LINE or not improved:
                    break

            passed = self.get_result_score() >= self.PASS_LINE
            self.extract_current_state_answers(verified=passed)
            return passed
        except Exception as e:
            self.logger.error(f"[MULTI] fallback failed: {e}")
            self.extract_current_state_answers(verified=False)
            return False

    def _find_correct_per_item_js(self):
        try:
            result = self.page.evaluate("""
                () => {
                    const items = document.querySelectorAll('.exercise-items .item.choice-item');
                    const results = [];
                    items.forEach(item => {
                        const corrects = [];
                        const opts = item.querySelectorAll('input.choice');
                        for (let i = 0; i < opts.length; i++) {
                            if (opts[i].checked) corrects.push(i);
                        }
                        if (corrects.length === 0) {
                            const labels = item.querySelectorAll('.choice-option');
                            for (let i = 0; i < labels.length; i++) {
                                const all = [labels[i], ...labels[i].querySelectorAll('*')];
                                for (const el of all) {
                                    const cls = (el.className || '').toString().toLowerCase();
                                    if (cls.includes('success') || cls.includes('correct') ||
                                        cls.includes('result-green') || cls.includes('bg-success')) {
                                        corrects.push(i);
                                        break;
                                    }
                                }
                            }
                        }
                        results.push(corrects);
                    });
                    return results;
                }
            """)
            return result if result else None
        except Exception as e:
            self.logger.error(f"_find_correct_per_item_js error: {e}")
            return None
