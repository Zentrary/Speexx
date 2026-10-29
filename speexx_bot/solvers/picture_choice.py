"""Solver for type-picture-choice exercises."""

import json
import time

from .base import BaseSolver


class PictureChoiceSolver(BaseSolver):
    MAX_ITERATIONS = 8

    def extract_current_state_answers(self, verified=True):
        self.capture_initial_context()
        mapping = self.extract_solution_mapping()
        has_any = bool(mapping and any(m.get("src") for m in mapping))
        return self.record_answer(
            "picture-choice", mapping, verified=(verified and has_any)
        )

    def _count_matching_pictures(self, mapping):
        expected = 0
        matched = 0
        items = self.page.locator(".exercise-items .item").all()
        for entry in mapping:
            idx = entry["item_idx"]
            target_src = entry.get("src", "")
            target_id = entry.get("drag_id", "")
            if not target_src and not target_id:
                continue
            expected += 1
            if idx < len(items):
                img = items[idx].locator("img").first
                if img.count() > 0:
                    cur_src = img.get_attribute("src") or ""
                    cur_id = img.get_attribute("data-drag-drop-id") or ""
                    cur_base = cur_src.rsplit("/", 1)[-1].split("?", 1)[0]
                    tgt_base = target_src.rsplit("/", 1)[-1].split("?", 1)[0]
                    if (target_id and cur_id == target_id) or (
                        target_src and (cur_src == target_src or (tgt_base and cur_base == tgt_base))
                    ):
                        matched += 1
        return matched, expected

    def solve(self):
        self.logger.info("=== Picture Choice Solver ===")
        self.start_timer()
        if not self.wait_for_page_ready():
            return False
        self.capture_initial_context()

        if self.already_passed():
            self.extract_current_state_answers(verified=True)
            return True

        cached = self._find_cached_answer(expected_type="picture-choice")
        cached_mapping = cached.get("answers") if isinstance(cached, dict) else None
        if cached_mapping:
            self.step(f"[CACHE] Using saved picture-choice mapping ({len(cached_mapping)} items)")
            self.perform_picture_drag(cached_mapping)
            self.click_correction()
            score = self.get_result_score()
            if score >= self.PASS_LINE:
                self.verify_step("ตรวจคะแนนจับคู่รูปภาพ (Cache)", True, f"ได้คะแนน {score}/100")
                self.record_answer("picture-choice", cached_mapping, verified=True)
                return True
            self.step("[CACHE] Cached picture-choice failed — falling back to solve")
            self.click_repeat()

        self.click_correction()
        if self.get_result_score(wait_for_score=False) >= 100:
            self.extract_current_state_answers(verified=True)
            self.verify_step("ตรวจคะแนนจับคู่รูปภาพ", True, "ได้คะแนน 100/100")
            return True
        if not self.click_solution():
            self.report_problem("picture_choice_no_solution")
            self.extract_current_state_answers(verified=False)
            return False

        mapping = self.extract_solution_mapping()
        if not mapping or all(not m.get("src") for m in mapping):
            self.report_problem("picture_choice_extract_empty")
            self.extract_current_state_answers(verified=False)
            return False

        self.record_answer("picture-choice", mapping, verified=True)
        self.verify_step("บันทึกเฉลยจับคู่รูปภาพลงฐานข้อมูล", True, f"{len(mapping)} รูป")

        self.click_repeat()
        for iteration in range(self.MAX_ITERATIONS):
            self.perform_picture_drag(mapping)
            self.click_correction()
            score = self.get_result_score()
            if score >= self.PASS_LINE:
                self.verify_step("ตรวจคะแนนจับคู่รูปภาพ", True, f"ได้คะแนน {score}/100")
                return True
            if iteration + 1 < self.MAX_ITERATIONS:
                self.click_repeat()
        final_sc = self.get_result_score()
        ok = final_sc >= self.PASS_LINE
        self.verify_step("ตรวจคะแนนจับคู่รูปภาพ", ok, f"ได้คะแนน {final_sc}/100")
        return ok

    def extract_solution_mapping(self):
        mapping = []
        try:
            items = self.page.locator(".exercise-items .item").all()
            for idx, item in enumerate(items):
                img = item.locator("img.picture-gap, img.drag-drop").first
                if img.count() == 0:
                    img = item.locator("img").first
                if img.count() > 0:
                    src = img.get_attribute("src") or ""
                    dd_id = img.get_attribute("data-drag-drop-id") or ""
                    mapping.append({"item_idx": idx, "src": src, "drag_id": dd_id})
                else:
                    mapping.append({"item_idx": idx, "src": "", "drag_id": ""})
        except Exception:
            pass
        return mapping

    def _find_picture_source(self, target_src, target_id):
        if target_src:
            for sel in (
                ".draggable-container img[src=" + json.dumps(target_src) + "]",
                "img[src=" + json.dumps(target_src) + "]",
            ):
                loc = self.page.locator(sel).first
                if loc.count() > 0:
                    return loc
            basename = target_src.rsplit("/", 1)[-1].split("?", 1)[0]
            if basename:
                for cand in self.page.locator(".draggable-container img").all():
                    try:
                        csrc = (cand.get_attribute("src") or "").split("?", 1)[0]
                        if csrc.endswith("/" + basename) or csrc == basename:
                            return cand
                    except Exception:
                        continue
        if target_id:
            for sel in (
                f".draggable-container img[data-drag-drop-id='{target_id}']",
                f"img[data-drag-drop-id='{target_id}']",
            ):
                loc = self.page.locator(sel).first
                if loc.count() > 0:
                    return loc
        return None

    def perform_picture_drag(self, mapping):
        moved = False
        destination_armed = False
        click_placed = 0
        drag_placed = 0
        try:
            for repair_pass in range(2):
                matched_now, expected_now = self._count_matching_pictures(mapping)
                if expected_now > 0 and matched_now >= expected_now:
                    break

                for entry in mapping:
                    idx = entry["item_idx"]
                    target_src = entry.get("src", "")
                    target_id = entry.get("drag_id", "")
                    items = self.page.locator(".exercise-items .item").all()
                    if idx >= len(items) or (not target_src and not target_id):
                        destination_armed = False
                        continue
                    item = items[idx]
                    existing_img = item.locator("img").first
                    if existing_img.count() > 0 and target_src:
                        cur_src = existing_img.get_attribute("src") or ""
                        cur_base = cur_src.rsplit("/", 1)[-1].split("?", 1)[0]
                        tgt_base = target_src.rsplit("/", 1)[-1].split("?", 1)[0]
                        if cur_src == target_src or (tgt_base and cur_base == tgt_base):
                            destination_armed = False
                            continue
                    source = self._find_picture_source(target_src, target_id)
                    if source is None:
                        destination_armed = False
                        continue
                    placeholder = item.locator(".drag-drop-placeholder").first
                    target = placeholder if placeholder.count() > 0 else item
                    placed = False
                    used_drag = False
                    if repair_pass == 0:
                        try:
                            if not destination_armed:
                                target.click(timeout=2000)
                                destination_armed = True
                            source.click(timeout=2000)
                            time.sleep(0.06)

                            items_now = self.page.locator(".exercise-items .item").all()
                            if idx < len(items_now):
                                placed_img = items_now[idx].locator("img").first
                                placed_src = (placed_img.get_attribute("src") or "") if placed_img.count() else ""
                                placed = bool(placed_src) and (
                                    placed_src == target_src
                                    or placed_src.rsplit("/", 1)[-1].split("?", 1)[0]
                                    == target_src.rsplit("/", 1)[-1].split("?", 1)[0]
                                )
                        except Exception as e:
                            self.logger.debug(f"[PICTURE] Click-to-place failed for item {idx}: {e}")

                    if not placed:
                        destination_armed = False
                        items_now = self.page.locator(".exercise-items .item").all()
                        source_now = self._find_picture_source(target_src, target_id)
                        if idx < len(items_now) and source_now is not None:
                            target_now = items_now[idx].locator(".drag-drop-placeholder").first
                            target_now = target_now if target_now.count() > 0 else items_now[idx]
                            if self.fast_drag(source_now, target_now):
                                items_after = self.page.locator(".exercise-items .item").all()
                                if idx < len(items_after):
                                    p_img = items_after[idx].locator("img").first
                                    p_src = (p_img.get_attribute("src") or "") if p_img.count() else ""
                                    placed = bool(p_src) and (
                                        p_src == target_src
                                        or p_src.rsplit("/", 1)[-1].split("?", 1)[0]
                                        == target_src.rsplit("/", 1)[-1].split("?", 1)[0]
                                    )
                            if not placed:
                                items_now = self.page.locator(".exercise-items .item").all()
                                source_now = self._find_picture_source(target_src, target_id)
                                if idx < len(items_now) and source_now is not None:
                                    target_now = items_now[idx].locator(".drag-drop-placeholder").first
                                    target_now = target_now if target_now.count() > 0 else items_now[idx]
                                    placed = self.precise_drag(source_now, target_now)
                            if placed:
                                drag_placed += 1
                                used_drag = True
                    if placed:
                        moved = True
                        if not used_drag:
                            click_placed += 1
                        time.sleep(0.04)

            matched_final, expected_final = self._count_matching_pictures(mapping)
            self.verify_step(
                "ตรวจสอบการวางรูปภาพครบทุกจุด",
                matched_final == expected_final and expected_final > 0,
                f"ครบ {matched_final}/{expected_final} รูป",
            )
            self.logger.info(
                "[PICTURE] Placement methods: %s by click, %s by drag fallback (%s/%s verified)",
                click_placed, drag_placed, matched_final, expected_final,
            )
        except Exception as e:
            self.logger.error(f"[PICTURE] Placement error: {e}")
        return moved
