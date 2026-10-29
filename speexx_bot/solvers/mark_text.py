"""Solver for type-mark-the-text / type-mark-text exercises."""

from .base import BaseSolver


class MarkTextSolver(BaseSolver):
    MAX_ITERATIONS = 5

    def extract_current_state_answers(self, verified=True):
        self.capture_initial_context()
        group_positions, all_positions, marked_words = self.extract_correct_positions()
        has_any = bool(group_positions or all_positions or marked_words)
        primary = marked_words if marked_words else (group_positions or all_positions)
        return self.record_answer(
            "mark-text",
            primary,
            verified=(verified and has_any),
            group_positions=group_positions,
            all_positions=all_positions,
            marked_words=marked_words,
        )

    def solve(self):
        self.logger.info("=== Mark Text Solver ===")
        self.start_timer()
        if not self.wait_for_page_ready():
            return False
        self.capture_initial_context()

        if self.already_passed():
            self.extract_current_state_answers(verified=True)
            return True

        cached = self._find_cached_answer(expected_type="mark-text")
        if isinstance(cached, dict):
            c_group = cached.get("group_positions") or []
            c_all = cached.get("all_positions") or []
            for pos_list in (c_group, c_all):
                if pos_list:
                    self.step(f"[CACHE] Trying saved mark-text positions ({len(pos_list)} items)")
                    self.click_by_positions(pos_list)
                    self.click_correction()
                    score = self.get_result_score()
                    if score >= self.PASS_LINE:
                        self.verify_step("ตรวจคะแนน Mark Text (Cache)", True, f"ได้คะแนน {score}/100")
                        self.record_answer(
                            "mark-text",
                            cached.get("answers", pos_list),
                            verified=True,
                            group_positions=c_group,
                            all_positions=c_all,
                            marked_words=cached.get("marked_words", []),
                        )
                        return True
                    self.click_repeat()

        self.click_correction()
        if self.get_result_score(wait_for_score=False) >= 100:
            self.extract_current_state_answers(verified=True)
            self.verify_step("ตรวจคะแนน Mark Text", True, "ได้คะแนน 100/100")
            return True
        if not self.click_solution():
            self.report_problem("mark_text_no_solution")
            self.extract_current_state_answers(verified=False)
            return False

        group_positions, all_positions, marked_words = self.extract_correct_positions()
        if not group_positions and not all_positions:
            self.report_problem("mark_text_extract_empty")
            self.extract_current_state_answers(verified=False)
            return False

        primary = marked_words if marked_words else (group_positions or all_positions)
        self.record_answer(
            "mark-text",
            primary,
            verified=True,
            group_positions=group_positions,
            all_positions=all_positions,
            marked_words=marked_words,
        )
        self.verify_step("บันทึกเฉลย Mark Text ลงฐานข้อมูล", True, f"{len(group_positions or all_positions)} จุด")

        self.click_repeat()
        for approach in ["group", "all"]:
            positions = group_positions if approach == "group" else all_positions
            if not positions:
                continue
            self.logger.info(f"--- Trying approach: {approach} ({len(positions)} clicks) ---")
            for iteration in range(self.MAX_ITERATIONS):
                self.click_by_positions(positions)
                self.click_correction()
                score = self.get_result_score()
                self.logger.info(f"--- Iteration {iteration+1}/{self.MAX_ITERATIONS} | Score: {score} ---")
                if score >= self.PASS_LINE:
                    self.verify_step("ตรวจคะแนน Mark Text", True, f"ได้คะแนน {score}/100")
                    elapsed = self.stop_timer()
                    self.logger.info(f"SUCCESS! Time: {elapsed}")
                    return True
                if iteration + 1 < self.MAX_ITERATIONS:
                    self.click_repeat()
            if self.get_result_score() >= self.PASS_LINE:
                return True
            self.click_repeat()
        final_sc = self.get_result_score()
        ok = final_sc >= self.PASS_LINE
        self.verify_step("ตรวจคะแนน Mark Text", ok, f"ได้คะแนน {final_sc}/100")
        return ok

    def extract_correct_positions(self):
        try:
            result = self.page.evaluate("""
                () => {
                    const allWords = Array.from(document.querySelectorAll('.exercise-items .word'));
                    const hasActiveClass = (node) => {
                        if (!node) return false;
                        const cls = (node.className || '').toString().toLowerCase();
                        return cls.includes('selected') || cls.includes('marked') ||
                               cls.includes('success') || cls.includes('correct') ||
                               cls.includes('highlight') || cls.includes('chosen') ||
                               cls.includes('result-green');
                    };
                    const anyExplicitlyMarked = allWords.some(w => {
                        const mt = w.closest('.mark-text');
                        return hasActiveClass(w) || hasActiveClass(mt);
                    });

                    const groupPositions = [];
                    const allPositions = [];
                    const markedWords = [];
                    const seenMarkTexts = new Set();
                    allWords.forEach((w, i) => {
                        const mt = w.closest('.mark-text');
                        const isMarked = anyExplicitlyMarked
                            ? (hasActiveClass(w) || hasActiveClass(mt))
                            : Boolean(mt);
                        if (isMarked) {
                            allPositions.push(i);
                            if (mt) {
                                if (!seenMarkTexts.has(mt)) {
                                    seenMarkTexts.add(mt);
                                    groupPositions.push(i);
                                    markedWords.push((mt.innerText || '').trim());
                                }
                            } else {
                                groupPositions.push(i);
                                markedWords.push((w.innerText || '').trim());
                            }
                        }
                    });
                    return { groupPositions, allPositions, markedWords };
                }
            """)
            group_positions = result.get("groupPositions", []) if result else []
            all_positions = result.get("allPositions", []) if result else []
            marked_words = [w for w in (result.get("markedWords", []) if result else []) if w]
            return group_positions, all_positions, marked_words
        except Exception as e:
            self.logger.error(f"extract_correct_positions error: {e}")
            return [], [], []

    def click_by_positions(self, positions):
        try:
            res = self.page.evaluate("""
                (positions) => {
                    const isMarkedNode = (node) => {
                        if (!node) return false;
                        const cls = (node.className || '').toString().toLowerCase();
                        return cls.includes('selected') || cls.includes('marked') ||
                               cls.includes('highlight') || cls.includes('chosen') ||
                               cls.includes('active');
                    };
                    const seenGroups = new Set();
                    const allWords = Array.from(document.querySelectorAll('.exercise-items .word'));
                    allWords.forEach(w => {
                        const mt = w.closest('.mark-text');
                        if (mt) {
                            if (seenGroups.has(mt)) return;
                            if (isMarkedNode(mt) || isMarkedNode(w)) {
                                seenGroups.add(mt);
                                try { w.click(); } catch(e) {}
                            }
                        } else if (isMarkedNode(w)) {
                            try { w.click(); } catch(e) {}
                        }
                    });

                    let clickedCount = 0;
                    let verifiedCount = 0;
                    positions.forEach(idx => {
                        if (idx < allWords.length) {
                            const el = allWords[idx];
                            try {
                                el.scrollIntoView({ block: 'nearest' });
                                el.click();
                                clickedCount++;
                                const mt = el.closest('.mark-text');
                                if (isMarkedNode(el) || isMarkedNode(mt)) verifiedCount++;
                            } catch(e) {}
                        }
                    });
                    return { clickedCount, verifiedCount, expected: positions.length };
                }
            """, positions) or {}
            clicked = int(res.get("clickedCount", 0))
            verified = int(res.get("verifiedCount", clicked))
            expected = int(res.get("expected", len(positions)))
            self.verify_step(
                "คลิกเลือกคำ Mark Text ครบทุกจุด",
                clicked == expected and expected > 0,
                f"คลิก {clicked}/{expected} จุด (ไฮไลต์แล้ว {verified})",
            )
        except Exception as e:
            self.logger.error(f"click_by_positions error: {e}")
