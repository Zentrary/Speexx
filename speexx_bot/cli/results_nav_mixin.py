"""ResultsNavigationMixin: /results navigation, chapter activation, Exercises tab, and Show more expansion."""

import re
import time

from ..speed_config import get as _sp
from ..ui_utils import Fore, Style


class ResultsNavigationMixin:
    def _is_on_results_page(self, url=None):
        """Return True ONLY when the URL pathname itself is /results (ignoring ?goBackTo=.../results)."""
        try:
            raw = url if url is not None else (self.page.url if self.page else "")
            clean = (raw or "").split("?")[0].split("#")[0].rstrip("/").lower()
            return clean.endswith("/results") or "/results/" in clean
        except Exception:
            return False

    def _count_visible_exercise_rows(self):
        if not self.page:
            return 0
        try:
            return int(self.page.evaluate("""
                () => {
                    const rows = document.querySelectorAll('tbody tr.clickable');
                    let count = 0;
                    for (const row of rows) {
                        let cur = row;
                        let hidden = false;
                        while (cur && cur.nodeType === 1) {
                            if (cur.hasAttribute('hidden') || cur.getAttribute('aria-hidden') === 'true' ||
                                (cur.dataset && cur.dataset.hidden === 'true')) {
                                hidden = true;
                                break;
                            }
                            const cls = (cur.className && cur.className.baseVal !== undefined
                                ? cur.className.baseVal : (cur.className || '')).toString().toLowerCase();
                            if (/(^|\\s)(ng-hide|d-none|hidden|u-hidden)(\\s|$)/.test(cls)) {
                                hidden = true;
                                break;
                            }
                            const st = window.getComputedStyle(cur);
                            if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') {
                                hidden = true;
                                break;
                            }
                            cur = cur.parentElement;
                        }
                        if (hidden) continue;
                        const rect = row.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) count++;
                    }
                    return count;
                }
            """) or 0)
        except Exception:
            return 0

    def _get_visible_exercise_rows(self):
        if not self.page:
            return []
        try:
            visible_indices = self.page.evaluate("""
                () => {
                    const rows = Array.from(document.querySelectorAll('tbody tr.clickable'));
                    const indices = [];
                    rows.forEach((row, idx) => {
                        let cur = row;
                        let hidden = false;
                        while (cur && cur.nodeType === 1) {
                            if (cur.hasAttribute('hidden') || cur.getAttribute('aria-hidden') === 'true' ||
                                (cur.dataset && cur.dataset.hidden === 'true')) {
                                hidden = true;
                                break;
                            }
                            const cls = (cur.className && cur.className.baseVal !== undefined
                                ? cur.className.baseVal : (cur.className || '')).toString().toLowerCase();
                            if (/(^|\\s)(ng-hide|d-none|hidden|u-hidden)(\\s|$)/.test(cls)) {
                                hidden = true;
                                break;
                            }
                            const st = window.getComputedStyle(cur);
                            if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') {
                                hidden = true;
                                break;
                            }
                            cur = cur.parentElement;
                        }
                        if (!hidden) {
                            const rect = row.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {
                                indices.push(idx);
                            }
                        }
                    });
                    return indices;
                }
            """) or []
            base = self.page.locator("tbody tr.clickable")
            return [base.nth(idx) for idx in visible_indices]
        except Exception as e:
            self.logger.debug(f"[ROWS] _get_visible_exercise_rows error: {e}")
            return []

    def _wait_for_visible_exercise_rows(self, timeout_ms=15000):
        deadline = time.time() + max(0.5, timeout_ms / 1000.0)
        while time.time() < deadline:
            if self._count_visible_exercise_rows() > 0:
                return True
            if self._find_show_more_expander() is not None:
                return True
            time.sleep(0.25)
        return self._count_visible_exercise_rows() > 0

    def _find_show_more_expander(self):
        if not self.page:
            return None
        try:
            found = self.page.evaluate("""
                () => {
                    document.querySelectorAll('[data-speexx-expander-target]').forEach(el => {
                        el.removeAttribute('data-speexx-expander-target');
                    });

                    const isNodeHidden = (el) => {
                        if (!el || el.nodeType !== 1) return false;
                        if (el.hasAttribute('hidden') || el.getAttribute('aria-hidden') === 'true' ||
                            (el.dataset && el.dataset.hidden === 'true')) return true;
                        const cls = (el.className && el.className.baseVal !== undefined
                            ? el.className.baseVal : (el.className || '')).toString().toLowerCase();
                        if (/(^|\\s)(ng-hide|d-none|hidden|u-hidden)(\\s|$)/.test(cls)) return true;
                        const st = window.getComputedStyle(el);
                        return st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0';
                    };

                    const isVisibleChain = (el) => {
                        let cur = el;
                        while (cur && cur.nodeType === 1) {
                            if (isNodeHidden(cur)) return false;
                            cur = cur.parentElement;
                        }
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };

                    const getVisibleText = (node) => {
                        if (!node) return '';
                        if (node.nodeType === 3) return node.nodeValue || '';
                        if (node.nodeType !== 1) return '';
                        const tag = (node.tagName || '').toUpperCase();
                        if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT') return '';
                        if (isNodeHidden(node)) return '';
                        let out = '';
                        for (const child of node.childNodes) {
                            out += ' ' + getVisibleText(child);
                        }
                        return out;
                    };

                    const hasVisibleUpIcon = (el) => {
                        const checkCls = (node) => {
                            const c = (node.className && node.className.baseVal !== undefined
                                ? node.className.baseVal : (node.className || '')).toString().toLowerCase();
                            return /(chevron-up|angle-up|arrow-up|caret-up|expand-less|up-arrow)/.test(c);
                        };
                        if (checkCls(el)) return true;
                        for (const sub of el.querySelectorAll('i, svg, span, path, use')) {
                            if (!isVisibleChain(sub)) continue;
                            if (checkCls(sub)) return true;
                        }
                        return false;
                    };

                    const collapseRe = /(\\bshow\\s*less\\b|\\bsee\\s*less\\b|\\bview\\s*less\\b|\\bload\\s*less\\b|\\bcollapse\\b|แสดงน้อยลง|ดูน้อยลง|น้อยลง|ย่อรายการ|ซ่อนรายการ)/i;
                    const expandRe = /(\\bshow\\s*more\\b|\\bsee\\s*more\\b|\\bload\\s*more\\b|\\bview\\s*more\\b|แสดงเพิ่มเติม|ดูเพิ่มเติม|โหลดเพิ่มเติม)/i;

                    const cleanLabel = (s) => (s || '')
                        .replace(/[⌄∨▼▾⌃∧▲▴+…•·]/g, ' ')
                        .replace(/\\s+/g, ' ')
                        .trim();

                    const allEls = Array.from(document.querySelectorAll(
                        "div.show-more, [class*='show-more'], button, a, [role='button'], span, div, td, p, li"
                    ));

                    const candidates = [];
                    for (const el of allEls) {
                        if (el.closest && el.closest('tbody tr.clickable')) continue;
                        if (el.querySelector && el.querySelector('table, tbody, tr.clickable')) continue;
                        if (!isVisibleChain(el)) continue;
                        if (hasVisibleUpIcon(el)) continue;

                        const rawVis = getVisibleText(el);
                        if (/[⌃∧▲▴]/.test(rawVis)) continue;

                        const visClean = cleanLabel(rawVis);
                        const ariaClean = cleanLabel(el.getAttribute('aria-label') || '');
                        const titleClean = cleanLabel(el.getAttribute('title') || '');
                        const cls = (el.className && el.className.baseVal !== undefined
                            ? el.className.baseVal : (el.className || '')).toString().toLowerCase();
                        const isShowMoreClass = /(^|[\\s_-])show-more($|[\\s_-])/.test(cls);

                        if (visClean && collapseRe.test(visClean)) continue;
                        if (!visClean && (collapseRe.test(ariaClean) || collapseRe.test(titleClean))) continue;
                        if (visClean.length > 80) continue;

                        const visMatches = expandRe.test(visClean) || visClean === 'เพิ่มเติม';
                        const attrMatches = !visClean && (
                            expandRe.test(ariaClean) || expandRe.test(titleClean) ||
                            ariaClean === 'เพิ่มเติม' || titleClean === 'เพิ่มเติม'
                        );
                        const emptyClassMatches = isShowMoreClass && !visClean && !ariaClean && !titleClean;

                        if (!visMatches && !attrMatches && !emptyClassMatches) continue;

                        const tag = (el.tagName || '').toUpperCase();
                        let priority = 0;
                        if (isShowMoreClass) priority += 100;
                        if (tag === 'BUTTON' || tag === 'A' || el.getAttribute('role') === 'button') priority += 60;
                        if (el.hasAttribute('onclick') || el.hasAttribute('ng-click')) priority += 40;
                        const st = window.getComputedStyle(el);
                        if (st.cursor === 'pointer') priority += 30;
                        // Prefer tighter/deeper elements over outer layout wrappers
                        let depth = 0;
                        let p = el;
                        while (p) { depth++; p = p.parentElement; }

                        candidates.push({
                            el,
                            priority,
                            textLen: visClean.length || ariaClean.length || 1,
                            depth,
                        });
                    }

                    if (!candidates.length) return false;

                    candidates.sort((a, b) => {
                        if (b.priority !== a.priority) return b.priority - a.priority;
                        if (a.textLen !== b.textLen) return a.textLen - b.textLen;
                        return b.depth - a.depth;
                    });

                    candidates[0].el.setAttribute('data-speexx-expander-target', 'true');
                    return true;
                }
            """)
            if found:
                return self.page.locator("[data-speexx-expander-target='true']").first
        except Exception as e:
            self.logger.debug(f"[EXPAND] _find_show_more_expander error: {e}")
        return None

    def _ensure_all_exercises_visible(self):
        try:
            max_attempts = 50
            stagnant_clicks = 0
            for attempt in range(max_attempts):
                try:
                    self.page.evaluate("""
                        () => {
                            const rows = Array.from(document.querySelectorAll('tbody tr.clickable'));
                            for (let i = rows.length - 1; i >= 0; i--) {
                                const r = rows[i].getBoundingClientRect();
                                if (r.width > 0 && r.height > 0) {
                                    rows[i].scrollIntoView({ block: 'end' });
                                    break;
                                }
                            }
                        }
                    """)
                except Exception:
                    pass

                btn = self._find_show_more_expander()
                if btn is None:
                    vis_now = self._count_visible_exercise_rows()
                    self.logger.info(
                        f"[EXPAND] All exercises visible (visible_rows={vis_now}, no active 'Show more' expander)"
                    )
                    return True

                before_vis = self._count_visible_exercise_rows()
                try:
                    before_dom = self.page.locator("tbody tr.clickable").count()
                except Exception:
                    before_dom = 0

                clicked = False
                try:
                    btn.scroll_into_view_if_needed(timeout=2000)
                except Exception:
                    try:
                        btn.evaluate("el => el.scrollIntoView({block: 'center'})")
                    except Exception:
                        pass
                time.sleep(0.15)

                for use_force in (False, True):
                    try:
                        btn.click(timeout=3000, force=use_force)
                        clicked = True
                        break
                    except Exception:
                        continue
                if not clicked:
                    try:
                        btn.evaluate("el => el.click()")
                        clicked = True
                    except Exception as e:
                        self.logger.error(f"[EXPAND] Click failed: {e}")
                        return False

                self.logger.info(
                    f"[EXPAND] Clicked 'Show more' #{attempt + 1} "
                    f"(visible_before={before_vis}, dom_before={before_dom})"
                )

                after_vis = before_vis
                after_dom = before_dom
                for _ in range(16):
                    time.sleep(0.25)
                    after_vis = self._count_visible_exercise_rows()
                    try:
                        after_dom = self.page.locator("tbody tr.clickable").count()
                    except Exception:
                        after_dom = before_dom
                    if after_vis > before_vis or after_dom > before_dom:
                        break
                    if self._find_show_more_expander() is None:
                        break

                if after_vis <= before_vis and after_dom <= before_dom:
                    if self._find_show_more_expander() is None:
                        return True
                    stagnant_clicks += 1
                    if stagnant_clicks >= 3:
                        self.logger.info("[EXPAND] Visible/DOM row count stopped increasing; stopping expansion")
                        return True
                else:
                    stagnant_clicks = 0

            return True
        except Exception as e:
            self.logger.error(f"[EXPAND] Error: {e}")
            return False

    def _click_progress_nav(self):
        selectors = [
            "a[href*='/results']",
            "h6:has-text('ความก้าวหน้า')",
            "h6:has-text('Progress')",
            "h6:has-text('Results')",
            "h6:has-text('ผลการเรียน')",
            "div.flex-col:has-text('ความก้าวหน้า')",
            "div.flex-col:has-text('Progress')",
            "a:has-text('ความก้าวหน้า')",
            "a:has-text('Progress')",
            "a:has-text('Results')",
            "button:has-text('Progress')",
            "button:has-text('ความก้าวหน้า')",
        ]
        for sel in selectors:
            try:
                loc = self.page.locator(sel)
                count = loc.count()
                for idx in range(count):
                    btn = loc.nth(idx)
                    try:
                        if btn.is_visible(timeout=800):
                            btn.click(timeout=8000)
                            return True
                    except Exception:
                        continue
            except Exception:
                continue
        return False

    def _discover_results_url(self, default=None):
        try:
            m = re.search(r"/articles/(\d+)", self.page.url or "")
            if m:
                self.last_results_url = f"https://portal.speexx.com/articles/{m.group(1)}/results"
                return self.last_results_url
            href = self.page.evaluate("""
                () => {
                    for (const a of document.querySelectorAll('a[href]')) {
                        const h = a.getAttribute('href') || '';
                        if (h.includes('/results')) return a.href;
                    }
                    for (const a of document.querySelectorAll('a[href]')) {
                        const m = (a.getAttribute('href') || '').match(/\\/articles\\/(\\d+)/);
                        if (m) return 'https://portal.speexx.com/articles/' + m[1] + '/results';
                    }
                    return null;
                }
            """)
            if isinstance(href, str) and "/results" in href.lower():
                self.last_results_url = href
                return href
        except Exception:
            pass
        return self.last_results_url or default

    def _is_exercises_tab_active(self):
        if not self.page:
            return False
        try:
            return bool(self.page.evaluate("""
                () => {
                    const cands = Array.from(document.querySelectorAll(
                        "#results-table-exercises, [id*='results-table-exercises'], [role='tab'], button, a, li"
                    ));
                    for (const el of cands) {
                        const id = (el.id || '').toLowerCase();
                        const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
                        const isExTab = id.includes('results-table-exercises') ||
                            txt === 'exercises' || txt === 'แบบฝึกหัด';
                        if (!isExTab) continue;
                        const cls = ((el.className || '') + ' ' +
                            ((el.parentElement && el.parentElement.className) || '')).toLowerCase();
                        const aria = (el.getAttribute('aria-selected') || '').toLowerCase();
                        if (aria === 'true' || /(^|[-_\\s])(active|selected|current)([-_\\s]|$)/.test(cls)) {
                            return true;
                        }
                    }
                    return false;
                }
            """))
        except Exception:
            return False

    def _click_exercises_tab(self, force=False):
        if not self.page:
            return False
        if not force and self._count_visible_exercise_rows() > 0:
            return True
        selectors = [
            "#results-table-exercises",
            "[id*='results-table-exercises']",
            "[role='tab']:has-text('Exercises')",
            "[role='tab']:has-text('แบบฝึกหัด')",
            "button:has-text('Exercises')",
            "button:has-text('แบบฝึกหัด')",
            "a:has-text('Exercises')",
            "a:has-text('แบบฝึกหัด')",
            "li:has-text('Exercises')",
            "li:has-text('แบบฝึกหัด')",
        ]
        for sel in selectors:
            try:
                loc = self.page.locator(sel)
                count = loc.count()
                for idx in range(count):
                    tab = loc.nth(idx)
                    try:
                        if tab.is_visible(timeout=800):
                            tab.scroll_into_view_if_needed()
                            time.sleep(0.2)
                            tab.click(timeout=5000)
                            time.sleep(0.6)
                            return True
                    except Exception:
                        continue
            except Exception:
                continue
        return False

    def _activate_chapter_on_results(self, cid=None, name=None, force_click=False):
        if not self.page:
            return False
        target_cid = str(cid).strip() if cid is not None and str(cid).strip() else (
            str(self.current_chapter_cid).strip() if self.current_chapter_cid else ""
        )
        target_name = (name if name is not None else (self.current_chapter_name or "")).strip()
        if not target_cid and (not target_name or target_name == self.DEFAULT_CHAPTER_NAME):
            return True

        try:
            self.page.locator(".level-container").first.wait_for(state="visible", timeout=15000)
        except Exception:
            return False

        try:
            state = self.page.evaluate(
                """
                ([cid, name]) => {
                    document.querySelectorAll('[data-speexx-chapter-target]').forEach(el => {
                        el.removeAttribute('data-speexx-chapter-target');
                    });
                    const containers = Array.from(document.querySelectorAll('.level-container'));
                    if (!containers.length) return { found: false, alreadyActive: false, resolvedCid: null, resolvedName: null };

                    const normName = (name || '').trim().toLowerCase();
                    let matched = null;
                    if (cid) {
                        matched = containers.find(c => (c.getAttribute('data-id') || '').trim() === cid) || null;
                    }
                    if (!matched && normName) {
                        matched = containers.find(c => {
                            const tEl = c.querySelector('.level-text') || c.querySelector('.level-inside-box') || c;
                            const txt = (tEl.innerText || tEl.textContent || '').trim().toLowerCase();
                            return txt === normName;
                        }) || null;
                    }
                    if (!matched) {
                        return { found: false, alreadyActive: false, resolvedCid: null, resolvedName: null };
                    }

                    const box = matched.querySelector('.level-inside-box') || matched;
                    box.setAttribute('data-speexx-chapter-target', 'true');

                    const isExplicitActive = (el) => {
                        const b = el.querySelector('.level-inside-box');
                        const cls = ((el.className || '') + ' ' + ((b && b.className) || '')).toLowerCase();
                        const aria = (el.getAttribute('aria-selected') || (b && b.getAttribute('aria-selected')) || '').toLowerCase();
                        return aria === 'true' || /(^|[-_\\s])(active|selected|current|open)([-_\\s]|$)/.test(cls);
                    };

                    const otherActive = containers.some(c => c !== matched && isExplicitActive(c));
                    const alreadyActive = isExplicitActive(matched) && !otherActive;
                    const tEl = matched.querySelector('.level-text') || box;
                    const resolvedName = (tEl.innerText || tEl.textContent || '').trim() || null;
                    const resolvedCid = matched.getAttribute('data-id') || null;
                    let firstRowTitle = '';
                    for (const r of document.querySelectorAll('tbody tr.clickable')) {
                        const rect = r.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            const td = r.querySelector('td');
                            firstRowTitle = td ? (td.innerText || td.textContent || '').trim() : '';
                            if (firstRowTitle) break;
                        }
                    }

                    return { found: true, alreadyActive, resolvedCid, resolvedName, firstRowTitle };
                }
                """,
                [target_cid, target_name],
            )
        except Exception as e:
            self.logger.debug(f"[CHAPTER] inspect failed: {e}")
            return False

        if not isinstance(state, dict) or not state.get("found"):
            self.logger.warning(f"[CHAPTER] Target chapter not found in DOM (cid={target_cid}, name={target_name})")
            return False

        if state.get("resolvedCid") and not self.current_chapter_cid:
            self.current_chapter_cid = state["resolvedCid"]
        if state.get("resolvedName") and (not self.current_chapter_name or self.current_chapter_name == self.DEFAULT_CHAPTER_NAME):
            self.current_chapter_name = state["resolvedName"]

        was_already_active = bool(state.get("alreadyActive"))
        prev_first_title = " ".join((state.get("firstRowTitle") or "").split()).strip()
        known_key = (state.get("resolvedName") or target_name or self.current_chapter_name or "").strip()
        known_titles = self._chapter_live_titles.get(known_key) or []
        if not was_already_active and prev_first_title and known_titles:
            norm_first = prev_first_title.replace("🎧", "").strip().casefold()
            top_norms = [
                " ".join(t.replace("🎧", "").split()).strip().casefold()
                for t in known_titles[:3]
            ]
            if norm_first and norm_first in top_norms:
                was_already_active = True

        if not force_click and was_already_active and self._count_visible_exercise_rows() > 0:
            return True
        chapter_box = self.page.locator("[data-speexx-chapter-target='true']").first
        try:
            chapter_box.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass

        clicked = False
        for use_force in (False, True):
            try:
                chapter_box.click(timeout=8000, force=use_force)
                clicked = True
                break
            except Exception:
                continue
        if not clicked:
            try:
                chapter_box.evaluate("el => el.click()")
                clicked = True
            except Exception as e:
                self.logger.error(f"[CHAPTER] Click failed for {target_name}: {e}")
                return False

        # Wait for the chapter's live exercise list to finish updating in the DOM
        wait_window = 0.8 if (was_already_active and prev_first_title) else 5.0
        deadline = time.time() + wait_window
        while time.time() < deadline:
            time.sleep(0.25)
            try:
                settled = self.page.evaluate(
                    """
                    ([prevTitle]) => {
                        let curTitle = '';
                        for (const r of document.querySelectorAll('tbody tr.clickable')) {
                            const rect = r.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {
                                const td = r.querySelector('td');
                                curTitle = td ? (td.innerText || td.textContent || '').trim() : '';
                                if (curTitle) break;
                            }
                        }
                        return {
                            changed: Boolean(curTitle && curTitle !== prevTitle),
                            hasRows: Boolean(curTitle),
                        };
                    }
                    """,
                    [prev_first_title],
                )
                if settled:
                    if settled.get("changed"):
                        break
                    if was_already_active and settled.get("hasRows"):
                        break
            except Exception:
                break
        time.sleep(0.3)
        return True

    def _ensure_results_chapter_and_exercises_ready(self, force_chapter_click=False, wait_timeout=15000):
        if not self.page:
            return False
        if not self._is_on_results_page():
            if not self.navigate_to_results(interactive=False):
                return False
            force_chapter_click = False

        if self.current_chapter_cid or (
            self.current_chapter_name and self.current_chapter_name != self.DEFAULT_CHAPTER_NAME
        ):
            self._activate_chapter_on_results(
                self.current_chapter_cid,
                self.current_chapter_name,
                force_click=force_chapter_click,
            )

        self._click_exercises_tab(force=force_chapter_click)
        self._wait_for_visible_exercise_rows(timeout_ms=wait_timeout)
        self._ensure_all_exercises_visible()
        return True

    def check_course_progress(self):
        if getattr(self, "force_solve_all", False):
            return False
        try:
            if self._is_on_results_page():
                info_title = self.page.locator(".progress-info .info-title").first
                if info_title.count() > 0:
                    text = info_title.inner_text().strip()
                    if re.search(r"\b100\s*%", text):
                        return True
                return False

            direct_url = self._discover_results_url()
            if direct_url:
                self.page.goto(direct_url, wait_until="domcontentloaded", timeout=20000)
                try:
                    self.page.locator(".level-container, .progress-info").first.wait_for(
                        state="visible", timeout=8000
                    )
                except Exception:
                    pass
            else:
                self.page.goto("https://portal.speexx.com/", wait_until="domcontentloaded", timeout=20000)
                time.sleep(1.0)
                if self._click_progress_nav():
                    time.sleep(1.0)

            info_title = self.page.locator(".progress-info .info-title").first
            if info_title.count() > 0:
                text = info_title.inner_text().strip()
                if re.search(r"\b100\s*%", text):
                    return True
            return False
        except Exception as e:
            self.logger.error(f"[PROGRESS] Error checking status: {e}")
            return False

    def navigate_to_results(self, interactive=True):
        if not self.page:
            self.print_status("ERROR", "Browser not started.")
            if interactive:
                self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
            return False

        # If ALREADY on /results pathname, stay right here without bouncing to Dashboard!
        if self._is_on_results_page():
            try:
                self._discover_results_url()
                self.page.locator(".level-container").first.wait_for(state="visible", timeout=8000)
                if self.current_chapter_cid or (
                    self.current_chapter_name and self.current_chapter_name != self.DEFAULT_CHAPTER_NAME
                ):
                    self._activate_chapter_on_results(
                        self.current_chapter_cid,
                        self.current_chapter_name,
                        force_click=False,
                    )
                self._click_exercises_tab(force=False)
                self._wait_for_visible_exercise_rows(timeout_ms=6000)
                self._ensure_chapter_db_loaded(announce=False)
                return True
            except Exception as stay_err:
                self.logger.debug(f"[NAV] In-place /results check fallback: {stay_err}")

        discovered_before = self._discover_results_url()
        # Fast direct navigation to /results if we already know the article's /results URL!
        if discovered_before:
            try:
                self.page.goto(discovered_before, wait_until="domcontentloaded", timeout=20000)
                self.page.locator(".level-container").first.wait_for(
                    state="visible", timeout=12000
                )
                if self.current_chapter_cid or (
                    self.current_chapter_name and self.current_chapter_name != self.DEFAULT_CHAPTER_NAME
                ):
                    self._activate_chapter_on_results(
                        self.current_chapter_cid,
                        self.current_chapter_name,
                        force_click=False,
                    )
                self._click_exercises_tab(force=False)
                self._wait_for_visible_exercise_rows(timeout_ms=8000)
                self._ensure_chapter_db_loaded(announce=False)
                self.print_status("OK", "Results loaded.")
                return True
            except Exception as direct_err:
                self.logger.debug(f"[NAV] Direct /results failed ({direct_err}); trying Dashboard -> Progress")

        self.print_status("INFO", "Navigating to Dashboard -> Progress -> Exercises...")
        fallback_url = discovered_before or "https://portal.speexx.com/articles/10960433/results"
        try:
            self.page.goto("https://portal.speexx.com/", wait_until="domcontentloaded", timeout=20000)
            time.sleep(1.2)
            fallback_url = (
                self._discover_results_url()
                or discovered_before
                or "https://portal.speexx.com/articles/10960433/results"
            )

            if self._click_progress_nav():
                time.sleep(1.5)
            else:
                self.logger.warning("[NAV] Progress button not found, falling back to direct URL")
                raise Exception("Progress button not found")

            self.page.locator(".level-container").first.wait_for(state="visible", timeout=15000)
            self._discover_results_url()

            if self.current_chapter_cid or (
                self.current_chapter_name and self.current_chapter_name != self.DEFAULT_CHAPTER_NAME
            ):
                self._activate_chapter_on_results(
                    self.current_chapter_cid,
                    self.current_chapter_name,
                    force_click=True,
                )

            self._click_exercises_tab(force=True)
            self._wait_for_visible_exercise_rows(timeout_ms=8000)

            self._ensure_chapter_db_loaded(announce=False)
            self.print_status("OK", "Results loaded via Dashboard.")
            return True
        except Exception as e:
            self.print_status("WAIT", f"Dashboard navigation failed: {str(e)}. Using direct URL.")
            try:
                self.page.goto(fallback_url, wait_until="domcontentloaded")
                self.page.locator(".level-container").first.wait_for(
                    state="visible", timeout=15000
                )
                if self.current_chapter_cid or (
                    self.current_chapter_name and self.current_chapter_name != self.DEFAULT_CHAPTER_NAME
                ):
                    self._activate_chapter_on_results(
                        self.current_chapter_cid,
                        self.current_chapter_name,
                        force_click=True,
                    )
                self._click_exercises_tab(force=True)
                self._wait_for_visible_exercise_rows(timeout_ms=8000)
                self._ensure_chapter_db_loaded(announce=False)
                self.print_status("OK", "Results loaded via fallback.")
                return True
            except Exception as e2:
                self.print_status("ERROR", f"Failed to navigate: {str(e2)}")
                if interactive:
                    self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
                return False
