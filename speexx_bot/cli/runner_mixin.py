"""ExerciseRunnerMixin: auto_solve_exercise, continuous auto-continue progression, and batch solving."""

import time

from ..constants import UNSUPPORTED_TYPES
from ..solvers import ExerciseEngine
from ..ui_utils import Fore, Style


class ExerciseRunnerMixin:
    def _ask_solve_mode(self):
        print(f"\n  {Fore.CYAN}--- {self.T['solve_mode_title']} ---{Style.RESET_ALL}")
        print(f"  {Fore.WHITE}[1]{Style.RESET_ALL} {self.T['solve_mode_force']}")
        print(f"  {Fore.WHITE}[2]{Style.RESET_ALL} {self.T['solve_mode_skip_passed']}")
        print(f"  {Fore.WHITE}[0]{Style.RESET_ALL} {self.T['cancel']}")
        try:
            c = self._input(
                f"\n  {Fore.CYAN}[>] {self.T['select_mode_prompt']}{Style.RESET_ALL}"
            ).strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if c == "1":
            return True
        if c == "2" or c == "":
            return False
        if c == "0":
            return None
        return False

    def start_new_learning_path(self, first_title, row_index=None):
        print(f"\n  {Fore.CYAN}--- {self.T['opt_new_learning_path']} ---{Style.RESET_ALL}")
        print(f"  {self.T['start_from'].format(first_title)}")
        force = self._ask_solve_mode()
        if force is None:
            return
        self.force_solve_all = force
        try:
            confirm = self._input(
                f"\n  {Fore.CYAN}[>] {self.T['confirm_auto_continue']}{Style.RESET_ALL}"
            ).strip()
        except (EOFError, KeyboardInterrupt):
            return
        if confirm == "0":
            return
        self.auto_solve_exercise(
            first_title,
            selected_pages=None,
            is_continuation=False,
            already_opened=False,
            auto_continue=True,
            row_index=row_index,
        )

    def auto_solve_batch(self, titles):
        if not titles:
            return

        normalized_items = []
        for item in titles:
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                normalized_items.append((item[0], item[1]))
            else:
                normalized_items.append((str(item), None))

        self.print_header()
        print(f"  {Fore.CYAN}=== {self.T['batch_mode_header'].format(len(normalized_items))} ==={Style.RESET_ALL}\n")
        for i, (t, _) in enumerate(normalized_items, 1):
            print(f"  {Fore.WHITE}[{i}]{Style.RESET_ALL} {t}")
        print(f"\n  {Fore.YELLOW}{self.T['batch_mode_notice']}{Style.RESET_ALL}")

        force = self._ask_solve_mode()
        if force is None:
            return
        self.force_solve_all = force

        try:
            confirm = self._input(
                f"\n  {Fore.CYAN}[>] {self.T['confirm_start_now']}{Style.RESET_ALL}"
            ).strip()
            if confirm == "0":
                return
        except Exception:
            return

        batch_results = []

        for idx, (title, r_idx) in enumerate(normalized_items, 1):
            self.print_header()
            print(f"  {Fore.CYAN}=== [{idx}/{len(normalized_items)}] {title} ==={Style.RESET_ALL}")

            if idx > 1:
                try:
                    self.navigate_to_results()
                    time.sleep(1.5)
                except Exception:
                    pass

            try:
                status, score, elapsed = self.auto_solve_exercise(
                    title,
                    selected_pages=None,
                    is_continuation=False,
                    already_opened=False,
                    batch_mode=True,
                    row_index=r_idx,
                )
            except Exception as e:
                self.print_status("ERROR", f"Batch error on '{title}': {e}")
                status, score, elapsed = "ERROR", 0, "N/A"

            batch_results.append((title, status, score, elapsed))
            if status == "SUCCESS":
                status_code = "OK"
            elif status == "SKIPPED":
                status_code = "SKIP"
            else:
                status_code = "ERROR"
            self.print_status(
                status_code,
                f"[{idx}/{len(normalized_items)}] {title}: {status} ({score}) | {elapsed}"
            )

        self._print_batch_summary_report(batch_results)

        try:
            self.navigate_to_results()
            time.sleep(1)
        except Exception:
            pass

    def auto_solve_exercise(self, title, selected_pages=None,
                            is_continuation=False, already_opened=False,
                            total_pages=None, batch_mode=False,
                            auto_continue=False, continuation_depth=0,
                            chain_seen_titles=None, row_index=None,
                            chain_direction=None):
        self._ensure_chapter_db_loaded(announce=False)

        if not is_continuation and not batch_mode:
            self.print_status("INFO", f"{self.T['auto_solve']}: {title}")
            self.print_status("INFO", self.T['will_not_move'])

        final_status = "FAILED"
        final_score = 0
        final_elapsed = "N/A"
        pages_recorded_count = 0
        exercise_db_saved = False
        if auto_continue:
            if chain_seen_titles is None:
                chain_seen_titles = set()
            norm_init_title = self._norm_ex_title(title)
            if norm_init_title and norm_init_title != "unknown":
                if row_index is not None:
                    chain_seen_titles.add(f"row:{norm_init_title}#{row_index}")
                else:
                    chain_seen_titles.add(f"title:{norm_init_title}")

        try:
            if not already_opened and not is_continuation:
                clicked = self._click_row_safely(title, row_index=row_index)
                if not clicked:
                    self.capture_web_error(
                        "cannot_open_exercise_row",
                        exercise_title=title,
                        extra={"row_index": row_index},
                    )
                    self.print_status(
                        "ERROR",
                        f"Cannot open '{title}' — skipping"
                    )
                    if not batch_mode:
                        self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
                    return ("ERROR", 0, "N/A")

                try:
                    self.page.wait_for_selector(
                        ".exercise, video, .exercises-large-navigation li",
                        state="visible",
                        timeout=15000
                    )
                except Exception as e:
                    self.logger.warning(f"[WAIT] Exercise page not ready: {str(e)[:80]}")
                    if self._is_on_results_page():
                        self.logger.info("[WAIT] Still on /results after row click; retrying inner cell click...")
                        if self._click_row_safely(title, row_index=row_index, click_inner_cell=True):
                            try:
                                self.page.wait_for_selector(
                                    ".exercise, video, .exercises-large-navigation li",
                                    state="visible",
                                    timeout=12000
                                )
                            except Exception:
                                pass
                self.wait_for_exercise_content_ready(timeout=6.0)

            self._ensure_chapter_db_loaded(announce=False)

            if not title or title == "Unknown":
                detected_title = self.get_current_exercise_title()
                if detected_title and detected_title != "Unknown":
                    title = detected_title

            if auto_continue and chain_seen_titles is not None:
                cur_pkt = self._extract_packet_key(self.page.url)
                if cur_pkt:
                    chain_seen_titles.add(f"pkt:{cur_pkt}")
                norm_resolved = self._norm_ex_title(title)
                if norm_resolved and norm_resolved != "unknown":
                    if row_index is not None:
                        chain_seen_titles.add(f"row:{norm_resolved}#{row_index}")
                    else:
                        chain_seen_titles.add(f"title:{norm_resolved}")

            if total_pages is None:
                total_pages = self.get_total_exercises(retries=3, wait_seconds=0.6)

            if total_pages == 0:
                if self._is_on_results_page():
                    self.logger.warning("[TOTAL] Still on /results (total=0), re-selecting chapter & clicking row...")
                    if self._click_row_safely(title, row_index=row_index, click_inner_cell=True):
                        time.sleep(0.8)
                        total_pages = self.get_total_exercises(retries=3, wait_seconds=0.6)
                else:
                    self.logger.warning("[TOTAL] First attempt = 0, retrying with reload...")
                    try:
                        self.page.reload(wait_until="domcontentloaded", timeout=15000)
                        time.sleep(0.8)
                        total_pages = self.get_total_exercises(retries=3, wait_seconds=0.6)
                    except Exception as e:
                        self.logger.error(f"[TOTAL] Reload failed: {e}")

            if total_pages == 0:
                try:
                    if self.page.locator(".exercise, .video").count() > 0:
                        total_pages = 1
                        self.logger.info("[TOTAL] Single-page exercise detected without nav bar")
                except Exception:
                    pass

            if total_pages == 0:
                self.capture_web_error(
                    "cannot_determine_total_pages",
                    exercise_title=title,
                )
                self.print_status("ERROR", "Cannot determine total.")
                if not batch_mode:
                    self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
                return (final_status, final_score, final_elapsed)

            if not batch_mode:
                self.print_status("INFO", self.T['found_pages'].format(total_pages))

            if selected_pages is None:
                pages_to_solve = list(range(1, total_pages + 1))
                is_full = True
            else:
                pages_to_solve = [p for p in selected_pages if 1 <= p <= total_pages]
                is_full = (len(pages_to_solve) == total_pages)

            if not pages_to_solve:
                self.print_status("ERROR", "No valid pages selected.")
                return (final_status, final_score, final_elapsed)

            effective_force = self.force_solve_all
            captured_page_errors = set()

            def _solver_diag_cb(reason, **kw):
                pnum = int(kw.get("page_number") or 0)
                captured_page_errors.add(pnum)
                self.capture_web_error(
                    reason,
                    exercise_title=kw.get("exercise_title") or title,
                    page_number=pnum,
                    solver_name=kw.get("solver") or "",
                    extra=kw.get("extra"),
                )

            engine = ExerciseEngine(
                self.page,
                self.logger,
                answer_db=self.answer_db,
                page_answer_index=self.page_answer_index,
                diagnostic_cb=_solver_diag_cb,
            )
            results = []
            all_success = True
            has_skipped = False
            early_modal_completed = False
            PASS_LINE = 51
            MAX_TIME_PER_PAGE = 300

            for idx_pos, i in enumerate(pages_to_solve):
                # Check if Speexx already popped up the Completion Modal (e.g. remaining pages were already green!)
                if self.detect_completion_modal():
                    if not effective_force:
                        self.logger.info(
                            f"[VERIFY] [OK] Speexx เปิดหน้าสรุปผล Completion Modal ก่อนหน้า {i}/{total_pages} "
                            f"(หน้าถัดไปผ่านครบแล้ว) — ข้ามไปยังขั้นตอนกด Continue ทันที"
                        )
                        early_modal_completed = True
                        break
                    else:
                        self._close_modal_keep_staying()

                if total_pages > 1:
                    nav_ok = self.navigate_to_exercise_page(i)
                    if not nav_ok and self.detect_completion_modal() and not effective_force:
                        self.logger.info(
                            f"[VERIFY] [OK] Completion Modal ปรากฏขณะสลับไปหน้า {i}/{total_pages}"
                        )
                        early_modal_completed = True
                        break
                else:
                    self.wait_for_exercise_content_ready(timeout=6.0)

                et = engine.detect_type(wait_timeout=6.0)
                if et == "unknown" and self.detect_completion_modal() and not effective_force:
                    early_modal_completed = True
                    break

                self.print_status("PAGE", f"{self.T['page']} {i}/{total_pages} | {self.T['type']}: {et}")

                if et in UNSUPPORTED_TYPES:
                    display_name = UNSUPPORTED_TYPES[et]
                    self._record_page_to_db(
                        title,
                        i,
                        total_pages,
                        et,
                        solver=None,
                        verified_override=(et == "type-intro"),
                        persist=True,
                    )
                    pages_recorded_count += 1
                    if et == "type-intro":
                        self.print_status("SKIP", self.T["skip_intro"])
                    else:
                        self.print_status(
                            "SKIP",
                            self.T["skip_unsupported"].format(display_name, et),
                        )
                    results.append((i, "SKIPPED", 0, "N/A"))
                    has_skipped = True
                    if idx_pos == len(pages_to_solve) - 1:
                        self._try_skip_to_next_page()
                    continue

                solver = engine.get_solver(
                    et,
                    force_solve=effective_force,
                    exercise_title=title,
                    page_number=i,
                )
                if not solver:
                    snapshot = self._capture_diagnostic_snapshot(title, i, et)
                    self._record_page_to_db(
                        title,
                        i,
                        total_pages,
                        et,
                        solver=None,
                        verified_override=False,
                        persist=True,
                    )
                    pages_recorded_count += 1
                    detail = f" Snapshot: {snapshot}" if snapshot else ""
                    self.print_status("ERROR", f"No solver for {et}. Skipping.{detail}")
                    results.append((i, "NO SOLVER", 0, "N/A"))
                    all_success = False
                    continue

                self._capture_answer_page_context(
                    title, i, total_pages, et, solver
                )

                page_pass_line = (
                    100 if et in {"type-drag-drop", "type-drag-drop-table"}
                    else PASS_LINE
                )

                if et == "type-video":
                    vid_res = True
                    try:
                        vid_res = solver.solve()
                    except Exception as e:
                        self.print_status("ERROR", f"Video solver error: {e}")
                        self.capture_web_error(
                            "video_solver_exception",
                            exercise_title=title,
                            page_number=i,
                            exercise_type=et,
                            solver_name="VideoSolver",
                            extra={"error": str(e)},
                        )
                    if vid_res == "RE_DETECT":
                        et = engine.detect_type(wait_timeout=4.5)
                        self.print_status("PAGE", f"{self.T['page']} {i}/{total_pages} | {self.T['type']}: {et}")
                        solver = engine.get_solver(
                            et,
                            force_solve=effective_force,
                            exercise_title=title,
                            page_number=i,
                        )
                        if not solver:
                            results.append((i, "NO SOLVER", 0, "N/A"))
                            all_success = False
                            continue
                        self._capture_answer_page_context(
                            title, i, total_pages, et, solver
                        )
                        page_pass_line = (
                            100 if et in {"type-drag-drop", "type-drag-drop-table"}
                            else PASS_LINE
                        )
                    else:
                        self._record_page_to_db(
                            title,
                            i,
                            total_pages,
                            et,
                            solver=solver,
                            verified_override=True,
                            persist=True,
                        )
                        pages_recorded_count += 1
                        elapsed = solver.stop_timer() if solver.start_time else "N/A"
                        self.print_status("RESULT", f"{self.T['page']} {i}: {self.T['success']} (video) | {elapsed}")
                        results.append((i, "SUCCESS", 100, elapsed))
                        if idx_pos == len(pages_to_solve) - 1:
                            self._try_skip_to_next_page()
                        continue

                if not effective_force:
                    try:
                        existing_score = solver.get_result_score(wait_for_score=False)
                    except Exception:
                        existing_score = 0

                    if existing_score >= page_pass_line:
                        try:
                            solver.extract_current_state_answers(verified=True)
                        except Exception as e:
                            self.logger.debug(f"[DB] Early-pass extract warning: {e}")
                        self._record_page_to_db(
                            title,
                            i,
                            total_pages,
                            et,
                            solver=solver,
                            verified_override=True,
                            persist=True,
                        )
                        pages_recorded_count += 1
                        self.print_status(
                            "RESULT",
                            f"{self.T['page']} {i}: {self.T['success']} "
                            f"({existing_score}) [already passed]"
                        )
                        results.append((i, "SUCCESS", existing_score, "0.00s"))
                        if idx_pos == len(pages_to_solve) - 1:
                            self._try_skip_to_next_page()
                        continue
                else:
                    self.logger.info(
                        f"[FORCE] Page {i}: force_solve=True — skipping early-pass check"
                    )

                max_retries = 3
                retries = 0
                success = False
                score = 0
                elapsed = "N/A"
                best_score = 0
                page_start_time = time.time()

                while retries < max_retries:
                    if time.time() - page_start_time > MAX_TIME_PER_PAGE:
                        self.print_status(
                            "WAIT",
                            f"Page {i} exceeded {MAX_TIME_PER_PAGE}s. Skipping."
                        )
                        success = False
                        break

                    try:
                        success = solver.solve()
                    except Exception as e:
                        self.print_status("ERROR", f"Solver error: {str(e)}")
                        self.capture_web_error(
                            "solver_exception",
                            exercise_title=title,
                            page_number=i,
                            exercise_type=et,
                            solver_name=type(solver).__name__,
                            extra={"error": str(e)},
                        )
                        captured_page_errors.add(i)
                        success = False

                    elapsed = solver.stop_timer() if solver.start_time else "N/A"
                    # If Speexx immediately popped up the completion modal upon passing this page:
                    if self.detect_completion_modal():
                        info_now = self.extract_completion_info()
                        try:
                            modal_sc = int(str(info_now.get("score", "100")).strip())
                        except Exception:
                            modal_sc = 100
                        score = max(score, modal_sc, page_pass_line if success else 0)
                    else:
                        score = solver.get_result_score(wait_for_score=True)

                    if score > best_score:
                        best_score = score

                    if score >= page_pass_line:
                        success = True
                        break
                    else:
                        retries += 1
                        if retries < max_retries:
                            self.print_status("WAIT", self.T['retrying'].format(retries, max_retries))
                            self._reset_exercise_page()
                            solver.start_timer()
                        else:
                            self.print_status("WAIT", f"{self.T['max_retries']} (Score: {best_score})")

                passed_page = score >= page_pass_line
                if not passed_page and solver.last_recorded_answer is None:
                    try:
                        solver.extract_current_state_answers(verified=False)
                    except Exception:
                        pass

                has_verified_solution = (
                    isinstance(solver.last_recorded_answer, dict)
                    and solver.last_recorded_answer.get("verified", True) is not False
                    and bool(solver.last_recorded_answer.get("answers"))
                )
                verified_state = True if (passed_page or has_verified_solution) else False

                self._record_page_to_db(
                    title,
                    i,
                    total_pages,
                    et,
                    solver=solver,
                    verified_override=verified_state,
                    persist=True,
                )
                pages_recorded_count += 1

                if passed_page:
                    self.logger.info(
                        f"[VERIFY] [OK] หน้า {i}/{total_pages} ({et}) ผ่านเกณฑ์ด้วยคะแนน {score}/100 ({elapsed})"
                    )
                    self.print_status("RESULT", f"{self.T['page']} {i}: {self.T['success']} ({score}) | {elapsed}")
                    results.append((i, "SUCCESS", score, elapsed))
                    if self.detect_completion_modal():
                        if not effective_force or idx_pos == len(pages_to_solve) - 1:
                            early_modal_completed = True
                            break
                        else:
                            self._close_modal_keep_staying()
                    elif idx_pos == len(pages_to_solve) - 1 or pages_to_solve[idx_pos + 1] == i + 1:
                        if self._try_skip_to_next_page() and self.detect_completion_modal():
                            if not effective_force or idx_pos == len(pages_to_solve) - 1:
                                early_modal_completed = True
                                break
                            else:
                                self._close_modal_keep_staying()
                else:
                    if i not in captured_page_errors:
                        self.capture_web_error(
                            f"page_score_below_pass_{best_score}",
                            exercise_title=title,
                            page_number=i,
                            exercise_type=et,
                            solver_name=type(solver).__name__,
                            extra={"best_score": best_score, "pass_line": page_pass_line},
                        )
                        captured_page_errors.add(i)
                    self.print_status("ERROR", f"{self.T['page']} {i}: {self.T['failed']} (Score: {best_score}) | {elapsed}")
                    results.append((i, "FAILED", best_score, elapsed))
                    all_success = False
                    if idx_pos == len(pages_to_solve) - 1:
                        self._try_skip_to_next_page()

            self._print_summary_report(results)

            final_status = "SUCCESS" if all_success else "FAILED"
            if has_skipped and all((r[1] == "SKIPPED") for r in results):
                final_status = "SKIPPED"

            for _, _, s, _ in results:
                if isinstance(s, (int, float)) and s > final_score:
                    final_score = s
            total_secs = 0.0
            for _, _, _, e in results:
                total_secs += self._parse_elapsed_seconds(e)
            final_elapsed = f"{total_secs:.2f}s"

            self._save_answer_db(self.current_chapter_name)
            exercise_db_saved = True
            self.print_status(
                "DB",
                self.T["db_saved_exercise"].format(
                    title,
                    self.current_chapter_name,
                    pages_recorded_count,
                ),
            )

            if batch_mode:
                if not is_full:
                    self.print_status("INFO", self.T['selected_only'])
                self.print_status("INFO", "Done.")
                try:
                    if self.detect_completion_modal():
                        self._auto_dismiss_modal()
                        time.sleep(0.5)
                except Exception:
                    pass
                return (final_status, final_score, final_elapsed)

            self.print_status("INFO", self.T['selected_only'] if not is_full else "Done.")
            if not is_full:
                self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
                return (final_status, final_score, final_elapsed)

            # Check for Completion Modal regardless of whether all_success had a transient hiccup!
            modal_ready = early_modal_completed or self.detect_completion_modal()
            if not modal_ready:
                modal_wait_secs = 14 if all_success else 3
                modal_ready = self.wait_for_completion_modal(timeout=modal_wait_secs)

            if modal_ready:
                modal_info = self.extract_completion_info()
                self.logger.info(
                    f"[VERIFY] [OK] ยืนยันหน้าสรุปผล Completion Modal: score={modal_info.get('score')}/{modal_info.get('score_max')} "
                    f"title={modal_info.get('title')} time={modal_info.get('time')}"
                )
                if final_status != "SUCCESS":
                    try:
                        msc = int(str(modal_info.get("score") or "0").strip())
                        if msc >= PASS_LINE:
                            final_status = "SUCCESS"
                            final_score = max(final_score, msc)
                    except Exception:
                        pass

                previous_url = self.page.url
                previous_pkt = self._extract_packet_key(previous_url)
                previous_title = title if (title and title != "Unknown") else self.get_current_exercise_title()
                if auto_continue:
                    if continuation_depth >= self.MAX_NEW_EXERCISE_CHAIN:
                        self.print_status(
                            "ERROR",
                            self.T["stop_chain_limit"].format(self.MAX_NEW_EXERCISE_CHAIN),
                        )
                        return (final_status, final_score, final_elapsed)
                    action = "continue" if self.click_modal_continue() else "none"
                else:
                    action = self.handle_completion_modal(results, skip_summary=True)
                if action == "repeat":
                    self.print_status("INFO", "Restarting packet (Repeat)...")
                    time.sleep(0.8)
                    try:
                        self.navigate_to_exercise_page(1)
                    except Exception:
                        pass
                    return self.auto_solve_exercise(
                        title, selected_pages=None,
                        is_continuation=True, already_opened=True,
                        total_pages=total_pages,
                        row_index=row_index,
                        chain_direction=chain_direction,
                    )
                elif action == "continue":
                    self.print_status("OK", "Moving on (Continue)...")
                    try:
                        if auto_continue:
                            # Wait up to 10s for Speexx to either load the next exercise packet OR redirect to /results
                            self.page.wait_for_function(
                                """
                                (previous) => {
                                    if (window.location.href !== previous.url) return true;
                                    const selectors = [
                                        '.folders-dropdown .title span',
                                        'h1.exercise-header',
                                        '.subheader .title',
                                        '.packet-title'
                                    ];
                                    return selectors.some(selector => {
                                        const element = document.querySelector(selector);
                                        return element && element.textContent.trim() &&
                                            element.textContent.trim() !== previous.title;
                                    });
                                }
                                """,
                                arg={"url": previous_url, "title": previous_title},
                                timeout=10000,
                            )
                            if self._is_on_results_page():
                                self.logger.info(
                                    "[CONTINUE] Speexx redirected Continue learning back to /results (goBackTo) — opening next exercise in order"
                                )
                                return self._continue_auto_from_results(
                                    title, final_status, final_score,
                                    final_elapsed, chain_seen_titles,
                                    continuation_depth,
                                    current_row_index=row_index,
                                    chain_direction=chain_direction,
                                )

                        # Wait for the new packet route & exercise content to finish settling
                        settle_deadline = time.time() + 8.0
                        while time.time() < settle_deadline:
                            if self._is_on_results_page():
                                break
                            cand_pkt = self._extract_packet_key(self.page.url)
                            cand_title = self.get_current_exercise_title()
                            pkt_changed = bool(cand_pkt and cand_pkt != previous_pkt)
                            title_changed = bool(
                                cand_title and cand_title != "Unknown" and cand_title != previous_title
                            )
                            if pkt_changed or title_changed:
                                break
                            time.sleep(0.15)

                        if self._is_on_results_page():
                            self.logger.info(
                                "[CONTINUE] Speexx navigated to /results — opening next exercise in order"
                            )
                            return self._continue_auto_from_results(
                                title, final_status, final_score,
                                final_elapsed, chain_seen_titles,
                                continuation_depth,
                                current_row_index=row_index,
                                chain_direction=chain_direction,
                            )

                        self.wait_for_exercise_content_ready(timeout=6.5)

                        new_total = self.get_total_exercises(
                            retries=4,
                            wait_seconds=0.6,
                        )
                        new_title = self.get_current_exercise_title()
                        new_pkt = self._extract_packet_key(self.page.url)

                        if auto_continue and new_total == 0:
                            return self._continue_auto_from_results(
                                title, final_status, final_score,
                                final_elapsed, chain_seen_titles,
                                continuation_depth,
                                current_row_index=row_index,
                                chain_direction=chain_direction,
                            )
                        if (auto_continue and new_pkt == previous_pkt and
                                (new_title == previous_title or new_title == "Unknown")):
                            self.logger.warning("[CONTINUE] Still on same exercise after Continue; falling back to /results")
                            return self._continue_auto_from_results(
                                title, final_status, final_score,
                                final_elapsed, chain_seen_titles,
                                continuation_depth,
                                current_row_index=row_index,
                                chain_direction=chain_direction,
                            )

                        known_titles = self._chapter_live_titles.get(self.current_chapter_name) or []
                        next_row_idx = None
                        if auto_continue and self.force_solve_all and row_index is not None and known_titles:
                            expected_idx = (
                                row_index + 1 if chain_direction == "down" else row_index - 1
                            )
                            if 0 <= expected_idx < len(known_titles):
                                expected_title = known_titles[expected_idx]
                                if (
                                    expected_title
                                    and new_title
                                    and new_title != "Unknown"
                                    and self._norm_ex_title(new_title)
                                    != self._norm_ex_title(expected_title)
                                ):
                                    self.logger.info(
                                        f"[CONTINUE] Speexx ข้ามไปที่ '{new_title}' — "
                                        f"เปิดแบบฝึกหัดถัดไปตามลำดับ '{expected_title}' แทน"
                                    )
                                    return self._continue_auto_from_results(
                                        title, final_status, final_score,
                                        final_elapsed, chain_seen_titles,
                                        continuation_depth,
                                        current_row_index=row_index,
                                        chain_direction=chain_direction,
                                    )
                                next_row_idx = expected_idx
                                if (not new_title or new_title == "Unknown") and expected_title:
                                    new_title = expected_title

                        if next_row_idx is None and known_titles and new_title and new_title != "Unknown":
                            nt_norm = self._norm_ex_title(new_title)
                            for k_idx, kt in enumerate(known_titles):
                                if self._norm_ex_title(kt) == nt_norm:
                                    next_row_idx = k_idx
                                    break

                        if auto_continue and new_pkt and f"pkt:{new_pkt}" in (chain_seen_titles or set()):
                            self.print_status("OK", self.T["stop_loop_detected"])
                            return (final_status, final_score, final_elapsed)

                        self.logger.info(
                            f"[VERIFY] [OK] เข้าสู่แบบฝึกหัดถัดไปสำเร็จ: {new_title} ({new_total} หน้า)"
                        )
                        self.print_status("OK", f"New exercise loaded: {new_title} ({new_total} pages)")
                        return self.auto_solve_exercise(
                            new_title, selected_pages=None,
                            is_continuation=True, already_opened=True,
                            total_pages=new_total,
                            auto_continue=auto_continue,
                            continuation_depth=continuation_depth + 1,
                            chain_seen_titles=chain_seen_titles,
                            row_index=next_row_idx,
                            chain_direction=chain_direction,
                        )
                    except Exception as e:
                        if auto_continue:
                            self.logger.warning(
                                f"[CONTINUE] Direct exercise navigation failed; "
                                f"trying Results fallback: {e}"
                            )
                            return self._continue_auto_from_results(
                                title, final_status, final_score,
                                final_elapsed, chain_seen_titles,
                                continuation_depth,
                                current_row_index=row_index,
                                chain_direction=chain_direction,
                            )
                        self.print_status("WAIT", self.T["new_page_not_loaded"].format(e))
                        return (final_status, final_score, final_elapsed)
                else:
                    if auto_continue:
                        return self._continue_auto_from_results(
                            title, final_status, final_score,
                            final_elapsed, chain_seen_titles,
                            continuation_depth,
                            current_row_index=row_index,
                            chain_direction=chain_direction,
                        )
                    return (final_status, final_score, final_elapsed)
            else:
                if auto_continue:
                    if continuation_depth >= self.MAX_NEW_EXERCISE_CHAIN:
                        self.print_status(
                            "ERROR",
                            self.T["stop_chain_limit"].format(self.MAX_NEW_EXERCISE_CHAIN),
                        )
                        return (final_status, final_score, final_elapsed)
                    return self._continue_auto_from_results(
                        title, final_status, final_score,
                        final_elapsed, chain_seen_titles,
                        continuation_depth,
                        current_row_index=row_index,
                        chain_direction=chain_direction,
                    )
                return (final_status, final_score, final_elapsed)

        except Exception as e:
            self.print_status("ERROR", f"Auto solve error: {str(e)}")
            self.capture_web_error(
                "auto_solve_unhandled_exception",
                exercise_title=title,
                extra={"error": str(e)},
            )
        finally:
            try:
                if not exercise_db_saved and (pages_recorded_count > 0 or self.answer_db or self.structured_page_records):
                    self._save_answer_db(self.current_chapter_name)
            except Exception as save_err:
                self.logger.error(f"[DB] Final save error: {save_err}")
            if not is_continuation and not batch_mode:
                try:
                    self.after_solve_menu()
                except Exception:
                    pass

        return (final_status, final_score, final_elapsed)

    def _next_uncompleted_exercise_entry(
        self,
        current_title,
        rows=None,
        seen_titles=None,
        current_row_index=None,
        chain_direction=None,
    ):
        if seen_titles is None:
            seen_titles = set()

        exercises = [
            info for info in self._inspect_all_visible_result_rows()
            if info.get("title")
        ]
        if not exercises:
            return None, None, chain_direction

        current_key = self._norm_ex_title(current_title)
        current_index = -1

        if current_row_index is not None and 0 <= current_row_index < len(exercises):
            if self._norm_ex_title(exercises[current_row_index]["title"]) == current_key:
                current_index = current_row_index

        if current_index < 0 and current_key:
            matching_indices = [
                idx for idx, item in enumerate(exercises)
                if self._norm_ex_title(item["title"]) == current_key
            ]
            if matching_indices:
                if current_row_index is not None:
                    current_index = min(matching_indices, key=lambda x: abs(x - current_row_index))
                else:
                    current_index = matching_indices[0]

        resolved_direction = chain_direction
        # Speexx /results lists exercises newest-at-top [1] (index 0) and Lesson 1.1 at-bottom [N] (index N-1).
        # Chronological learning order is UPWARD: index - 1 -> index - 2 -> ... -> 0!
        if resolved_direction == "down":
            start_i = current_index + 1 if current_index >= 0 else 0
            indexes = list(range(start_i, len(exercises)))
        else:
            if current_index > 0:
                resolved_direction = "up"
                indexes = list(range(current_index - 1, -1, -1))
                if not self.force_solve_all:
                    indexes.extend(range(len(exercises) - 1, current_index, -1))
            elif current_index == 0:
                if self.force_solve_all:
                    # Started at [1] (topmost row) in Force mode with no new exercise above it: step [2]..[N]
                    resolved_direction = "down"
                    indexes = list(range(1, len(exercises)))
                else:
                    resolved_direction = "up"
                    indexes = list(range(len(exercises) - 1, 0, -1))
            else:
                resolved_direction = "up"
                indexes = list(range(len(exercises) - 1, -1, -1))

        for index in indexes:
            item = exercises[index]
            name = item["title"]
            if not name:
                continue
            r_idx = item["row_index"]
            norm_name = self._norm_ex_title(name)
            row_key = f"row:{norm_name}#{r_idx}"
            title_key = f"title:{norm_name}"

            if not self.force_solve_all and item["is_completed"]:
                continue
            if row_key in seen_titles or norm_name in seen_titles:
                continue
            if title_key in seen_titles and sum(
                1 for x in exercises if self._norm_ex_title(x["title"]) == norm_name
            ) <= 1:
                continue

            seen_titles.add(row_key)
            return name, r_idx, resolved_direction

        return None, None, resolved_direction

    def _next_uncompleted_exercise_title(self, current_title, rows, seen_titles):
        name, _, _ = self._next_uncompleted_exercise_entry(current_title, rows, seen_titles)
        return name

    def _continue_auto_from_results(
        self,
        current_title,
        status,
        score,
        elapsed,
        seen_titles,
        continuation_depth,
        current_row_index=None,
        chain_direction=None,
    ):
        try:
            if not self.force_solve_all and self.check_course_progress():
                self.print_status("OK", self.T["course_100_stop"])
                return (status, score, elapsed)

            self._ensure_results_chapter_and_exercises_ready(
                force_chapter_click=False,
                wait_timeout=15000,
            )
            if seen_titles is None:
                seen_titles = set()
            next_title, next_row_idx, next_dir = self._next_uncompleted_exercise_entry(
                current_title,
                rows=None,
                seen_titles=seen_titles,
                current_row_index=current_row_index,
                chain_direction=chain_direction,
            )
            if not next_title:
                stop_key = "finished_all_in_chapter" if self.force_solve_all else "no_more_uncompleted"
                self.print_status("OK", self.T[stop_key])
                return (status, score, elapsed)

            msg_key = "opening_next_exercise" if self.force_solve_all else "opening_uncompleted"
            self.print_status("INFO", self.T[msg_key].format(next_title))
            if not self._click_row_safely(next_title, row_index=next_row_idx):
                self.print_status("ERROR", self.T["open_next_failed"].format(next_title))
                return (status, score, elapsed)
            self.page.wait_for_selector(
                ".exercise, video, .exercises-large-navigation li",
                state="visible",
                timeout=15000,
            )
            self.wait_for_exercise_content_ready(timeout=6.0)
            next_total = self.get_total_exercises(retries=3, wait_seconds=0.6)
            if next_total == 0:
                if self.page.locator(".exercise, .video").count() > 0:
                    next_total = 1
                else:
                    self.print_status("ERROR", self.T["opened_no_pages"].format(next_title))
                    return (status, score, elapsed)
            return self.auto_solve_exercise(
                next_title,
                selected_pages=None,
                is_continuation=True,
                already_opened=True,
                total_pages=next_total,
                auto_continue=True,
                continuation_depth=continuation_depth + 1,
                chain_seen_titles=seen_titles,
                row_index=next_row_idx,
                chain_direction=next_dir,
            )
        except Exception as e:
            self.print_status("WAIT", self.T["results_return_failed"].format(e))
            return (status, score, elapsed)
