"""ModalAndPageMixin: exercise page navigation, Completion Modal handling, summary reports, and HTML dumps."""

import os
import re
import time
from datetime import datetime

from ..solvers import ExerciseEngine
from ..ui_utils import Fore, Style, pad_display, truncate_display


class ModalAndPageMixin:
    def open_exercise_menu(self, title, row_index=None):
        self.print_header()
        print(f"  {Fore.CYAN}--- {self.T['exercise_menu']}: {title} ---{Style.RESET_ALL}\n")
        print(f"  {Fore.WHITE}[1]{Style.RESET_ALL} {self.T['opt_new_learning_path']}")
        print(f"  {Fore.WHITE}[2]{Style.RESET_ALL} {self.T['opt_dump']}")
        print(f"  {Fore.WHITE}[0]{Style.RESET_ALL} {self.T['back']}")
        try:
            c = self._input(f"\n  {Fore.CYAN}[>] Select: {Style.RESET_ALL}").strip()
            if c == "" or c == "0":
                return
            if c == "1":
                self.start_new_learning_path(title, row_index=row_index)
            elif c == "2":
                self.dump_all_exercise_pages(title, row_index=row_index)
        except ValueError:
            pass

    def dump_all_exercise_pages(self, title, row_index=None):
        self.print_status("INFO", f"Dumping {title}...")
        try:
            self._ensure_chapter_db_loaded(announce=False)
            if not self._click_row_safely(title, row_index=row_index):
                self.print_status("ERROR", f"Cannot open '{title}'")
                self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
                return
            time.sleep(2)
            total = self.get_total_exercises()
            if total == 0:
                self.print_status("ERROR", "Cannot determine total.")
                self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
                return
            engine = ExerciseEngine(
                self.page,
                self.logger,
                answer_db=self.answer_db,
                page_answer_index=self.page_answer_index,
            )
            safe = re.sub(r'[\\/*?:"<>|]', "", title).replace(" ", "_")
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            for i in range(1, total + 1):
                self.navigate_to_exercise_page(i)
                time.sleep(1)
                fn = f"{self.dump_folder}/{safe}_exercise_{i}_{ts}.html"
                with open(fn, "w", encoding="utf-8") as f:
                    f.write(self.page.content())
                et = engine.detect_type()
                solver = engine.get_solver(et, exercise_title=title, page_number=i)
                if solver is not None:
                    try:
                        is_passed = solver.get_result_score() >= solver.PASS_LINE
                        solver.extract_current_state_answers(verified=is_passed)
                    except Exception:
                        pass
                self._record_page_to_db(title, i, total, et, solver=solver, persist=True)
                self.print_status("OK", f"Dumped {i}/{total}: {fn}")
            self.print_status("OK", "All dumped.")
            self.print_status("INFO", "Returning to exercise list...")
            try:
                self.page.go_back()
                time.sleep(2)
            except Exception:
                pass
            self.navigate_to_results()
            time.sleep(1)
            self.fetch_exercises()
            return
        except Exception as e:
            self.print_status("ERROR", f"Error: {str(e)}")
            self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")

    def get_total_exercises(self, retries=4, wait_seconds=1.5):
        selectors = [
            ".exercises-large-navigation.visible-lg li",
            ".exercises-large-navigation.visible-md li",
            ".exercises-large-navigation.visible-sm li",
            ".exercises-large-navigation li",
            ".exercises-small-navigation li",
        ]
        for attempt in range(retries):
            try:
                for sel in selectors:
                    items = self.page.locator(sel).all()
                    if items:
                        self.logger.info(
                            f"[TOTAL] Found {len(items)} pages via {sel} "
                            f"(attempt {attempt+1}/{retries})"
                        )
                        return len(items)
            except Exception as e:
                self.logger.debug(f"[TOTAL] attempt {attempt+1} error: {e}")

            if attempt < retries - 1:
                time.sleep(wait_seconds)

        self.logger.warning(
            f"[TOTAL] Cannot find exercise navigation after {retries} attempts"
        )
        return 0

    def wait_for_exercise_content_ready(self, timeout=6.0):
        """Wait until the current exercise page has mounted its real type-* class and interactive DOM (or real <video>)."""
        deadline = time.time() + float(timeout)
        start_ts = time.time()
        while time.time() < deadline:
            try:
                ready = bool(
                    self.page.evaluate(
                        """
                        (elapsedSec) => {
                            const isVis = (el) => {
                                if (!el) return false;
                                const st = window.getComputedStyle(el);
                                if (!st || st.display === 'none' || st.visibility === 'hidden' || parseFloat(st.opacity || '1') === 0) {
                                    return false;
                                }
                                const r = el.getBoundingClientRect();
                                return r.width > 4 && r.height > 4;
                            };

                            const exList = Array.from(document.querySelectorAll('.exercise'));
                            const visEx = exList.find(isVis) || exList[0] || null;
                            const cls = visEx ? (visEx.getAttribute('class') || '') : '';
                            const hasTypeClass = /\\btype-[a-z-]+/.test(cls) || cls.includes('pronunciation');

                            if (hasTypeClass) {
                                if (cls.includes('type-intro') || cls.includes('type-video')) {
                                    return true;
                                }
                                const hasInner = Boolean(
                                    document.querySelector(
                                        '.exercise-items .item, .exercise-items input, .exercise-items .drag-drop-placeholder, ' +
                                        '.exercise-items .drag-drop, .exercise-items .gap, .exercise-items .word, ' +
                                        '.draggable-container .drag-drop, button.start-exercise, [class*="pronunciation"]'
                                    )
                                );
                                if (hasInner) return true;
                                if (elapsedSec >= 2.8 && document.querySelector('.exercise-items')) return true;
                            }

                            if (elapsedSec >= 1.2) {
                                const hasVisVideo = Array.from(document.querySelectorAll('video')).some(v => {
                                    if (!isVis(v)) return false;
                                    return Boolean(v.currentSrc || v.src || v.getAttribute('src') || v.querySelector('source[src]') || v.readyState > 0);
                                });
                                if (hasVisVideo) return true;
                            }
                            return false;
                        }
                        """,
                        time.time() - start_ts,
                    )
                )
                if ready:
                    return True
            except Exception:
                pass
            time.sleep(0.1)
        return False

    def navigate_to_exercise_page(self, num):
        try:
            nav_info = self.page.evaluate(
                """
                (targetNum) => {
                    const sels = [
                        '.exercises-large-navigation.visible-lg li',
                        '.exercises-large-navigation.visible-md li',
                        '.exercises-large-navigation.visible-sm li',
                        '.exercises-large-navigation li',
                        '.exercises-small-navigation li'
                    ];
                    for (const sel of sels) {
                        const raw = Array.from(document.querySelectorAll(sel));
                        const vis = raw.filter(el => {
                            const r = el.getBoundingClientRect();
                            return r.width > 0 && r.height > 0;
                        });
                        const items = vis.length > 0 ? vis : raw;
                        if (items.length >= targetNum && targetNum >= 1) {
                            document.querySelectorAll('[data-speexx-nav-target]').forEach(
                                n => n.removeAttribute('data-speexx-nav-target')
                            );
                            const li = items[targetNum - 1];
                            const cls = ((li.className || '') + ' ' + ((li.querySelector('a,span,div') || {}).className || '')).toLowerCase();
                            const alreadyActive = cls.includes('active') || cls.includes('current') || cls.includes('selected');
                            li.setAttribute('data-speexx-nav-target', '1');
                            return { found: true, alreadyActive, total: items.length };
                        }
                    }
                    return { found: false, alreadyActive: false, total: 0 };
                }
                """,
                int(num),
            ) or {}
            if not nav_info.get("found"):
                return False
            if nav_info.get("alreadyActive") and num == 1:
                self.wait_for_exercise_content_ready(timeout=6.0)
                return True

            prev_url = ""
            try:
                prev_url = self.page.url or ""
            except Exception:
                pass

            target = self.page.locator("[data-speexx-nav-target='1']").first
            if target.count() == 0:
                return False
            target.click(timeout=3000)

            # Wait briefly for route `/exercise/<num>` update when SPA uses numbered exercise URLs
            if "/exercise/" in prev_url:
                url_deadline = time.time() + 2.5
                expected_suffix = f"/exercise/{int(num)}"
                while time.time() < url_deadline:
                    cur_u = (self.page.url or "").split("?")[0]
                    if cur_u.endswith(expected_suffix):
                        break
                    time.sleep(0.06)

            self.wait_for_exercise_content_ready(timeout=5.5)
            time.sleep(0.1)
            return True
        except Exception as e:
            self.logger.debug(f"[NAV] navigate_to_exercise_page({num}) error: {e}")
            return False

    def detect_completion_modal(self):
        try:
            return bool(
                self.page.evaluate(
                    """
                    () => {
                        const isVis = (el) => {
                            if (!el) return false;
                            const st = window.getComputedStyle(el);
                            if (!st || st.display === 'none' || st.visibility === 'hidden' || parseFloat(st.opacity || '1') === 0) {
                                return false;
                            }
                            const r = el.getBoundingClientRect();
                            return r.width > 2 && r.height > 2;
                        };

                        for (const sel of [
                            '.circliful-and-results',
                            '.circliful-container-results',
                            '.exercise-result-container',
                            '#nextButton',
                            'button.block-button.btn-primary.next',
                            'button.text-button-custom.repeat'
                        ]) {
                            const nodes = document.querySelectorAll(sel);
                            for (const n of nodes) {
                                if (isVis(n)) return true;
                            }
                        }

                        const clickables = document.querySelectorAll(
                            "button, a, [role='button'], .btn, .block-button"
                        );
                        for (const b of clickables) {
                            if (!isVis(b)) continue;
                            const txt = (b.innerText || b.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                            if (
                                txt === 'continue learning' ||
                                txt === 'เรียนรู้ต่อ' ||
                                txt === 'next exercise' ||
                                txt.includes('continue learning') ||
                                txt.includes('เรียนรู้ต่อ')
                            ) {
                                return true;
                            }
                        }

                        const bodyText = document.body ? (document.body.innerText || '') : '';
                        const low = bodyText.toLowerCase();
                        const hasCongrats = (
                            bodyText.includes('ทำได้ดีมาก') ||
                            bodyText.includes('ยอดเยี่ยม') ||
                            low.includes('great job') ||
                            low.includes('well done') ||
                            low.includes('good job') ||
                            low.includes('congratulations') ||
                            low.includes('exercise completed')
                        );
                        const hasResultCue = (
                            low.includes('/100') ||
                            low.includes('continue learning') ||
                            bodyText.includes('เรียนรู้ต่อ') ||
                            (low.includes('result') && low.includes('repeat')) ||
                            (bodyText.includes('ผลลัพธ์') && bodyText.includes('ทำซ้ำ'))
                        );
                        return Boolean(hasCongrats && hasResultCue);
                    }
                    """
                )
            )
        except Exception:
            return False

    @staticmethod
    def _norm_ex_title(text):
        cleaned = (text or "").replace("🎧", "")
        cleaned = re.sub(r"^[·•\-–—]+\s*", "", cleaned.strip())
        return " ".join(cleaned.split()).strip().casefold()

    @staticmethod
    def _extract_packet_key(url):
        if not url:
            return ""
        clean = str(url).split("?", 1)[0].split("#", 1)[0].rstrip("/")
        m = re.search(r"([a-z0-9_-]*packet/\d+|/packets?/\d+)", clean, re.I)
        if m:
            return m.group(1).strip("/").lower()
        clean = re.sub(r"/exercise/\d+$", "", clean, flags=re.I)
        if clean.lower().endswith("/results") or "/results/" in clean.lower():
            return ""
        return clean.lower()

    def wait_for_completion_modal(self, timeout=15):
        deadline = time.time() + float(timeout)
        start_t = time.time()
        while time.time() < deadline:
            if self._is_on_results_page():
                return False
            if self.detect_completion_modal():
                elapsed = time.time() - start_t
                self.print_status("OK", f"Completion modal detected (after {elapsed:.1f}s)")
                return True
            time.sleep(0.2)
        self.print_status("WAIT", f"Completion modal NOT detected within {timeout}s")
        return False

    def wait_for_modal_settled(self, timeout=5.0):
        """Wait for Completion Modal loading spinner to finish and score + #nextButton to hydrate."""
        deadline = time.time() + float(timeout)
        while time.time() < deadline:
            try:
                settled = bool(
                    self.page.evaluate(
                        """
                        () => {
                            const isVis = (el) => {
                                if (!el) return false;
                                const st = window.getComputedStyle(el);
                                if (!st || st.display === 'none' || st.visibility === 'hidden' || parseFloat(st.opacity || '1') === 0) {
                                    return false;
                                }
                                const r = el.getBoundingClientRect();
                                return r.width > 2 && r.height > 2;
                            };

                            // Check if any loading spinner inside modal/results is still spinning
                            const spinners = document.querySelectorAll(
                                '.circliful-and-results .spinner, .circliful-and-results [us-spinner], ' +
                                '.modal .spinner, .modal [us-spinner], us-spinner .spinner, [class*="loading-spinner"]'
                            );
                            for (const sp of spinners) {
                                if (isVis(sp)) return false;
                            }

                            let hasScore = false;
                            const numEl = document.querySelector('.circliful-container-results .timer .number');
                            if (numEl && /\\d+/.test(numEl.textContent || '')) hasScore = true;
                            const resTexts = document.querySelectorAll('.exercise-result-container .text');
                            if (resTexts.length > 0 && /\\d+/.test(resTexts[0].textContent || '')) hasScore = true;

                            let hasBtn = false;
                            for (const sel of ['#nextButton', 'button.block-button.btn-primary.next', '.modal button.next']) {
                                const b = document.querySelector(sel);
                                if (b && !b.disabled && isVis(b)) {
                                    hasBtn = true;
                                    break;
                                }
                            }
                            return Boolean(hasScore && hasBtn);
                        }
                        """
                    )
                )
                if settled:
                    time.sleep(0.18)
                    return True
            except Exception:
                pass
            time.sleep(0.1)
        return False

    def extract_completion_info(self):
        self.wait_for_modal_settled(timeout=3.5)
        info = {"score": "N/A", "score_max": "N/A", "level": "N/A",
                "progress": "N/A", "time": "N/A", "title": "N/A"}
        try:
            score_num = self.page.locator(".circliful-container-results .timer .number").first
            if score_num.count() > 0:
                info["score"] = score_num.text_content().strip()
            result_container = self.page.locator(".exercise-result-container").first
            if result_container.count() > 0:
                texts = result_container.locator(".text").all()
                if len(texts) >= 2:
                    info["score"] = texts[0].inner_text().strip()
                    info["score_max"] = texts[1].inner_text().strip()
            level_num = self.page.locator(".circliful-container-progress .timer .number").first
            if level_num.count() > 0:
                info["level"] = level_num.text_content().strip()
            prog_text = self.page.locator(".exercise-percentage-container .text").first
            if prog_text.count() > 0:
                info["progress"] = prog_text.text_content().strip()
            try:
                body_text = self.page.locator("body").inner_text(timeout=2000)
                if info["score"] == "N/A":
                    m_sc = re.search(r"\b(\d{1,3})\s*/\s*(100)\b", body_text)
                    if m_sc:
                        info["score"] = m_sc.group(1)
                        info["score_max"] = m_sc.group(2)
                for time_pat in (
                    r"เวลา\s+\d+\s*ชม\.\s*\d+\s*น\.",
                    r"เวลา\s+\d+\s*(?:ชม\.|น\.|วินาที)",
                    r"Time(?:\s+spent)?\s*:?\s*\d+\s*h(?:rs?|ours?)?\s*\d+\s*m(?:in(?:s|utes)?)?",
                    r"Time(?:\s+spent)?\s*:?\s*\d+\s*m(?:in(?:s|utes)?)?(?:\s*\d+\s*s(?:ec)?)?",
                    r"\b\d+\s*h\s*\d+\s*m(?:in)?\b",
                ):
                    m = re.search(time_pat, body_text, re.I)
                    if m:
                        info["time"] = m.group(0).strip()
                        break
                for title_pat in (
                    r"ขั้นตอน\s+\d+\s*[·•:\-]\s*[^\n]+",
                    r"Step\s+\d+\s*[·•:\-]\s*[^\n]+",
                    r"[·•]\s*[^\n]{3,80}",
                ):
                    m2 = re.search(title_pat, body_text, re.I)
                    if m2:
                        info["title"] = m2.group(0).strip()
                        break
            except Exception:
                pass
        except Exception as e:
            self.logger.error(f"extract_completion_info error: {e}")
        return info

    def _close_modal_keep_staying(self):
        """Close a premature completion modal via its X/close button without leaving the exercise."""
        try:
            closed = self.page.evaluate(
                """
                () => {
                    const isVis = (el) => {
                        if (!el) return false;
                        const st = window.getComputedStyle(el);
                        if (!st || st.display === 'none' || st.visibility === 'hidden') return false;
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                    };
                    for (const sel of [
                        '.modal .close',
                        '.modal-dialog .close',
                        '.circliful-and-results .close',
                        "button.close",
                        "[aria-label='Close']",
                        "[aria-label='ปิด']"
                    ]) {
                        for (const el of document.querySelectorAll(sel)) {
                            if (isVis(el)) {
                                el.click();
                                return true;
                            }
                        }
                    }
                    return false;
                }
                """
            )
            if closed:
                time.sleep(0.25)
                return not self.detect_completion_modal()
        except Exception:
            pass
        return False

    def click_modal_repeat(self):
        try:
            for sel in [
                "button.text-button-custom.repeat",
                ".modal button.repeat",
                "button.repeat",
                "button:has-text('ทำซ้ำ')",
                "button:has-text('Repeat')",
                "button:has-text('Try again')",
                "button:has-text('Redo')",
            ]:
                btn = self.page.locator(sel).first
                if btn.count() > 0 and btn.is_visible(timeout=1500):
                    btn.click(timeout=4000, force=True)
                    self.print_status("OK", f"Clicked [{self.T['repeat']}]")
                    deadline = time.time() + 3.0
                    while time.time() < deadline:
                        if not self.detect_completion_modal():
                            break
                        time.sleep(0.1)
                    return True
            return False
        except Exception as e:
            self.print_status("ERROR", f"Repeat click failed: {e}")
            return False

    def click_modal_continue(self):
        self.wait_for_modal_settled(timeout=5.0)
        prev_url = ""
        try:
            prev_url = self.page.url or ""
        except Exception:
            pass

        try:
            for attempt in range(3):
                target_meta = self.page.evaluate(
                    """
                    () => {
                        document.querySelectorAll('[data-speexx-continue-btn]').forEach(
                            n => n.removeAttribute('data-speexx-continue-btn')
                        );
                        const isVis = (el) => {
                            if (!el || el.disabled) return false;
                            const st = window.getComputedStyle(el);
                            if (!st || st.display === 'none' || st.visibility === 'hidden' || parseFloat(st.opacity || '1') === 0) {
                                return false;
                            }
                            const r = el.getBoundingClientRect();
                            return r.width > 4 && r.height > 4;
                        };

                        const prioritySelectors = [
                            '#nextButton',
                            'button.block-button.btn-primary.next',
                            '.modal button.btn-primary.next',
                            '.modal button.next',
                            'a.block-button.btn-primary.next'
                        ];
                        for (const sel of prioritySelectors) {
                            for (const el of document.querySelectorAll(sel)) {
                                if (isVis(el)) {
                                    el.setAttribute('data-speexx-continue-btn', '1');
                                    const r = el.getBoundingClientRect();
                                    return {
                                        found: true,
                                        label: (el.innerText || el.textContent || sel).trim(),
                                        cx: r.left + r.width / 2,
                                        cy: r.top + r.height / 2
                                    };
                                }
                            }
                        }

                        const candidates = Array.from(document.querySelectorAll(
                            "button, a, [role='button'], .btn, .block-button, div[class*='button'], span[class*='button']"
                        ));
                        const exactPhrases = [
                            'เรียนรู้ต่อ',
                            'continue learning',
                            'next exercise',
                            'continue',
                            'ถัดไป'
                        ];
                        for (const phrase of exactPhrases) {
                            for (const el of candidates) {
                                if (!isVis(el)) continue;
                                const txt = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                                if (txt === phrase || (phrase.length > 6 && txt.includes(phrase))) {
                                    el.setAttribute('data-speexx-continue-btn', '1');
                                    const r = el.getBoundingClientRect();
                                    return {
                                        found: true,
                                        label: (el.innerText || el.textContent || phrase).trim(),
                                        cx: r.left + r.width / 2,
                                        cy: r.top + r.height / 2
                                    };
                                }
                            }
                        }
                        return { found: false };
                    }
                    """
                ) or {}

                if not target_meta.get("found"):
                    time.sleep(0.25)
                    continue

                btn = self.page.locator("[data-speexx-continue-btn='1']").first
                label = target_meta.get("label") or self.T["continue"]
                try:
                    if attempt == 0 and btn.count() > 0:
                        btn.scroll_into_view_if_needed(timeout=1500)
                        btn.click(timeout=3500)
                    elif attempt == 1:
                        cx = float(target_meta.get("cx") or 0)
                        cy = float(target_meta.get("cy") or 0)
                        if cx > 0 and cy > 0:
                            self.page.mouse.click(cx, cy)
                        elif btn.count() > 0:
                            btn.click(timeout=3500, force=True)
                    else:
                        if btn.count() > 0:
                            btn.evaluate("el => el.click()")
                except Exception as click_err:
                    self.logger.debug(f"[MODAL] Continue click attempt {attempt+1} error: {click_err}")
                    try:
                        if btn.count() > 0:
                            btn.click(timeout=2500, force=True)
                    except Exception:
                        pass

                # Verify that either URL changed OR modal closed!
                deadline = time.time() + 3.5
                transitioned = False
                while time.time() < deadline:
                    cur_url = ""
                    try:
                        cur_url = self.page.url or ""
                    except Exception:
                        pass
                    if (prev_url and cur_url and cur_url != prev_url) or (not self.detect_completion_modal()):
                        transitioned = True
                        break
                    time.sleep(0.12)

                if transitioned:
                    self.print_status("OK", f"Clicked [{label}] & verified modal transition")
                    self.logger.info(f"[VERIFY] [OK] กดปุ่ม '{label}' สำเร็จและยืนยันการออกจากหน้าสรุปผลแล้ว")
                    return True

                self.logger.warning(
                    f"[MODAL] Continue button '{label}' clicked (attempt {attempt+1}/3) "
                    f"but modal still visible; retrying..."
                )

            self.capture_web_error(
                "modal_continue_stuck",
                exercise_title=self.get_current_exercise_title(),
                extra={"prev_url": prev_url},
            )
            return False
        except Exception as e:
            self.print_status("ERROR", f"Continue click failed: {e}")
            self.capture_web_error(
                "modal_continue_exception",
                exercise_title=self.get_current_exercise_title(),
                extra={"error": str(e)},
            )
            return False

    def _print_summary_report(self, results):
        total_time = 0.0
        success_count = 0
        fail_count = 0
        skip_count = 0
        for _, r, _, e in results:
            if r == "SUCCESS":
                success_count += 1
            elif r == "SKIPPED":
                skip_count += 1
            else:
                fail_count += 1
            total_time += self._parse_elapsed_seconds(e)
        print()
        print(f"  {Fore.CYAN}{'=' * 75}{Style.RESET_ALL}")
        print(f"  {Fore.GREEN}   >>> {self.T['summary']} <<<{Style.RESET_ALL}")
        print(f"  {Fore.CYAN}{'=' * 75}{Style.RESET_ALL}")
        print(f"  {Fore.CYAN}   {self.T['exercise_list']}:{Style.RESET_ALL}")
        print(f"  {Fore.CYAN}{'-' * 75}{Style.RESET_ALL}")
        for pn, r, s, e in results:
            if r == "SUCCESS":
                icon = f"{Fore.GREEN}[OK]{Style.RESET_ALL}"
                status_text = self.T['pass']
            elif r == "SKIPPED":
                icon = f"{Fore.YELLOW}[--]{Style.RESET_ALL}"
                status_text = self.T['skip']
            else:
                icon = f"{Fore.RED}[X ]{Style.RESET_ALL}"
                status_text = self.T['fail']
            page_col = pad_display(f"{self.T['page']} {pn}", 8)
            stat_col = pad_display(status_text, 8)
            score_col = pad_display(f"{self.T['score']} {s:>3}/100", 15)
            print(f"   {icon} {page_col} | {stat_col} | {score_col} | {self.T['time_spent']} {e}")
        print(f"  {Fore.CYAN}{'-' * 75}{Style.RESET_ALL}")
        print(f"  {Fore.GREEN}   {pad_display(self.T['passed_count'], 14)}: {success_count}{Style.RESET_ALL}")
        if fail_count > 0:
            print(f"  {Fore.RED}   {pad_display(self.T['failed_count'], 14)}: {fail_count}{Style.RESET_ALL}")
        if skip_count > 0:
            print(f"  {Fore.YELLOW}   {pad_display(self.T['skipped_count'], 14)}: {skip_count}{Style.RESET_ALL}")
        print(f"  {Fore.CYAN}   {pad_display(self.T['total_time'], 14)}: {total_time:.2f} s{Style.RESET_ALL}")
        print(f"  {Fore.CYAN}{'=' * 75}{Style.RESET_ALL}")

    def handle_completion_modal(self, results, skip_summary=False):
        info = self.extract_completion_info()
        if not skip_summary:
            self._print_summary_report(results)
        print(f"\n  {Fore.CYAN}   Speexx Info:{Style.RESET_ALL}")
        print(f"  {Fore.CYAN}{'-' * 75}{Style.RESET_ALL}")
        if info.get("title", "N/A") != "N/A":
            print(f"   >>> {info['title']}")
        if info.get("score", "N/A") != "N/A":
            print(f"   {self.T['score']} : {info['score']} / {info.get('score_max', '100')}")
        if info.get("level", "N/A") != "N/A":
            print(f"   Level : {info['level']}")
        if info.get("progress", "N/A") != "N/A":
            print(f"   Progress : {info['progress']}")
        if info.get("time", "N/A") != "N/A":
            print(f"   Time : {info['time']}")
        print(f"  {Fore.CYAN}{'=' * 75}{Style.RESET_ALL}")

        print(f"\n  {Fore.CYAN}--- {self.T['what_next']} ---{Style.RESET_ALL}")
        print(f"  {Fore.WHITE}[1]{Style.RESET_ALL} {self.T['repeat']}")
        print(f"  {Fore.WHITE}[2]{Style.RESET_ALL} {self.T['continue']}")
        print(f"  {Fore.WHITE}[0]{Style.RESET_ALL} {self.T['nothing']}")

        while True:
            try:
                c = self._input(f"\n  {Fore.CYAN}[>] {self.T['choose_prompt']}{Style.RESET_ALL}").strip()
                if c == "1":
                    if self.click_modal_repeat():
                        return "repeat"
                elif c == "2":
                    if self.click_modal_continue():
                        time.sleep(2)
                        try:
                            self.page.wait_for_load_state("domcontentloaded", timeout=5000)
                        except Exception:
                            pass
                        return "continue"
                elif c == "0" or c == "":
                    return "none"
            except (ValueError, KeyboardInterrupt, EOFError):
                return "none"

    def get_current_exercise_title(self):
        try:
            for sel in [
                ".folders-dropdown .title span",
                "h1.exercise-header",
                ".subheader .title",
                ".exercise-header .title",
                ".packet-title",
            ]:
                el = self.page.locator(sel).first
                if el.count() > 0:
                    txt = el.inner_text().strip()
                    if txt:
                        return txt
        except Exception:
            pass
        return "Unknown"

    def _reset_exercise_page(self):
        try:
            clicked = self.page.evaluate(
                """
                () => {
                    const isVis = (el) => {
                        if (!el || el.disabled) return false;
                        if (el.closest('.circliful-and-results, .modal, .modal-dialog')) return false;
                        const st = window.getComputedStyle(el);
                        if (!st || st.display === 'none' || st.visibility === 'hidden') return false;
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                    };
                    for (const sel of [
                        'button.action-exercise-button.repeat',
                        'button.repeat',
                        "[class*='repeat']"
                    ]) {
                        for (const el of document.querySelectorAll(sel)) {
                            if (isVis(el)) {
                                el.click();
                                return sel;
                            }
                        }
                    }
                    for (const el of document.querySelectorAll('button, [role="button"]')) {
                        if (!isVis(el)) continue;
                        const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
                        if (txt === 'ทำซ้ำ' || txt === 'repeat' || txt === 'try again' || txt === 'redo') {
                            el.click();
                            return txt;
                        }
                    }
                    return null;
                }
                """
            )
            if clicked:
                self.logger.info(f"[RESET] Clicked repeat via: {clicked}")
                time.sleep(0.35)
                return True
            self.logger.info("[RESET] No page-level repeat button found")
            return False
        except Exception as e:
            self.logger.error(f"[RESET] Error: {e}")
            return False

    def _try_skip_to_next_page(self):
        try:
            clicked = self.page.evaluate(
                """
                () => {
                    const isVis = (el) => {
                        if (!el || el.disabled) return false;
                        if (el.closest('.circliful-and-results, .modal, .modal-dialog')) return false;
                        if (el.id === 'nextButton') return false;
                        const st = window.getComputedStyle(el);
                        if (!st || st.display === 'none' || st.visibility === 'hidden') return false;
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                    };
                    for (const el of document.querySelectorAll('button.action-exercise-button.next')) {
                        if (isVis(el)) {
                            el.click();
                            return 'button.action-exercise-button.next';
                        }
                    }
                    for (const el of document.querySelectorAll('button, [role="button"]')) {
                        if (!isVis(el)) continue;
                        const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
                        if (txt === 'ถัดไป' || txt === 'next') {
                            el.click();
                            return txt;
                        }
                    }
                    return null;
                }
                """
            )
            if clicked:
                self.logger.info(f"[SKIP] Clicked Next via: {clicked}")
                time.sleep(0.25)
                return True
            return False
        except Exception as e:
            self.logger.error(f"[SKIP] Error: {e}")
            return False

    def _parse_elapsed_seconds(self, elapsed):
        if not elapsed or elapsed == "N/A":
            return 0.0
        try:
            if "m" in elapsed:
                parts = elapsed.replace("m", "").replace("s", "").split()
                return float(parts[0]) * 60 + float(parts[1])
            return float(elapsed.replace("s", ""))
        except Exception:
            return 0.0

    def _auto_dismiss_modal(self):
        if self._close_modal_keep_staying():
            self.logger.info("[BATCH] Dismissed modal via close button")
            return True
        if self.click_modal_continue():
            self.logger.info("[BATCH] Dismissed modal via continue button")
            return True
        try:
            self.page.keyboard.press("Escape")
            time.sleep(0.25)
            return True
        except Exception:
            pass
        return False

    def _print_batch_summary_report(self, batch_results):
        total_time = 0.0
        success_count = 0
        fail_count = 0
        skip_count = 0

        for _, status, _, elapsed in batch_results:
            if status == "SUCCESS":
                success_count += 1
            elif status == "SKIPPED":
                skip_count += 1
            else:
                fail_count += 1
            total_time += self._parse_elapsed_seconds(elapsed)

        print()
        print(f"  {Fore.CYAN}{'=' * 78}{Style.RESET_ALL}")
        print(f"  {Fore.GREEN}   >>> {self.T['batch_summary_title']} <<<{Style.RESET_ALL}")
        print(f"  {Fore.CYAN}{'=' * 78}{Style.RESET_ALL}")
        print(f"  {Fore.CYAN}   {self.T['batch_selected_count'].format(len(batch_results))}{Style.RESET_ALL}")
        print(f"  {Fore.CYAN}{'-' * 78}{Style.RESET_ALL}")

        for title, status, score, elapsed in batch_results:
            if status == "SUCCESS":
                icon = f"{Fore.GREEN}[OK]{Style.RESET_ALL}"
                status_text = self.T['pass']
            elif status == "SKIPPED":
                icon = f"{Fore.YELLOW}[--]{Style.RESET_ALL}"
                status_text = self.T['skip']
            else:
                icon = f"{Fore.RED}[X ]{Style.RESET_ALL}"
                status_text = self.T['fail']
            td = pad_display(truncate_display(title, 40), 40)
            st_col = pad_display(status_text, 8)
            score_color = Fore.GREEN if score >= 51 else Fore.RED
            print(
                f"   {icon} {td} | {st_col} | "
                f"{score_color}{score:>3}/100{Style.RESET_ALL} | {elapsed}"
            )

        print(f"  {Fore.CYAN}{'-' * 78}{Style.RESET_ALL}")
        print(f"  {Fore.GREEN}   {pad_display(self.T['passed_count'], 14)}: {success_count}{Style.RESET_ALL}")
        if fail_count > 0:
            print(f"  {Fore.RED}   {pad_display(self.T['failed_count'], 14)}: {fail_count}{Style.RESET_ALL}")
        if skip_count > 0:
            print(f"  {Fore.YELLOW}   {pad_display(self.T['skipped_count'], 14)}: {skip_count}{Style.RESET_ALL}")
        print(f"  {Fore.CYAN}   {pad_display(self.T['total_time'], 14)}: {total_time:.2f}s{Style.RESET_ALL}")
        print(f"  {Fore.CYAN}{'=' * 78}{Style.RESET_ALL}")
