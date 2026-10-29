"""ExerciseListMixin: chapter menu, live /results row batch inspection, exercise menu, and row clicker."""

import re
import time

from ..ui_utils import Fore, Style, pad_display, truncate_display


class ExerciseListMixin:
    @staticmethod
    def _is_test_chapter_name(name):
        low = (name or "").strip().lower()
        return any(
            kw in low
            for kw in ("test", "assessment", "exam", "quiz", "แบบทดสอบ", "ข้อสอบ", "ประเมิน")
        )

    def fetch_and_select_chapter(self):
        if not self.page:
            return
        self.print_header()
        print(f"  {Fore.CYAN}--- {self.T['available_chapters']} ---{Style.RESET_ALL}\n")
        try:
            if not self._is_on_results_page():
                self.print_status("INFO", "Navigating to Progress page...")
                if not self.navigate_to_results():
                    return

            self.page.locator(".level-container").first.wait_for(
                state="visible", timeout=30000
            )
            chapters = self.page.locator(".level-container").all()
            self.current_chapters = []
            for ch in chapters:
                box = ch.locator(".level-inside-box")
                cls = box.get_attribute("class") or ""
                if "future" in cls:
                    continue
                name = box.locator(".level-text").inner_text().strip()
                if self._is_test_chapter_name(name):
                    continue
                cid = ch.get_attribute("data-id")
                self.current_chapters.append((name, cid))
            if not self.current_chapters:
                self.print_status("ERROR", self.T['no_chapters'])
                self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
                return
            for i, (n, _) in enumerate(self.current_chapters, 1):
                print(f"  {Fore.WHITE}[{i}]{Style.RESET_ALL} {n}")
            print(f"\n  {Fore.WHITE}[0]{Style.RESET_ALL} {self.T['back']}")
            try:
                c = self._input(f"\n  {Fore.CYAN}[>] {self.T['select_chapter']}{Style.RESET_ALL}").strip()
                if c == "" or c == "0":
                    return
                c_int = int(c)
                if 1 <= c_int <= len(self.current_chapters):
                    n, cid = self.current_chapters[c_int - 1]
                    self.select_chapter(cid, n)
            except ValueError:
                pass
        except Exception as e:
            self.print_status("ERROR", f"Error: {str(e)}")
            self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")

    def select_chapter(self, cid, name):
        self.print_status("WAIT", f"Selecting {name}...")
        try:
            self.current_chapter_cid = cid
            self.current_chapter_name = name
            self._load_answer_db(name, announce=True)

            already_navigated = False
            if not self._is_on_results_page():
                if not self.navigate_to_results():
                    return
                already_navigated = True

            self._ensure_results_chapter_and_exercises_ready(
                force_chapter_click=not already_navigated,
                wait_timeout=15000,
            )
            self.print_status("OK", f"{name} selected.")
            self.fetch_exercises(_already_prepared=True)
        except Exception as e:
            self.print_status("ERROR", f"Error: {str(e)}")
            self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")

    def _parse_selection(self, s, max_n):
        s = (s or "").strip().lower()
        if not s or s == "all":
            return list(range(1, max_n + 1))
        result = []
        try:
            if ',' in s:
                parts = s.split(',')
                for p in parts:
                    p = p.strip()
                    if '-' in p:
                        a, b = p.split('-')
                        result.extend(range(int(a), int(b) + 1))
                    else:
                        result.append(int(p))
            elif '-' in s:
                a, b = s.split('-')
                result = list(range(int(a), int(b) + 1))
            else:
                result = [int(s)]
        except Exception:
            return []
        seen = set()
        clean = []
        for i in result:
            if 1 <= i <= max_n and i not in seen:
                seen.add(i)
                clean.append(i)
        return clean

    def _inspect_result_row(self, row, row_index=0):
        info = {
            "row_index": row_index,
            "title": "",
            "date": "",
            "time_spent": "",
            "score_text": "",
            "score": None,
            "has_checkmark": False,
            "is_completed": False,
            "review": "",
        }
        try:
            tds = row.locator("td").all()
            if len(tds) < 4:
                return info
            info["title"] = " ".join((tds[0].inner_text() or "").split()).strip()
            info["date"] = " ".join((tds[1].inner_text() or "").split()).strip()
            info["time_spent"] = " ".join((tds[2].inner_text() or "").split()).strip()
            info["score_text"] = " ".join((tds[3].inner_text() or "").split()).strip()
            if len(tds) >= 5:
                btns = tds[4].locator("button").all()
                if btns:
                    info["review"] = " ".join((btns[0].inner_text() or "").split()).strip()
                else:
                    info["review"] = " ".join((tds[4].inner_text() or "").split()).strip()

            m = re.search(r"\d+", info["score_text"])
            if m:
                info["score"] = int(m.group(0))

            try:
                has_check = tds[3].evaluate("""
                    (cell) => {
                        const html = (cell.innerHTML || '').toLowerCase();
                        const text = (cell.innerText || cell.textContent || '').trim();
                        if (/[✓✔☑]/.test(text)) return true;
                        const nodes = [cell, ...cell.querySelectorAll('i, svg, span, img, div')];
                        let foundPassIcon = false;
                        for (const n of nodes) {
                            const cls = (n.className && n.className.baseVal !== undefined
                                ? n.className.baseVal : (n.className || '')).toString().toLowerCase();
                            const aria = (n.getAttribute && (n.getAttribute('aria-label') || '') || '').toLowerCase();
                            const combined = cls + ' ' + aria;
                            if (/(times|cross|wrong|error|fail|red|close)/.test(combined)) {
                                return false;
                            }
                            if (/(check|tick|success|passed|complete|result-green|green)/.test(combined)) {
                                foundPassIcon = true;
                            }
                        }
                        if (foundPassIcon) return true;
                        if (cell.querySelector('svg') && !html.includes('cross') && !html.includes('error')) {
                            return true;
                        }
                        return false;
                    }
                """)
                info["has_checkmark"] = bool(has_check)
            except Exception:
                info["has_checkmark"] = False

            if info["score"] is not None:
                info["is_completed"] = info["score"] >= 51
            else:
                info["is_completed"] = info["has_checkmark"]
        except Exception as e:
            self.logger.debug(f"[ROW] inspect failed: {e}")
        return info

    def _inspect_all_visible_result_rows(self):
        if not self.page:
            return []
        try:
            raw_list = self.page.evaluate(
                """
                () => {
                    const out = [];
                    let visIdx = 0;
                    const rows = document.querySelectorAll('tbody tr.clickable');
                    for (const row of rows) {
                        const st = window.getComputedStyle(row);
                        if (!st || st.display === 'none' || st.visibility === 'hidden' || parseFloat(st.opacity || '1') === 0) {
                            continue;
                        }
                        const rect = row.getBoundingClientRect();
                        if (rect.width <= 0 || rect.height <= 0) continue;

                        const tds = row.querySelectorAll('td');
                        if (tds.length < 4) {
                            visIdx++;
                            continue;
                        }
                        const clean = (el) => (el ? (el.innerText || el.textContent || '') : '').replace(/\\s+/g, ' ').trim();
                        const title = clean(tds[0]);
                        const date = clean(tds[1]);
                        const timeSpent = clean(tds[2]);
                        const scoreText = clean(tds[3]);
                        let review = '';
                        if (tds.length >= 5) {
                            const btn = tds[4].querySelector('button');
                            review = btn ? clean(btn) : clean(tds[4]);
                        }
                        const m = scoreText.match(/\\d+/);
                        const score = m ? parseInt(m[0], 10) : null;

                        let hasCheckmark = false;
                        const cell = tds[3];
                        const html = (cell.innerHTML || '').toLowerCase();
                        if (/[✓✔☑]/.test(scoreText)) {
                            hasCheckmark = true;
                        } else {
                            let bad = false;
                            let passIcon = false;
                            const nodes = [cell, ...cell.querySelectorAll('i, svg, span, img, div')];
                            for (const n of nodes) {
                                const cls = (n.className && n.className.baseVal !== undefined
                                    ? n.className.baseVal : (n.className || '')).toString().toLowerCase();
                                const aria = (n.getAttribute && (n.getAttribute('aria-label') || '') || '').toLowerCase();
                                const combined = cls + ' ' + aria;
                                if (/(times|cross|wrong|error|fail|red|close)/.test(combined)) {
                                    bad = true;
                                    break;
                                }
                                if (/(check|tick|success|passed|complete|result-green|green)/.test(combined)) {
                                    passIcon = true;
                                }
                            }
                            if (!bad && (passIcon || (cell.querySelector('svg') && !html.includes('cross') && !html.includes('error')))) {
                                hasCheckmark = true;
                            }
                        }

                        const isCompleted = score !== null ? (score >= 51) : hasCheckmark;
                        out.push({
                            row_index: visIdx,
                            title,
                            date,
                            time_spent: timeSpent,
                            score_text: scoreText,
                            score,
                            has_checkmark: hasCheckmark,
                            is_completed: isCompleted,
                            review
                        });
                        visIdx++;
                    }
                    return out;
                }
                """
            ) or []
            if self.current_chapter_name and raw_list:
                self._chapter_live_titles[self.current_chapter_name] = [
                    r["title"] for r in raw_list if r.get("title")
                ]
            return raw_list
        except Exception as e:
            self.logger.debug(f"[ROW] batch inspect fallback: {e}")
            rows = self._get_visible_exercise_rows()
            res = [self._inspect_result_row(r, row_index=idx) for idx, r in enumerate(rows)]
            if self.current_chapter_name and res:
                self._chapter_live_titles[self.current_chapter_name] = [
                    r["title"] for r in res if r.get("title")
                ]
            return res

    def fetch_exercises(self, _already_prepared=False):
        self.print_header()
        print(f"  {Fore.CYAN}--- {self.T['exercise_list']} ---{Style.RESET_ALL}\n")
        try:
            self._ensure_chapter_db_loaded(announce=False)
            if not _already_prepared:
                self._ensure_results_chapter_and_exercises_ready(
                    force_chapter_click=False,
                    wait_timeout=15000,
                )
            else:
                self._wait_for_visible_exercise_rows(timeout_ms=15000)
                self._ensure_all_exercises_visible()

            row_infos = self._inspect_all_visible_result_rows()
            if not row_infos:
                self.print_status("ERROR", self.T['no_exercises'])
                self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
                return

            hdr = (
                f"  {Fore.CYAN}"
                f"{pad_display(self.T['table_no'], 6)}| "
                f"{pad_display(self.T['table_title'], 34)}| "
                f"{pad_display(self.T['table_date'], 13)}| "
                f"{pad_display(self.T['table_time'], 10)}| "
                f"{pad_display(self.T['table_score'], 8)}| "
                f"{self.T['table_review']}{Style.RESET_ALL}"
            )
            print(hdr)
            print(f"  {Fore.CYAN}{'-' * 96}{Style.RESET_ALL}")

            exercises = []
            for r_info in row_infos:
                row_idx = r_info["row_index"]
                if not r_info["title"] and r_info["score_text"] == "" and not r_info["date"]:
                    continue
                i = len(exercises) + 1
                title = r_info["title"]
                date = r_info["date"]
                t_spent = r_info["time_spent"]
                score_disp = r_info["score_text"]
                if not score_disp and r_info["has_checkmark"]:
                    score_disp = "✓"
                rb = r_info["review"]
                exercises.append((title, rb, row_idx))

                td = pad_display(truncate_display(title, 34), 34)
                no_col = pad_display(f"[{i}]", 6)
                date_col = pad_display(truncate_display(date, 13), 13)
                time_col = pad_display(truncate_display(t_spent, 10), 10)
                score_col = pad_display(truncate_display(score_disp, 8), 8)
                score_color = (
                    Fore.GREEN if (r_info["score"] == 100 or (r_info["score"] is None and r_info["has_checkmark"]))
                    else (Fore.YELLOW if (r_info["score"] is not None and r_info["score"] >= 51) else Fore.WHITE)
                )
                print(
                    f"  {no_col}| {td}| {date_col}| {time_col}| "
                    f"{score_color}{score_col}{Style.RESET_ALL}| {rb}"
                )

            known_pages = {
                item.get("title"): item.get("pages_total", 0)
                for item in self.chapter_catalog
            }
            seen_cat_titles = set()
            new_catalog = []
            for title, _, _ in exercises:
                if title and title not in seen_cat_titles:
                    seen_cat_titles.add(title)
                    new_catalog.append({
                        "title": title,
                        "pages_total": known_pages.get(title, 0),
                    })
            self.chapter_catalog = new_catalog
            self.logger.info(
                "[DB] Chapter catalogue: %s unique exercises (%s live web rows)",
                len(self.chapter_catalog),
                len(exercises),
            )

            self._save_answer_db(self.current_chapter_name)
            print(f"  {Fore.CYAN}{'-' * 96}{Style.RESET_ALL}")
            print(f"\n  {Fore.WHITE}[0]{Style.RESET_ALL} {self.T['back']}")
            try:
                sel_input = self._input(
                    f"\n  {Fore.CYAN}[>] {self.T['select_exercises']}{Style.RESET_ALL}"
                )
                if sel_input == "" or sel_input.strip() == "0":
                    return

                selected = self._parse_selection(sel_input, len(exercises))
                if not selected:
                    self.print_status("ERROR", self.T['invalid_choice'])
                    self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
                    return

                selected_items = [
                    (exercises[idx - 1][0], exercises[idx - 1][2])
                    for idx in selected
                ]

                if len(selected_items) == 1:
                    t0, r0 = selected_items[0]
                    self.open_exercise_menu(t0, row_index=r0)
                else:
                    print(
                        f"\n  {Fore.CYAN}--- "
                        f"{self.T['multi_select_mode_title'].format(len(selected))} "
                        f"---{Style.RESET_ALL}"
                    )
                    print(f"  {Fore.WHITE}[1]{Style.RESET_ALL} {self.T['opt_new_learning_path']}")
                    print(f"  {Fore.WHITE}[2]{Style.RESET_ALL} {self.T['opt_one_by_one']}")

                    try:
                        mode = self._input(
                            f"  {Fore.CYAN}[>] {self.T['select_mode_prompt']}{Style.RESET_ALL}"
                        ).strip()
                    except Exception:
                        mode = "1"

                    if mode == "2":
                        for t_item, r_item in selected_items:
                            self.open_exercise_menu(t_item, row_index=r_item)
                            time.sleep(0.5)
                    else:
                        t0, r0 = selected_items[0]
                        self.start_new_learning_path(t0, row_index=r0)

            except ValueError:
                pass
        except Exception as e:
            self.print_status("ERROR", f"Error: {str(e)}")
            self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")

    def _find_matching_exercise_row(self, title, row_index=None):
        rows = self._get_visible_exercise_rows()
        if not rows:
            return None

        infos = self._inspect_all_visible_result_rows()
        if not infos:
            return None

        target_norm = self._norm_ex_title(title)

        if row_index is not None and 0 <= row_index < min(len(rows), len(infos)):
            row_title_norm = self._norm_ex_title(infos[row_index].get("title") or "")
            if not target_norm or row_title_norm == target_norm:
                return rows[row_index]

        if not target_norm:
            return rows[0]

        exact_matches = []
        partial_matches = []
        limit = min(len(rows), len(infos))
        for idx in range(limit):
            r_info = infos[idx]
            row_title_norm = self._norm_ex_title(r_info.get("title") or "")
            if not row_title_norm:
                continue
            if row_title_norm == target_norm:
                exact_matches.append((idx, rows[idx], r_info))
            elif target_norm in row_title_norm or row_title_norm in target_norm:
                partial_matches.append((idx, rows[idx], r_info))

        if exact_matches:
            if row_index is not None:
                best = min(exact_matches, key=lambda x: abs(x[0] - row_index))
                return best[1]
            if len(exact_matches) > 1 and not self.force_solve_all:
                for _, row, r_info in exact_matches:
                    if not r_info["is_completed"]:
                        return row
            return exact_matches[0][1]

        if partial_matches:
            if row_index is not None:
                best = min(partial_matches, key=lambda x: abs(x[0] - row_index))
                return best[1]
            if len(partial_matches) > 1 and not self.force_solve_all:
                for _, row, r_info in partial_matches:
                    if not r_info["is_completed"]:
                        return row
            return partial_matches[0][1]

        return None

    def _click_row_safely(self, title, wait_timeout=15000, row_index=None, click_inner_cell=False):
        row = None
        on_results = self._is_on_results_page()

        # Fast path: if already on /results with visible rows, inspect once and click immediately
        if on_results:
            try:
                row = self._find_matching_exercise_row(title, row_index=row_index)
            except Exception as e:
                self.logger.debug(f"[CLICK] Fast-path row lookup error: {e}")

        if row is None:
            try:
                if not self._is_on_results_page() or self._count_visible_exercise_rows() == 0:
                    self.logger.info("[CLICK] Exercise table empty or off /results — recovering chapter & Exercises view")
                    self._ensure_results_chapter_and_exercises_ready(
                        force_chapter_click=False,
                        wait_timeout=min(wait_timeout, 12000),
                    )
                else:
                    if self.current_chapter_cid or (
                        self.current_chapter_name and self.current_chapter_name != self.DEFAULT_CHAPTER_NAME
                    ):
                        self._activate_chapter_on_results(
                            self.current_chapter_cid,
                            self.current_chapter_name,
                            force_click=False,
                        )
                    self._click_exercises_tab(force=False)
                    self._ensure_all_exercises_visible()
            except Exception as e:
                self.logger.debug(f"[CLICK] Table recovery check error: {e}")

            row = self._find_matching_exercise_row(title, row_index=row_index)

        if row is None:
            self.logger.info(
                f"[CLICK] '{title}' not in current visible rows — forcing chapter re-select & Show more expansion"
            )
            try:
                self._ensure_results_chapter_and_exercises_ready(
                    force_chapter_click=True,
                    wait_timeout=min(wait_timeout, 12000),
                )
            except Exception as e:
                self.logger.debug(f"[CLICK] Forced chapter refresh error: {e}")
            row = self._find_matching_exercise_row(title, row_index=row_index)

        if row is None:
            vis_total = self._count_visible_exercise_rows()
            dom_total = 0
            try:
                dom_total = self.page.locator("tbody tr.clickable").count()
            except Exception:
                pass
            self.logger.warning(
                f"[CLICK] Row not found within {wait_timeout}ms for '{title}' "
                f"(row_index={row_index}, visible_rows={vis_total}, dom_rows={dom_total})"
            )
            return False

        time.sleep(0.15)

        try:
            row.scroll_into_view_if_needed(timeout=3000)
            time.sleep(0.15)
        except Exception as e:
            self.logger.debug(f"[CLICK] scroll_into_view failed: {e}")
            try:
                row.evaluate("el => el.scrollIntoView({block: 'center'})")
                time.sleep(0.3)
            except Exception:
                pass

        target = row
        if click_inner_cell:
            try:
                inner = row.locator("td a, td").first
                if inner.count() > 0:
                    target = inner
            except Exception:
                target = row

        def _opened_packet():
            try:
                cur_u = self.page.url or ""
                base_u = cur_u.split("?")[0].lower()
                return "/results" not in base_u and bool(self._extract_packet_key(cur_u))
            except Exception:
                return False

        for mode_label, click_fn in (
            ("normal", lambda: target.click(timeout=3000)),
            ("force", lambda: target.click(timeout=2500, force=True)),
            ("JS", lambda: target.evaluate("el => el.click()", timeout=2500)),
        ):
            if _opened_packet():
                self.logger.info(f"[CLICK] '{title}' already navigated to packet ({self.page.url})")
                return True
            try:
                click_fn()
                self.logger.info(f"[CLICK] '{title}' clicked ({mode_label}, inner={click_inner_cell})")
                return True
            except Exception as e:
                if _opened_packet():
                    self.logger.info(
                        f"[CLICK] '{title}' navigated during {mode_label} click ({self.page.url})"
                    )
                    return True
                self.logger.debug(f"[CLICK] {mode_label} click failed: {str(e)[:120]}")

        return _opened_packet()
