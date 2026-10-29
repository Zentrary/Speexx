"""DiagnosticsMixin: session logging, Playwright web event listeners, error capture, and terminal output."""

import json
import logging
import os
import re
import shutil
import sys
from datetime import datetime

from ..logging_utils import TeeLogger, _TeeLogHandler
from ..ui_utils import Fore, Style


class DiagnosticsMixin:
    def ensure_folders(self):
        for f in [self.config_folder, self.logs_folder,
                  self.dump_folder, self.reports_folder, self.profiles_folder]:
            if not os.path.exists(f):
                os.makedirs(f)

    def setup_logging(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_log_dir = os.path.join(self.logs_folder, f"session_{ts}")
        self.session_errors_dir = os.path.join(self.session_log_dir, "errors")
        os.makedirs(self.session_errors_dir, exist_ok=True)

        self.log_filename = os.path.join(self.session_log_dir, "log.txt")
        self.error_counter = 0
        self.recent_web_events = []
        self._attached_diag_pages = set()

        self.original_stdout = sys.stdout
        self.tee_logger = TeeLogger(self.log_filename, self.original_stdout)
        sys.stdout = self.tee_logger

        self.logger = logging.getLogger(f"speexx.{ts}")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        self.logger.handlers.clear()
        handler = _TeeLogHandler(self.tee_logger)
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        self.logger.addHandler(handler)
        self.logger.info("Program started")
        self.logger.info(f"Session log folder: {self.session_log_dir}")
        self.logger.info(f"Log file: {self.log_filename}")

    def _record_web_event(self, kind, detail):
        if kind == "NAV" and detail:
            m_art = re.search(r"/articles/(\d+)", str(detail))
            if m_art:
                self.last_results_url = f"https://portal.speexx.com/articles/{m_art.group(1)}/results"
        entry = {
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "kind": kind,
            "detail": str(detail)[:500],
        }
        self.recent_web_events.append(entry)
        if len(self.recent_web_events) > 120:
            self.recent_web_events = self.recent_web_events[-120:]

    def _attach_web_diagnostics(self, page):
        if not page:
            return
        pid = id(page)
        if pid in self._attached_diag_pages:
            return
        self._attached_diag_pages.add(pid)

        def on_frame_nav(frame):
            try:
                if frame == page.main_frame:
                    u = frame.url or ""
                    self._record_web_event("NAV", u)
                    self.logger.info(f"[WEB-NAV] {u}")
            except Exception:
                pass

        def on_page_error(err):
            try:
                msg = str(err)[:400]
                self._record_web_event("PAGEERROR", msg)
                self.logger.warning(f"[WEB-JS-ERROR] {msg}")
            except Exception:
                pass

        def on_console(msg):
            try:
                mtype = (msg.type or "").lower()
                if mtype in ("error", "warning"):
                    txt = (msg.text or "")[:400]
                    self._record_web_event(f"CONSOLE_{mtype.upper()}", txt)
                    self.logger.info(f"[WEB-CONSOLE:{mtype}] {txt}")
            except Exception:
                pass

        def on_req_failed(req):
            try:
                u = req.url or ""
                if "speexx" in u.lower():
                    fail_obj = req.failure
                    fail_str = (
                        fail_obj.get("errorText")
                        if isinstance(fail_obj, dict)
                        else str(fail_obj)
                    )
                    detail = f"{req.method} {u} -> {fail_str}"
                    self._record_web_event("REQ_FAIL", detail)
                    self.logger.warning(f"[WEB-REQ-FAIL] {detail[:400]}")
            except Exception:
                pass

        def on_response(resp):
            try:
                st = resp.status
                u = resp.url or ""
                if st >= 400 and "speexx" in u.lower():
                    detail = f"{st} {resp.request.method} {u}"
                    self._record_web_event("HTTP_ERR", detail)
                    self.logger.warning(f"[WEB-HTTP-ERR] {detail[:400]}")
            except Exception:
                pass

        try:
            page.on("framenavigated", on_frame_nav)
            page.on("pageerror", on_page_error)
            page.on("console", on_console)
            page.on("requestfailed", on_req_failed)
            page.on("response", on_response)
        except Exception as e:
            self.logger.debug(f"[WEB-DIAG] attach warning: {e}")

    def capture_web_error(
        self,
        reason,
        exercise_title="",
        page_number=0,
        exercise_type="",
        solver_name="",
        extra=None,
    ):
        import traceback as _tb

        self.error_counter += 1
        now_dt = datetime.now()
        stamp = now_dt.strftime("%H%M%S")
        slug = re.sub(r"[^A-Za-z0-9ก-๙._-]+", "_", str(reason or "error")).strip("._")[:48] or "error"
        err_dir = os.path.join(
            self.session_errors_dir,
            f"err_{self.error_counter:03d}_{slug}_{stamp}",
        )
        os.makedirs(err_dir, exist_ok=True)

        html_path = os.path.join(err_dir, "errorinwebsite.html")
        png_path = os.path.join(err_dir, "error.png")
        json_path = os.path.join(err_dir, "error_details.json")

        latest_html = os.path.join(self.session_log_dir, "errorinwebsite.html")
        latest_png = os.path.join(self.session_log_dir, "error.png")
        latest_json = os.path.join(self.session_log_dir, "error_details.json")

        current_url = ""
        visible_buttons = []
        body_excerpt = ""
        saved_html = False
        saved_png = False

        if self.page:
            try:
                current_url = self.page.url or ""
            except Exception:
                current_url = ""

            try:
                dom_meta = self.page.evaluate("""
                    () => {
                        const btns = [];
                        document.querySelectorAll("button, [role='button'], a.btn, .show-more").forEach(b => {
                            const r = b.getBoundingClientRect();
                            const st = window.getComputedStyle(b);
                            if (r.width > 0 && r.height > 0 && st.display !== 'none' && st.visibility !== 'hidden') {
                                const t = ((b.innerText || b.textContent || '') + ' | aria=' + (b.getAttribute('aria-label') || '') + ' | cls=' + (b.className || '')).replace(/\\s+/g, ' ').trim();
                                if (t) btns.push(t.slice(0, 140));
                            }
                        });
                        const bodyTxt = document.body ? (document.body.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 1000) : '';
                        return { btns: btns.slice(0, 30), bodyTxt };
                    }
                """) or {}
                visible_buttons = dom_meta.get("btns") or []
                body_excerpt = dom_meta.get("bodyTxt") or ""
            except Exception:
                pass

            try:
                raw_html = self.page.content()
                header_comment = (
                    f"<!-- SPEEXX DIAGNOSTIC SNAPSHOT\n"
                    f"  Timestamp : {now_dt.isoformat()}\n"
                    f"  Reason    : {reason}\n"
                    f"  URL       : {current_url}\n"
                    f"  Chapter   : {self.current_chapter_name}\n"
                    f"  Exercise  : {exercise_title}\n"
                    f"  Page      : {page_number}\n"
                    f"  Type      : {exercise_type}\n"
                    f"  Solver    : {solver_name}\n"
                    f"-->\n"
                )
                full_html = header_comment + raw_html
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(full_html)
                shutil.copy2(html_path, latest_html)
                saved_html = True
            except Exception as e:
                self.logger.warning(f"[DIAG] Cannot save errorinwebsite.html: {e}")

            try:
                try:
                    self.page.screenshot(path=png_path, full_page=True, timeout=5000)
                except Exception:
                    self.page.screenshot(path=png_path, full_page=False, timeout=5000)
                shutil.copy2(png_path, latest_png)
                saved_png = True
            except Exception as e:
                self.logger.warning(f"[DIAG] Cannot save error.png: {e}")

        tb_str = ""
        exc_info = sys.exc_info()
        if exc_info and exc_info[0] is not None:
            tb_str = "".join(_tb.format_exception(*exc_info))

        details = {
            "error_id": self.error_counter,
            "timestamp": now_dt.isoformat(),
            "reason": str(reason),
            "url": current_url,
            "chapter_name": self.current_chapter_name,
            "chapter_cid": self.current_chapter_cid,
            "exercise_title": exercise_title,
            "page_number": page_number,
            "exercise_type": exercise_type,
            "solver_name": solver_name,
            "saved_html": saved_html,
            "saved_png": saved_png,
            "visible_buttons": visible_buttons,
            "body_excerpt": body_excerpt,
            "extra": extra,
            "traceback": tb_str,
            "recent_web_events": self.recent_web_events[-40:],
        }
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(details, f, ensure_ascii=False, indent=2)
            shutil.copy2(json_path, latest_json)
        except Exception as e:
            self.logger.warning(f"[DIAG] Cannot save error_details.json: {e}")

        artifacts = ["log.txt"]
        if saved_html:
            artifacts.append("errorinwebsite.html")
        if saved_png:
            artifacts.append("error.png")
        msg = (
            f"บันทึกไฟล์ตรวจสอบปัญหาแล้ว ({reason}) -> {self.session_log_dir} "
            f"[{', '.join(artifacts)}]"
        )
        print(f"  {Fore.MAGENTA}[DIAG]{Style.RESET_ALL} {msg}")
        self.logger.warning(f"[DIAG] {msg} | bundle={err_dir}")
        return err_dir

    def _capture_diagnostic_snapshot(self, title, page_number, exercise_type):
        if not self.page:
            return None
        err_dir = self.capture_web_error(
            f"unsupported_or_no_solver_{exercise_type}",
            exercise_title=title,
            page_number=page_number,
            exercise_type=exercise_type,
        )
        safe = re.sub(r"[^A-Za-z0-9ก-๙._-]+", "_", title).strip("._") or "exercise"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(
            self.dump_folder,
            f"diagnostic_{safe}_page{page_number}_{exercise_type}_{stamp}.html",
        )
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.page.content())
            self.logger.warning(f"[DIAGNOSTIC] Snapshot saved: {path} (bundle={err_dir})")
            return path
        except Exception as e:
            self.logger.warning(f"[DIAGNOSTIC] Snapshot failed: {e}")
            return err_dir

    def clear_screen(self):
        try:
            os.system('cls' if os.name == 'nt' else 'clear')
        except Exception:
            pass

    def print_header(self, clear=True):
        if clear:
            self.clear_screen()
        print("""                
   .d888b,?88,.d88b, d8888b d8888b?88,  88P?88,  88P
   ?8b,   `?88'  ?88d8b_,dPd8b_,dP `?8bd8P' `?8bd8P'
     `?8b   88b  d8P88b    88b     d8P?8b,  d8P?8b, 
  `?888P'   888888P'`?888P'`?888P'd8P' `?8bd8P' `?8b
            88P'                                    
           d88                      Make by Zentrary               
           ?8P                                      
""")

    def print_status(self, t, msg):
        prefix_map = {
            "INFO": f"{Fore.CYAN}[INFO]{Style.RESET_ALL}",
            "OK":   f"{Fore.GREEN}[ OK ]{Style.RESET_ALL}",
            "ERROR":f"{Fore.RED}[ERR ]{Style.RESET_ALL}",
            "WAIT": f"{Fore.YELLOW}[WAIT]{Style.RESET_ALL}",
            "PAGE": f"{Fore.MAGENTA}[PAGE]{Style.RESET_ALL}",
            "RESULT": f"{Fore.WHITE}[>>  ]{Style.RESET_ALL}",
            "MENU": f"{Fore.CYAN}[MENU]{Style.RESET_ALL}",
            "SKIP": f"{Fore.YELLOW}[SKIP]{Style.RESET_ALL}",
            "DB": f"{Fore.BLUE}[ DB ]{Style.RESET_ALL}",
        }
        prefix = prefix_map.get(t, "[?]")
        print(f"  {prefix} {msg}")
        self.logger.info(f"{t}: {msg}")
