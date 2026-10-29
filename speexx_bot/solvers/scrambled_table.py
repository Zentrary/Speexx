"""Solver for type-scrambled-table exercises."""

import time

from .base import BaseSolver


class ScrambledTableSolver(BaseSolver):
    MAX_ITERATIONS = 8

    def extract_current_state_answers(self, verified=True):
        self.capture_initial_context()
        mapping = self.extract_correct_mapping()
        has_any = bool(mapping and any(m.get("text") for m in mapping))
        return self.record_answer(
            "scrambled-table", mapping, verified=(verified and has_any)
        )

    def _count_matching_cells(self, correct_map):
        cur_map = {m["idx"]: m.get("text") for m in self.extract_correct_mapping()}
        expected = 0
        matched = 0
        for entry in correct_map:
            if not isinstance(entry, dict) or not entry.get("text"):
                continue
            expected += 1
            if cur_map.get(entry["idx"]) == entry["text"]:
                matched += 1
        return matched, expected

    def solve(self):
        self.logger.info("=== Scrambled Table Solver ===")
        self.start_timer()
        if not self.wait_for_page_ready():
            return False
        self.capture_initial_context()

        if self.already_passed():
            self.extract_current_state_answers(verified=True)
            return True

        cached = self._find_cached_answer(expected_type="scrambled-table")
        cached_map = cached.get("answers") if isinstance(cached, dict) else None
        if cached_map:
            self.step(f"[CACHE] Using saved table answers ({len(cached_map)} items)")
            self.arrange_cells(cached_map, fast=True)
            self.click_correction()
            score = self.get_result_score()
            if score >= self.PASS_LINE:
                self.verify_step("ตรวจคะแนนตารางเรียงคำ (Cache)", True, f"ได้คะแนน {score}/100")
                self.record_answer("scrambled-table", cached_map, verified=True)
                self.logger.info(f"[CACHE] Scrambled table completed in {self.stop_timer()}")
                return True
            self.logger.warning("[CACHE] Fast cached placement did not pass; retrying reliably")
            self.click_repeat()

        self.click_correction()
        if not self.click_solution():
            self.report_problem("scrambled_table_no_solution")
            self.extract_current_state_answers(verified=False)
            return False

        correct_map = self.extract_correct_mapping()
        if not correct_map or all(m.get("text") is None for m in correct_map):
            self.logger.warning("Failed to extract scrambled table mapping")
            self.report_problem("scrambled_table_extract_empty")
            self.extract_current_state_answers(verified=False)
            return False

        self.record_answer("scrambled-table", correct_map, verified=True)
        self.verify_step("บันทึกเฉลยตารางเรียงคำลงฐานข้อมูล", True, f"{len(correct_map)} แถว")

        self.click_repeat()

        for iteration in range(self.MAX_ITERATIONS):
            self.arrange_cells(correct_map, fast=(iteration == 0))
            self.click_correction()
            score = self.get_result_score()
            self.logger.info(f"--- Iteration {iteration+1}/{self.MAX_ITERATIONS} | Score: {score} ---")
            if score >= self.PASS_LINE:
                self.verify_step("ตรวจคะแนนตารางเรียงคำ", True, f"ได้คะแนน {score}/100")
                elapsed = self.stop_timer()
                self.logger.info(f"SUCCESS! Time: {elapsed}")
                return True
            if iteration + 1 < self.MAX_ITERATIONS:
                self.click_repeat()
        final_sc = self.get_result_score()
        ok = final_sc >= self.PASS_LINE
        self.verify_step("ตรวจคะแนนตารางเรียงคำ", ok, f"ได้คะแนน {final_sc}/100")
        return ok

    def extract_correct_mapping(self):
        try:
            result = self.page.evaluate("""
                () => {
                    const items = document.querySelectorAll('.exercise-items .item');
                    const mapping = [];
                    items.forEach((item, idx) => {
                        const cell = item.querySelector('.scrambled-cell');
                        if (!cell) {
                            mapping.push({idx: idx, text: null});
                            return;
                        }
                        const text = (cell.innerText || '').trim();
                        mapping.push({idx: idx, text: text});
                    });
                    return mapping;
                }
            """)
            return result if result else []
        except Exception as e:
            self.logger.error(f"extract_correct_mapping error: {e}")
            return []

    def arrange_cells(self, correct_map, fast=False):
        moved = False
        try:
            total_items = self.page.locator(".exercise-items .item").count()
            expected_by_idx = {
                entry["idx"]: entry["text"]
                for entry in correct_map
                if isinstance(entry, dict) and "idx" in entry
            }
            for repair_pass in range(2):
                matched_now, expected_now = self._count_matching_cells(correct_map)
                if expected_now > 0 and matched_now >= expected_now:
                    break

                for entry in correct_map:
                    idx = entry["idx"]
                    target_text = entry["text"]
                    if not target_text or idx >= total_items:
                        continue
                    target_item = self.page.locator(".exercise-items .item").nth(idx)
                    target_slot = target_item.locator(".scrambled-cell-container").first
                    if target_slot.count() == 0:
                        continue
                    current = target_slot.locator(".scrambled-cell").first
                    if current.count() > 0:
                        try:
                            if current.inner_text().strip() == target_text:
                                continue
                        except Exception:
                            pass

                    source = None
                    pool_cells = self.page.locator(
                        ".scrambled-cell:not(.exercise-items .item .scrambled-cell)"
                    ).all()
                    for cell in pool_cells:
                        try:
                            if cell.inner_text().strip() == target_text:
                                source = cell
                                break
                        except Exception:
                            continue

                    if source is None:
                        for j in range(total_items):
                            if j == idx:
                                continue
                            other_cell = (
                                self.page.locator(".exercise-items .item")
                                .nth(j)
                                .locator(".scrambled-cell")
                                .first
                            )
                            if other_cell.count() == 0:
                                continue
                            try:
                                txt = other_cell.inner_text().strip()
                            except Exception:
                                continue
                            if txt != target_text:
                                continue
                            if expected_by_idx.get(j) == txt:
                                continue
                            source = other_cell
                            break

                    if source is None:
                        for cell in self.page.locator(".scrambled-cell").all():
                            try:
                                if cell.inner_text().strip() == target_text:
                                    source = cell
                                    break
                            except Exception:
                                continue

                    if source is None:
                        self.logger.warning(f"Cell '{target_text}' not found in DOM")
                        continue

                    placed = self.fast_drag(source, target_slot) if (fast and repair_pass == 0) else False
                    now_ok = False
                    try:
                        chk = (
                            self.page.locator(".exercise-items .item")
                            .nth(idx)
                            .locator(".scrambled-cell-container .scrambled-cell")
                            .first
                        )
                        if chk.count() > 0 and chk.inner_text().strip() == target_text:
                            now_ok = True
                    except Exception:
                        pass

                    if not now_ok:
                        try:
                            source.click(timeout=1500)
                            time.sleep(0.05)
                            target_slot.click(timeout=1500)
                            time.sleep(0.06)
                            chk = (
                                self.page.locator(".exercise-items .item")
                                .nth(idx)
                                .locator(".scrambled-cell-container .scrambled-cell")
                                .first
                            )
                            now_ok = chk.count() > 0 and chk.inner_text().strip() == target_text
                        except Exception:
                            pass

                    if not now_ok:
                        placed = self.precise_drag(source, target_slot)

                    if placed or now_ok:
                        moved = True

            matched_final, expected_final = self._count_matching_cells(correct_map)
            self.verify_step(
                "ตรวจสอบการวางคำตอบตารางเรียงคำ",
                matched_final == expected_final and expected_final > 0,
                f"ครบ {matched_final}/{expected_final} แถว",
            )
        except Exception as e:
            self.logger.error(f"arrange_cells error: {e}")
        return moved
