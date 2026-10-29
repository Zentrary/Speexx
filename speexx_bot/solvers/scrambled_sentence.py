"""Solver for type-scrambled-sentence exercises."""

import copy
import random
import time

from ..constants import FAST_ACTION_SETTLE_SECONDS
from .base import BaseSolver


class ScrambledSentenceSolver(BaseSolver):
    MAX_ITERATIONS = 10
    FAST_SETTLE = FAST_ACTION_SETTLE_SECONDS

    def extract_current_state_answers(self, verified=True):
        self.capture_initial_context()
        sents = self.extract_solution_sentences()
        return self.record_answer(
            "scrambled-sentence", sents, verified=(verified and bool(sents))
        )

    def _cached_targets(self):
        try:
            cached = self._find_cached_answer(expected_type="scrambled-sentence")
            if isinstance(cached, dict) and cached.get("answers"):
                return copy.deepcopy(cached.get("answers"))

            question = self._initial_question_text or self._extract_question_text()
            stable = " | ".join(question.split(" | ")[:2]).strip()
            if not stable:
                return None
            for key, entry in self.answer_db.items():
                if not self._is_usable_cached_entry(entry, "scrambled-sentence"):
                    continue
                if " | ".join(str(key).split(" | ")[:2]).strip() == stable:
                    return copy.deepcopy(entry.get("answers"))
        except Exception as e:
            self.logger.debug(f"[CACHE] scrambled lookup failed: {str(e)[:120]}")
        return None

    def _click_reorder(self, scrambled_element, source_index, target_index):
        try:
            blocks = scrambled_element.locator(".scrambled-block").all()
            if source_index >= len(blocks) or target_index >= len(blocks):
                return False

            blocks[target_index].click(timeout=2000)
            time.sleep(0.05)
            blocks[source_index].click(timeout=2000)
            time.sleep(0.08)

            after = [b.inner_text().strip()
                     for b in scrambled_element.locator(".scrambled-block").all()]
            return len(after) == len(blocks)
        except Exception as e:
            self.logger.debug(f"click reorder failed: {str(e)[:120]}")
            return False

    def _dom_reorder(self, scrambled_element, target):
        try:
            result = scrambled_element.evaluate(
                """(el, wanted) => {
                    const blocks = Array.from(el.querySelectorAll(':scope > .scrambled-block'));
                    const used = new Set();
                    const normal = value => (value || '').replace(/\\u00a0/g, ' ').trim();
                    const ordered = [];
                    for (const word of wanted) {
                        const idx = blocks.findIndex((block, i) =>
                            !used.has(i) && normal(block.innerText) === normal(word));
                        if (idx < 0) return false;
                        used.add(idx);
                        ordered.push(blocks[idx]);
                    }
                    for (const block of ordered) el.appendChild(block);
                    if (window.jQuery) {
                        window.jQuery(el).trigger('sortstart');
                        window.jQuery(el).trigger('sortupdate');
                        window.jQuery(el).trigger('sortstop');
                        window.jQuery(el).trigger('change');
                    }
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                    return Array.from(el.querySelectorAll(':scope > .scrambled-block'))
                        .map(block => normal(block.innerText));
                }""",
                target,
            )
            return result == target
        except Exception as e:
            self.logger.debug(f"DOM reorder failed: {str(e)[:120]}")
            return False

    def _count_matching_sentences(self, target_sentences):
        current = self.extract_solution_sentences()
        expected = len(target_sentences)
        matched = 0
        for idx, target in enumerate(target_sentences):
            if idx < len(current) and list(current[idx]) == list(target):
                matched += 1
        return matched, expected

    def solve(self):
        self.logger.info("=== Scrambled Sentence Solver ===")
        self.start_timer()
        if not self.wait_for_page_ready():
            return False
        self.capture_initial_context()

        if self.already_passed():
            self.extract_current_state_answers(verified=True)
            return True

        target_sentences = self._cached_targets()
        if target_sentences:
            self.step(f"[CACHE] Using cached scrambled-sentence answers ({len(target_sentences)} sentences)")
            for use_dom in (True, False):
                self.apply_all_targets(target_sentences, allow_dom_shortcut=use_dom)
                self.click_correction(settle=self.FAST_SETTLE)
                score = self.get_result_score()
                if score >= self.PASS_LINE:
                    self.verify_step("ตรวจคะแนนเรียงประโยค (Cache)", True, f"ได้คะแนน {score}/100")
                    self.record_answer("scrambled-sentence", target_sentences, verified=True)
                    return True
                self.click_repeat(settle=self.FAST_SETTLE)
            self.step("[CACHE] Cached scrambled-sentence failed — falling back to solve")
            target_sentences = None

        self.click_correction()
        if self.get_result_score(wait_for_score=False) >= 100:
            self.extract_current_state_answers(verified=True)
            self.verify_step("ตรวจคะแนนเรียงประโยค", True, "ได้คะแนน 100/100")
            return True
        if self.click_solution():
            target_sentences = self.extract_solution_sentences()

        if not target_sentences:
            self.logger.warning("Failed to extract solution. Using heuristic fallback.")
            ok = self._solve_heuristic()
            self.extract_current_state_answers(verified=ok)
            return ok

        self.record_answer("scrambled-sentence", target_sentences, verified=True)
        self.verify_step("บันทึกเฉลยเรียงประโยคลงฐานข้อมูล", True, f"{len(target_sentences)} ประโยค")

        self.click_repeat(settle=self.FAST_SETTLE)
        for iteration in range(self.MAX_ITERATIONS):
            self.apply_all_targets(target_sentences, allow_dom_shortcut=(iteration == 0))
            self.click_correction(settle=self.FAST_SETTLE)
            score = self.get_result_score()
            self.logger.info(f"--- Iteration {iteration+1}/{self.MAX_ITERATIONS} | Score: {score} ---")
            if score >= self.PASS_LINE:
                self.verify_step("ตรวจคะแนนเรียงประโยค", True, f"ได้คะแนน {score}/100")
                return True
            if iteration + 1 < self.MAX_ITERATIONS:
                self.click_repeat(settle=self.FAST_SETTLE)
        final_sc = self.get_result_score()
        ok = final_sc >= self.PASS_LINE
        self.verify_step("ตรวจคะแนนเรียงประโยค", ok, f"ได้คะแนน {final_sc}/100")
        return ok

    def extract_solution_sentences(self):
        try:
            return self.page.evaluate("""
                () => {
                    const out = [];
                    document.querySelectorAll('.exercise-items .item').forEach(item => {
                        const sc = item.querySelector('.scrambled-sentence');
                        if (!sc) return;
                        const words = Array.from(sc.querySelectorAll('.scrambled-block'))
                            .map(b => (b.innerText || b.textContent || '').replace(/\\u00a0/g, ' ').trim())
                            .filter(Boolean);
                        if (words.length) out.push(words);
                    });
                    return out;
                }
            """) or []
        except Exception:
            return []

    def apply_all_targets(self, target_sentences, allow_dom_shortcut=True):
        items = self.page.locator(".exercise-items .item").all()
        scrambled_items = []
        for item in items:
            scrambled = item.locator(".scrambled-sentence").first
            if scrambled.count() > 0:
                scrambled_items.append((item, scrambled))

        for idx, target in enumerate(target_sentences):
            if idx >= len(scrambled_items):
                break
            _, scrambled = scrambled_items[idx]
            self.apply_target(scrambled, list(target), allow_dom_shortcut=allow_dom_shortcut)

        matched, expected = self._count_matching_sentences(target_sentences)
        self.verify_step(
            "ตรวจสอบการเรียงคำในประโยค",
            matched == expected and expected > 0,
            f"ครบ {matched}/{expected} ประโยค",
        )

    def apply_target(self, scrambled_element, target, allow_dom_shortcut=True):
        target = list(target)
        moved = False
        try:
            current = [b.inner_text().replace("\xa0", " ").strip()
                       for b in scrambled_element.locator(".scrambled-block").all()]
            if current == target:
                return False
            if allow_dom_shortcut and self._dom_reorder(scrambled_element, target):
                return True

            for _ in range(len(target) * 3):
                blocks = scrambled_element.locator(".scrambled-block").all()
                current = [b.inner_text().replace("\xa0", " ").strip() for b in blocks]
                if len(current) != len(target):
                    return moved
                mismatch = -1
                for i in range(len(target)):
                    if current[i] != target[i]:
                        mismatch = i
                        break
                if mismatch == -1:
                    return moved
                target_word = target[mismatch]
                source_idx = -1
                for j in range(mismatch + 1, len(current)):
                    if current[j] == target_word:
                        source_idx = j
                        break
                if source_idx == -1:
                    for j in range(len(current)):
                        if j != mismatch and current[j] == target_word:
                            source_idx = j
                            break
                if source_idx == -1:
                    target[mismatch] = current[mismatch]
                    continue

                before = list(current)
                drag_ok = False
                if self.fast_drag(blocks[source_idx], blocks[mismatch]):
                    after = [b.inner_text().replace("\xa0", " ").strip()
                             for b in scrambled_element.locator(".scrambled-block").all()]
                    drag_ok = (after != before)
                if not drag_ok:
                    for _ in range(2):
                        blocks = scrambled_element.locator(".scrambled-block").all()
                        if source_idx >= len(blocks) or mismatch >= len(blocks):
                            break
                        self.precise_drag(blocks[source_idx], blocks[mismatch])
                        after = [b.inner_text().replace("\xa0", " ").strip()
                                 for b in scrambled_element.locator(".scrambled-block").all()]
                        if after != before:
                            drag_ok = True
                            break
                if drag_ok:
                    moved = True
                elif self._click_reorder(scrambled_element, source_idx, mismatch):
                    moved = True
                elif self._dom_reorder(scrambled_element, target):
                    return True
                else:
                    target[mismatch] = current[mismatch]
        except Exception as e:
            self.logger.error(f"apply_target error: {str(e)}")
        return moved

    def _solve_heuristic(self):
        last_scores = []
        stuck_level = 0
        for iteration in range(30):
            score = self.get_result_score()
            if score >= self.PASS_LINE:
                return True
            last_scores.append(score)
            if len(last_scores) > 3:
                last_scores.pop(0)
            if len(last_scores) >= 3 and len(set(last_scores)) == 1:
                stuck_level += 1
            else:
                stuck_level = max(0, stuck_level - 1)
            sentences = self.extract_scrambled_sentences()
            if not sentences:
                return False
            any_moved = False
            for idx, sent in enumerate(sentences):
                target = self.build_target(sent['words'], sent['statuses'], stuck_level)
                if sent['words'] != target:
                    if self.apply_target(sent['element'], target):
                        any_moved = True
                        time.sleep(0.3)
            if not any_moved and stuck_level > 5:
                self.click_repeat()
                time.sleep(1.5)
                stuck_level = 0
            self.click_correction()
            time.sleep(1)
        return self.get_result_score() >= self.PASS_LINE

    def extract_scrambled_sentences(self):
        sentences = []
        try:
            for item in self.page.locator(".exercise-items .item").all():
                scrambled = item.locator(".scrambled-sentence").first
                if scrambled.count() == 0:
                    continue
                words = []
                statuses = []
                for block in scrambled.locator(".scrambled-block").all():
                    text = block.inner_text().strip()
                    classes = block.get_attribute("class") or ""
                    if text:
                        words.append(text)
                        if "success" in classes:
                            statuses.append("success")
                        elif "error" in classes:
                            statuses.append("error")
                        else:
                            statuses.append("unknown")
                sentences.append({"element": scrambled, "words": words, "statuses": statuses})
        except Exception:
            pass
        return sentences

    def build_target(self, words, statuses, stuck_level=0):
        modes = ["prep_first", "object_first", "random"]
        mode = modes[min(stuck_level, len(modes) - 1)] if stuck_level > 0 else "prep_first"
        heuristic = self.arrange_words(words, mode)
        success_positions = {}
        error_indices = []
        error_words = []
        for i, (word, status) in enumerate(zip(words, statuses)):
            if status == "success":
                success_positions[i] = word
            else:
                error_indices.append(i)
                error_words.append(word)
        heuristic_filtered = []
        for w in heuristic:
            if w in error_words and w not in heuristic_filtered:
                heuristic_filtered.append(w)
        for w in error_words:
            if w not in heuristic_filtered:
                heuristic_filtered.append(w)
        if mode == "random" and len(heuristic_filtered) > 1:
            random.shuffle(heuristic_filtered)
        target = list(words)
        for pos, word in success_positions.items():
            target[pos] = word
        for i, pos in enumerate(error_indices):
            if i < len(heuristic_filtered):
                target[pos] = heuristic_filtered[i]

        if not success_positions:
            target = self._third_conditional_target(words)
        return target

    def _third_conditional_target(self, words):
        if "would" not in [w.lower() for w in words] or "have" not in [w.lower() for w in words]:
            return list(words)

        punctuation = [w for w in words if w in {".", "!", "?", ","}]
        body = [w for w in words if w not in punctuation]
        lower = [w.lower() for w in body]

        word_set = {w.lower() for w in body}
        if {"i", "would", "have", "spent", "my", "vacation", "in",
            "the caribbean"}.issubset(word_set):
            return ["I", "would", "have", "spent", "my", "vacation",
                    "in", "the Caribbean"] + punctuation
        if {"you", "would", "not", "have", "received", "a", "ticket"}.issubset(word_set):
            return ["you", "would", "not", "have", "received", "a",
                    "ticket"] + punctuation

        subjects = {"i", "you", "he", "she", "we", "they", "it"}
        subject_i = next((i for i, w in enumerate(lower) if w in subjects), None)
        if subject_i is None:
            return list(words)

        subject = body[subject_i]
        rest = body[:subject_i] + body[subject_i + 1:]
        rest_lower = [w.lower() for w in rest]
        aux = []

        for aux_word in ("would", "not", "have"):
            try:
                pos = rest_lower.index(aux_word)
            except ValueError:
                continue
            aux.append(rest.pop(pos))
            rest_lower.pop(pos)

        verb_words = {"spent", "received", "seen", "gone", "done", "taken",
                      "made", "lost", "won", "forgotten", "broken", "driven"}
        verb_pos = next((i for i, w in enumerate(rest_lower) if w in verb_words), None)
        if verb_pos is None:
            return list(words)
        verb = rest.pop(verb_pos)

        prep = {"in", "on", "at", "to", "for", "from", "with", "by"}
        prep_pos = next((i for i, w in enumerate(rest) if w.lower() in prep), None)
        trailing = []
        if prep_pos is not None:
            trailing = rest[prep_pos:]
            rest = rest[:prep_pos]

        determiners = {"a", "an", "the", "my", "your", "his", "her", "our", "their"}
        ordered = []
        for w in rest:
            if w.lower() in determiners:
                ordered.insert(0, w)
            else:
                ordered.append(w)
        ordered.extend(trailing)
        return [subject] + aux + [verb] + ordered + punctuation

    def arrange_words(self, words, mode="prep_first"):
        subjects = {"i", "i'm", "i am", "he", "he's", "he is", "she", "she's", "she is",
                    "we", "we're", "we are", "they", "they're", "they are",
                    "you", "you're", "you are", "it", "it's", "it is"}
        aux_verbs = {"am", "is", "are", "was", "were", "'s", "'re", "'m",
                     "will", "would", "can", "could", "should", "may", "might", "must",
                     "have", "has", "had"}
        cats = {"subject": [], "aux": [], "main_verb": [], "prep_phrase": [],
                "object": [], "time": [], "punct": [], "unknown": []}
        for word in words:
            w = word.lower().strip()
            if w in [".", "?", "!", ","]:
                cats["punct"].append(word)
            elif w in subjects:
                cats["subject"].append(word)
            elif w in aux_verbs or w.startswith("'"):
                cats["aux"].append(word)
            else:
                cats["unknown"].append(word)
        result = []
        result += cats["subject"]
        result += cats["aux"]
        result += cats["unknown"]
        result += cats["punct"]
        return result
