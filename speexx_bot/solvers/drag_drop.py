"""Solver for type-drag-drop and type-drag-drop-table exercises."""

import time

from .base import BaseSolver


class DragDropSolver(BaseSolver):
    MAX_ITERATIONS = 3
    EMPTY_TILE = "__SPEEXX_EMPTY_DRAG_TILE__"

    @staticmethod
    def _normalise(text):
        return " ".join((text or "").split())

    @classmethod
    def _answer_text(cls, text):
        return cls.EMPTY_TILE if not cls._normalise(text) else cls._normalise(text)

    @classmethod
    def _is_empty_answer(cls, answer):
        return answer == cls.EMPTY_TILE

    def _slot_answers(self):
        placeholders = self.page.locator(".exercise-items .drag-drop-placeholder").all()
        tiles = self.page.locator(
            ".exercise-items .drag-drop:not(.draggable-container .drag-drop)"
        ).all()
        if placeholders and len(placeholders) >= len(tiles) and any(
            ph.locator(".drag-drop").count() > 0 for ph in placeholders
        ):
            out = []
            for ph in placeholders:
                inner = ph.locator(".drag-drop").first
                if inner.count() > 0:
                    out.append(self._answer_text(inner.inner_text()))
                else:
                    txt = self._normalise(ph.inner_text())
                    out.append(self._answer_text(txt) if txt else self.EMPTY_TILE)
            return out
        if not tiles:
            tiles = self.page.locator(
                ".exercise-items [data-drag-drop-id]:not(.draggable-container [data-drag-drop-id])"
            ).all()
        return [self._answer_text(tile.inner_text()) for tile in tiles]

    def _source_tiles(self):
        return self.page.locator(".draggable-container .drag-drop").all()

    def _tile_text(self, tile):
        try:
            return tile.inner_text().strip()
        except Exception:
            return ""

    def extract_current_state_answers(self, verified=True):
        self.capture_initial_context()
        slot_vals = [
            a for a in self._slot_answers()
            if a and not self._is_empty_answer(a)
        ]
        if slot_vals:
            return self.record_answer("drag-drop", slot_vals, verified=verified)
        src_vals = [
            self._normalise(self._tile_text(t))
            for t in self._source_tiles()
            if self._normalise(self._tile_text(t))
        ]
        return self.record_answer("drag-drop", src_vals, verified=False)

    def _restore_by_group_id(self):
        tiles = self._source_tiles()
        if not tiles:
            return []

        groups = {}
        for tile in tiles:
            gid = tile.get_attribute("data-group-id")
            if not gid:
                return []
            text = self._answer_text(self._tile_text(tile))
            groups.setdefault(gid, []).append(text)

        if not groups:
            return []

        items = self.page.locator(".exercise-items .item").all()
        if not items:
            return []

        placeholder_rows = []
        for item in items:
            placeholders = item.locator(".drag-drop-placeholder").all()
            if placeholders:
                placeholder_rows.append(placeholders)

        if not placeholder_rows:
            return []

        column_count = len(placeholder_rows[0])
        if column_count == 0:
            return []

        columns = {}
        for gid, texts in groups.items():
            try:
                col_idx = int(gid) - 1
            except (ValueError, TypeError):
                return []
            if 0 <= col_idx < column_count:
                columns[col_idx] = list(texts)

        answers = []
        for row in placeholder_rows:
            for col_idx in range(len(row)):
                col_tiles = columns.get(col_idx, [])
                if col_tiles:
                    answers.append(col_tiles.pop(0))
                else:
                    answers.append(self.EMPTY_TILE)

        return answers

    def _restore_solution(self):
        self.click_correction()

        ok = self.click_solution()
        if ok:
            answers = self._slot_answers()
            self.click_repeat()
            if answers and any(answers):
                return answers

        self.logger.info("[DND] No solution button, using data-group-id fallback")
        self.click_repeat()
        return self._restore_by_group_id()

    def _all_slot_targets(self):
        placeholders = self.page.locator(".exercise-items .drag-drop-placeholder").all()
        combined = self.page.locator(
            ".exercise-items .drag-drop-placeholder, "
            ".exercise-items .drag-drop:not(.drag-drop-placeholder .drag-drop):not(.draggable-container .drag-drop)"
        ).all()
        if len(combined) > len(placeholders):
            return combined
        return placeholders

    def _count_matching_slots(self, answers):
        expected = 0
        matched = 0
        slots = self._all_slot_targets()
        for idx, answer in enumerate(answers):
            if answer is None or answer == "" or self._is_empty_answer(answer):
                continue
            expected += 1
            if idx < len(slots):
                try:
                    cur = self._answer_text(slots[idx].inner_text())
                    if cur.casefold() == self._answer_text(answer).casefold():
                        matched += 1
                except Exception:
                    pass
        return matched, expected

    def _fill_slots(self, answers):
        moved = 0
        click_placed = 0
        drag_placed = 0
        destination_armed = False

        for repair_pass in range(2):
            matched_now, expected_now = self._count_matching_slots(answers)
            if expected_now > 0 and matched_now >= expected_now:
                break

            for index, answer in enumerate(answers):
                slots = self._all_slot_targets()
                if answer is None or answer == "" or self._is_empty_answer(answer) or index >= len(slots):
                    destination_armed = False
                    continue
                wanted = self._answer_text(answer)
                try:
                    existing_slot_text = self._answer_text(slots[index].inner_text())
                    if existing_slot_text.casefold() == wanted.casefold():
                        destination_armed = False
                        continue
                except Exception:
                    pass

                source = None
                for candidate in self._source_tiles():
                    if self._answer_text(self._tile_text(candidate)) == wanted:
                        source = candidate
                        break
                if source is None:
                    for candidate in self._source_tiles():
                        candidate_text = self._answer_text(self._tile_text(candidate))
                        if candidate_text.casefold() == wanted.casefold():
                            source = candidate
                            break
                if source is None:
                    self.logger.debug(
                        "Tile already placed or unavailable for slot %s: %r", index, answer
                    )
                    destination_armed = False
                    continue

                placed = False
                used_drag = False
                if repair_pass == 0:
                    try:
                        before = len(self._source_tiles())
                        if not destination_armed:
                            slots[index].click(timeout=2000)
                            destination_armed = True
                        source.click(timeout=2000)
                        time.sleep(0.06)

                        live_slots = self._all_slot_targets()
                        slot_text = (
                            self._answer_text(live_slots[index].inner_text())
                            if index < len(live_slots)
                            else ""
                        )
                        source_still_present = any(
                            self._answer_text(self._tile_text(candidate)) == wanted
                            for candidate in self._source_tiles()
                        )
                        placed = (
                            slot_text.casefold() == wanted.casefold()
                            or len(self._source_tiles()) < before
                            or not source_still_present
                        )
                        if not placed and destination_armed:
                            live_slots = self._all_slot_targets()
                            if index < len(live_slots):
                                live_slots[index].click(timeout=1500)
                                live_source = next(
                                    (
                                        c for c in self._source_tiles()
                                        if self._answer_text(self._tile_text(c)).casefold() == wanted.casefold()
                                    ),
                                    None,
                                )
                                if live_source is not None:
                                    live_source.click(timeout=1500)
                                    time.sleep(0.06)
                                    live_slots_after = self._all_slot_targets()
                                    now_text = (
                                        self._answer_text(live_slots_after[index].inner_text())
                                        if index < len(live_slots_after)
                                        else ""
                                    )
                                    placed = now_text.casefold() == wanted.casefold()
                    except Exception as e:
                        self.logger.debug(f"[DND] Click-to-place failed for slot {index}: {e}")

                if not placed:
                    destination_armed = False
                    live_source = next(
                        (
                            c for c in self._source_tiles()
                            if self._answer_text(self._tile_text(c)).casefold() == wanted.casefold()
                        ),
                        None,
                    )
                    live_slots = self._all_slot_targets()
                    if live_source is not None and index < len(live_slots):
                        if self.fast_drag(live_source, live_slots[index]):
                            live_after = self._all_slot_targets()
                            if index < len(live_after):
                                try:
                                    placed = (
                                        self._answer_text(live_after[index].inner_text()).casefold()
                                        == wanted.casefold()
                                    )
                                except Exception:
                                    placed = False
                        if not placed:
                            live_source = next(
                                (
                                    c for c in self._source_tiles()
                                    if self._answer_text(self._tile_text(c)).casefold() == wanted.casefold()
                                ),
                                None,
                            )
                            live_slots = self._all_slot_targets()
                            if live_source is not None and index < len(live_slots):
                                placed = self.precise_drag(live_source, live_slots[index])
                        used_drag = placed

                if placed:
                    moved += 1
                    if used_drag:
                        drag_placed += 1
                    else:
                        click_placed += 1
                    time.sleep(0.04)

        matched_final, expected_final = self._count_matching_slots(answers)
        self.verify_step(
            "ตรวจสอบการวางคำตอบ Drag & Drop",
            matched_final == expected_final and expected_final > 0,
            f"ครบ {matched_final}/{expected_final} จุด",
        )
        self.logger.info(
            "[DND] Placement methods: %s by click, %s by drag fallback (%s/%s verified)",
            click_placed, drag_placed, matched_final, expected_final,
        )
        return moved

    def solve(self):
        self.logger.info("=== Drag & Drop Solver Started ===")
        self.start_timer()

        try:
            if not self.wait_for_page_ready():
                return False
            self.capture_initial_context()

            if self.already_passed():
                self.logger.info("[DND] Already passed (score >= 51)")
                self.extract_current_state_answers(verified=True)
                return True

            cached = self._find_cached_answer(expected_type="drag-drop")
            cached_answers = cached.get("answers") if isinstance(cached, dict) else None
            if cached_answers:
                self.step(f"[CACHE] Using saved drag-drop answers ({len(cached_answers)} items)")
                self._fill_slots(cached_answers)
                self.click_correction()
                score = self.get_result_score()
                if score >= self.PASS_LINE:
                    self.verify_step("ตรวจคะแนน Drag & Drop (Cache)", True, f"ได้คะแนน {score}/100")
                    self.record_answer("drag-drop", cached_answers, verified=True)
                    self.logger.info("[CACHE] Drag/drop completed in %s", self.stop_timer())
                    return True
                self.step("[CACHE] Cached drag-drop did not pass — falling back to solve")
                self.click_repeat()

            answers = self._restore_solution()
            if not answers or not any(answers):
                self.logger.error("Could not extract drag/drop solution mapping")
                self.report_problem("drag_drop_extract_failed")
                self.extract_current_state_answers(verified=False)
                return False
            extracted_count = sum(
                1 for answer in answers if answer is not None and answer != "" and not self._is_empty_answer(answer)
            )
            self.record_answer("drag-drop", answers, verified=True)
            self.verify_step("บันทึกเฉลย Drag & Drop ลงฐานข้อมูล", True, f"{extracted_count} จุด")

            for attempt in range(self.MAX_ITERATIONS):
                self._fill_slots(answers)
                self.click_correction()
                score = self.get_result_score()
                if score >= 100:
                    self.verify_step("ตรวจคะแนน Drag & Drop", True, f"ได้คะแนน {score}/100")
                    self.logger.info("Drag/drop completed in %s", self.stop_timer())
                    return True
                if attempt + 1 < self.MAX_ITERATIONS:
                    self.click_repeat()
            final_sc = self.get_result_score()
            ok = final_sc >= self.PASS_LINE
            self.verify_step("ตรวจคะแนน Drag & Drop", ok, f"ได้คะแนน {final_sc}/100")
            return ok
        except Exception as e:
            self.logger.error(f"Drag/drop error: {e}")
            self.report_problem("drag_drop_exception", {"error": str(e)})
            self.extract_current_state_answers(verified=False)
            return False
