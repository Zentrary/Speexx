"""BaseSolver: shared DOM helpers, action buttons, scoring, caching, and drag primitives."""

import copy
import re
import time
from datetime import datetime
from difflib import SequenceMatcher

from ..constants import ACTION_SETTLE_SECONDS, FAST_ACTION_SETTLE_SECONDS
from ..ui_utils import Fore, Style


class BaseSolver:
    PASS_LINE = 51

    def __init__(self, page, logger, answer_db=None, page_answer_index=None, diagnostic_cb=None):
        self.page = page
        self.logger = logger
        self.answer_db = answer_db if answer_db is not None else {}
        self.page_answer_index = page_answer_index if page_answer_index is not None else {}
        self.diagnostic_cb = diagnostic_cb
        self.exercise_title = ""
        self.page_number = 0
        self.start_time = None
        self.end_time = None
        self._initial_question_text = None
        self._initial_prompt_text = None
        self.last_recorded_question = None
        self.last_recorded_prompt = None
        self.last_recorded_answer = None

    def solve(self):
        raise NotImplementedError

    def start_timer(self):
        self.start_time = time.time()

    def stop_timer(self):
        if not self.start_time:
            return "N/A"
        self.end_time = time.time()
        elapsed = self.end_time - self.start_time
        minutes = int(elapsed // 60)
        seconds = elapsed % 60
        if minutes > 0:
            return f"{minutes}m {seconds:.2f}s"
        return f"{seconds:.2f}s"

    def step(self, msg):
        print(f"    >> {msg}")
        self.logger.info(f"STEP: {msg}")

    def verify_step(self, step_name, ok, detail=""):
        suffix = f" ({detail})" if detail else ""
        if ok:
            print(f"    {Fore.GREEN}[CHECK OK]{Style.RESET_ALL} {step_name}{suffix}")
            self.logger.info(f"[CHECK OK] {step_name}{suffix}")
        else:
            print(f"    {Fore.YELLOW}[CHECK !!]{Style.RESET_ALL} {step_name}{suffix}")
            self.logger.warning(f"[CHECK FAIL] {step_name}{suffix}")
        return ok

    def report_problem(self, reason, extra=None):
        self.logger.warning(f"[PROBLEM] {reason} | extra={extra}")
        if callable(self.diagnostic_cb):
            try:
                self.diagnostic_cb(
                    reason,
                    exercise_title=self.exercise_title,
                    page_number=self.page_number,
                    solver_name=self.__class__.__name__,
                    extra=extra,
                )
            except Exception as e:
                self.logger.debug(f"[PROBLEM] diagnostic_cb error: {e}")

    def _wait_until_js(self, js_fn, arg=None, timeout=4.0, interval=0.055):
        deadline = time.time() + max(0.05, float(timeout))
        last_val = None
        while True:
            try:
                last_val = (
                    self.page.evaluate(js_fn)
                    if arg is None
                    else self.page.evaluate(js_fn, arg)
                )
                if last_val:
                    return last_val
            except Exception:
                pass
            if time.time() >= deadline:
                break
            time.sleep(interval)
        return last_val

    def _normalise_question_text(self, text):
        if text is None:
            return ""
        cleaned = str(text).replace("\xa0", " ").replace("\n", " ").replace("\t", " ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned.casefold()

    def _extract_prompt_text(self):
        try:
            for sel in [".instructions-text", ".exercise-instructions", "h2.instructions"]:
                el = self.page.locator(sel).first
                if el.count() > 0:
                    txt = el.inner_text().strip()
                    if txt:
                        return txt
        except Exception:
            pass
        return ""

    def capture_initial_context(self):
        q = self._extract_question_text()
        if q and q != "Unknown Question":
            self._initial_question_text = q
        p = self._extract_prompt_text()
        if p:
            self._initial_prompt_text = p

    def record_answer(self, answer_type, answers, verified=True, **extra):
        entry = {
            "type": answer_type,
            "answers": copy.deepcopy(answers),
            "timestamp": datetime.now().isoformat(),
        }
        for k, v in extra.items():
            if v is not None:
                entry[k] = copy.deepcopy(v)
        if not verified:
            entry["verified"] = False

        q_text = self._initial_question_text or self._extract_question_text()
        p_text = self._initial_prompt_text or self._extract_prompt_text() or ""
        self.last_recorded_question = q_text
        self.last_recorded_prompt = p_text
        self.last_recorded_answer = copy.deepcopy(entry)

        if self.answer_db is not None and q_text:
            existing = self.answer_db.get(q_text)
            existing_verified = (
                isinstance(existing, dict) and existing.get("verified", True) is not False
            )
            if verified or not existing_verified:
                self.answer_db[q_text] = copy.deepcopy(entry)

        if (verified and self.page_answer_index is not None
                and self.exercise_title and self.page_number):
            idx_key = (self.exercise_title.strip().casefold(), int(self.page_number))
            self.page_answer_index[idx_key] = copy.deepcopy(entry)

        return entry

    def extract_current_state_answers(self, verified=True):
        return None

    def extract_fallback_page_record(self, fallback_type="unknown", verified=False):
        try:
            current = self.extract_current_state_answers(verified=verified)
            if isinstance(current, dict):
                return current
        except Exception as e:
            self.logger.debug(f"[DB] extract_current_state_answers fallback error: {e}")

        raw_items = []
        try:
            for item in self.page.locator(".exercise-items .item").all():
                txt = " ".join((item.inner_text() or "").split()).strip()
                if txt:
                    raw_items.append(txt)
        except Exception:
            pass
        return self.record_answer(fallback_type, raw_items, verified=verified)

    def _is_usable_cached_entry(self, entry, expected_type=None):
        if not isinstance(entry, dict):
            return False
        if entry.get("verified", True) is False:
            return False
        if expected_type and entry.get("type") != expected_type:
            return False
        return True

    def _find_cached_answer(self, question_text=None, expected_type=None):
        if self.page_answer_index and self.exercise_title and self.page_number:
            idx_key = (self.exercise_title.strip().casefold(), int(self.page_number))
            indexed = self.page_answer_index.get(idx_key)
            if self._is_usable_cached_entry(indexed, expected_type):
                return copy.deepcopy(indexed)

        if not self.answer_db:
            return None

        source = (
            question_text
            if question_text is not None
            else (self._initial_question_text or self._extract_question_text())
        )
        if not source:
            return None

        exact = self.answer_db.get(source)
        if self._is_usable_cached_entry(exact, expected_type):
            return copy.deepcopy(exact)

        source_norm = self._normalise_question_text(source)
        if not source_norm:
            return None

        best_value = None
        best_score = 0.0
        for key, value in self.answer_db.items():
            if not isinstance(key, str) or not self._is_usable_cached_entry(value, expected_type):
                continue
            key_norm = self._normalise_question_text(key)
            if not key_norm:
                continue
            if key_norm == source_norm:
                return copy.deepcopy(value)
            shorter_len = min(len(source_norm), len(key_norm))
            longer_len = max(len(source_norm), len(key_norm))
            if (shorter_len >= 45 and longer_len > 0
                    and (shorter_len / longer_len) >= 0.75
                    and (source_norm in key_norm or key_norm in source_norm)):
                return copy.deepcopy(value)
            score = SequenceMatcher(None, source_norm[:2000], key_norm[:2000]).ratio()
            if score > best_score:
                best_score = score
                best_value = value

        if best_score >= 0.85 and best_value is not None:
            return copy.deepcopy(best_value)
        return None

    def _extract_question_text(self):
        try:
            parts = []
            for sel in [".instructions-text", "h1.exercise-header", ".exercise-items"]:
                el = self.page.locator(sel).first
                if el.count() > 0:
                    txt = el.inner_text().strip()
                    if txt:
                        parts.append(txt)
            if len(parts) <= 1:
                gap_el = self.page.locator(".gap-container").first
                if gap_el.count() > 0:
                    gtxt = gap_el.inner_text().strip()
                    if gtxt and gtxt not in parts:
                        parts.append(gtxt)
            if parts:
                return " | ".join(parts)
        except Exception:
            pass

        try:
            url = self.page.url
            if url:
                clean_url = url.split('?')[0]
                return f"URL_Fallback_{clean_url}"
        except Exception:
            pass

        return "Unknown Question"

    def _safe_click(self, locator, timeout=5000, description=""):
        try:
            if locator.count() == 0:
                return False
            if not locator.is_visible(timeout=2000):
                return False
        except Exception:
            return False

        try:
            locator.click(timeout=timeout)
            return True
        except Exception as e:
            self.logger.debug(f"[SAFE_CLICK] normal fail ({description}): {str(e)[:100]}")

        try:
            self.page.evaluate("""
                () => {
                    document.querySelectorAll(
                        '.no-editable, .exercise-bottom-bar-opaque-box, [class*="opaque"]'
                    ).forEach(el => {
                        try {
                            el.style.pointerEvents = 'none';
                            el.style.zIndex = '-1';
                        } catch(e) {}
                    });
                }
            """)
        except Exception:
            pass

        try:
            locator.click(timeout=timeout, force=True)
            return True
        except Exception as e:
            self.logger.debug(f"[SAFE_CLICK] force fail ({description}): {str(e)[:100]}")

        try:
            locator.evaluate("el => el.click()")
            return True
        except Exception as e:
            self.logger.debug(f"[SAFE_CLICK] JS fail ({description}): {str(e)[:100]}")

        return False

    def _click_first_matching(self, selectors, description="", vis_timeout=2000, click_timeout=5000):
        for sel in selectors:
            try:
                loc = self.page.locator(sel)
                count = loc.count()
                for i in range(min(count, 4)):
                    btn = loc.nth(i)
                    try:
                        if btn.is_visible(timeout=vis_timeout):
                            if self._safe_click(btn, timeout=click_timeout, description=description):
                                return True
                    except Exception:
                        continue
            except Exception:
                continue
        return False

    def _locate_action_button(self, kind, wait_timeout=1.8):
        if not self.page:
            return None
        found = self._wait_until_js(
            """
            (targetKind) => {
                document.querySelectorAll('[data-speexx-action-target]').forEach(el => {
                    el.removeAttribute('data-speexx-action-target');
                });
                const isVis = (el) => {
                    if (!el || el.disabled || el.getAttribute('aria-disabled') === 'true') return false;
                    let cur = el;
                    while (cur && cur.nodeType === 1) {
                        if (cur.hasAttribute('hidden') || cur.getAttribute('aria-hidden') === 'true') return false;
                        const st = window.getComputedStyle(cur);
                        if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') return false;
                        cur = cur.parentElement;
                    }
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                };
                const isModalBtn = (el) => Boolean(
                    el.closest('.circliful-and-results, .modal-results, .modal-dialog, [role="dialog"]')
                );
                const buttons = Array.from(document.querySelectorAll("button, [role='button'], a.btn"));
                const matches = [];
                for (const b of buttons) {
                    if (!isVis(b)) continue;
                    if ((targetKind === 'repeat' || targetKind === 'next' || targetKind === 'correction') && isModalBtn(b)) {
                        continue;
                    }
                    const cls = (b.className || '').toString().toLowerCase();
                    const aria = (b.getAttribute('aria-label') || '').trim().toLowerCase();
                    const title = (b.getAttribute('title') || '').trim().toLowerCase();
                    const txt = (b.innerText || b.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    const meta = aria + ' ' + title + ' ' + txt;
                    let prio = 0;

                    if (targetKind === 'correction') {
                        if (/\\bcorrect\\b/.test(cls) && cls.includes('action-exercise-button')) prio = 100;
                        else if (/\\bcorrect\\b/.test(cls)) prio = 90;
                        else if (/(\\bcorrection\\b|\\bcheck\\b|ตรวจคำตอบ|ตรวจสอบ)/.test(meta) || txt === 'ตรวจ') prio = 75;
                    } else if (targetKind === 'solution') {
                        if (/\\bsolution\\b/.test(cls)) prio = 100;
                        else if (/(\\bsolution\\b|show solution|ดูเฉลย|เฉลย)/.test(meta)) prio = 80;
                    } else if (targetKind === 'repeat') {
                        if (/\\brepeat\\b/.test(cls) && cls.includes('action-exercise-button')) prio = 100;
                        else if (/\\brepeat\\b/.test(cls)) prio = 90;
                        else if (/(\\brepeat\\b|try again|\\bretry\\b|ทำซ้ำ|ลองอีกครั้ง|ลองใหม่)/.test(meta)) prio = 75;
                    } else if (targetKind === 'start') {
                        if (cls.includes('start-exercise')) prio = 100;
                        else if (aria === 'start' || aria === 'เริ่ม' || txt === 'start' || txt === 'เริ่มต้น' || txt === 'เริ่ม') prio = 80;
                    } else if (targetKind === 'next') {
                        if (/\\bnext\\b/.test(cls) && cls.includes('action-exercise-button')) prio = 100;
                        else if (/(\\bnext\\b|ถัดไป)/.test(meta)) prio = 75;
                    }

                    if (prio > 0) {
                        matches.push({ el: b, prio });
                    }
                }
                if (!matches.length) return false;
                matches.sort((a, b) => b.prio - a.prio);
                matches[0].el.setAttribute('data-speexx-action-target', targetKind);
                return true;
            }
            """,
            arg=kind,
            timeout=wait_timeout,
            interval=0.055,
        )
        if found:
            return self.page.locator(f"[data-speexx-action-target='{kind}']").first
        return None

    def _is_post_correction_ready(self):
        try:
            return bool(self.page.evaluate("""
                () => {
                    const isVis = (el) => {
                        if (!el) return false;
                        const st = window.getComputedStyle(el);
                        if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') return false;
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                    };
                    if (isVis(document.querySelector('.result-badge-text'))) return true;
                    if (isVis(document.querySelector('.exercise-result-container'))) return true;
                    if (isVis(document.querySelector('.circliful-and-results'))) return true;
                    for (const b of document.querySelectorAll("button, [role='button'], a")) {
                        if (!isVis(b)) continue;
                        const cls = (b.className || '').toString().toLowerCase();
                        const txt = ((b.innerText || b.textContent || '') + ' ' + (b.getAttribute('aria-label') || '')).toLowerCase();
                        if (/\\b(solution|repeat)\\b/.test(cls)) return true;
                        if (/(solution|เฉลย|repeat|try again|ทำซ้ำ|continue learning|เรียนรู้ต่อ)/.test(txt)) return true;
                    }
                    const graded = document.querySelector(
                        '.status-green, .status-red, .result-green, .result-red, .score-bar, .result-bar'
                    );
                    if (graded) return true;
                    const bodyTxt = (document.body ? (document.body.innerText || '') : '');
                    if (/(Very good|Excellent|Well done|Great job|Try again|You can do better|100\\/100 Result|ดีมาก|ยอดเยี่ยม|ทำได้ดีมาก|ลองอีกครั้ง)/.test(bodyTxt)) {
                        return true;
                    }
                    return false;
                }
            """))
        except Exception:
            return False

    def already_passed(self):
        if getattr(self, 'force_solve', False):
            return False
        try:
            score = self.get_result_score(wait_for_score=False)
            return score >= self.PASS_LINE
        except Exception:
            return False

    def click_correction(self, settle=ACTION_SETTLE_SECONDS):
        self._handle_audio_setup_modal()
        selectors = [
            "button.action-exercise-button.correct",
            "button.correct",
            "button[aria-label*='Correction' i]",
            "button[aria-label*='Check' i]",
            "button[aria-label*='ตรวจ']",
            "button:has-text('Check')",
            "button:has-text('Correction')",
            "button:has-text('ตรวจคำตอบ')",
            "button:has-text('ตรวจ')",
        ]
        try:
            clicked = False
            fast_btn = self._locate_action_button("correction", wait_timeout=1.6)
            if fast_btn is not None:
                clicked = self._safe_click(fast_btn, timeout=3500, description="correction")
            if not clicked:
                clicked = self._click_first_matching(selectors, description="correction", vis_timeout=600)

            if not clicked:
                self.verify_step("กดปุ่มตรวจสอบ [Correction]", False, "ไม่พบปุ่มตรวจสอบ")
                return False

            ready = self._wait_until_js(
                """
                () => {
                    const isVis = (el) => {
                        if (!el) return false;
                        const st = window.getComputedStyle(el);
                        if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') return false;
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                    };
                    if (isVis(document.querySelector('.result-badge-text'))) return true;
                    if (isVis(document.querySelector('.exercise-result-container'))) return true;
                    if (isVis(document.querySelector('.circliful-and-results'))) return true;
                    for (const b of document.querySelectorAll("button, [role='button'], a")) {
                        if (!isVis(b)) continue;
                        const cls = (b.className || '').toString().toLowerCase();
                        const txt = ((b.innerText || b.textContent || '') + ' ' + (b.getAttribute('aria-label') || '')).toLowerCase();
                        if (/\\b(solution|repeat)\\b/.test(cls)) return true;
                        if (/(solution|เฉลย|repeat|try again|ทำซ้ำ|continue learning|เรียนรู้ต่อ)/.test(txt)) return true;
                    }
                    if (document.querySelector('.status-green, .status-red, .result-green, .result-red, .score-bar, .result-bar')) return true;
                    const bodyTxt = (document.body ? (document.body.innerText || '') : '');
                    return /(Very good|Excellent|Well done|Great job|Try again|You can do better|100\\/100 Result|ดีมาก|ยอดเยี่ยม|ทำได้ดีมาก|ลองอีกครั้ง)/.test(bodyTxt);
                }
                """,
                timeout=1.6,
                interval=0.055,
            )
            if not ready:
                retry_btn = self._locate_action_button("correction", wait_timeout=0.5)
                if retry_btn is not None:
                    self._safe_click(retry_btn, timeout=2500, description="correction-retry")
                ready = self._wait_until_js(
                    "() => Boolean(document.querySelector('.result-badge-text, button.solution, button.repeat, .status-green, .status-red'))",
                    timeout=max(0.8, settle),
                    interval=0.06,
                )
            self.verify_step("กดปุ่มตรวจสอบ [Correction]", True, "ตรวจคำตอบแล้ว" if ready else "คลิกแล้ว")
            return True
        except Exception as e:
            self.logger.error(f"Failed Correction: {str(e)}")
            self.verify_step("กดปุ่มตรวจสอบ [Correction]", False, str(e)[:80])
        return False

    def click_next(self):
        selectors = [
            "button.action-exercise-button.next",
            "button[aria-label*='Next' i]",
            "button[aria-label*='ถัดไป']",
            "button:has-text('Next')",
            "button:has-text('ถัดไป')",
        ]
        try:
            clicked = False
            fast_btn = self._locate_action_button("next", wait_timeout=0.9)
            if fast_btn is not None:
                clicked = self._safe_click(fast_btn, timeout=3000, description="next")
            if not clicked:
                clicked = self._click_first_matching(selectors, description="next", vis_timeout=500)
            if clicked:
                self.step("Clicked [Next]")
                time.sleep(FAST_ACTION_SETTLE_SECONDS)
                return True
        except Exception as e:
            self.logger.error(f"Failed Next: {str(e)}")
        return False

    def click_solution(self, settle=ACTION_SETTLE_SECONDS):
        selectors = [
            "button.solution",
            "button.action-exercise-button.solution",
            "button[aria-label*='Solution' i]",
            "button[aria-label*='เฉลย']",
            "button:has-text('Solution')",
            "button:has-text('Show solution')",
            "button:has-text('เฉลย')",
            "button:has-text('ดูเฉลย')",
        ]
        try:
            clicked = False
            fast_btn = self._locate_action_button("solution", wait_timeout=2.6)
            if fast_btn is not None:
                clicked = self._safe_click(fast_btn, timeout=3500, description="solution")
            if not clicked:
                clicked = self._click_first_matching(selectors, description="solution", vis_timeout=600)

            if not clicked:
                self.verify_step("รอและกดปุ่มเฉลย [Solution]", False, "ไม่มีปุ่มเฉลยในข้อนี้")
                return False

            # Wait briefly until solution state updates in DOM
            self._wait_until_js(
                """
                () => {
                    const inputs = Array.from(document.querySelectorAll("input.answer, input.answer-gap"));
                    if (inputs.length && inputs.some(i => (i.value || '').trim().length > 0)) return true;
                    const phTiles = document.querySelectorAll(".exercise-items .drag-drop-placeholder .drag-drop, .exercise-items .scrambled-cell-container .scrambled-cell");
                    if (phTiles.length > 0) return true;
                    const checked = document.querySelectorAll("input.choice:checked, .choice-option.correct, .choice-option.success, .word.selected, .mark-text.selected");
                    if (checked.length > 0) return true;
                    const gaps = Array.from(document.querySelectorAll(".exercise-items .gap"));
                    if (gaps.length && gaps.some(g => (g.innerText || '').trim().length > 0)) return true;
                    const blocks = document.querySelectorAll(".scrambled-sentence .scrambled-block");
                    if (blocks.length > 0) return true;
                    const imgs = document.querySelectorAll(".exercise-items .item img");
                    if (imgs.length > 0) return true;
                    return false;
                }
                """,
                timeout=max(0.8, settle + 1.2),
                interval=0.055,
            )
            time.sleep(0.08)
            self.verify_step("รอและกดปุ่มเฉลย [Solution]", True, "แสดงเฉลยพร้อมดึงข้อมูลแล้ว")
            return True
        except Exception as e:
            self.logger.error(f"Failed Solution: {str(e)}")
            self.verify_step("รอและกดปุ่มเฉลย [Solution]", False, str(e)[:80])
        return False

    def click_repeat(self, settle=ACTION_SETTLE_SECONDS):
        selectors = [
            "button.action-exercise-button.repeat",
            "button.text-button-custom.repeat",
            "button.repeat",
            "button[aria-label*='Repeat' i]",
            "button[aria-label*='Retry' i]",
            "button[aria-label*='ทำซ้ำ']",
            "button:has-text('Repeat')",
            "button:has-text('Try again')",
            "button:has-text('Retry')",
            "button:has-text('ทำซ้ำ')",
            "button:has-text('ลองอีกครั้ง')",
            "button:has-text('ลองใหม่')",
        ]
        try:
            clicked = False
            fast_btn = self._locate_action_button("repeat", wait_timeout=2.2)
            if fast_btn is not None:
                clicked = self._safe_click(fast_btn, timeout=3500, description="repeat")
            if not clicked:
                clicked = self._click_first_matching(selectors, description="repeat", vis_timeout=500)

            if not clicked:
                self.verify_step("กดปุ่มทำซ้ำ [Repeat]", False, "ไม่พบปุ่มทำซ้ำ")
                return False

            reset_ok = self._wait_until_js(
                """
                () => {
                    const isVis = (el) => {
                        if (!el || el.disabled) return false;
                        if (el.closest('.circliful-and-results, .modal, .modal-dialog')) return false;
                        const st = window.getComputedStyle(el);
                        if (!st || st.display === 'none' || st.visibility === 'hidden' || parseFloat(st.opacity || '1') === 0) return false;
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                    };
                    const inputs = Array.from(document.querySelectorAll('input.answer, input.answer-gap'));
                    if (inputs.length > 0 && inputs.some(inp => inp.disabled || inp.readOnly)) {
                        return false;
                    }
                    for (const b of document.querySelectorAll("button, [role='button']")) {
                        if (!isVis(b)) continue;
                        const cls = (b.className || '').toString().toLowerCase();
                        const txt = ((b.innerText || b.textContent || '') + ' ' + (b.getAttribute('aria-label') || '')).toLowerCase();
                        if (/\\b(correction|correct|start-exercise)\\b/.test(cls)) return true;
                        if (/(\\bcheck\\b|\\bcorrection\\b|ตรวจคำตอบ|ตรวจสอบ|\\bstart\\b|เริ่มต้น)/.test(txt)) return true;
                    }
                    return false;
                }
                """,
                timeout=max(1.5, settle + 1.8),
                interval=0.05,
            )
            time.sleep(0.12)
            if self.has_start_button():
                self.click_start()
            self.verify_step("กดปุ่มทำซ้ำ [Repeat]", True, "รีเซ็ตหน้าพร้อมกรอกคำตอบแล้ว" if reset_ok else "คลิกแล้ว")
            return True
        except Exception as e:
            self.logger.error(f"Failed Repeat: {str(e)}")
            self.verify_step("กดปุ่มทำซ้ำ [Repeat]", False, str(e)[:80])
        return False

    def _start_button_selectors(self):
        return [
            "button.start-exercise",
            "button[aria-label='Start' i]",
            "button[aria-label='เริ่ม']",
            "button:has-text('Start')",
            "button:has-text('เริ่มต้น')",
            "button:has-text('เริ่ม')",
        ]

    def click_start(self):
        try:
            clicked = False
            fast_btn = self._locate_action_button("start", wait_timeout=1.2)
            if fast_btn is not None:
                clicked = self._safe_click(fast_btn, timeout=3000, description="start")
            if not clicked:
                clicked = self._click_first_matching(
                    self._start_button_selectors(), description="start", vis_timeout=500
                )
            if clicked:
                self._wait_until_js(
                    """
                    () => {
                        const s = document.querySelector("button.start-exercise");
                        if (s) {
                            const st = window.getComputedStyle(s);
                            const r = s.getBoundingClientRect();
                            if (st.display !== 'none' && st.visibility !== 'hidden' && r.width > 0 && r.height > 0) {
                                return false;
                            }
                        }
                        return Boolean(document.querySelector('.exercise-items, video, input.answer, .drag-drop'));
                    }
                    """,
                    timeout=2.5,
                    interval=0.055,
                )
                new_prompt = self._extract_prompt_text()
                if new_prompt:
                    self._initial_prompt_text = new_prompt
                self.verify_step("กดปุ่มเริ่ม [Start]", True)
                return True
        except Exception as e:
            self.logger.error(f"Failed Start: {str(e)}")
        return False

    def has_start_button(self):
        try:
            return bool(self.page.evaluate("""
                () => {
                    for (const b of document.querySelectorAll("button, [role='button']")) {
                        if (b.disabled) continue;
                        const st = window.getComputedStyle(b);
                        if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') continue;
                        const r = b.getBoundingClientRect();
                        if (r.width <= 0 || r.height <= 0) continue;
                        const cls = (b.className || '').toString().toLowerCase();
                        const aria = (b.getAttribute('aria-label') || '').trim().toLowerCase();
                        const txt = (b.innerText || b.textContent || '').trim().toLowerCase();
                        if (cls.includes('start-exercise') || aria === 'start' || aria === 'เริ่ม' ||
                            txt === 'start' || txt === 'เริ่มต้น' || txt === 'เริ่ม') {
                            return true;
                        }
                    }
                    return false;
                }
            """))
        except Exception:
            return False

    def _read_score_once_js(self):
        try:
            val = self.page.evaluate("""
                () => {
                    const isVis = (el) => {
                        if (!el) return false;
                        const st = window.getComputedStyle(el);
                        if (st.display === 'none' || st.visibility === 'hidden') return false;
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                    };

                    const badge = document.querySelector('.result-badge-text');
                    if (badge && isVis(badge)) {
                        const dr = badge.getAttribute('data-result');
                        if (dr !== null && dr !== '' && !isNaN(parseInt(dr, 10))) {
                            return parseInt(dr, 10);
                        }
                        const m = (badge.innerText || badge.textContent || '').match(/\\d+/);
                        if (m) return parseInt(m[0], 10);
                    }

                    for (const sel of ['.exercise-result-container .text', '.circliful-container-results .timer .number']) {
                        const el = document.querySelector(sel);
                        if (el && isVis(el)) {
                            const m = (el.innerText || el.textContent || '').match(/\\d+/);
                            if (m) return parseInt(m[0], 10);
                        }
                    }

                    const clone = document.body ? document.body.cloneNode(true) : null;
                    const nonBtnText = (() => {
                        if (!clone) return '';
                        clone.querySelectorAll('button, script, style').forEach(el => el.remove());
                        return (clone.innerText || clone.textContent || '');
                    })();

                    const resMatch = nonBtnText.match(/(\\d{1,3})\\s*\\/\\s*100\\s*Result/i);
                    if (resMatch) {
                        return parseInt(resMatch[1], 10);
                    }

                    const passPhrases = [
                        'Very good!', 'Very good', 'Excellent', 'Well done', 'Perfect',
                        'Great job', 'Good job', 'Nice work', 'Congratulations',
                        'ดีมาก', 'ยอดเยี่ยม', 'ยอดมาก', 'ทำได้ดีมาก', 'เก่งมาก'
                    ];
                    const failPhrases = [
                        'Try again', 'You can do better', 'Not quite', 'Keep trying',
                        'Have another go', 'ลองอีกครั้ง', 'พยายามอีกครั้ง', 'คุณทำได้ดีกว่านี้'
                    ];
                    for (const p of passPhrases) {
                        if (nonBtnText.includes(p)) return 100;
                    }
                    for (const f of failPhrases) {
                        if (nonBtnText.includes(f)) return 0;
                    }

                    const bars = Array.from(document.querySelectorAll(".score-bar, .result-bar, [class*='bar-']")).filter(isVis);
                    if (bars.length > 0) {
                        let greenCount = 0;
                        for (const bar of bars) {
                            const cls = (bar.className || '').toString().toLowerCase();
                            if (cls.includes('green') || cls.includes('success')) greenCount++;
                        }
                        if (greenCount === bars.length) return 100;
                        if (greenCount > 0) return Math.floor((greenCount / bars.length) * 100);
                    }

                    const greens = document.querySelectorAll(
                        ".icon-acepted-checkmark.status-green, .icon-accepted-checkmark.status-green, .result-container [class*='success'], .result-container [class*='result-green']"
                    );
                    if (greens.length > 0) return 100;

                    return -1;
                }
            """)
            if isinstance(val, (int, float)) and val >= 0:
                return int(val)
            return None
        except Exception:
            return None

    def get_result_score(self, wait_for_score=True):
        try:
            score = self._read_score_once_js()
            if score is not None:
                return score
            if wait_for_score:
                deadline = time.time() + 0.55
                while time.time() < deadline:
                    time.sleep(0.06)
                    score = self._read_score_once_js()
                    if score is not None:
                        return score
            return 0
        except Exception:
            return 0

    def wait_for_page_ready(self):
        try:
            self.page.wait_for_selector(".exercise, .video", state="visible", timeout=10000)
            self._wait_until_js(
                "() => Boolean(document.querySelector('.exercise-items, video, button.start-exercise, .instructions-text'))",
                timeout=1.5,
                interval=0.05,
            )
            return True
        except Exception:
            return False

    def precise_drag(self, source, target):
        for attempt in range(2):
            try:
                try:
                    source.scroll_into_view_if_needed(timeout=1500)
                except Exception:
                    pass
                try:
                    target.scroll_into_view_if_needed(timeout=1500)
                except Exception:
                    pass
                time.sleep(0.04)
                source_box = source.bounding_box()
                target_box = target.bounding_box()
                if not source_box or not target_box:
                    return False
                sx = source_box['x'] + source_box['width'] / 2
                sy = source_box['y'] + source_box['height'] / 2
                tx = target_box['x'] + target_box['width'] / 2
                ty = target_box['y'] + target_box['height'] / 2
                self.page.mouse.move(sx, sy)
                time.sleep(0.04)
                self.page.mouse.down()
                time.sleep(0.05)
                self.page.mouse.move(sx + 6, sy + 6)
                time.sleep(0.03)
                steps = 10
                for step_i in range(1, steps + 1):
                    x = sx + (tx - sx) * step_i / steps
                    y = sy + (ty - sy) * step_i / steps
                    self.page.mouse.move(x, y)
                    time.sleep(0.012)
                self.page.mouse.move(tx, ty)
                time.sleep(0.08)
                self.page.mouse.move(tx + 1, ty)
                time.sleep(0.04)
                self.page.mouse.move(tx, ty)
                time.sleep(0.04)
                self.page.mouse.up()
                time.sleep(0.08)
                return True
            except Exception as e:
                self.logger.error(f"Drag error (attempt {attempt+1}): {str(e)}")
                try:
                    self.page.mouse.up()
                except Exception:
                    pass
                time.sleep(0.1)
        return False

    def fast_drag(self, source, target):
        try:
            source.scroll_into_view_if_needed(timeout=1200)
            target.scroll_into_view_if_needed(timeout=1200)
            source_box = source.bounding_box()
            target_box = target.bounding_box()
            if not source_box or not target_box:
                return False
            sx = source_box["x"] + source_box["width"] / 2
            sy = source_box["y"] + source_box["height"] / 2
            tx = target_box["x"] + target_box["width"] / 2
            ty = target_box["y"] + target_box["height"] / 2
            self.page.mouse.move(sx, sy)
            self.page.mouse.down()
            time.sleep(0.025)
            self.page.mouse.move(sx + 5, sy + 5)
            time.sleep(0.02)
            self.page.mouse.move((sx + tx) / 2, (sy + ty) / 2)
            time.sleep(0.02)
            self.page.mouse.move(tx, ty)
            time.sleep(0.04)
            self.page.mouse.up()
            time.sleep(0.04)
            return True
        except Exception as e:
            self.logger.debug(f"[FAST_DRAG] failed: {str(e)[:120]}")
            try:
                self.page.mouse.up()
            except Exception:
                pass
            return False

    def _handle_audio_setup_modal(self):
        try:
            close_btn = self.page.locator(
                "button.close[data-dismiss='modal'], #exit-icon, "
                "div.modal-content button.close, .modal button[aria-label='Close' i], "
                ".modal button[aria-label='ปิด']"
            ).first
            if close_btn.count() > 0 and close_btn.is_visible(timeout=500):
                self.logger.info("[AUDIO] Audio setup popup detected. Closing immediately...")
                self._safe_click(close_btn, timeout=3000, description="audio setup close")
                self.step("Closed Audio setup popup")
                time.sleep(0.5)
                return True
        except Exception as e:
            self.logger.debug(f"[AUDIO] Error checking/handling audio setup modal: {e}")
        return False
