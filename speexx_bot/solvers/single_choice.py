"""Solver for type-single-choice exercises."""

import time

from .base import BaseSolver


class SingleChoiceSolver(BaseSolver):
    MAX_ITERATIONS = 5

    def extract_current_state_answers(self, verified=True):
        self.capture_initial_context()
        per_item = self._find_correct_per_item_js()
        if per_item:
            flat = []
            has_any = False
            for c in per_item:
                if isinstance(c, list) and c:
                    flat.append(c[0])
                    has_any = True
                elif isinstance(c, int):
                    flat.append(c)
                    has_any = True
                else:
                    flat.append(0)
            if has_any:
                return self.record_answer(
                    "single-choice", flat, verified=verified, subtype="multi"
                )
        idx = self.find_correct_option()
        if idx is not None:
            return self.record_answer(
                "single-choice", [idx], verified=verified, subtype="legacy"
            )
        return self.record_answer("single-choice", [], verified=False)

    def _select_and_verify_single_choices(self, answers, subtype):
        try:
            res = self.page.evaluate(
                """
                ([ansList, mode]) => {
                    const clickRadio = (inp) => {
                        if (!inp) return false;
                        if (!inp.checked) {
                            try { inp.click(); } catch (e) {}
                        }
                        if (!inp.checked) {
                            const lbl = inp.closest('label, .choice-option');
                            if (lbl) { try { lbl.click(); } catch (e) {} }
                        }
                        if (!inp.checked) {
                            inp.checked = true;
                            inp.dispatchEvent(new Event('input', { bubbles: true }));
                            inp.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                        return Boolean(inp.checked);
                    };

                    if (mode === 'legacy') {
                        const opts = Array.from(document.querySelectorAll('.choice-option'));
                        const idx = ansList[0] ?? 0;
                        const inp = opts[idx] ? opts[idx].querySelector('input.choice') : null;
                        const ok = clickRadio(inp);
                        return { matched: ok ? 1 : 0, expected: 1 };
                    }

                    if (mode === 'group') {
                        const allInps = Array.from(document.querySelectorAll('.exercise-items .item.choice-item input.choice'));
                        const idx = ansList[0] ?? 0;
                        const ok = clickRadio(allInps[idx]);
                        return { matched: ok ? 1 : 0, expected: 1 };
                    }

                    const items = Array.from(document.querySelectorAll('.exercise-items .item.choice-item'));
                    let matched = 0;
                    const expected = Math.min(ansList.length, items.length);
                    for (let i = 0; i < expected; i++) {
                        const opts = Array.from(items[i].querySelectorAll('input.choice'));
                        const idx = ansList[i];
                        if (idx >= 0 && idx < opts.length && clickRadio(opts[idx])) {
                            matched++;
                        }
                    }
                    return { matched, expected };
                }
                """,
                [list(answers), subtype or "multi"],
            ) or {"matched": 0, "expected": len(answers)}

            matched = int(res.get("matched", 0))
            expected = int(res.get("expected", len(answers)))

            # Repair any stubborn item via Playwright locator click
            if matched < expected:
                if subtype == "legacy":
                    options = self.page.locator(".choice-option").all()
                    if answers and answers[0] < len(options):
                        inp = options[answers[0]].locator("input.choice").first
                        if inp.count() > 0:
                            inp.click(force=True, timeout=2000)
                            matched = 1
                elif subtype == "group":
                    opts = self.page.locator(".exercise-items .item.choice-item input.choice").all()
                    if answers and answers[0] < len(opts):
                        opts[answers[0]].click(force=True, timeout=2000)
                        matched = 1
                else:
                    items = self.page.locator(".exercise-items .item.choice-item").all()
                    matched = 0
                    for i, idx in enumerate(answers):
                        if i >= len(items):
                            break
                        opts = items[i].locator("input.choice").all()
                        if idx < len(opts):
                            try:
                                if not opts[idx].is_checked():
                                    opts[idx].click(force=True, timeout=2000)
                                if opts[idx].is_checked():
                                    matched += 1
                            except Exception:
                                pass

            self.verify_step(
                "เลือกตัวเลือก Single Choice ครบทุกข้อ",
                matched == expected and expected > 0,
                f"ครบ {matched}/{expected} ข้อ",
            )
            return expected > 0
        except Exception as e:
            self.logger.error(f"[CHOICE] select_and_verify failed: {e}")
            return False

    def _apply_cached_answers(self, answers, subtype):
        return self._select_and_verify_single_choices(answers, subtype)

    def _save_choice_to_db(self, answers, subtype=None, verified=True):
        try:
            extra = {"subtype": subtype} if subtype else {}
            self.record_answer("single-choice", list(answers), verified=verified, **extra)
            self.verify_step("บันทึกเฉลย Single Choice ลงฐานข้อมูล", verified, f"{len(answers)} ข้อ")
        except Exception as e:
            self.logger.error(f"[DB] Save single-choice failed: {e}")

    def solve(self):
        self.logger.info("=== Single Choice Solver ===")
        self.start_timer()

        if not self.wait_for_page_ready():
            return False
        self.capture_initial_context()

        if self.already_passed():
            self.logger.info("[CHOICE] Already passed (score >= 51)")
            self.extract_current_state_answers(verified=True)
            return True

        cached = self._find_cached_answer(expected_type="single-choice")
        if cached and cached.get("type") == "single-choice":
            subtype = cached.get("subtype", "multi")
            answers = cached.get("answers", [])
            if answers:
                self.step(f"[CACHE] Found saved answers ({subtype}): {answers}")
                if self._apply_cached_answers(answers, subtype):
                    self.click_correction()
                    score = self.get_result_score()
                    if score >= self.PASS_LINE:
                        self.verify_step("ตรวจคะแนน Single Choice (Cache)", True, f"ได้คะแนน {score}/100")
                        self._save_choice_to_db(answers, subtype=subtype, verified=True)
                        return True
                    self.step("[CACHE] Cached answers failed — falling back to solve")
                    self.click_repeat()

        self.click_correction()
        has_solution = self.click_solution()

        try:
            item_count = self.page.locator(".exercise-items .item.choice-item").count()
        except Exception:
            item_count = 0

        if item_count == 0:
            ok = self._solve_single_legacy()
            if not ok and self.last_recorded_answer is None:
                self.extract_current_state_answers(verified=False)
            return ok

        try:
            group_count = self.page.evaluate("""
                () => new Set(Array.from(document.querySelectorAll(
                    '.exercise-items .item.choice-item input.choice'
                )).map(input => input.name || input.getAttribute('data-group-id') || input.value)).size
            """)
        except Exception:
            group_count = item_count

        if item_count > 1 and group_count == 1:
            ok = self._solve_single_group_choice()
            if not ok and self.last_recorded_answer is None:
                self.extract_current_state_answers(verified=False)
            return ok

        if not has_solution:
            self.logger.info("[CHOICE] No solution button — using fallback")
            return self._solve_without_solution(item_count)

        correct_per_item = self._find_correct_per_item_js()
        if correct_per_item:
            normalised = []
            for c in correct_per_item:
                if isinstance(c, list):
                    normalised.append(c[0] if c else 0)
                elif isinstance(c, int):
                    normalised.append(c)
                else:
                    normalised.append(0)
            self._save_choice_to_db(normalised, subtype="multi", verified=True)

        ok = self._solve_multi_item(item_count)
        if not ok and self.last_recorded_answer is None:
            self.extract_current_state_answers(verified=False)
        return ok

    def _solve_without_solution(self, item_count):
        items = self.page.locator(".exercise-items .item.choice-item").all()
        if not items:
            self.extract_current_state_answers(verified=False)
            return False

        opts_counts = []
        for item in items:
            n = item.locator("input.choice").count()
            if n == 0:
                self.extract_current_state_answers(verified=False)
                return False
            opts_counts.append(n)

        self.click_repeat()
        time.sleep(1.2)

        current = [0] * item_count
        items = self.page.locator(".exercise-items .item.choice-item").all()
        for i in range(min(item_count, len(items))):
            try:
                opts = items[i].locator("input.choice").all()
                if opts:
                    opts[0].click(force=True, timeout=3000)
                    time.sleep(0.1)
            except Exception:
                pass

        self.click_correction()
        time.sleep(1.5)
        score = self.get_result_score()
        self.step(f"[BRUTE] initial score={score}")

        if score >= self.PASS_LINE:
            self._save_choice_to_db(current, subtype="brute", verified=True)
            return True

        max_iter = item_count * 3
        iteration = 0
        improved = True

        while improved and iteration < max_iter and score < self.PASS_LINE:
            improved = False
            iteration += 1

            items = self.page.locator(".exercise-items .item.choice-item").all()
            if len(items) < item_count:
                passed = score >= self.PASS_LINE
                self._save_choice_to_db(current, subtype="brute", verified=passed)
                return passed

            for i in range(item_count):
                n_opts = opts_counts[i]
                if n_opts <= 1:
                    continue

                new_idx = (current[i] + 1) % n_opts

                items_now = self.page.locator(".exercise-items .item.choice-item").all()
                if i >= len(items_now):
                    continue
                opts = items_now[i].locator("input.choice").all()
                if new_idx >= len(opts):
                    continue
                try:
                    opts[new_idx].click(force=True, timeout=3000)
                    time.sleep(0.2)
                except Exception:
                    continue

                self.click_correction()
                time.sleep(1.5)
                new_score = self.get_result_score()

                if new_score > score:
                    score = new_score
                    current[i] = new_idx
                    improved = True
                    self.step(f"[BRUTE] item {i} → option {new_idx}, score={score}")
                    if score >= self.PASS_LINE:
                        self._save_choice_to_db(current, subtype="brute", verified=True)
                        return True
                else:
                    items_revert = self.page.locator(
                        ".exercise-items .item.choice-item"
                    ).all()
                    if i < len(items_revert):
                        opts = items_revert[i].locator("input.choice").all()
                        if current[i] < len(opts):
                            try:
                                opts[current[i]].click(force=True, timeout=3000)
                                time.sleep(0.2)
                            except Exception:
                                pass

        passed = score >= self.PASS_LINE
        self._save_choice_to_db(current, subtype="brute", verified=passed)
        return passed

    def _solve_multi_item(self, item_count):
        correct_per_item = None
        for _ in range(4):
            correct_per_item = self._find_correct_per_item_js()
            if correct_per_item and all(c is not None and len(c) > 0 for c in correct_per_item):
                break
            time.sleep(0.1)
        if not correct_per_item or any(c is None for c in correct_per_item):
            correct_per_item = self._find_correct_per_item()
            if not correct_per_item or any(c is None for c in correct_per_item):
                return False

        normalised = []
        for choices in correct_per_item:
            if isinstance(choices, list):
                if len(choices) >= 1 and isinstance(choices[0], int):
                    choices = choices[0]
                else:
                    return False
            if not isinstance(choices, int):
                return False
            normalised.append(choices)
        correct_per_item = normalised
        self.step(f"Detected correct per item: {correct_per_item}")
        self._save_choice_to_db(correct_per_item, subtype="multi", verified=True)

        self.click_repeat()

        for iteration in range(self.MAX_ITERATIONS):
            self._select_and_verify_single_choices(correct_per_item, "multi")
            self.click_correction()
            score = self.get_result_score()
            self.logger.info(
                f"--- Iteration {iteration+1}/{self.MAX_ITERATIONS} | Score: {score} ---")
            if score >= self.PASS_LINE:
                self.verify_step("ตรวจคะแนน Single Choice", True, f"ได้คะแนน {score}/100")
                return True
            if iteration + 1 < self.MAX_ITERATIONS:
                self.click_repeat()
        final_sc = self.get_result_score()
        ok = final_sc >= self.PASS_LINE
        self.verify_step("ตรวจคะแนน Single Choice", ok, f"ได้คะแนน {final_sc}/100")
        return ok

    def _solve_single_group_choice(self):
        options = self.page.locator(
            '.exercise-items .item.choice-item input.choice').all()
        correct_index = None
        for index, option in enumerate(options):
            try:
                if option.is_checked(timeout=500):
                    correct_index = index
                    break
            except Exception:
                continue
        if correct_index is None:
            self.logger.warning('[CHOICE] solution did not expose a selected option')
            return False
        self.step(f'Detected grouped correct option: {correct_index}')

        self._save_choice_to_db([correct_index], subtype="group", verified=True)
        self.click_repeat()

        for iteration in range(self.MAX_ITERATIONS):
            self._select_and_verify_single_choices([correct_index], "group")
            self.click_correction()
            score = self.get_result_score()
            self.logger.info(
                f'--- Grouped iteration {iteration+1}/{self.MAX_ITERATIONS} | Score: {score} ---')
            if score >= self.PASS_LINE:
                self.verify_step("ตรวจคะแนน Single Choice (Group)", True, f"ได้คะแนน {score}/100")
                return True
            if iteration + 1 < self.MAX_ITERATIONS:
                self.click_repeat()
        return self.get_result_score() >= self.PASS_LINE

    def _find_correct_per_item_js(self):
        try:
            result = self.page.evaluate("""
                () => {
                    const items = document.querySelectorAll('.exercise-items .item.choice-item');
                    const results = [];

                    const isGreenish = (str) => {
                        if (!str) return false;
                        const s = str.toString().toLowerCase();
                        return s.includes('success') || s.includes('correct') ||
                               s.includes('result-green') || s.includes('bg-success') ||
                               s.includes('green') || s.includes('is-correct') ||
                               s.includes('is-checked') || s.includes('selected-correct');
                    };

                    const isSolutionSelected = (el) => {
                        if (!el) return false;
                        const cls = (el.className || '').toString().toLowerCase();
                        const aria = (el.getAttribute('aria-checked') || '').toLowerCase();
                        const data = (el.getAttribute('data-correct') || '').toLowerCase();
                        return aria === 'true' || data === 'true' ||
                               /(^|[-_ ])(selected|active|checked|solution)([-_ ]|$)/.test(cls);
                    };

                    const isGreenStyle = (el) => {
                        try {
                            const style = window.getComputedStyle(el);
                            const values = [style.backgroundColor, style.color,
                                style.borderColor, style.outlineColor].join(' ');
                            const colors = [...values.matchAll(
                                /rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/g
                            )];
                            return colors.some(m => {
                                const r = parseInt(m[1]), g = parseInt(m[2]), b = parseInt(m[3]);
                                return g > r + 25 && g > b + 15;
                            });
                        } catch(e) { return false; }
                    };

                    items.forEach(item => {
                        const corrects = [];
                        const opts = item.querySelectorAll('input.choice');

                        for (let i = 0; i < opts.length; i++) {
                            if (opts[i].checked || isSolutionSelected(opts[i]) ||
                                isSolutionSelected(opts[i].closest('label')) ||
                                isSolutionSelected(opts[i].parentElement)) {
                                if (!corrects.includes(i)) corrects.push(i);
                            }
                        }

                        if (corrects.length === 0) {
                            for (let i = 0; i < opts.length; i++) {
                                if (isGreenish(opts[i].className)) {
                                    if (!corrects.includes(i)) corrects.push(i);
                                }
                            }
                        }

                        if (corrects.length === 0) {
                            const labels = item.querySelectorAll('.choice-option');
                            for (let i = 0; i < labels.length; i++) {
                                const all = [labels[i], ...labels[i].querySelectorAll('*')];
                                for (const el of all) {
                                    if (isGreenish(el.className) || isSolutionSelected(el) ||
                                        isGreenStyle(el)) {
                                        if (!corrects.includes(i)) corrects.push(i);
                                        break;
                                    }
                                }
                            }
                        }

                        if (corrects.length === 0) {
                            const labels = item.querySelectorAll('.choice-option');
                            for (let i = 0; i < labels.length; i++) {
                                try {
                                    const style = window.getComputedStyle(labels[i]);
                                    const bg = style.backgroundColor || '';
                                    const m = bg.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                                    if (m) {
                                        const r = parseInt(m[1]);
                                        const g = parseInt(m[2]);
                                        const b = parseInt(m[3]);
                                        if (g > r + 30 && g > b + 30) {
                                            if (!corrects.includes(i)) corrects.push(i);
                                        }
                                    }
                                } catch(e) {}
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

    def _find_correct_per_item(self):
        results = []
        try:
            items = self.page.locator(".exercise-items .item.choice-item").all()
            for item in items:
                results.append(self._find_correct_in_item(item))
        except Exception:
            pass
        return results

    def _find_correct_in_item(self, item):
        try:
            opts = item.locator("input.choice").all()
            for i, opt in enumerate(opts):
                try:
                    if opt.is_checked(timeout=1000):
                        return i
                except Exception:
                    pass
            labels = item.locator(".choice-option").all()
            for i, label in enumerate(labels):
                try:
                    all_el = [label] + label.locator("*").all()
                    for el in all_el:
                        cls = (el.get_attribute("class") or "").lower()
                        aria = (el.get_attribute("aria-checked") or "").lower()
                        data = (el.get_attribute("data-correct") or "").lower()
                        if (any(k in cls for k in ("success", "correct", "result-green", "bg-success"))
                                or aria == "true" or data == "true"
                                or any(k in cls.split() for k in ("selected", "active", "checked", "solution"))):
                            return i
                except Exception:
                    pass
        except Exception:
            pass
        return None

    def _solve_single_legacy(self):
        correct_idx = None
        for _ in range(4):
            correct_idx = self.find_correct_option()
            if correct_idx is not None:
                break
            time.sleep(0.1)
        if correct_idx is None:
            return False

        self._save_choice_to_db([correct_idx], subtype="legacy", verified=True)
        self.click_repeat()

        for iteration in range(self.MAX_ITERATIONS):
            self._select_and_verify_single_choices([correct_idx], "legacy")
            self.click_correction()
            score = self.get_result_score()
            if score >= self.PASS_LINE:
                self.verify_step("ตรวจคะแนน Single Choice (Legacy)", True, f"ได้คะแนน {score}/100")
                return True
            if iteration + 1 < self.MAX_ITERATIONS:
                self.click_repeat()
        return self.get_result_score() >= self.PASS_LINE

    def find_correct_option(self):
        try:
            idx = self.page.evaluate("""
                () => {
                    const radios = document.querySelectorAll('input.choice');
                    for (let i = 0; i < radios.length; i++) {
                        if (radios[i].checked) return i;
                    }
                    const opts = document.querySelectorAll('.choice-option');
                    for (let i = 0; i < opts.length; i++) {
                        const all = [opts[i], ...opts[i].querySelectorAll('*')];
                        for (const el of all) {
                            const cls = (el.className || '').toString().toLowerCase();
                            if (cls.includes('success') || cls.includes('correct') ||
                                cls.includes('result-green') || cls.includes('bg-success')) {
                                return i;
                            }
                        }
                    }
                    return -1;
                }
            """)
            if idx is not None and idx >= 0:
                return idx
        except Exception:
            pass
        return None
