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

    def _sync_dnd_dom(self):
        """Tag visible logical slots inside .exercise-items and visible unused tiles inside .draggable-container."""
        try:
            data = self.page.evaluate(
                """
                () => {
                    for (const old of document.querySelectorAll('[data-speexx-dnd-slot]')) {
                        old.removeAttribute('data-speexx-dnd-slot');
                    }
                    for (const old of document.querySelectorAll('[data-speexx-dnd-src]')) {
                        old.removeAttribute('data-speexx-dnd-src');
                    }

                    const isVis = (el, stopRoot) => {
                        if (!el) return false;
                        let cur = el;
                        while (cur && cur !== document.body) {
                            if (cur.classList && cur.classList.contains('ng-hide')) return false;
                            const st = window.getComputedStyle(cur);
                            if (!st || st.display === 'none' || st.visibility === 'hidden' || parseFloat(st.opacity || '1') === 0) {
                                return false;
                            }
                            if (cur === stopRoot) break;
                            cur = cur.parentElement;
                        }
                        const r = el.getBoundingClientRect();
                        return r.width > 2 && r.height > 2;
                    };

                    const getText = (el) => {
                        if (!el) return '';
                        const raw = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
                        if (raw) return raw;
                        const img = el.querySelector('img');
                        if (img) {
                            return (img.getAttribute('alt') || img.getAttribute('title') || img.getAttribute('src') || '').trim();
                        }
                        return '';
                    };

                    const exRoot = document.querySelector('.exercise-items');
                    const rawCands = exRoot
                        ? Array.from(exRoot.querySelectorAll('.drag-drop-placeholder, .drag-drop'))
                              .filter(el => !el.closest('.draggable-container') && isVis(el, exRoot))
                        : [];
                    const candSet = new Set(rawCands);

                    const logicalSlots = rawCands.filter(el => {
                        const isPh = el.classList.contains('drag-drop-placeholder');
                        if (isPh) {
                            // If a visible .drag-drop child is inside this placeholder, prefer the inner .drag-drop
                            const innerVisTile = Array.from(el.querySelectorAll('.drag-drop')).find(ch => ch !== el && candSet.has(ch));
                            if (innerVisTile) return false;
                        }
                        // Skip nested .drag-drop inside another visible .drag-drop
                        let p = el.parentElement;
                        while (p && p !== exRoot) {
                            if (candSet.has(p) && !p.classList.contains('drag-drop-placeholder')) {
                                return false;
                            }
                            p = p.parentElement;
                        }
                        return true;
                    });

                    const slots = logicalSlots.map((el, idx) => {
                        el.setAttribute('data-speexx-dnd-slot', String(idx));
                        return {
                            idx,
                            text: getText(el),
                            isPlaceholder: el.classList.contains('drag-drop-placeholder'),
                        };
                    });

                    const poolRoot = document.querySelector('.draggable-container');
                    const rawPool = poolRoot
                        ? Array.from(poolRoot.querySelectorAll('.drag-drop')).filter(el => isVis(el, poolRoot))
                        : [];
                    const poolSet = new Set(rawPool);
                    const visSources = rawPool.filter(el => {
                        let p = el.parentElement;
                        while (p && p !== poolRoot) {
                            if (poolSet.has(p)) return false;
                            p = p.parentElement;
                        }
                        const txt = getText(el);
                        return txt.length > 0;
                    });

                    const sources = visSources.map((el, idx) => {
                        el.setAttribute('data-speexx-dnd-src', String(idx));
                        return {
                            idx,
                            text: getText(el),
                            groupId: el.getAttribute('data-group-id') || '',
                        };
                    });

                    return { slots, sources };
                }
                """
            )
            if isinstance(data, dict):
                return {
                    "slots": data.get("slots") or [],
                    "sources": data.get("sources") or [],
                }
        except Exception as e:
            self.logger.debug(f"[DND] _sync_dnd_dom error: {e}")
        return {"slots": [], "sources": []}

    def _slot_answers(self):
        state = self._sync_dnd_dom()
        slots = state["slots"]
        if slots:
            return [self._answer_text(s.get("text", "")) for s in slots]
        tiles = self.page.locator(
            ".exercise-items [data-drag-drop-id]:not(.draggable-container [data-drag-drop-id])"
        ).all()
        return [self._answer_text(tile.inner_text()) for tile in tiles]

    def _source_tiles(self):
        state = self._sync_dnd_dom()
        return [
            self.page.locator(f"[data-speexx-dnd-src='{s['idx']}']").first
            for s in state["sources"]
        ]

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
        state = self._sync_dnd_dom()
        return [
            self.page.locator(f"[data-speexx-dnd-slot='{s['idx']}']").first
            for s in state["slots"]
        ]

    def _count_matching_slots(self, answers):
        expected = 0
        matched = 0
        slots = self._sync_dnd_dom()["slots"]
        for idx, answer in enumerate(answers):
            if answer is None or answer == "" or self._is_empty_answer(answer):
                continue
            expected += 1
            if idx < len(slots):
                cur = self._answer_text(slots[idx].get("text", ""))
                if cur.casefold() == self._answer_text(answer).casefold():
                    matched += 1
        return matched, expected

    def _wait_slot_matches(self, slot_index, wanted_text, timeout=0.28):
        wanted_cf = self._answer_text(wanted_text).casefold()
        deadline = time.time() + timeout
        while time.time() < deadline:
            slots = self._sync_dnd_dom()["slots"]
            if slot_index < len(slots):
                cur_cf = self._answer_text(slots[slot_index].get("text", "")).casefold()
                if cur_cf == wanted_cf:
                    return True
            time.sleep(0.045)
        return False

    @classmethod
    def _pick_matching_source_idx(cls, sources, wanted_text):
        wanted = cls._answer_text(wanted_text)
        for src in sources:
            if cls._answer_text(src.get("text", "")) == wanted:
                return src["idx"]
        wanted_cf = wanted.casefold()
        for src in sources:
            if cls._answer_text(src.get("text", "")).casefold() == wanted_cf:
                return src["idx"]
        return None

    def _fill_slots(self, answers):
        moved = 0
        click_placed = 0
        drag_placed = 0
        destination_armed = False

        for repair_pass in range(2):
            matched_now, expected_now = self._count_matching_slots(answers)
            if expected_now > 0 and matched_now >= expected_now:
                break

            if repair_pass > 0:
                destination_armed = False

            for index, answer in enumerate(answers):
                if answer is None or answer == "" or self._is_empty_answer(answer):
                    destination_armed = False
                    continue

                wanted = self._answer_text(answer)
                state = self._sync_dnd_dom()
                slots_info = state["slots"]
                if index >= len(slots_info):
                    destination_armed = False
                    continue

                existing_slot_text = self._answer_text(slots_info[index].get("text", ""))
                if existing_slot_text.casefold() == wanted.casefold():
                    destination_armed = False
                    continue

                # If a wrong tile is occupying this slot, click it back to the pool first
                if not self._is_empty_answer(existing_slot_text):
                    try:
                        wrong_loc = self.page.locator(f"[data-speexx-dnd-slot='{index}']").first
                        wrong_loc.click(timeout=1500)
                        time.sleep(0.08)
                        destination_armed = False
                        state = self._sync_dnd_dom()
                        slots_info = state["slots"]
                    except Exception:
                        destination_armed = False

                src_idx = self._pick_matching_source_idx(state["sources"], wanted)
                if src_idx is None:
                    self.logger.debug(
                        "Tile already placed or unavailable for slot %s: %r", index, answer
                    )
                    destination_armed = False
                    continue

                placed = False
                used_drag = False
                if repair_pass == 0:
                    try:
                        slot_loc = self.page.locator(f"[data-speexx-dnd-slot='{index}']").first
                        src_loc = self.page.locator(f"[data-speexx-dnd-src='{src_idx}']").first
                        if not destination_armed:
                            slot_loc.click(timeout=2000)
                            time.sleep(0.03)
                            destination_armed = True
                        src_loc.click(timeout=2000)
                        placed = self._wait_slot_matches(index, wanted, timeout=0.25)

                        if not placed:
                            # Re-sync and explicitly arm target slot before clicking source tile
                            destination_armed = False
                            state = self._sync_dnd_dom()
                            if index < len(state["slots"]):
                                cur_after = self._answer_text(state["slots"][index].get("text", ""))
                                if not self._is_empty_answer(cur_after) and cur_after.casefold() != wanted.casefold():
                                    self.page.locator(f"[data-speexx-dnd-slot='{index}']").first.click(timeout=1500)
                                    time.sleep(0.07)
                                    state = self._sync_dnd_dom()
                                retry_src_idx = self._pick_matching_source_idx(state["sources"], wanted)
                                if retry_src_idx is not None and index < len(state["slots"]):
                                    self.page.locator(f"[data-speexx-dnd-slot='{index}']").first.click(timeout=1500)
                                    time.sleep(0.04)
                                    self.page.locator(f"[data-speexx-dnd-src='{retry_src_idx}']").first.click(timeout=1500)
                                    placed = self._wait_slot_matches(index, wanted, timeout=0.25)
                                    destination_armed = placed
                    except Exception as e:
                        destination_armed = False
                        self.logger.debug(f"[DND] Click-to-place failed for slot {index}: {e}")

                if not placed:
                    destination_armed = False
                    state = self._sync_dnd_dom()
                    drag_src_idx = self._pick_matching_source_idx(state["sources"], wanted)
                    if drag_src_idx is not None and index < len(state["slots"]):
                        src_loc = self.page.locator(f"[data-speexx-dnd-src='{drag_src_idx}']").first
                        slot_loc = self.page.locator(f"[data-speexx-dnd-slot='{index}']").first
                        if self.fast_drag(src_loc, slot_loc):
                            placed = self._wait_slot_matches(index, wanted, timeout=0.25)
                        if not placed:
                            state = self._sync_dnd_dom()
                            drag_src_idx = self._pick_matching_source_idx(state["sources"], wanted)
                            if drag_src_idx is not None and index < len(state["slots"]):
                                src_loc = self.page.locator(f"[data-speexx-dnd-src='{drag_src_idx}']").first
                                slot_loc = self.page.locator(f"[data-speexx-dnd-slot='{index}']").first
                                if self.precise_drag(src_loc, slot_loc):
                                    placed = self._wait_slot_matches(index, wanted, timeout=0.3) or True
                        used_drag = placed

                if placed:
                    moved += 1
                    if used_drag:
                        drag_placed += 1
                    else:
                        click_placed += 1
                    time.sleep(0.03)

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
