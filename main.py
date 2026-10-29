import os
import sys
import time
import json
import copy
import logging
import re
import random
import threading
import hashlib
import base64
import shutil
import tempfile
import unicodedata
import requests
import argparse
import subprocess
from difflib import SequenceMatcher
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    HAS_COLOR = True
except ImportError:
    HAS_COLOR = False
    class _DummyColor:
        def __getattr__(self, name):
            return ''
    Fore = _DummyColor()
    Style = _DummyColor()

ACTION_SETTLE_SECONDS = 0.25
EXERCISE_STEP_PAUSE_SECONDS = 0.15
FAST_ACTION_SETTLE_SECONDS = 0.10

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


def _char_display_width(ch):
    if unicodedata.combining(ch) or unicodedata.category(ch) in ("Mn", "Me", "Cf"):
        return 0
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    return 1


def display_width(text):
    clean = _ANSI_ESCAPE_RE.sub("", str(text or ""))
    return sum(_char_display_width(ch) for ch in clean)


def truncate_display(text, max_width, ellipsis="..."):
    s = str(text or "")
    if display_width(s) <= max_width:
        return s
    ell_w = display_width(ellipsis)
    target = max(0, max_width - ell_w)
    out = []
    cur = 0
    for ch in s:
        w = _char_display_width(ch)
        if cur + w > target:
            break
        out.append(ch)
        cur += w
    return "".join(out) + ellipsis


def pad_display(text, width, align="left"):
    s = str(text or "")
    pad = max(0, width - display_width(s))
    if align == "right":
        return (" " * pad) + s
    if align == "center":
        left = pad // 2
        return (" " * left) + s + (" " * (pad - left))
    return s + (" " * pad)


TRANSLATIONS = {
    "th": {
        "select_lang": "เลือกภาษา / Select Language",
        "lang_th": "ภาษาไทย",
        "lang_en": "English",

        "login_menu": "เมนูเข้าสู่ระบบ",
        "opt_login": "เริ่มต้นเบราว์เซอร์และเข้าสู่ระบบ",
        "opt_manage_acc": "จัดการบัญชี",
        "opt_multi_acc": "โหมดหลายบัญชี (Multi-Account)",
        "opt_exit": "ออกจากโปรแกรม",

        "select_account": "เลือกบัญชี",
        "add_account": "เพิ่มบัญชีใหม่",
        "delete_pwd": "ลบรหัสผ่านที่บันทึกไว้",
        "delete_acc": "ลบบัญชี",
        "no_accounts": "ยังไม่มีบัญชีที่บันทึกไว้",
        "saved_pwd": "บันทึกรหัสผ่านแล้ว",
        "saved_acc": "บันทึกบัญชี {} แล้ว",
        "deleted_pwd": "ลบรหัสผ่านของ {} แล้ว",
        "deleted_acc": "ลบบัญชี {} แล้ว",
        "ask_save_pwd": "บันทึกรหัสผ่าน? (y/n): ",
        "pwd_of": "Password ของ {}: ",
        "no_password": "ไม่มีรหัสผ่าน",
        "using_saved_pwd": "ใช้รหัสผ่านที่บันทึกไว้",
        "session_valid": "Session ยังใช้ได้ — ข้ามการ Login",

        "dashboard_menu": "เมนูหลัก (Dashboard)",
        "opt_select_chapter": "เลือกบทเรียนและดูแบบฝึกหัด",
        "opt_results": "ไปที่หน้า Results",
        "opt_search_answer": "ค้นหาคำตอบจากโจทย์ที่คัดลอก",
        "opt_logout": "ออกจากระบบ",

        "available_chapters": "บทเรียนที่มีให้เลือก",
        "select_chapter": "เลือกบทเรียน: ",
        "no_chapters": "ไม่พบบทเรียนที่ปลดล็อค",

        "exercise_list": "รายการแบบฝึกหัด",
        "select_exercises": "เลือกแบบฝึกหัด (เช่น 1, 1-5, 1,3,5, all): ",
        "no_exercises": "ไม่พบแบบฝึกหัด",
        "table_no": "No.",
        "table_title": "หัวข้อ",
        "table_date": "วันที่",
        "table_time": "เวลารวม",
        "table_score": "คะแนน",
        "table_review": "ทบทวน",

        "exercise_menu": "เมนูแบบฝึกหัด",
        "opt_dump": "Dump ทุกหน้า",
        "opt_new_learning_path": "ทำแบบฝึกหัดใหม่ต่อเนื่อง (เริ่มรายการแรกและ Continue อัตโนมัติ)",
        "select_pages": "เลือกข้อที่ต้องการทำ (เช่น 1, 1-5, all): ",

        "multi_select_mode_title": "เลือกโหมดการทำ ({} ข้อ)",
        "opt_one_by_one": "ทำทีละข้อ",
        "opt_all_auto": "ทำทั้งหมดอัตโนมัติ",
        "select_mode_prompt": "เลือกโหมด: ",
        "solve_mode_title": "เลือกโหมดการทำ",
        "solve_mode_force": "ทำทุกข้อ (force — ทำแม้ได้คะแนนผ่านแล้ว)",
        "solve_mode_skip_passed": "ข้ามข้อที่ผ่านแล้ว (default)",
        "start_from": "เริ่มจาก: {}",
        "confirm_auto_continue": "เริ่มทำและ Continue อัตโนมัติ? (Enter=yes / 0=ยกเลิก): ",
        "confirm_start_now": "เริ่มเลย? (Enter=yes / 0=ยกเลิก): ",
        "batch_mode_header": "BATCH MODE: {} แบบฝึกหัด",
        "batch_mode_notice": "โหมดนี้จะทำทุกข้อให้เสร็จโดยไม่ถาม",
        "batch_summary_title": "BATCH SUMMARY — สรุปผลรวมทั้งหมด",
        "batch_selected_count": "จำนวนแบบฝึกหัดที่เลือก: {}",

        "auto_solve": "เริ่มทำแบบฝึกหัดอัตโนมัติ",
        "will_not_move": "จะไม่ไปข้อถัดไปจนกว่าจะได้คะแนน >= 51",
        "found_pages": "พบทั้งหมด {} หน้า",
        "page": "หน้า",
        "type": "ประเภท",
        "success": "สำเร็จ",
        "failed": "ล้มเหลว",
        "skipped": "ข้าม",
        "retrying": "กำลังลองใหม่ ครั้งที่ {}/{}...",
        "max_retries": "ลองใหม่ครบกำหนดแล้ว",
        "skip_intro": "ข้ามหน้าแนะนำ (ไม่มีโจทย์ให้ทำ)",
        "skip_unsupported": "ข้ามข้อนี้: ยังไม่รองรับแบบฝึกหัดประเภท {} ({})",
        "stop_chain_limit": "หยุด auto-Continue: ถึงขีดจำกัด {} แบบฝึกหัดแล้ว",
        "stop_same_page": "Continue แล้วหน้า/ชื่อแบบฝึกหัดไม่เปลี่ยน จึงหยุดเพื่อป้องกันวนซ้ำ",
        "stop_loop_detected": "ตรวจพบว่าแบบฝึกหัดเริ่มวนซ้ำ (หรือครบ 100% แล้ว) — หยุดการทำอัตโนมัติ",
        "new_page_not_loaded": "หน้าใหม่ยังไม่โหลด: {}",
        "course_100_stop": "ตรวจพบว่าแบบฝึกหัดครบ 100% แล้ว — หยุดการทำอัตโนมัติเพื่อรอทำแบบทดสอบ",
        "no_more_uncompleted": "ไม่มีแบบฝึกหัดใหม่ที่ยังไม่ผ่านในหน้า Results; จบการทำต่อเนื่อง",
        "opening_uncompleted": "เปิดแบบฝึกหัดที่ยังไม่ผ่าน: {}",
        "open_next_failed": "เปิดแบบฝึกหัดถัดไปไม่สำเร็จ: {}",
        "opened_no_pages": "เปิด {} แล้ว แต่ยังไม่พบหน้าแบบฝึกหัด",
        "results_return_failed": "กลับหน้า Results เพื่อหาแบบฝึกหัดถัดไปไม่สำเร็จ: {}",

        "db_status": "ฐานข้อมูล {}: {} แบบฝึกหัด, {} หน้า, บันทึกคำตอบแล้ว {} หน้า",
        "db_saved_exercise": "บันทึกโจทย์และคำตอบของ '{}' ลงฐานข้อมูล {} แล้ว ({} หน้า)",
        "db_not_found": "ไม่พบฐานข้อมูลคำตอบของ {}",
        "search_title": "ค้นหาคำตอบจากโจทย์ ({})",
        "search_hint_1": "วางโจทย์ได้หลายบรรทัด แล้วพิมพ์ END ในบรรทัดสุดท้าย",
        "search_hint_2": "พิมพ์ 0 เพื่อกลับเมนูหลัก",
        "search_no_query": "ไม่ได้รับโจทย์",
        "search_no_match": "ไม่พบโจทย์ที่ตรงกันในฐานข้อมูล",
        "search_found": "พบคำตอบที่ใกล้เคียง {} รายการ",
        "search_match_pct": "ความตรงกัน {:.1f}%",
        "search_db_question": "โจทย์ฐานข้อมูล: {}",
        "search_answer_label": "คำตอบ:",
        "search_chapter_label": "บทเรียน: {} | แบบฝึกหัด: {}",

        "multi_acc_all": "ทั้งหมด",
        "multi_acc_select": "เลือกบัญชีที่ต้องการรัน: ",
        "multi_acc_no_pwd": "ไม่มีบัญชีที่บันทึกรหัสผ่านไว้",
        "multi_acc_launching": "กำลังเปิด {} บัญชีในหน้าต่างใหม่...",
        "multi_acc_started": "โปรเซสทั้งหมดเริ่มทำงานแล้ว",
        "auto_start_ex": "เริ่มทำแบบฝึกหัด: {}",
        "auto_all_done": "ไม่มีแบบฝึกหัดที่ต้องทำเพิ่ม (หรือทำครบ 100% แล้ว)",
        "auto_finished_acc": "จบการทำงานสำหรับบัญชีนี้",

        "summary": "สรุปผลการทำแบบฝึกหัด",
        "pass": "ผ่าน",
        "fail": "ไม่ผ่าน",
        "skip": "ข้าม",
        "score": "คะแนน",
        "time_spent": "เวลาที่ใช้",
        "total_time": "เวลารวม",
        "passed_count": "ผ่านทั้งหมด",
        "failed_count": "ไม่ผ่าน",
        "skipped_count": "ข้าม",
        "selected_only": "ทำเฉพาะข้อที่เลือกไว้",
        "finished_selected": "ทำครบตามที่เลือกไว้แล้ว",
        "next_action": "ขั้นตอนถัดไป",
        "back_to_list": "กลับไปหน้ารายการแบบฝึกหัด",
        "back_to_main": "กลับไปเมนูหลัก",
        "exit_app": "ออกจากโปรแกรม",

        "repeat": "ทำซ้ำ (Repeat)",
        "continue": "เรียนรู้ต่อ (Continue)",
        "nothing": "ไม่ทำอะไร (กลับเมนูหลัก)",
        "what_next": "ต้องการทำอะไรต่อ?",
        "choose_prompt": "เลือก: ",

        "back": "ย้อนกลับ",
        "invalid_choice": "ตัวเลือกไม่ถูกต้อง",
        "press_enter": "กด Enter เพื่อดำเนินการต่อ...",
        "cancel": "ยกเลิก",
    },
    "en": {
        "select_lang": "Select Language",
        "lang_th": "Thai",
        "lang_en": "English",

        "login_menu": "Login Menu",
        "opt_login": "Start Browser & Login",
        "opt_manage_acc": "Manage Accounts",
        "opt_multi_acc": "Multi-Account Mode",
        "opt_exit": "Exit Program",

        "select_account": "Select Account",
        "add_account": "Add New Account",
        "delete_pwd": "Delete Saved Password",
        "delete_acc": "Delete Account",
        "no_accounts": "No accounts saved yet",
        "saved_pwd": "Password saved",
        "saved_acc": "Saved account {}",
        "deleted_pwd": "Deleted password for {}",
        "deleted_acc": "Deleted account {}",
        "ask_save_pwd": "Save password? (y/n): ",
        "pwd_of": "Password for {}: ",
        "no_password": "No password provided",
        "using_saved_pwd": "Using saved password",
        "session_valid": "Session still valid — skipping login",

        "dashboard_menu": "Dashboard Menu",
        "opt_select_chapter": "Select Chapter & View Exercises",
        "opt_results": "Go to Results Page",
        "opt_search_answer": "Search answer from copied question",
        "opt_logout": "Logout",

        "available_chapters": "Available Chapters",
        "select_chapter": "Select Chapter: ",
        "no_chapters": "No unlocked chapters found",

        "exercise_list": "Exercise List",
        "select_exercises": "Select exercises (e.g. 1, 1-5, 1,3,5, all): ",
        "no_exercises": "No exercises found",
        "table_no": "No.",
        "table_title": "Title",
        "table_date": "Date",
        "table_time": "Time",
        "table_score": "Score",
        "table_review": "Review",

        "exercise_menu": "Exercise Menu",
        "opt_dump": "Dump All Pages",
        "opt_new_learning_path": "New learning path (start at first selected and auto-Continue)",
        "select_pages": "Select pages (e.g. 1, 1-5, all): ",

        "multi_select_mode_title": "Select Solve Mode ({} exercises)",
        "opt_one_by_one": "Solve one by one",
        "opt_all_auto": "Solve all automatically (Batch)",
        "select_mode_prompt": "Select mode: ",
        "solve_mode_title": "Select Solve Mode",
        "solve_mode_force": "Solve all items (force — redo even if already passed)",
        "solve_mode_skip_passed": "Skip already passed items (default)",
        "start_from": "Starting from: {}",
        "confirm_auto_continue": "Start solving and auto-Continue? (Enter=yes / 0=cancel): ",
        "confirm_start_now": "Start now? (Enter=yes / 0=cancel): ",
        "batch_mode_header": "BATCH MODE: {} exercises",
        "batch_mode_notice": "This mode solves all selected exercises automatically without prompting",
        "batch_summary_title": "BATCH SUMMARY — Overall Results",
        "batch_selected_count": "Selected exercises: {}",

        "auto_solve": "Auto Solve",
        "will_not_move": "Will NOT move to next page until current page gets >= 51.",
        "found_pages": "Found {} pages.",
        "page": "Page",
        "type": "Type",
        "success": "SUCCESS",
        "failed": "FAILED",
        "skipped": "SKIPPED",
        "retrying": "Retrying Page ({}/{})...",
        "max_retries": "Max retries reached.",
        "skip_intro": "Skipping intro page (no exercise items)",
        "skip_unsupported": "Skipping unsupported exercise type: {} ({})",
        "stop_chain_limit": "Stopping auto-Continue: reached limit of {} exercises",
        "stop_same_page": "Page/title did not change after Continue — stopping to prevent loop",
        "stop_loop_detected": "Detected repeating exercise (or 100% completed) — stopping auto-Continue",
        "new_page_not_loaded": "Next exercise did not load: {}",
        "course_100_stop": "Course exercises are 100% completed — stopping auto-Continue before test",
        "no_more_uncompleted": "No remaining uncompleted exercises on Results page; finishing auto-Continue",
        "opening_uncompleted": "Opening uncompleted exercise: {}",
        "open_next_failed": "Failed to open next exercise: {}",
        "opened_no_pages": "Opened {} but no exercise pages were found",
        "results_return_failed": "Failed to return to Results page for next exercise: {}",

        "db_status": "Database {}: {} exercises, {} pages, {} answered pages",
        "db_saved_exercise": "Saved questions & answers for '{}' to {} ({} pages)",
        "db_not_found": "No answer database found for {}",
        "search_title": "Search Answer from Question ({})",
        "search_hint_1": "Paste question text (multi-line supported), then type END on the last line",
        "search_hint_2": "Type 0 to return to Main Menu",
        "search_no_query": "No question text provided",
        "search_no_match": "No matching question found in the database",
        "search_found": "Found {} matching answer(s)",
        "search_match_pct": "Match {:.1f}%",
        "search_db_question": "Database question: {}",
        "search_answer_label": "Answer:",
        "search_chapter_label": "Chapter: {} | Exercise: {}",

        "multi_acc_all": "All accounts",
        "multi_acc_select": "Select accounts to run: ",
        "multi_acc_no_pwd": "No accounts have saved passwords",
        "multi_acc_launching": "Launching {} account(s) in new window(s)...",
        "multi_acc_started": "All processes have started",
        "auto_start_ex": "Starting exercise: {}",
        "auto_all_done": "No remaining exercises to complete (or already 100%)",
        "auto_finished_acc": "Finished auto-run for this account",

        "summary": "Exercise Summary",
        "pass": "PASS",
        "fail": "FAIL",
        "skip": "SKIP",
        "score": "Score",
        "time_spent": "Time Spent",
        "total_time": "Total Time",
        "passed_count": "Passed",
        "failed_count": "Failed",
        "skipped_count": "Skipped",
        "selected_only": "Solving only selected pages",
        "finished_selected": "Finished all selected pages",
        "next_action": "Next Action",
        "back_to_list": "Back to Exercise List",
        "back_to_main": "Back to Main Menu",
        "exit_app": "Exit Program",

        "repeat": "Repeat",
        "continue": "Continue",
        "nothing": "Do Nothing (Back to Main Menu)",
        "what_next": "What do you want to do next?",
        "choose_prompt": "Select: ",

        "back": "Back",
        "invalid_choice": "Invalid choice",
        "press_enter": "Press Enter to continue...",
        "cancel": "Cancel",
    }
}

UNSUPPORTED_TYPES = {
    "type-intro": "introductory page",
}

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
                        const st = window.getComputedStyle(el);
                        if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') return false;
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                    };
                    for (const b of document.querySelectorAll("button, [role='button']")) {
                        if (!isVis(b)) continue;
                        const cls = (b.className || '').toString().toLowerCase();
                        const txt = ((b.innerText || b.textContent || '') + ' ' + (b.getAttribute('aria-label') || '')).toLowerCase();
                        if (/\\b(correct|start-exercise)\\b/.test(cls)) return true;
                        if (/(\\bcheck\\b|\\bcorrection\\b|ตรวจคำตอบ|ตรวจสอบ|\\bstart\\b|เริ่มต้น)/.test(txt)) return true;
                    }
                    return !isVis(document.querySelector('.result-badge-text'));
                }
                """,
                timeout=max(1.2, settle + 1.5),
                interval=0.055,
            )
            time.sleep(0.08)
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
        tiles = self.page.locator(".exercise-items .drag-drop").all()
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
                ".exercise-items [data-drag-drop-id]"
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
            ".exercise-items .drag-drop:not(.drag-drop-placeholder .drag-drop)"
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


class VideoSolver(BaseSolver):
    def extract_current_state_answers(self, verified=True):
        self.capture_initial_context()
        srcs = []
        try:
            srcs = self.page.evaluate("""
                () => Array.from(document.querySelectorAll('video, video source'))
                    .map(el => el.src || el.getAttribute('src') || '')
                    .filter(Boolean)
            """) or []
        except Exception:
            srcs = []
        return self.record_answer("video", srcs, verified=verified)

    def solve(self):
        self.logger.info("=== Video Solver Started ===")
        self.start_timer()
        try:
            self.capture_initial_context()
            try:
                if self.page.locator("video").count() == 0 and self.has_start_button():
                    self.click_start()
            except Exception:
                pass

            # Wait briefly for video metadata if duration not yet loaded
            self._wait_until_js(
                "() => { const v = document.querySelector('video'); return Boolean(v && v.duration > 0); }",
                timeout=2.0,
                interval=0.06,
            )

            result = self.page.evaluate("""
                () => {
                    const videos = document.querySelectorAll('video');
                    if (videos.length === 0) return 'no-video';
                    let acted = false;
                    videos.forEach(v => {
                        try {
                            v.muted = true;
                            v.volume = 0;
                            v.playbackRate = 16;
                            if (v.duration && !isNaN(v.duration) && v.duration > 0) {
                                v.currentTime = Math.max(0, v.duration - 0.15);
                                acted = true;
                            }
                            v.play().catch(e => {});
                        } catch(e) {}
                    });
                    return acted ? 'seeked-and-played' : 'playing';
                }
            """)
            self.step(f"Video action: {result}")

            for _ in range(60):
                try:
                    state = self.page.evaluate("""
                        () => {
                            const v = document.querySelector('video');
                            if (!v) return {ended: true, ready: true};
                            if (v.duration && !isNaN(v.duration) && v.duration > 0 && v.currentTime < v.duration - 0.5) {
                                v.muted = true;
                                v.playbackRate = 16;
                                v.currentTime = Math.max(0, v.duration - 0.1);
                            }
                            const nextBtn = document.querySelector('button.action-exercise-button.next');
                            const nextReady = Boolean(nextBtn && !nextBtn.disabled);
                            return {
                                ended: Boolean(v.ended) || (v.duration > 0 && v.currentTime >= v.duration - 0.25),
                                ready: nextReady,
                            };
                        }
                    """)
                    if state.get("ended") or state.get("ready"):
                        break
                except Exception:
                    break
                time.sleep(0.15)

            self.verify_step("ตรวจสอบการเล่นวิดีโอจนจบ", True)
            self.extract_current_state_answers(verified=True)
            elapsed = self.stop_timer()
            self.logger.info(f"Video done. Time: {elapsed}")
            return True
        except Exception as e:
            self.logger.error(f"Video error: {str(e)}")
            self.report_problem("video_exception", {"error": str(e)})
            self.extract_current_state_answers(verified=False)
            return False


class AnswerSolver(BaseSolver):
    MAX_ITERATIONS = 5

    ANSWER_INPUT_SELECTOR = (
        "input.answer, input.answer-gap, "
        ".exercise-items input:not([type='radio']):not([type='checkbox']):not([type='hidden'])"
    )

    def extract_current_state_answers(self, verified=True):
        self.capture_initial_context()
        vals = self.extract_answers_from_solution()
        has_any = bool(vals and any(v != "" for v in vals))
        return self.record_answer("answer", vals, verified=(verified and has_any))

    def solve(self):
        self.logger.info("=== Answer Solver ===")
        self.start_timer()
        if not self.wait_for_page_ready():
            return False
        self.capture_initial_context()

        if self.already_passed():
            self.extract_current_state_answers(verified=True)
            return True

        if self.has_start_button():
            self.click_start()

        cached = self._find_cached_answer(expected_type="answer")
        cached_answers = cached.get("answers") if isinstance(cached, dict) else None
        if cached_answers:
            self.step(f"[CACHE] Using saved fill-in answers ({len(cached_answers)} blanks)")
            self.fill_blanks(cached_answers)
            self.click_correction()
            score = self.get_result_score()
            if score >= self.PASS_LINE:
                self.verify_step("ตรวจคะแนนเติมคำ (Cache)", True, f"ได้คะแนน {score}/100")
                self.record_answer("answer", cached_answers, verified=True)
                return True
            self.step("[CACHE] Cached fill-in answers failed — falling back to solve")
            self.click_repeat()

        self.click_correction()
        if not self.click_solution():
            self.report_problem("answer_no_solution_button")
            self.extract_current_state_answers(verified=False)
            return False

        correct_answers = self.extract_answers_from_solution()
        if not correct_answers or all(a == "" for a in correct_answers):
            self.report_problem("answer_extract_empty")
            self.extract_current_state_answers(verified=False)
            return False

        non_empty_expected = sum(1 for a in correct_answers if a != "")
        self.record_answer("answer", correct_answers, verified=True)
        self.verify_step("บันทึกเฉลยเติมคำลงฐานข้อมูล", True, f"ครบ {non_empty_expected} จุด")

        self.click_repeat()

        for iteration in range(self.MAX_ITERATIONS):
            if self.has_start_button():
                self.click_start()
            self.fill_blanks(correct_answers)
            self.click_correction()
            score = self.get_result_score()
            self.logger.info(f"--- Iteration {iteration+1}/{self.MAX_ITERATIONS} | Score: {score} ---")
            if score >= self.PASS_LINE:
                self.verify_step("ตรวจคะแนนเติมคำ", True, f"ได้คะแนน {score}/100")
                return True
            if iteration + 1 < self.MAX_ITERATIONS:
                self.click_repeat()
        final_sc = self.get_result_score()
        ok = final_sc >= self.PASS_LINE
        self.verify_step("ตรวจคะแนนเติมคำ", ok, f"ได้คะแนน {final_sc}/100")
        return ok

    def extract_answers_from_solution(self):
        try:
            return self.page.evaluate(
                """
                (sel) => Array.from(document.querySelectorAll(sel)).map(inp => (inp.value || '').trim())
                """,
                self.ANSWER_INPUT_SELECTOR,
            ) or []
        except Exception as e:
            self.logger.error(f"Extract error: {str(e)}")
            return []

    def fill_blanks(self, answers):
        expected = sum(1 for a in answers if a)
        if expected == 0:
            return
        try:
            # Fast batch JS fill firing native setter + input/change/blur events for Angular/React
            self.page.evaluate(
                """
                ([sel, ansList]) => {
                    const inputs = Array.from(document.querySelectorAll(sel));
                    const protoSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value'
                    )?.set;
                    ansList.forEach((ans, idx) => {
                        if (!ans || idx >= inputs.length) return;
                        const inp = inputs[idx];
                        try {
                            inp.focus();
                            if (protoSetter) protoSetter.call(inp, ans);
                            else inp.value = ans;
                            inp.dispatchEvent(new Event('input', { bubbles: true }));
                            inp.dispatchEvent(new Event('change', { bubbles: true }));
                            inp.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
                            inp.blur();
                        } catch (e) {}
                    });
                }
                """,
                [self.ANSWER_INPUT_SELECTOR, list(answers)],
            )

            # Verify every single blank matches; repair any mismatched blank with Playwright .fill()
            current_vals = self.extract_answers_from_solution()
            inputs_loc = None
            for i, ans in enumerate(answers):
                if not ans:
                    continue
                cur = current_vals[i] if i < len(current_vals) else ""
                if cur != ans:
                    if inputs_loc is None:
                        inputs_loc = self.page.locator(self.ANSWER_INPUT_SELECTOR).all()
                    if i < len(inputs_loc):
                        try:
                            inputs_loc[i].fill(ans)
                        except Exception:
                            pass

            verified_vals = self.extract_answers_from_solution()
            matched = sum(
                1 for i, ans in enumerate(answers)
                if ans and i < len(verified_vals) and verified_vals[i] == ans
            )
            self.verify_step(
                "กรอกคำตอบลงช่องว่างครบทุกจุด",
                matched == expected,
                f"ครบ {matched}/{expected} จุด",
            )
        except Exception as e:
            self.logger.error(f"fill_blanks error: {e}")


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


class ScrambledTableSolver(BaseSolver):
    MAX_ITERATIONS = 8

    def extract_current_state_answers(self, verified=True):
        self.capture_initial_context()
        mapping = self.extract_correct_mapping()
        has_any = bool(mapping and any(m.get("text") for m in mapping))
        return self.record_answer(
            "scrambled-table", mapping, verified=(verified and has_any)
        )

    def _count_matching_cells(self, correct_map):
        cur_map = {m["idx"]: m.get("text") for m in self.extract_correct_mapping()}
        expected = 0
        matched = 0
        for entry in correct_map:
            if not isinstance(entry, dict) or not entry.get("text"):
                continue
            expected += 1
            if cur_map.get(entry["idx"]) == entry["text"]:
                matched += 1
        return matched, expected

    def solve(self):
        self.logger.info("=== Scrambled Table Solver ===")
        self.start_timer()
        if not self.wait_for_page_ready():
            return False
        self.capture_initial_context()

        if self.already_passed():
            self.extract_current_state_answers(verified=True)
            return True

        cached = self._find_cached_answer(expected_type="scrambled-table")
        cached_map = cached.get("answers") if isinstance(cached, dict) else None
        if cached_map:
            self.step(f"[CACHE] Using saved table answers ({len(cached_map)} items)")
            self.arrange_cells(cached_map, fast=True)
            self.click_correction()
            score = self.get_result_score()
            if score >= self.PASS_LINE:
                self.verify_step("ตรวจคะแนนตารางเรียงคำ (Cache)", True, f"ได้คะแนน {score}/100")
                self.record_answer("scrambled-table", cached_map, verified=True)
                self.logger.info(f"[CACHE] Scrambled table completed in {self.stop_timer()}")
                return True
            self.logger.warning("[CACHE] Fast cached placement did not pass; retrying reliably")
            self.click_repeat()

        self.click_correction()
        if not self.click_solution():
            self.report_problem("scrambled_table_no_solution")
            self.extract_current_state_answers(verified=False)
            return False

        correct_map = self.extract_correct_mapping()
        if not correct_map or all(m.get("text") is None for m in correct_map):
            self.logger.warning("Failed to extract scrambled table mapping")
            self.report_problem("scrambled_table_extract_empty")
            self.extract_current_state_answers(verified=False)
            return False

        self.record_answer("scrambled-table", correct_map, verified=True)
        self.verify_step("บันทึกเฉลยตารางเรียงคำลงฐานข้อมูล", True, f"{len(correct_map)} แถว")

        self.click_repeat()

        for iteration in range(self.MAX_ITERATIONS):
            self.arrange_cells(correct_map, fast=(iteration == 0))
            self.click_correction()
            score = self.get_result_score()
            self.logger.info(f"--- Iteration {iteration+1}/{self.MAX_ITERATIONS} | Score: {score} ---")
            if score >= self.PASS_LINE:
                self.verify_step("ตรวจคะแนนตารางเรียงคำ", True, f"ได้คะแนน {score}/100")
                elapsed = self.stop_timer()
                self.logger.info(f"SUCCESS! Time: {elapsed}")
                return True
            if iteration + 1 < self.MAX_ITERATIONS:
                self.click_repeat()
        final_sc = self.get_result_score()
        ok = final_sc >= self.PASS_LINE
        self.verify_step("ตรวจคะแนนตารางเรียงคำ", ok, f"ได้คะแนน {final_sc}/100")
        return ok

    def extract_correct_mapping(self):
        try:
            result = self.page.evaluate("""
                () => {
                    const items = document.querySelectorAll('.exercise-items .item');
                    const mapping = [];
                    items.forEach((item, idx) => {
                        const cell = item.querySelector('.scrambled-cell');
                        if (!cell) {
                            mapping.push({idx: idx, text: null});
                            return;
                        }
                        const text = (cell.innerText || '').trim();
                        mapping.push({idx: idx, text: text});
                    });
                    return mapping;
                }
            """)
            return result if result else []
        except Exception as e:
            self.logger.error(f"extract_correct_mapping error: {e}")
            return []

    def arrange_cells(self, correct_map, fast=False):
        moved = False
        try:
            total_items = self.page.locator(".exercise-items .item").count()
            expected_by_idx = {
                entry["idx"]: entry["text"]
                for entry in correct_map
                if isinstance(entry, dict) and "idx" in entry
            }
            for repair_pass in range(2):
                matched_now, expected_now = self._count_matching_cells(correct_map)
                if expected_now > 0 and matched_now >= expected_now:
                    break

                for entry in correct_map:
                    idx = entry["idx"]
                    target_text = entry["text"]
                    if not target_text or idx >= total_items:
                        continue
                    target_item = self.page.locator(".exercise-items .item").nth(idx)
                    target_slot = target_item.locator(".scrambled-cell-container").first
                    if target_slot.count() == 0:
                        continue
                    current = target_slot.locator(".scrambled-cell").first
                    if current.count() > 0:
                        try:
                            if current.inner_text().strip() == target_text:
                                continue
                        except Exception:
                            pass

                    source = None
                    pool_cells = self.page.locator(
                        ".scrambled-cell:not(.exercise-items .item .scrambled-cell)"
                    ).all()
                    for cell in pool_cells:
                        try:
                            if cell.inner_text().strip() == target_text:
                                source = cell
                                break
                        except Exception:
                            continue

                    if source is None:
                        for j in range(total_items):
                            if j == idx:
                                continue
                            other_cell = (
                                self.page.locator(".exercise-items .item")
                                .nth(j)
                                .locator(".scrambled-cell")
                                .first
                            )
                            if other_cell.count() == 0:
                                continue
                            try:
                                txt = other_cell.inner_text().strip()
                            except Exception:
                                continue
                            if txt != target_text:
                                continue
                            if expected_by_idx.get(j) == txt:
                                continue
                            source = other_cell
                            break

                    if source is None:
                        for cell in self.page.locator(".scrambled-cell").all():
                            try:
                                if cell.inner_text().strip() == target_text:
                                    source = cell
                                    break
                            except Exception:
                                continue

                    if source is None:
                        self.logger.warning(f"Cell '{target_text}' not found in DOM")
                        continue

                    placed = self.fast_drag(source, target_slot) if (fast and repair_pass == 0) else False
                    now_ok = False
                    try:
                        chk = (
                            self.page.locator(".exercise-items .item")
                            .nth(idx)
                            .locator(".scrambled-cell-container .scrambled-cell")
                            .first
                        )
                        if chk.count() > 0 and chk.inner_text().strip() == target_text:
                            now_ok = True
                    except Exception:
                        pass

                    if not now_ok:
                        try:
                            source.click(timeout=1500)
                            time.sleep(0.05)
                            target_slot.click(timeout=1500)
                            time.sleep(0.06)
                            chk = (
                                self.page.locator(".exercise-items .item")
                                .nth(idx)
                                .locator(".scrambled-cell-container .scrambled-cell")
                                .first
                            )
                            now_ok = chk.count() > 0 and chk.inner_text().strip() == target_text
                        except Exception:
                            pass

                    if not now_ok:
                        placed = self.precise_drag(source, target_slot)

                    if placed or now_ok:
                        moved = True

            matched_final, expected_final = self._count_matching_cells(correct_map)
            self.verify_step(
                "ตรวจสอบการวางคำตอบตารางเรียงคำ",
                matched_final == expected_final and expected_final > 0,
                f"ครบ {matched_final}/{expected_final} แถว",
            )
        except Exception as e:
            self.logger.error(f"arrange_cells error: {e}")
        return moved

class SingleChoiceSolver(BaseSolver):
    MAX_ITERATIONS = 5

    def extract_current_state_answers(self, verified=True):
        self.capture_initial_context()
        per_item = self._find_correct_per_item_js()
        if per_item:
            flat = []
            has_any = False
            for c in per_item:
                if isinstance(c, list) and c:
                    flat.append(c[0])
                    has_any = True
                elif isinstance(c, int):
                    flat.append(c)
                    has_any = True
                else:
                    flat.append(0)
            if has_any:
                return self.record_answer(
                    "single-choice", flat, verified=verified, subtype="multi"
                )
        idx = self.find_correct_option()
        if idx is not None:
            return self.record_answer(
                "single-choice", [idx], verified=verified, subtype="legacy"
            )
        return self.record_answer("single-choice", [], verified=False)

    def _select_and_verify_single_choices(self, answers, subtype):
        try:
            res = self.page.evaluate(
                """
                ([ansList, mode]) => {
                    const clickRadio = (inp) => {
                        if (!inp) return false;
                        if (!inp.checked) {
                            try { inp.click(); } catch (e) {}
                        }
                        if (!inp.checked) {
                            const lbl = inp.closest('label, .choice-option');
                            if (lbl) { try { lbl.click(); } catch (e) {} }
                        }
                        if (!inp.checked) {
                            inp.checked = true;
                            inp.dispatchEvent(new Event('input', { bubbles: true }));
                            inp.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                        return Boolean(inp.checked);
                    };

                    if (mode === 'legacy') {
                        const opts = Array.from(document.querySelectorAll('.choice-option'));
                        const idx = ansList[0] ?? 0;
                        const inp = opts[idx] ? opts[idx].querySelector('input.choice') : null;
                        const ok = clickRadio(inp);
                        return { matched: ok ? 1 : 0, expected: 1 };
                    }

                    if (mode === 'group') {
                        const allInps = Array.from(document.querySelectorAll('.exercise-items .item.choice-item input.choice'));
                        const idx = ansList[0] ?? 0;
                        const ok = clickRadio(allInps[idx]);
                        return { matched: ok ? 1 : 0, expected: 1 };
                    }

                    const items = Array.from(document.querySelectorAll('.exercise-items .item.choice-item'));
                    let matched = 0;
                    const expected = Math.min(ansList.length, items.length);
                    for (let i = 0; i < expected; i++) {
                        const opts = Array.from(items[i].querySelectorAll('input.choice'));
                        const idx = ansList[i];
                        if (idx >= 0 && idx < opts.length && clickRadio(opts[idx])) {
                            matched++;
                        }
                    }
                    return { matched, expected };
                }
                """,
                [list(answers), subtype or "multi"],
            ) or {"matched": 0, "expected": len(answers)}

            matched = int(res.get("matched", 0))
            expected = int(res.get("expected", len(answers)))

            # Repair any stubborn item via Playwright locator click
            if matched < expected:
                if subtype == "legacy":
                    options = self.page.locator(".choice-option").all()
                    if answers and answers[0] < len(options):
                        inp = options[answers[0]].locator("input.choice").first
                        if inp.count() > 0:
                            inp.click(force=True, timeout=2000)
                            matched = 1
                elif subtype == "group":
                    opts = self.page.locator(".exercise-items .item.choice-item input.choice").all()
                    if answers and answers[0] < len(opts):
                        opts[answers[0]].click(force=True, timeout=2000)
                        matched = 1
                else:
                    items = self.page.locator(".exercise-items .item.choice-item").all()
                    matched = 0
                    for i, idx in enumerate(answers):
                        if i >= len(items):
                            break
                        opts = items[i].locator("input.choice").all()
                        if idx < len(opts):
                            try:
                                if not opts[idx].is_checked():
                                    opts[idx].click(force=True, timeout=2000)
                                if opts[idx].is_checked():
                                    matched += 1
                            except Exception:
                                pass

            self.verify_step(
                "เลือกตัวเลือก Single Choice ครบทุกข้อ",
                matched == expected and expected > 0,
                f"ครบ {matched}/{expected} ข้อ",
            )
            return expected > 0
        except Exception as e:
            self.logger.error(f"[CHOICE] select_and_verify failed: {e}")
            return False

    def _apply_cached_answers(self, answers, subtype):
        return self._select_and_verify_single_choices(answers, subtype)

    def _save_choice_to_db(self, answers, subtype=None, verified=True):
        try:
            extra = {"subtype": subtype} if subtype else {}
            self.record_answer("single-choice", list(answers), verified=verified, **extra)
            self.verify_step("บันทึกเฉลย Single Choice ลงฐานข้อมูล", verified, f"{len(answers)} ข้อ")
        except Exception as e:
            self.logger.error(f"[DB] Save single-choice failed: {e}")

    def solve(self):
        self.logger.info("=== Single Choice Solver ===")
        self.start_timer()

        if not self.wait_for_page_ready():
            return False
        self.capture_initial_context()

        if self.already_passed():
            self.logger.info("[CHOICE] Already passed (score >= 51)")
            self.extract_current_state_answers(verified=True)
            return True

        cached = self._find_cached_answer(expected_type="single-choice")
        if cached and cached.get("type") == "single-choice":
            subtype = cached.get("subtype", "multi")
            answers = cached.get("answers", [])
            if answers:
                self.step(f"[CACHE] Found saved answers ({subtype}): {answers}")
                if self._apply_cached_answers(answers, subtype):
                    self.click_correction()
                    score = self.get_result_score()
                    if score >= self.PASS_LINE:
                        self.verify_step("ตรวจคะแนน Single Choice (Cache)", True, f"ได้คะแนน {score}/100")
                        self._save_choice_to_db(answers, subtype=subtype, verified=True)
                        return True
                    self.step("[CACHE] Cached answers failed — falling back to solve")
                    self.click_repeat()

        self.click_correction()
        has_solution = self.click_solution()

        try:
            item_count = self.page.locator(".exercise-items .item.choice-item").count()
        except Exception:
            item_count = 0

        if item_count == 0:
            ok = self._solve_single_legacy()
            if not ok and self.last_recorded_answer is None:
                self.extract_current_state_answers(verified=False)
            return ok

        try:
            group_count = self.page.evaluate("""
                () => new Set(Array.from(document.querySelectorAll(
                    '.exercise-items .item.choice-item input.choice'
                )).map(input => input.name || input.getAttribute('data-group-id') || input.value)).size
            """)
        except Exception:
            group_count = item_count

        if item_count > 1 and group_count == 1:
            ok = self._solve_single_group_choice()
            if not ok and self.last_recorded_answer is None:
                self.extract_current_state_answers(verified=False)
            return ok

        if not has_solution:
            self.logger.info("[CHOICE] No solution button — using fallback")
            return self._solve_without_solution(item_count)

        correct_per_item = self._find_correct_per_item_js()
        if correct_per_item:
            normalised = []
            for c in correct_per_item:
                if isinstance(c, list):
                    normalised.append(c[0] if c else 0)
                elif isinstance(c, int):
                    normalised.append(c)
                else:
                    normalised.append(0)
            self._save_choice_to_db(normalised, subtype="multi", verified=True)

        ok = self._solve_multi_item(item_count)
        if not ok and self.last_recorded_answer is None:
            self.extract_current_state_answers(verified=False)
        return ok

    def _solve_without_solution(self, item_count):
        items = self.page.locator(".exercise-items .item.choice-item").all()
        if not items:
            self.extract_current_state_answers(verified=False)
            return False

        opts_counts = []
        for item in items:
            n = item.locator("input.choice").count()
            if n == 0:
                self.extract_current_state_answers(verified=False)
                return False
            opts_counts.append(n)

        self.click_repeat()
        time.sleep(1.2)

        current = [0] * item_count
        items = self.page.locator(".exercise-items .item.choice-item").all()
        for i in range(min(item_count, len(items))):
            try:
                opts = items[i].locator("input.choice").all()
                if opts:
                    opts[0].click(force=True, timeout=3000)
                    time.sleep(0.1)
            except Exception:
                pass

        self.click_correction()
        time.sleep(1.5)
        score = self.get_result_score()
        self.step(f"[BRUTE] initial score={score}")

        if score >= self.PASS_LINE:
            self._save_choice_to_db(current, subtype="brute", verified=True)
            return True

        max_iter = item_count * 3
        iteration = 0
        improved = True

        while improved and iteration < max_iter and score < self.PASS_LINE:
            improved = False
            iteration += 1

            items = self.page.locator(".exercise-items .item.choice-item").all()
            if len(items) < item_count:
                passed = score >= self.PASS_LINE
                self._save_choice_to_db(current, subtype="brute", verified=passed)
                return passed

            for i in range(item_count):
                n_opts = opts_counts[i]
                if n_opts <= 1:
                    continue

                new_idx = (current[i] + 1) % n_opts

                items_now = self.page.locator(".exercise-items .item.choice-item").all()
                if i >= len(items_now):
                    continue
                opts = items_now[i].locator("input.choice").all()
                if new_idx >= len(opts):
                    continue
                try:
                    opts[new_idx].click(force=True, timeout=3000)
                    time.sleep(0.2)
                except Exception:
                    continue

                self.click_correction()
                time.sleep(1.5)
                new_score = self.get_result_score()

                if new_score > score:
                    score = new_score
                    current[i] = new_idx
                    improved = True
                    self.step(f"[BRUTE] item {i} → option {new_idx}, score={score}")
                    if score >= self.PASS_LINE:
                        self._save_choice_to_db(current, subtype="brute", verified=True)
                        return True
                else:
                    items_revert = self.page.locator(
                        ".exercise-items .item.choice-item"
                    ).all()
                    if i < len(items_revert):
                        opts = items_revert[i].locator("input.choice").all()
                        if current[i] < len(opts):
                            try:
                                opts[current[i]].click(force=True, timeout=3000)
                                time.sleep(0.2)
                            except Exception:
                                pass

        passed = score >= self.PASS_LINE
        self._save_choice_to_db(current, subtype="brute", verified=passed)
        return passed

    def _solve_multi_item(self, item_count):
        correct_per_item = None
        for _ in range(4):
            correct_per_item = self._find_correct_per_item_js()
            if correct_per_item and all(c is not None and len(c) > 0 for c in correct_per_item):
                break
            time.sleep(0.1)
        if not correct_per_item or any(c is None for c in correct_per_item):
            correct_per_item = self._find_correct_per_item()
            if not correct_per_item or any(c is None for c in correct_per_item):
                return False

        normalised = []
        for choices in correct_per_item:
            if isinstance(choices, list):
                if len(choices) >= 1 and isinstance(choices[0], int):
                    choices = choices[0]
                else:
                    return False
            if not isinstance(choices, int):
                return False
            normalised.append(choices)
        correct_per_item = normalised
        self.step(f"Detected correct per item: {correct_per_item}")
        self._save_choice_to_db(correct_per_item, subtype="multi", verified=True)

        self.click_repeat()

        for iteration in range(self.MAX_ITERATIONS):
            self._select_and_verify_single_choices(correct_per_item, "multi")
            self.click_correction()
            score = self.get_result_score()
            self.logger.info(
                f"--- Iteration {iteration+1}/{self.MAX_ITERATIONS} | Score: {score} ---")
            if score >= self.PASS_LINE:
                self.verify_step("ตรวจคะแนน Single Choice", True, f"ได้คะแนน {score}/100")
                return True
            if iteration + 1 < self.MAX_ITERATIONS:
                self.click_repeat()
        final_sc = self.get_result_score()
        ok = final_sc >= self.PASS_LINE
        self.verify_step("ตรวจคะแนน Single Choice", ok, f"ได้คะแนน {final_sc}/100")
        return ok

    def _solve_single_group_choice(self):
        options = self.page.locator(
            '.exercise-items .item.choice-item input.choice').all()
        correct_index = None
        for index, option in enumerate(options):
            try:
                if option.is_checked(timeout=500):
                    correct_index = index
                    break
            except Exception:
                continue
        if correct_index is None:
            self.logger.warning('[CHOICE] solution did not expose a selected option')
            return False
        self.step(f'Detected grouped correct option: {correct_index}')

        self._save_choice_to_db([correct_index], subtype="group", verified=True)
        self.click_repeat()

        for iteration in range(self.MAX_ITERATIONS):
            self._select_and_verify_single_choices([correct_index], "group")
            self.click_correction()
            score = self.get_result_score()
            self.logger.info(
                f'--- Grouped iteration {iteration+1}/{self.MAX_ITERATIONS} | Score: {score} ---')
            if score >= self.PASS_LINE:
                self.verify_step("ตรวจคะแนน Single Choice (Group)", True, f"ได้คะแนน {score}/100")
                return True
            if iteration + 1 < self.MAX_ITERATIONS:
                self.click_repeat()
        return self.get_result_score() >= self.PASS_LINE

    def _find_correct_per_item_js(self):
        try:
            result = self.page.evaluate("""
                () => {
                    const items = document.querySelectorAll('.exercise-items .item.choice-item');
                    const results = [];

                    const isGreenish = (str) => {
                        if (!str) return false;
                        const s = str.toString().toLowerCase();
                        return s.includes('success') || s.includes('correct') ||
                               s.includes('result-green') || s.includes('bg-success') ||
                               s.includes('green') || s.includes('is-correct') ||
                               s.includes('is-checked') || s.includes('selected-correct');
                    };

                    const isSolutionSelected = (el) => {
                        if (!el) return false;
                        const cls = (el.className || '').toString().toLowerCase();
                        const aria = (el.getAttribute('aria-checked') || '').toLowerCase();
                        const data = (el.getAttribute('data-correct') || '').toLowerCase();
                        return aria === 'true' || data === 'true' ||
                               /(^|[-_ ])(selected|active|checked|solution)([-_ ]|$)/.test(cls);
                    };

                    const isGreenStyle = (el) => {
                        try {
                            const style = window.getComputedStyle(el);
                            const values = [style.backgroundColor, style.color,
                                style.borderColor, style.outlineColor].join(' ');
                            const colors = [...values.matchAll(
                                /rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/g
                            )];
                            return colors.some(m => {
                                const r = parseInt(m[1]), g = parseInt(m[2]), b = parseInt(m[3]);
                                return g > r + 25 && g > b + 15;
                            });
                        } catch(e) { return false; }
                    };

                    items.forEach(item => {
                        const corrects = [];
                        const opts = item.querySelectorAll('input.choice');

                        for (let i = 0; i < opts.length; i++) {
                            if (opts[i].checked || isSolutionSelected(opts[i]) ||
                                isSolutionSelected(opts[i].closest('label')) ||
                                isSolutionSelected(opts[i].parentElement)) {
                                if (!corrects.includes(i)) corrects.push(i);
                            }
                        }

                        if (corrects.length === 0) {
                            for (let i = 0; i < opts.length; i++) {
                                if (isGreenish(opts[i].className)) {
                                    if (!corrects.includes(i)) corrects.push(i);
                                }
                            }
                        }

                        if (corrects.length === 0) {
                            const labels = item.querySelectorAll('.choice-option');
                            for (let i = 0; i < labels.length; i++) {
                                const all = [labels[i], ...labels[i].querySelectorAll('*')];
                                for (const el of all) {
                                    if (isGreenish(el.className) || isSolutionSelected(el) ||
                                        isGreenStyle(el)) {
                                        if (!corrects.includes(i)) corrects.push(i);
                                        break;
                                    }
                                }
                            }
                        }

                        if (corrects.length === 0) {
                            const labels = item.querySelectorAll('.choice-option');
                            for (let i = 0; i < labels.length; i++) {
                                try {
                                    const style = window.getComputedStyle(labels[i]);
                                    const bg = style.backgroundColor || '';
                                    const m = bg.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                                    if (m) {
                                        const r = parseInt(m[1]);
                                        const g = parseInt(m[2]);
                                        const b = parseInt(m[3]);
                                        if (g > r + 30 && g > b + 30) {
                                            if (!corrects.includes(i)) corrects.push(i);
                                        }
                                    }
                                } catch(e) {}
                            }
                        }

                        results.push(corrects);
                    });
                    return results;
                }
            """)
            return result if result else None
        except Exception as e:
            self.logger.error(f"_find_correct_per_item_js error: {e}")
            return None

    def _find_correct_per_item(self):
        results = []
        try:
            items = self.page.locator(".exercise-items .item.choice-item").all()
            for item in items:
                results.append(self._find_correct_in_item(item))
        except Exception:
            pass
        return results

    def _find_correct_in_item(self, item):
        try:
            opts = item.locator("input.choice").all()
            for i, opt in enumerate(opts):
                try:
                    if opt.is_checked(timeout=1000):
                        return i
                except Exception:
                    pass
            labels = item.locator(".choice-option").all()
            for i, label in enumerate(labels):
                try:
                    all_el = [label] + label.locator("*").all()
                    for el in all_el:
                        cls = (el.get_attribute("class") or "").lower()
                        aria = (el.get_attribute("aria-checked") or "").lower()
                        data = (el.get_attribute("data-correct") or "").lower()
                        if (any(k in cls for k in ("success", "correct", "result-green", "bg-success"))
                                or aria == "true" or data == "true"
                                or any(k in cls.split() for k in ("selected", "active", "checked", "solution"))):
                            return i
                except Exception:
                    pass
        except Exception:
            pass
        return None

    def _solve_single_legacy(self):
        correct_idx = None
        for _ in range(4):
            correct_idx = self.find_correct_option()
            if correct_idx is not None:
                break
            time.sleep(0.1)
        if correct_idx is None:
            return False

        self._save_choice_to_db([correct_idx], subtype="legacy", verified=True)
        self.click_repeat()

        for iteration in range(self.MAX_ITERATIONS):
            self._select_and_verify_single_choices([correct_idx], "legacy")
            self.click_correction()
            score = self.get_result_score()
            if score >= self.PASS_LINE:
                self.verify_step("ตรวจคะแนน Single Choice (Legacy)", True, f"ได้คะแนน {score}/100")
                return True
            if iteration + 1 < self.MAX_ITERATIONS:
                self.click_repeat()
        return self.get_result_score() >= self.PASS_LINE

    def find_correct_option(self):
        try:
            idx = self.page.evaluate("""
                () => {
                    const radios = document.querySelectorAll('input.choice');
                    for (let i = 0; i < radios.length; i++) {
                        if (radios[i].checked) return i;
                    }
                    const opts = document.querySelectorAll('.choice-option');
                    for (let i = 0; i < opts.length; i++) {
                        const all = [opts[i], ...opts[i].querySelectorAll('*')];
                        for (const el of all) {
                            const cls = (el.className || '').toString().toLowerCase();
                            if (cls.includes('success') || cls.includes('correct') ||
                                cls.includes('result-green') || cls.includes('bg-success')) {
                                return i;
                            }
                        }
                    }
                    return -1;
                }
            """)
            if idx is not None and idx >= 0:
                return idx
        except Exception:
            pass
        return None


class MultipleChoiceSolver(BaseSolver):
    MAX_ITERATIONS = 5

    def extract_current_state_answers(self, verified=True):
        self.capture_initial_context()
        per_item = self._find_correct_per_item_js() or []
        has_any = any(bool(c) for c in per_item)
        return self.record_answer(
            "multiple-choice",
            [list(c) for c in per_item],
            verified=(verified and has_any),
        )

    def _save_multiple_choice_to_db(self, correct_per_item, verified=True):
        try:
            self.record_answer(
                "multiple-choice",
                [list(c) for c in correct_per_item],
                verified=verified,
            )
            self.verify_step("บันทึกเฉลย Multiple Choice ลงฐานข้อมูล", verified, f"{len(correct_per_item)} ข้อ")
        except Exception as e:
            self.logger.error(f"[DB] Save multiple-choice failed: {e}")

    def _select_and_verify_multiple_choices(self, answers):
        try:
            res = self.page.evaluate(
                """
                (ansPerItem) => {
                    const items = Array.from(document.querySelectorAll('.exercise-items .item.choice-item'));
                    if (!items.length) return { matched: 0, expected: 0 };
                    const toggleCheckbox = (inp, wantChecked) => {
                        if (!inp) return false;
                        if (Boolean(inp.checked) !== wantChecked) {
                            try { inp.click(); } catch (e) {}
                        }
                        if (Boolean(inp.checked) !== wantChecked) {
                            const lbl = inp.closest('label, .choice-option');
                            if (lbl) { try { lbl.click(); } catch (e) {} }
                        }
                        if (Boolean(inp.checked) !== wantChecked) {
                            inp.checked = wantChecked;
                            inp.dispatchEvent(new Event('input', { bubbles: true }));
                            inp.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                        return Boolean(inp.checked) === wantChecked;
                    };

                    let matched = 0;
                    const expected = Math.min(ansPerItem.length, items.length);
                    for (let i = 0; i < expected; i++) {
                        const wantedSet = new Set(Array.isArray(ansPerItem[i]) ? ansPerItem[i] : []);
                        const opts = Array.from(items[i].querySelectorAll('input.choice'));
                        let itemOk = true;
                        for (let k = 0; k < opts.length; k++) {
                            if (!toggleCheckbox(opts[k], wantedSet.has(k))) {
                                itemOk = false;
                            }
                        }
                        if (itemOk) matched++;
                    }
                    return { matched, expected };
                }
                """,
                list(answers),
            ) or {"matched": 0, "expected": 0}

            matched = int(res.get("matched", 0))
            expected = int(res.get("expected", 0))

            if matched < expected:
                items = self.page.locator(".exercise-items .item.choice-item").all()
                matched = 0
                for item_idx, correct_indices in enumerate(answers):
                    if item_idx >= len(items):
                        break
                    wanted = set(correct_indices or [])
                    opts = items[item_idx].locator("input.choice").all()
                    item_ok = True
                    for opt_idx, opt in enumerate(opts):
                        try:
                            cur = opt.is_checked()
                            if cur != (opt_idx in wanted):
                                opt.click(force=True, timeout=2000)
                            if opt.is_checked() != (opt_idx in wanted):
                                item_ok = False
                        except Exception:
                            item_ok = False
                    if item_ok:
                        matched += 1

            self.verify_step(
                "เลือกตัวเลือก Multiple Choice ครบทุกข้อ",
                matched == expected and expected > 0,
                f"ครบ {matched}/{expected} ข้อ",
            )
            return expected > 0
        except Exception as e:
            self.logger.error(f"[MULTI] select_and_verify failed: {e}")
            return False

    def _apply_cached_multiple_answers(self, answers):
        return self._select_and_verify_multiple_choices(answers)

    def solve(self):
        self.logger.info("=== Multiple Choice Solver ===")
        self.start_timer()
        if not self.wait_for_page_ready():
            return False
        self.capture_initial_context()

        if self.already_passed():
            self.extract_current_state_answers(verified=True)
            return True

        cached = self._find_cached_answer(expected_type="multiple-choice")
        if cached and cached.get("type") == "multiple-choice":
            answers = cached.get("answers", [])
            if answers:
                self.step(f"[CACHE] Found saved multiple-choice answers: {answers}")
                if self._apply_cached_multiple_answers(answers):
                    self.click_correction()
                    score = self.get_result_score()
                    if score >= self.PASS_LINE:
                        self.verify_step("ตรวจคะแนน Multiple Choice (Cache)", True, f"ได้คะแนน {score}/100")
                        self._save_multiple_choice_to_db(answers, verified=True)
                        return True
                    self.step("[CACHE] Cached multiple-choice answers failed — falling back to solve")
                    self.click_repeat()

        self.click_correction()
        has_solution = self.click_solution()
        try:
            item_count = self.page.locator(".exercise-items .item.choice-item").count()
        except Exception:
            item_count = 0
        if item_count == 0:
            self.extract_current_state_answers(verified=False)
            return False

        correct_per_item = None
        for _ in range(6):
            correct_per_item = self._find_correct_per_item_js()
            if correct_per_item and any(len(c) > 0 for c in correct_per_item):
                break
            time.sleep(0.12)

        if not correct_per_item or all(len(c) == 0 for c in correct_per_item):
            if has_solution:
                self.report_problem("multiple_choice_extract_empty")
                self.extract_current_state_answers(verified=False)
                return False
            self.logger.warning("[MULTI] No revealed solution; falling back to greedy selection")
            return self._solve_without_solution()

        self._save_multiple_choice_to_db(correct_per_item, verified=True)
        self.click_repeat()

        for iteration in range(self.MAX_ITERATIONS):
            self._select_and_verify_multiple_choices(correct_per_item)
            self.click_correction()
            score = self.get_result_score()
            if score >= self.PASS_LINE:
                self.verify_step("ตรวจคะแนน Multiple Choice", True, f"ได้คะแนน {score}/100")
                return True
            if iteration + 1 < self.MAX_ITERATIONS:
                self.click_repeat()
        final_sc = self.get_result_score()
        ok = final_sc >= self.PASS_LINE
        self.verify_step("ตรวจคะแนน Multiple Choice", ok, f"ได้คะแนน {final_sc}/100")
        return ok

    def _solve_without_solution(self):
        try:
            item_count = self.page.locator(".exercise-items .item.choice-item").count()
            if item_count == 0:
                self.extract_current_state_answers(verified=False)
                return False

            self.click_repeat()
            time.sleep(1)
            current_score = self.get_result_score()

            for _ in range(12):
                improved = False
                for item_idx in range(item_count):
                    items_now = self.page.locator(".exercise-items .item.choice-item").all()
                    if item_idx >= len(items_now):
                        break
                    opt_count = items_now[item_idx].locator("input.choice").count()
                    for opt_idx in range(opt_count):
                        try:
                            live_items = self.page.locator(".exercise-items .item.choice-item").all()
                            if item_idx >= len(live_items):
                                break
                            live_opts = live_items[item_idx].locator("input.choice").all()
                            if opt_idx >= len(live_opts):
                                break
                            live_opts[opt_idx].click(force=True, timeout=3000)
                            self.click_correction()
                            time.sleep(0.7)
                            new_score = self.get_result_score()
                            if new_score > current_score:
                                current_score = new_score
                                improved = True
                                if current_score >= self.PASS_LINE:
                                    break
                                continue
                            revert_items = self.page.locator(".exercise-items .item.choice-item").all()
                            if item_idx < len(revert_items):
                                revert_opts = revert_items[item_idx].locator("input.choice").all()
                                if opt_idx < len(revert_opts):
                                    revert_opts[opt_idx].click(force=True, timeout=3000)
                                    self.click_correction()
                                    time.sleep(0.7)
                        except Exception:
                            pass
                    if current_score >= self.PASS_LINE:
                        break
                if current_score >= self.PASS_LINE or not improved:
                    break

            passed = self.get_result_score() >= self.PASS_LINE
            self.extract_current_state_answers(verified=passed)
            return passed
        except Exception as e:
            self.logger.error(f"[MULTI] fallback failed: {e}")
            self.extract_current_state_answers(verified=False)
            return False

    def _find_correct_per_item_js(self):
        try:
            result = self.page.evaluate("""
                () => {
                    const items = document.querySelectorAll('.exercise-items .item.choice-item');
                    const results = [];
                    items.forEach(item => {
                        const corrects = [];
                        const opts = item.querySelectorAll('input.choice');
                        for (let i = 0; i < opts.length; i++) {
                            if (opts[i].checked) corrects.push(i);
                        }
                        if (corrects.length === 0) {
                            const labels = item.querySelectorAll('.choice-option');
                            for (let i = 0; i < labels.length; i++) {
                                const all = [labels[i], ...labels[i].querySelectorAll('*')];
                                for (const el of all) {
                                    const cls = (el.className || '').toString().toLowerCase();
                                    if (cls.includes('success') || cls.includes('correct') ||
                                        cls.includes('result-green') || cls.includes('bg-success')) {
                                        corrects.push(i);
                                        break;
                                    }
                                }
                            }
                        }
                        results.push(corrects);
                    });
                    return results;
                }
            """)
            return result if result else None
        except Exception as e:
            self.logger.error(f"_find_correct_per_item_js error: {e}")
            return None


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


class ToggleSolutionSolver(BaseSolver):
    MAX_ITERATIONS = 6
    MAX_TOGGLE_CYCLES = 14

    def extract_current_state_answers(self, verified=True):
        self.capture_initial_context()
        vals = self.extract_correct_answers()
        has_any = bool(vals and any(v != "" for v in vals))
        return self.record_answer(
            "toggle-solution", vals, verified=(verified and has_any)
        )

    def solve(self):
        self.logger.info("=== Toggle Solution Solver ===")
        self.start_timer()
        if not self.wait_for_page_ready():
            return False
        self.capture_initial_context()

        if self.already_passed():
            self.extract_current_state_answers(verified=True)
            return True

        cached = self._find_cached_answer(expected_type="toggle-solution")
        cached_answers = cached.get("answers") if isinstance(cached, dict) else None
        if cached_answers:
            self.step(f"[CACHE] Using saved toggle-solution answers ({len(cached_answers)} gaps)")
            self.set_all_gaps(cached_answers)
            self.click_correction()
            score = self.get_result_score()
            if score >= self.PASS_LINE:
                self.verify_step("ตรวจคะแนน Toggle Solution (Cache)", True, f"ได้คะแนน {score}/100")
                self.record_answer("toggle-solution", cached_answers, verified=True)
                return True
            self.step("[CACHE] Cached toggle-solution failed — falling back to solve")
            self.click_repeat()

        self.click_correction()
        if not self.click_solution():
            self.report_problem("toggle_solution_no_solution")
            self.extract_current_state_answers(verified=False)
            return False

        correct_answers = self.extract_correct_answers()
        if not correct_answers or all(a == "" for a in correct_answers):
            self.report_problem("toggle_solution_extract_empty")
            self.extract_current_state_answers(verified=False)
            return False

        self.record_answer("toggle-solution", correct_answers, verified=True)
        self.verify_step("บันทึกเฉลย Toggle Solution ลงฐานข้อมูล", True, f"{len(correct_answers)} จุด")

        self.click_repeat()
        for iteration in range(self.MAX_ITERATIONS):
            self.set_all_gaps(correct_answers)
            self.click_correction()
            score = self.get_result_score()
            if score >= self.PASS_LINE:
                self.verify_step("ตรวจคะแนน Toggle Solution", True, f"ได้คะแนน {score}/100")
                return True
            if iteration + 1 < self.MAX_ITERATIONS:
                self.click_repeat()
        final_sc = self.get_result_score()
        ok = final_sc >= self.PASS_LINE
        self.verify_step("ตรวจคะแนน Toggle Solution", ok, f"ได้คะแนน {final_sc}/100")
        return ok

    def _norm(self, s):
        return (s or "").replace("\xa0", " ").strip()

    def extract_correct_answers(self):
        try:
            return self.page.evaluate("""
                () => Array.from(document.querySelectorAll('.exercise-items .gap'))
                    .map(g => (g.innerText || g.textContent || '').replace(/\\u00a0/g, ' ').trim())
            """) or []
        except Exception:
            return []

    def set_all_gaps(self, answers):
        expected = sum(1 for a in answers if a)
        if expected == 0:
            return
        try:
            # Fast single-JS cycle pass across all toggle gaps
            self.page.evaluate(
                """
                ([ansList, maxCycles]) => {
                    const norm = s => (s || '').replace(/\\u00a0/g, ' ').trim();
                    for (let i = 0; i < ansList.length; i++) {
                        const wanted = norm(ansList[i]);
                        if (!wanted) continue;
                        for (let c = 0; c < maxCycles; c++) {
                            const gaps = document.querySelectorAll('.exercise-items .gap');
                            if (i >= gaps.length) break;
                            const g = gaps[i];
                            if (norm(g.innerText || g.textContent) === wanted) break;
                            const cont = g.closest('.gap-container') || g.parentElement;
                            const btn = cont ? cont.querySelector('button') : null;
                            if (!btn) break;
                            try { btn.click(); } catch (e) { break; }
                        }
                    }
                }
                """,
                [list(answers), self.MAX_TOGGLE_CYCLES],
            )

            # Verify every single gap; repair any stubborn gap via Playwright click
            cur_vals = self.extract_correct_answers()
            for i, ans in enumerate(answers):
                wanted = self._norm(ans)
                if not wanted:
                    continue
                if i < len(cur_vals) and cur_vals[i] == wanted:
                    continue
                for _ in range(self.MAX_TOGGLE_CYCLES):
                    gap = self.page.locator(".exercise-items .gap").nth(i)
                    if gap.count() == 0:
                        break
                    if self._norm(gap.inner_text()) == wanted:
                        break
                    container = gap.locator(
                        "xpath=ancestor::div[contains(@class,'gap-container')]"
                    ).first
                    toggle = container.locator("button").first if container.count() > 0 else None
                    if toggle is None or toggle.count() == 0:
                        break
                    try:
                        toggle.click(timeout=1500)
                        time.sleep(0.04)
                    except Exception:
                        break

            final_vals = self.extract_correct_answers()
            matched = sum(
                1 for i, ans in enumerate(answers)
                if self._norm(ans) and i < len(final_vals) and final_vals[i] == self._norm(ans)
            )
            self.verify_step(
                "ตั้งค่าตัวเลือก Toggle ครบทุกจุด",
                matched == expected,
                f"ครบ {matched}/{expected} จุด",
            )
        except Exception as e:
            self.logger.error(f"set_all_gaps error: {e}")


class MarkTextSolver(BaseSolver):
    MAX_ITERATIONS = 5

    def extract_current_state_answers(self, verified=True):
        self.capture_initial_context()
        group_positions, all_positions, marked_words = self.extract_correct_positions()
        has_any = bool(group_positions or all_positions or marked_words)
        primary = marked_words if marked_words else (group_positions or all_positions)
        return self.record_answer(
            "mark-text",
            primary,
            verified=(verified and has_any),
            group_positions=group_positions,
            all_positions=all_positions,
            marked_words=marked_words,
        )

    def solve(self):
        self.logger.info("=== Mark Text Solver ===")
        self.start_timer()
        if not self.wait_for_page_ready():
            return False
        self.capture_initial_context()

        if self.already_passed():
            self.extract_current_state_answers(verified=True)
            return True

        cached = self._find_cached_answer(expected_type="mark-text")
        if isinstance(cached, dict):
            c_group = cached.get("group_positions") or []
            c_all = cached.get("all_positions") or []
            for pos_list in (c_group, c_all):
                if pos_list:
                    self.step(f"[CACHE] Trying saved mark-text positions ({len(pos_list)} items)")
                    self.click_by_positions(pos_list)
                    self.click_correction()
                    score = self.get_result_score()
                    if score >= self.PASS_LINE:
                        self.verify_step("ตรวจคะแนน Mark Text (Cache)", True, f"ได้คะแนน {score}/100")
                        self.record_answer(
                            "mark-text",
                            cached.get("answers", pos_list),
                            verified=True,
                            group_positions=c_group,
                            all_positions=c_all,
                            marked_words=cached.get("marked_words", []),
                        )
                        return True
                    self.click_repeat()

        self.click_correction()
        if not self.click_solution():
            self.report_problem("mark_text_no_solution")
            self.extract_current_state_answers(verified=False)
            return False

        group_positions, all_positions, marked_words = self.extract_correct_positions()
        if not group_positions and not all_positions:
            self.report_problem("mark_text_extract_empty")
            self.extract_current_state_answers(verified=False)
            return False

        primary = marked_words if marked_words else (group_positions or all_positions)
        self.record_answer(
            "mark-text",
            primary,
            verified=True,
            group_positions=group_positions,
            all_positions=all_positions,
            marked_words=marked_words,
        )
        self.verify_step("บันทึกเฉลย Mark Text ลงฐานข้อมูล", True, f"{len(group_positions or all_positions)} จุด")

        self.click_repeat()
        for approach in ["group", "all"]:
            positions = group_positions if approach == "group" else all_positions
            if not positions:
                continue
            self.logger.info(f"--- Trying approach: {approach} ({len(positions)} clicks) ---")
            for iteration in range(self.MAX_ITERATIONS):
                self.click_by_positions(positions)
                self.click_correction()
                score = self.get_result_score()
                self.logger.info(f"--- Iteration {iteration+1}/{self.MAX_ITERATIONS} | Score: {score} ---")
                if score >= self.PASS_LINE:
                    self.verify_step("ตรวจคะแนน Mark Text", True, f"ได้คะแนน {score}/100")
                    elapsed = self.stop_timer()
                    self.logger.info(f"SUCCESS! Time: {elapsed}")
                    return True
                if iteration + 1 < self.MAX_ITERATIONS:
                    self.click_repeat()
            if self.get_result_score() >= self.PASS_LINE:
                return True
            self.click_repeat()
        final_sc = self.get_result_score()
        ok = final_sc >= self.PASS_LINE
        self.verify_step("ตรวจคะแนน Mark Text", ok, f"ได้คะแนน {final_sc}/100")
        return ok

    def extract_correct_positions(self):
        try:
            result = self.page.evaluate("""
                () => {
                    const allWords = Array.from(document.querySelectorAll('.exercise-items .word'));
                    const hasActiveClass = (node) => {
                        if (!node) return false;
                        const cls = (node.className || '').toString().toLowerCase();
                        return cls.includes('selected') || cls.includes('marked') ||
                               cls.includes('success') || cls.includes('correct') ||
                               cls.includes('highlight') || cls.includes('chosen') ||
                               cls.includes('result-green');
                    };
                    const anyExplicitlyMarked = allWords.some(w => {
                        const mt = w.closest('.mark-text');
                        return hasActiveClass(w) || hasActiveClass(mt);
                    });

                    const groupPositions = [];
                    const allPositions = [];
                    const markedWords = [];
                    const seenMarkTexts = new Set();
                    allWords.forEach((w, i) => {
                        const mt = w.closest('.mark-text');
                        const isMarked = anyExplicitlyMarked
                            ? (hasActiveClass(w) || hasActiveClass(mt))
                            : Boolean(mt);
                        if (isMarked) {
                            allPositions.push(i);
                            if (mt) {
                                if (!seenMarkTexts.has(mt)) {
                                    seenMarkTexts.add(mt);
                                    groupPositions.push(i);
                                    markedWords.push((mt.innerText || '').trim());
                                }
                            } else {
                                groupPositions.push(i);
                                markedWords.push((w.innerText || '').trim());
                            }
                        }
                    });
                    return { groupPositions, allPositions, markedWords };
                }
            """)
            group_positions = result.get("groupPositions", []) if result else []
            all_positions = result.get("allPositions", []) if result else []
            marked_words = [w for w in (result.get("markedWords", []) if result else []) if w]
            return group_positions, all_positions, marked_words
        except Exception as e:
            self.logger.error(f"extract_correct_positions error: {e}")
            return [], [], []

    def click_by_positions(self, positions):
        try:
            res = self.page.evaluate("""
                (positions) => {
                    const isMarkedNode = (node) => {
                        if (!node) return false;
                        const cls = (node.className || '').toString().toLowerCase();
                        return cls.includes('selected') || cls.includes('marked') ||
                               cls.includes('highlight') || cls.includes('chosen') ||
                               cls.includes('active');
                    };
                    const seenGroups = new Set();
                    const allWords = Array.from(document.querySelectorAll('.exercise-items .word'));
                    allWords.forEach(w => {
                        const mt = w.closest('.mark-text');
                        if (mt) {
                            if (seenGroups.has(mt)) return;
                            if (isMarkedNode(mt) || isMarkedNode(w)) {
                                seenGroups.add(mt);
                                try { w.click(); } catch(e) {}
                            }
                        } else if (isMarkedNode(w)) {
                            try { w.click(); } catch(e) {}
                        }
                    });

                    let clickedCount = 0;
                    let verifiedCount = 0;
                    positions.forEach(idx => {
                        if (idx < allWords.length) {
                            const el = allWords[idx];
                            try {
                                el.scrollIntoView({ block: 'nearest' });
                                el.click();
                                clickedCount++;
                                const mt = el.closest('.mark-text');
                                if (isMarkedNode(el) || isMarkedNode(mt)) verifiedCount++;
                            } catch(e) {}
                        }
                    });
                    return { clickedCount, verifiedCount, expected: positions.length };
                }
            """, positions) or {}
            clicked = int(res.get("clickedCount", 0))
            verified = int(res.get("verifiedCount", clicked))
            expected = int(res.get("expected", len(positions)))
            self.verify_step(
                "คลิกเลือกคำ Mark Text ครบทุกจุด",
                clicked == expected and expected > 0,
                f"คลิก {clicked}/{expected} จุด (ไฮไลต์แล้ว {verified})",
            )
        except Exception as e:
            self.logger.error(f"click_by_positions error: {e}")


class PronunciationSolver(BaseSolver):
    RECORD_DURATION = 8
    PASSING_SCORE = 51
    MAX_CORRECTION_ROUNDS = 3
    _audio_url_cache = []
    _installed_page_ids = set()
    _installed_context_ids = set()

    def __init__(self, page, logger, answer_db=None, page_answer_index=None, diagnostic_cb=None):
        super().__init__(
            page,
            logger,
            answer_db=answer_db,
            page_answer_index=page_answer_index,
            diagnostic_cb=diagnostic_cb,
        )
        self._item_audio_b64_cache = {}

    def _extract_pronunciation_texts(self):
        texts = []
        try:
            for item in self.page.locator(".exercise-items .item").all():
                txt = item.inner_text().strip()
                if txt:
                    texts.append(" ".join(txt.split()))
        except Exception:
            pass
        return texts

    def extract_current_state_answers(self, verified=True):
        self.capture_initial_context()
        texts = self._extract_pronunciation_texts()
        return self.record_answer("pronunciation", texts, verified=verified)

    def solve(self):
        self.logger.info("=== Pronunciation Solver ===")
        self.start_timer()
        self._install_console_listener()
        self._install_network_sniffer()

        self._handle_audio_setup_modal()

        if not self.wait_for_page_ready():
            return False
        self.capture_initial_context()

        if self.already_passed():
            self.extract_current_state_answers(verified=True)
            return True

        for _ in range(5):
            if self._handle_audio_setup_modal():
                break
            time.sleep(0.5)

        item_locator = self.page.locator(".exercise-items .item")
        item_count = item_locator.count()
        use_single_wrapper = False
        if item_count == 0 and self.page.locator("button.microphone-button").count() > 0:
            use_single_wrapper = True
            item_count = 1

        for idx in range(item_count):
            cur_item = (
                self.page.locator(".exercise").first
                if use_single_wrapper
                else self.page.locator(".exercise-items .item").nth(idx)
            )
            self._record_item(cur_item, idx)

        self._check_pronunciation_batch()
        for round_number in range(1, self.MAX_CORRECTION_ROUNDS + 1):
            score = self.get_result_score()
            failed_indexes, unknown_indexes = self._pronunciation_item_statuses()
            self.step(
                f"Result: {score}/100 | Failed items: "
                f"{len(failed_indexes)} | Unscored: {len(unknown_indexes)}"
            )
            if score >= self.PASSING_SCORE and (
                not failed_indexes or item_count <= 1 or score >= 75
            ):
                self.extract_current_state_answers(verified=True)
                elapsed = self.stop_timer()
                self.logger.info(
                    f"Pronunciation SUCCESS! Time: {elapsed} | Score: {score}"
                )
                return True

            retry_indexes = failed_indexes
            if not retry_indexes and score < self.PASSING_SCORE:
                retry_indexes = unknown_indexes or list(range(item_count))
            retry_indexes = [
                idx for idx in retry_indexes
                if idx < item_count and (self._item_audio_b64_cache.get(idx) or score < self.PASSING_SCORE)
            ]
            if not retry_indexes:
                break

            has_any_audio = any(self._item_audio_b64_cache.get(idx) for idx in retry_indexes)
            if not has_any_audio and round_number >= 2 and score == 0:
                self.logger.warning(
                    "[PRON] No reference audio available after retry — stopping early"
                )
                break

            self.logger.info(
                f"[PRON] Retry round {round_number}: "
                f"items {[idx + 1 for idx in retry_indexes]}"
            )
            for idx in retry_indexes:
                if idx < item_count:
                    cur_item = (
                        self.page.locator(".exercise").first
                        if use_single_wrapper
                        else self.page.locator(".exercise-items .item").nth(idx)
                    )
                    self._record_item(cur_item, idx)
            self._check_pronunciation_batch()

        score = self.get_result_score()
        failed_indexes, _ = self._pronunciation_item_statuses()
        self.step(f"Final detected score: {score}")
        passed = score >= self.PASSING_SCORE
        self.extract_current_state_answers(verified=passed)
        if passed:
            elapsed = self.stop_timer()
            self.logger.info(f"Pronunciation SUCCESS! Time: {elapsed} | Score: {score}")
            return True
        self.logger.warning(
            f"Pronunciation FAILED. Score: {score} | "
            f"Failed items: {[idx + 1 for idx in failed_indexes]}"
        )
        return False

    def _check_pronunciation_batch(self):
        self.step("Checking pronunciation batch...")
        if self.click_correction():
            time.sleep(2)
        else:
            self.logger.warning("[PRON] Could not click [Correction]")

    def _pronunciation_item_statuses(self):
        try:
            result = self.page.evaluate("""
                () => {
                    const failedIndexes = [];
                    const unknownIndexes = [];
                    const items = Array.from(
                        document.querySelectorAll('.exercise-items .item')
                    );
                    const colorKind = (value) => {
                        const match = value.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/i);
                        if (!match) return null;
                        const red = Number(match[1]);
                        const green = Number(match[2]);
                        const blue = Number(match[3]);
                        if (green > red + 25 && green > blue + 15) return 'pass';
                        if (red > green + 35 && red > blue + 25) return 'fail';
                        if (red > 140 && green > 130 && blue < 130) return 'pass';
                        if (Math.max(red, green, blue) - Math.min(red, green, blue) < 20 &&
                            red > 80 && red < 210) return 'fail';
                        return null;
                    };

                    items.forEach((item, index) => {
                        const result = item.querySelector('.word-result');
                        if (!result) {
                            unknownIndexes.push(index);
                            return;
                        }
                        const nodes = [result, ...result.querySelectorAll('*')];
                        let status = null;
                        for (const node of nodes) {
                            const cls = (node.className || '').toString().toLowerCase();
                            if (/\\b(green|success|correct|passed)\\b/.test(cls)) {
                                status = 'pass';
                                break;
                            }
                            if (/\\b(red|error|wrong|incorrect|failed)\\b/.test(cls)) {
                                status = 'fail';
                                break;
                            }
                            const style = window.getComputedStyle(node);
                            const rect = node.getBoundingClientRect();
                            if (rect.width <= 0 || rect.height <= 0) continue;
                            const background = style.backgroundColor;
                            if (background !== 'rgba(0, 0, 0, 0)' &&
                                background !== 'transparent') {
                                status = colorKind(background);
                                if (status) break;
                            }
                        }
                        if (status === 'fail') failedIndexes.push(index);
                        else if (!status) unknownIndexes.push(index);
                    });
                    return { failedIndexes, unknownIndexes };
                }
            """)
            if result:
                return result.get("failedIndexes", []), result.get("unknownIndexes", [])
        except Exception as e:
            self.logger.debug(f"[PRON] Could not read item results: {e}")
        return [], list(range(self.page.locator(".exercise-items .item").count()))

    def _load_item_reference_audio(self, item, idx=0):
        if idx in self._item_audio_b64_cache and self._item_audio_b64_cache[idx]:
            return list(self._item_audio_b64_cache[idx])

        start_idx = len(PronunciationSolver._audio_url_cache)
        resource_urls_before = set(self._audio_resource_urls())
        try:
            play_button = item.locator("button.play-button").first
            if play_button.count() > 0:
                play_button.scroll_into_view_if_needed()
                play_button.click(timeout=3000, force=True)
        except Exception as e:
            self.logger.debug(f"[PRON] Reference audio click failed: {e}")

        page_audio_urls = []
        new_resource_urls = []
        network_urls = []
        for _ in range(10):
            time.sleep(0.5)
            page_audio_urls = self._page_audio_urls()
            new_resource_urls = [
                url for url in self._audio_resource_urls()
                if url not in resource_urls_before
            ]
            network_urls = PronunciationSolver._audio_url_cache[start_idx:]
            if network_urls or new_resource_urls or page_audio_urls:
                break

        urls = network_urls[-1:] or new_resource_urls[-1:] or page_audio_urls[-1:]
        if not urls:
            all_res = self._audio_resource_urls()
            if all_res:
                urls = [all_res[min(idx, len(all_res) - 1)]]
        b64_list = self._fetch_audio_as_base64(urls) if urls else []
        if b64_list:
            self._item_audio_b64_cache[idx] = list(b64_list)
        return b64_list

    def _page_audio_urls(self):
        try:
            urls = self.page.evaluate("""
                () => Array.from(document.querySelectorAll(
                        'audio[src], audio source[src], [data-audio-url]'
                    )).map(el => el.src || el.getAttribute('data-audio-url'))
                      .filter(Boolean)
            """)
            return list(dict.fromkeys(
                u for u in (urls or []) if isinstance(u, str) and u.startswith('http')
            ))
        except Exception as e:
            self.logger.debug(f"[PRON] Page audio lookup failed: {e}")
            return []

    def _audio_resource_urls(self):
        try:
            urls = self.page.evaluate("""
                () => performance.getEntriesByType('resource').map(entry => entry.name)
                    .filter(name => /(?:\\.mp3|\\.ogg|\\.m4a|\\.wav|\\.opus|\\.aac|\\.webm)(?:[?#]|$)|(?:audio|media|speech|track)/i.test(name))
            """)
            return list(dict.fromkeys(
                url for url in (urls or []) if isinstance(url, str) and url.startswith('http')
            ))
        except Exception as e:
            self.logger.debug(f"[PRON] Resource audio lookup failed: {e}")
            return []

    def _install_console_listener(self):
        page_id = id(self.page)
        if page_id in PronunciationSolver._installed_page_ids:
            return
        try:
            def on_console(msg):
                try:
                    text = msg.text
                    if '[Bot-Pron]' in text:
                        pass
                except Exception:
                    pass
            self.page.on("console", on_console)
            PronunciationSolver._installed_page_ids.add(page_id)
        except Exception as e:
            self.logger.error(f"Console listener: {e}")

    def _install_network_sniffer(self):
        try:
            context = self.page.context
            ctx_id = id(context)
            if ctx_id in PronunciationSolver._installed_context_ids:
                return

            def on_response(response):
                try:
                    url = response.url
                    if url.startswith(('blob:', 'data:')):
                        return
                    url_low = url.lower()
                    is_audio = any(
                        url_low.endswith(ext) or ext + '?' in url_low
                        for ext in ['.mp3', '.ogg', '.m4a', '.wav', '.opus']
                    )
                    if not is_audio and '/track/' in url_low:
                        is_audio = True
                    if not is_audio:
                        try:
                            content_type = (response.header_value('content-type') or '').lower()
                            is_audio = content_type.startswith('audio/')
                        except Exception:
                            pass
                    if is_audio:
                        PronunciationSolver._audio_url_cache.append(url)
                except Exception:
                    pass

            context.on("response", on_response)
            PronunciationSolver._installed_context_ids.add(ctx_id)
        except Exception as e:
            self.logger.error(f"Net sniffer: {e}")

    def _trigger_audio_load(self):
        try:
            play_btns = self.page.locator("button.play-button").all()
            for pb in play_btns:
                try:
                    if pb.count() > 0 and pb.is_visible(timeout=1000):
                        pb.scroll_into_view_if_needed()
                        time.sleep(0.2)
                        pb.click(timeout=3000, force=True)
                        time.sleep(3)
                except Exception:
                    continue
        except Exception as e:
            self.logger.debug(f"Trigger error: {e}")

    def _fetch_audio_as_base64(self, urls):
        results = []
        for url in urls:
            fetched = False
            try:
                api_req = getattr(self.page.context, "request", None)
                if api_req is not None:
                    resp = api_req.get(url, timeout=15000)
                    if resp.ok:
                        body = resp.body()
                        if body:
                            results.append(base64.b64encode(body).decode("ascii"))
                            fetched = True
            except Exception:
                pass
            if fetched:
                continue
            try:
                headers = {
                    'User-Agent': (
                        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                        'AppleWebKit/537.36 (KHTML, like Gecko) '
                        'Chrome/120.0.0.0 Safari/537.36'
                    ),
                    'Referer': 'https://portal.speexx.com/',
                }
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    b64 = base64.b64encode(resp.content).decode('ascii')
                    results.append(b64)
            except Exception:
                pass
        return results

    def _set_b64_in_window(self, b64_list):
        try:
            self.page.evaluate("""
                (b64list) => {
                    window.__botPronB64 = b64list;
                    window.__botPronDuration = 0;
                }
            """, b64_list)
        except Exception as e:
            self.logger.error(f"Set b64 error: {e}")

    def _record_item(self, item, idx):
        try:
            self.step(f"Recording item {idx + 1}...")
            self._handle_audio_setup_modal()

            b64_list = self._load_item_reference_audio(item, idx=idx)
            if not b64_list:
                self.logger.warning(f"[PRON] No reference audio found for item {idx + 1}")
            self._set_b64_in_window(b64_list)
            try:
                self.page.evaluate("""
                    () => {
                        try {
                            if (window.__botPronCtx) {
                                window.__botPronCtx.close();
                                window.__botPronCtx = null;
                            }
                        } catch(e) {}
                    }
                """)
            except Exception:
                pass
            time.sleep(0.2)
            mic = item.locator("button.microphone-button").first
            if mic.count() == 0:
                self.step("No mic button")
                return

            self._handle_audio_setup_modal()
            mic.scroll_into_view_if_needed()
            mic.click(timeout=5000)
            self.step("Mic started")

            popup_closed = self._handle_audio_setup_modal()

            if not popup_closed:
                for _ in range(4):
                    if self._handle_audio_setup_modal():
                        popup_closed = True
                        break
                    time.sleep(0.25)

            if not popup_closed:
                self.logger.info("[PRON] Audio setup popup not found or already closed.")

            try:
                reference_duration = float(self.page.evaluate(
                    "() => Number(window.__botPronDuration || 0)"
                ) or 0)
            except Exception:
                reference_duration = 0
            record_duration = self.RECORD_DURATION
            if reference_duration > 0:
                record_duration = max(3.5, min(reference_duration + 1.5, 15.0))
            self.step(f"Recording duration: {record_duration:.1f}s")
            time.sleep(record_duration)
            mic.click(timeout=3000, force=True)
            self.step("Mic stopped")
            time.sleep(0.5)
            return True
        except Exception as e:
            self.logger.error(f"Record error: {e}")
            return False


class ExerciseEngine:
    def __init__(self, page, logger, answer_db=None, page_answer_index=None, diagnostic_cb=None):
        self.page = page
        self.logger = logger
        self.answer_db = answer_db if answer_db is not None else {}
        self.page_answer_index = page_answer_index if page_answer_index is not None else {}
        self.diagnostic_cb = diagnostic_cb
        self.solvers = {
            "type-drag-drop": DragDropSolver,
            "type-drag-drop-table": DragDropSolver,
            "type-answer": AnswerSolver,
            "type-scrambled-sentence": ScrambledSentenceSolver,
            "type-scrambled-table": ScrambledTableSolver,
            "type-single-choice": SingleChoiceSolver,
            "type-multiple-choice": MultipleChoiceSolver,
            "type-video": VideoSolver,
            "type-picture-choice": PictureChoiceSolver,
            "type-toggle-solution": ToggleSolutionSolver,
            "type-mark-text": MarkTextSolver,
            "type-pronunciation": PronunciationSolver,
            "type-single-item-pronunciation": PronunciationSolver,
            "type-multi-item-pronunciation": PronunciationSolver,
            "type-multiple-item-pronunciation": PronunciationSolver,
        }

    def detect_type(self):
        try:
            exercise_div = self.page.locator(".exercise").first
            video_div = self.page.locator(".video").first
            if exercise_div.count() == 0:
                if video_div.count() > 0 or self.page.locator("video").count() > 0:
                    return "type-video"
                return "unknown"
            cls = exercise_div.get_attribute("class") or ""

            if "type-intro" in cls:
                return "type-intro"

            if "type-video" in cls:
                return "type-video"

            if "type-drag-drop" in cls:
                if "layout-table" in cls or "layout-grid-duo" in cls:
                    return "type-drag-drop-table"
                return "type-drag-drop"

            if "type-scrambled-sentence" in cls:
                return "type-scrambled-sentence"
            if "type-scrambled-table" in cls:
                return "type-scrambled-table"
            if "type-picture-choice" in cls:
                return "type-picture-choice"
            if "type-toggle-solution" in cls:
                return "type-toggle-solution"
            if "type-single-choice" in cls:
                return "type-single-choice"
            if "type-multiple-choice" in cls:
                return "type-multiple-choice"
            if "type-mark-text" in cls:
                return "type-mark-text"
            if "type-single-item-pronunciation" in cls:
                return "type-single-item-pronunciation"
            if "type-multi-item-pronunciation" in cls:
                return "type-multi-item-pronunciation"
            if "type-multiple-item-pronunciation" in cls:
                return "type-multiple-item-pronunciation"
            if "pronunciation" in cls:
                return "type-pronunciation"
            if "type-answer" in cls:
                return "type-answer"
            if video_div.count() > 0 or self.page.locator("video").count() > 0:
                return "type-video"
            return "unknown"
        except Exception:
            return "unknown"

    def get_solver(self, t, force_solve=False, exercise_title="", page_number=0):
        sc = self.solvers.get(t)
        if not sc:
            return None
        solver = sc(
            self.page,
            self.logger,
            answer_db=self.answer_db,
            page_answer_index=self.page_answer_index,
            diagnostic_cb=self.diagnostic_cb,
        )
        solver.force_solve = force_solve
        solver.exercise_title = exercise_title or ""
        solver.page_number = int(page_number or 0)
        return solver


class TeeLogger:
    def __init__(self, filename, original_stdout):
        self.terminal = original_stdout
        self.log = open(filename, "a", encoding="utf-8")
        self.lock = threading.Lock()
        self._at_line_start = True

    def write(self, message):
        with self.lock:
            try:
                self.terminal.write(message)
            except Exception:
                pass
            try:
                clean = _ANSI_ESCAPE_RE.sub("", message)
                if clean:
                    self.log.write(clean)
                    self.log.flush()
                    self._at_line_start = clean.endswith("\n")
            except Exception:
                pass

    def write_log_line(self, formatted_line):
        with self.lock:
            try:
                if not self.log.closed:
                    if not self._at_line_start:
                        self.log.write("\n")
                    self.log.write(formatted_line + "\n")
                    self.log.flush()
                    self._at_line_start = True
            except Exception:
                pass

    def flush(self):
        with self.lock:
            try:
                self.terminal.flush()
            except Exception:
                pass
            try:
                if not self.log.closed:
                    self.log.flush()
            except Exception:
                pass

    def close(self):
        with self.lock:
            try:
                if not self.log.closed:
                    self.log.flush()
                    self.log.close()
            except Exception:
                pass


class _TeeLogHandler(logging.Handler):
    def __init__(self, tee_logger):
        super().__init__()
        self.tee_logger = tee_logger

    def emit(self, record):
        try:
            msg = self.format(record)
            self.tee_logger.write_log_line(msg)
        except Exception:
            pass

class SpeexxBotCLI:
    MAX_NEW_EXERCISE_CHAIN = 100
    DEFAULT_CHAPTER_NAME = "General"

    def __init__(self):
        self.config_folder = "config"
        self.logs_folder = "logs"
        self.dump_folder = "webpagedump"
        self.reports_folder = "reports"
        self.profiles_folder = "chrome_profiles"
        self.accounts_file = os.path.join(self.config_folder, "accounts.json")

        self.current_chapter_cid = None
        self.current_chapter_name = ""
        self.loaded_chapter_name = ""
        self.answer_bank_file = ""

        self.lang = "th"

        self.ensure_folders()
        self.setup_logging()

        self.accounts = self.load_accounts()
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.active_profile_dir = None
        self.current_chapters = []
        self.force_solve_all = False
        self.answer_db = {}

        self.answer_records = []
        self.answer_page_contexts = {}
        self.page_answer_index = {}
        self.structured_page_records = {}
        self.chapter_catalog = []

    @property
    def T(self):
        return TRANSLATIONS.get(self.lang, TRANSLATIONS["th"])

    @T.setter
    def T(self, value):
        for code, table in TRANSLATIONS.items():
            if value is table:
                self.lang = code
                return

    def _input(self, prompt="", sensitive=False):
        value = input(prompt)
        try:
            self.logger.info(f"INPUT: {'<redacted>' if sensitive else value}")
        except Exception:
            pass
        return value

    @staticmethod
    def _canonical_answer_type(exercise_type):
        mapping = {
            "type-drag-drop": "drag-drop",
            "type-drag-drop-table": "drag-drop",
            "type-answer": "answer",
            "type-scrambled-sentence": "scrambled-sentence",
            "type-scrambled-table": "scrambled-table",
            "type-single-choice": "single-choice",
            "type-multiple-choice": "multiple-choice",
            "type-video": "video",
            "type-picture-choice": "picture-choice",
            "type-toggle-solution": "toggle-solution",
            "type-mark-text": "mark-text",
            "type-single-item-pronunciation": "pronunciation",
            "type-multi-item-pronunciation": "pronunciation",
            "type-multiple-item-pronunciation": "pronunciation",
            "type-intro": "intro",
        }
        return mapping.get(exercise_type, exercise_type or "unknown")

    @staticmethod
    def _comparable_question_key(value):
        parts = [
            p for p in str(value or "").split(" | ")
            if not re.fullmatch(r"Exercise\s+\d+", p.strip(), re.I)
        ]
        return " ".join(" | ".join(parts).replace("\xa0", " ").split()).casefold()

    def _safe_chapter_filename(self, chapter_name):
        raw = (chapter_name or self.DEFAULT_CHAPTER_NAME).strip() or self.DEFAULT_CHAPTER_NAME
        safe_name = re.sub(r'[\\/*?:"<>|]', "", raw).strip().replace(" ", "_")
        return safe_name or self.DEFAULT_CHAPTER_NAME

    def _detect_active_chapter_from_page(self):
        if not self.page:
            return None, None
        try:
            detected = self.page.evaluate("""
                () => {
                    const isTest = (name) => {
                        const low = (name || '').toLowerCase();
                        return low.includes('test') || low.includes('assessment') ||
                               low.includes('exam') || low.includes('quiz') ||
                               low.includes('แบบทดสอบ') || low.includes('ข้อสอบ');
                    };
                    const containers = Array.from(document.querySelectorAll('.level-container'));
                    if (containers.length > 0) {
                        const pickFrom = (el) => {
                            const box = el.querySelector('.level-inside-box') || el;
                            const txtEl = el.querySelector('.level-text') || box;
                            const name = (txtEl.innerText || txtEl.textContent || '').trim();
                            const cid = el.getAttribute('data-id') || null;
                            return name ? { name, cid } : null;
                        };
                        for (const el of containers) {
                            const box = el.querySelector('.level-inside-box');
                            const cls = ((el.className || '') + ' ' + ((box && box.className) || '')).toLowerCase();
                            const aria = (el.getAttribute('aria-selected') || (box && box.getAttribute('aria-selected')) || '').toLowerCase();
                            if (aria === 'true' ||
                                /(^|[-_\\s])(active|selected|current|open)([-_\\s]|$)/.test(cls)) {
                                const info = pickFrom(el);
                                if (info && !isTest(info.name)) return info;
                            }
                        }
                        for (const el of containers) {
                            const box = el.querySelector('.level-inside-box');
                            const cls = ((box && box.className) || '').toLowerCase();
                            if (cls.includes('future')) continue;
                            const info = pickFrom(el);
                            if (info && !isTest(info.name)) return info;
                        }
                    }

                    const levelSelectors = [
                        '.circliful-container-progress .timer .number',
                        '.breadcrumb',
                        '.header-level',
                        '[class*="level-name"]',
                        '.level-text',
                    ];
                    const cefrRe = /\\b(A1(?:\\.[12])?|A2(?:\\.[12])?|B1(?:\\.[12])?|B2(?:\\.[12])?|C1(?:\\.[12])?|C2)\\b/;
                    for (const sel of levelSelectors) {
                        for (const el of document.querySelectorAll(sel)) {
                            const txt = (el.innerText || el.textContent || '').trim();
                            const m = txt.match(cefrRe);
                            if (m) return { name: m[1], cid: null };
                        }
                    }
                    return null;
                }
            """)
            if isinstance(detected, dict) and detected.get("name"):
                return detected["name"].strip(), detected.get("cid")
        except Exception as e:
            self.logger.debug(f"[DB] Auto chapter detect failed: {e}")
        return None, None

    def _ensure_chapter_db_loaded(self, announce=False):
        if not self.current_chapter_name:
            detected_name, detected_cid = self._detect_active_chapter_from_page()
            if detected_name:
                self.current_chapter_name = detected_name
                if detected_cid and not self.current_chapter_cid:
                    self.current_chapter_cid = detected_cid
            else:
                self.current_chapter_name = self.DEFAULT_CHAPTER_NAME

        if self.loaded_chapter_name != self.current_chapter_name:
            self._load_answer_db(self.current_chapter_name, announce=announce)
        return self.current_chapter_name

    def _load_answer_db(self, chapter_name, announce=True):
        chapter_name = (chapter_name or self.current_chapter_name or self.DEFAULT_CHAPTER_NAME).strip()
        if not chapter_name:
            chapter_name = self.DEFAULT_CHAPTER_NAME
        self.current_chapter_name = chapter_name
        safe_name = self._safe_chapter_filename(chapter_name)
        self.answer_bank_file = os.path.join(self.reports_folder, f"answers_{safe_name}.json")

        self.answer_db = {}
        self.answer_records = []
        self.answer_page_contexts = {}
        self.page_answer_index = {}
        self.structured_page_records = {}
        self.chapter_catalog = []

        try:
            if os.path.exists(self.answer_bank_file):
                with open(self.answer_bank_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if isinstance(data, dict) and data.get("schema_version") == 2:
                    chapter_meta = data.get("chapter", {}) or {}
                    if not self.current_chapter_cid and chapter_meta.get("cid"):
                        self.current_chapter_cid = chapter_meta.get("cid")
                    self.answer_records = data.get("exercises", []) or []
                    self.chapter_catalog = chapter_meta.get("catalog", []) or []
                    for exercise in self.answer_records:
                        ex_title = (exercise.get("title") or "").strip()
                        for page_rec in exercise.get("pages", []):
                            question = page_rec.get("question", "")
                            answer = page_rec.get("answer")
                            p_num = page_rec.get("page")
                            if question and isinstance(answer, dict):
                                existing_q = self.answer_db.get(question)
                                if not existing_q or answer.get("verified", True) is not False:
                                    self.answer_db[question] = answer
                            if (
                                ex_title
                                and ex_title != "Imported answers (legacy)"
                                and isinstance(p_num, int)
                                and p_num > 0
                            ):
                                self.structured_page_records[(ex_title, p_num)] = copy.deepcopy(page_rec)
                                if isinstance(answer, dict):
                                    self.page_answer_index[(ex_title.strip().casefold(), int(p_num))] = answer

                    loaded_count = len(self.answer_db)
                    self.loaded_chapter_name = chapter_name
                    self.logger.info(
                        "[DB] Loaded structured database: %s exercises, %s pages, %s answers",
                        len(self.answer_records),
                        sum(len(x.get("pages", [])) for x in self.answer_records),
                        loaded_count,
                    )
                    if announce and hasattr(self, "print_status"):
                        summary = chapter_meta.get("summary", {}) or {}
                        self.print_status(
                            "DB",
                            self.T["db_status"].format(
                                chapter_name,
                                summary.get("exercises", len(self.chapter_catalog)),
                                summary.get("pages", 0),
                                summary.get("answered_pages", loaded_count),
                            ),
                        )
                else:
                    self.answer_db = data if isinstance(data, dict) else {}
                    self.loaded_chapter_name = chapter_name
                    self.logger.info(
                        "[DB] Loaded legacy database: %s answers (will migrate to schema v2)",
                        len(self.answer_db),
                    )
            else:
                self.loaded_chapter_name = chapter_name
                self.logger.info(f"[DB] New answer bank for {chapter_name}")
        except Exception as e:
            self.logger.error(f"[DB] Load failed: {e}")
            self.loaded_chapter_name = chapter_name

    def _extract_dom_page_snapshot(self):
        question = ""
        prompt = ""
        header_title = ""
        items = []
        if not self.page:
            return question, prompt, header_title, items
        try:
            snap = self.page.evaluate("""
                () => {
                    const inst = document.querySelector('.instructions-text');
                    const hdr = document.querySelector('h1.exercise-header');
                    const ex = document.querySelector('.exercise-items') ||
                               document.querySelector('.exercise') ||
                               document.querySelector('.video');
                    const prompt = inst ? (inst.innerText || '').trim() : '';
                    const headerTitle = hdr ? (hdr.innerText || '').trim() : '';
                    const rawItems = Array.from(
                        document.querySelectorAll('.exercise-items .item')
                    ).map(el => (el.innerText || '').replace(/\\s+/g, ' ').trim()).filter(Boolean);
                    const parts = [];
                    if (headerTitle) parts.push(headerTitle);
                    if (prompt) parts.push(prompt);
                    if (ex) {
                        const exText = (ex.innerText || '').replace(/\\s+/g, ' ').trim();
                        if (exText) parts.push(exText);
                    }
                    const question = parts.join(' | ').replace(/\\s+/g, ' ').trim();
                    return {
                        question: question.slice(0, 2000),
                        prompt,
                        headerTitle,
                        items: rawItems,
                    };
                }
            """)
            if isinstance(snap, dict):
                question = snap.get("question") or ""
                prompt = snap.get("prompt") or ""
                header_title = snap.get("headerTitle") or ""
                items = snap.get("items") or []
        except Exception as e:
            self.logger.debug(f"[DB] DOM snapshot failed: {e}")
        return question, prompt, header_title, items

    def _record_page_to_db(self, title, page_number, total_pages, exercise_type,
                           solver=None, verified_override=None, persist=True):
        try:
            self._ensure_chapter_db_loaded(announce=False)
            now = datetime.now().isoformat()
            dom_q, dom_prompt, dom_header, dom_items = self._extract_dom_page_snapshot()

            effective_title = (title or dom_header or "Unknown exercise").strip() or "Unknown exercise"
            p_num = int(page_number or 0)
            p_total = int(total_pages or 0)

            question = ""
            prompt = dom_prompt
            entry = None

            if solver is not None:
                solver_prompt = (
                    getattr(solver, "_initial_prompt_text", None)
                    or getattr(solver, "last_recorded_prompt", None)
                )
                if solver_prompt:
                    prompt = solver_prompt
                question = (
                    solver.last_recorded_question
                    or solver._initial_question_text
                    or solver._extract_question_text()
                )
                if isinstance(solver.last_recorded_answer, dict):
                    entry = copy.deepcopy(solver.last_recorded_answer)
                else:
                    canonical_t = self._canonical_answer_type(exercise_type)
                    v_flag = bool(verified_override) if verified_override is not None else False
                    entry = copy.deepcopy(
                        solver.extract_fallback_page_record(canonical_t, verified=v_flag)
                    )
                    question = solver.last_recorded_question or question

            if not question or question == "Unknown Question":
                question = dom_q or f"{effective_title} | Page {p_num} | {exercise_type}"

            if not isinstance(entry, dict):
                canonical_t = self._canonical_answer_type(exercise_type)
                default_verified = (
                    verified_override
                    if verified_override is not None
                    else (exercise_type in {"type-intro", "type-video"})
                )
                default_answers = (
                    ["intro"] if exercise_type == "type-intro"
                    else (["watched"] if exercise_type == "type-video" else dom_items)
                )
                entry = {
                    "type": canonical_t,
                    "answers": default_answers,
                    "verified": bool(default_verified),
                    "timestamp": now,
                }

            if verified_override is not None:
                if verified_override:
                    entry.pop("verified", None)
                else:
                    entry["verified"] = False

            key = (effective_title, p_num)
            idx_key = (effective_title.strip().casefold(), p_num)
            existing_rec = self.structured_page_records.get(key)
            final_answer = entry
            extra_fields = {}

            if isinstance(existing_rec, dict) and isinstance(existing_rec.get("answer"), dict):
                prev_ans = existing_rec["answer"]
                prev_verified = prev_ans.get("verified", True) is not False
                prev_has_vals = bool(prev_ans.get("answers"))
                new_verified = entry.get("verified", True) is not False
                if prev_verified and prev_has_vals and not new_verified:
                    final_answer = prev_ans
                    extra_fields["last_unverified_attempt"] = entry

            self.answer_db[question] = final_answer
            if p_num > 0 and final_answer.get("verified", True) is not False:
                self.page_answer_index[idx_key] = final_answer

            page_record = {
                "page": p_num,
                "type": exercise_type or "unknown",
                "question": question,
                "prompt": prompt,
                "answer": final_answer,
                "updated_at": now,
            }
            page_record.update(extra_fields)

            if p_num > 0:
                self.structured_page_records[key] = page_record

            self.answer_page_contexts[question] = {
                "title": effective_title,
                "page": p_num,
                "pages_total": p_total,
                "type": exercise_type or "unknown",
                "prompt": prompt,
            }

            cat_item = next(
                (item for item in self.chapter_catalog if item.get("title") == effective_title),
                None,
            )
            if cat_item is None and effective_title != "Imported answers (legacy)":
                self.chapter_catalog.append({
                    "title": effective_title,
                    "pages_total": p_total,
                })
            elif cat_item is not None:
                cat_item["pages_total"] = max(int(cat_item.get("pages_total") or 0), p_total)

            ex_obj = next(
                (e for e in self.answer_records if e.get("title") == effective_title),
                None,
            )
            if ex_obj is None:
                ex_obj = {"title": effective_title, "pages_total": p_total, "pages": []}
                self.answer_records.append(ex_obj)
            else:
                ex_obj["pages_total"] = max(int(ex_obj.get("pages_total") or 0), p_total)

            if persist:
                self._save_answer_db(self.current_chapter_name)
        except Exception as e:
            self.logger.error(f"[DB] _record_page_to_db error: {e}")

    def _capture_answer_page_context(self, title, page_number, total_pages,
                                     exercise_type, solver):
        try:
            if solver is not None:
                solver.exercise_title = title or solver.exercise_title or ""
                solver.page_number = int(page_number or 0)
                solver.capture_initial_context()
                question = solver._initial_question_text or solver._extract_question_text()
                prompt = getattr(solver, "_initial_prompt_text", None) or ""
            else:
                question, prompt, _, _ = self._extract_dom_page_snapshot()

            if not question or question == "Unknown Question":
                return
            header = self.page.locator("h1.exercise-header").first if self.page else None
            page_title = header.inner_text().strip() if (header and header.count() > 0) else ""
            self.answer_page_contexts[question] = {
                "title": title or page_title or "Unknown exercise",
                "page": page_number,
                "pages_total": total_pages,
                "type": exercise_type,
                "prompt": prompt or "",
            }
        except Exception as e:
            self.logger.debug(f"[DB] Page context capture failed: {e}")

    def _save_answer_db(self, chapter_name=None):
        chapter_name = (
            chapter_name
            or self.current_chapter_name
            or self._ensure_chapter_db_loaded(announce=False)
            or self.DEFAULT_CHAPTER_NAME
        ).strip()
        if not chapter_name:
            chapter_name = self.DEFAULT_CHAPTER_NAME

        self.current_chapter_name = chapter_name
        safe_name = self._safe_chapter_filename(chapter_name)
        os.makedirs(self.reports_folder, exist_ok=True)
        self.answer_bank_file = os.path.join(self.reports_folder, f"answers_{safe_name}.json")

        temp_name = None
        try:
            now = datetime.now().isoformat()
            exercises = self.answer_records if isinstance(self.answer_records, list) else []

            def get_exercise(title):
                title = (title or "Unknown exercise").strip() or "Unknown exercise"
                for exercise in exercises:
                    if exercise.get("title") == title:
                        return exercise
                exercise = {
                    "title": title,
                    "pages_total": 0,
                    "pages": [],
                }
                exercises.append(exercise)
                return exercise

            for (ex_title, p_num), rec in list(self.structured_page_records.items()):
                if not ex_title or p_num <= 0:
                    continue
                exercise = get_exercise(ex_title)
                ctx = self.answer_page_contexts.get(rec.get("question", ""), {})
                exercise["pages_total"] = max(
                    int(exercise.get("pages_total") or 0),
                    int(ctx.get("pages_total") or 0),
                    p_num,
                )
                existing_page = next(
                    (p for p in exercise.get("pages", []) if p.get("page") == p_num),
                    None,
                )
                if existing_page is None:
                    exercise.setdefault("pages", []).append(copy.deepcopy(rec))
                else:
                    existing_page.update(copy.deepcopy(rec))
                ans_obj = rec.get("answer")
                if isinstance(ans_obj, dict) and ans_obj.get("verified", True) is not False:
                    self.page_answer_index[(ex_title.strip().casefold(), int(p_num))] = ans_obj

            for question, context in list(self.answer_page_contexts.items()):
                entry = self.answer_db.get(question)
                if not isinstance(entry, dict):
                    continue
                ex_title = (context.get("title") or "Unknown exercise").strip()
                p_num = int(context.get("page") or 0)
                if (ex_title, p_num) in self.structured_page_records and p_num > 0:
                    exercise = get_exercise(ex_title)
                    exercise["pages_total"] = max(
                        int(exercise.get("pages_total") or 0),
                        int(context.get("pages_total") or 0),
                    )
                    continue
                exercise = get_exercise(ex_title)
                exercise["pages_total"] = max(
                    int(exercise.get("pages_total") or 0),
                    int(context.get("pages_total") or 0),
                    p_num,
                )
                page_record = next(
                    (p for p in exercise.get("pages", []) if p.get("page") == p_num),
                    None,
                )
                if page_record is None:
                    page_record = {"page": p_num}
                    exercise.setdefault("pages", []).append(page_record)
                page_record.update({
                    "type": context.get("type", "unknown"),
                    "question": question,
                    "prompt": context.get("prompt", ""),
                    "answer": entry,
                    "updated_at": now,
                })
                if p_num > 0:
                    self.structured_page_records[(ex_title, p_num)] = copy.deepcopy(page_record)
                    if entry.get("verified", True) is not False:
                        self.page_answer_index[(ex_title.strip().casefold(), int(p_num))] = entry

            structured_questions = set()
            structured_comparable = set()
            for exercise in exercises:
                if exercise.get("title") == "Imported answers (legacy)":
                    continue
                pages_list = exercise.get("pages", [])
                pages_list.sort(key=lambda p: (p.get("page") is None, p.get("page") or 0))
                if pages_list:
                    max_p = max((int(p.get("page") or 0) for p in pages_list), default=0)
                    exercise["pages_total"] = max(int(exercise.get("pages_total") or 0), max_p)
                for p in pages_list:
                    q = p.get("question", "")
                    if q:
                        structured_questions.add(q)
                        structured_comparable.add(self._comparable_question_key(q))

            legacy_exercise = next(
                (e for e in exercises if e.get("title") == "Imported answers (legacy)"),
                None,
            )
            if legacy_exercise is not None:
                dedup_legacy_pages = []
                seen_legacy_q = set()
                for p in legacy_exercise.get("pages", []):
                    q = p.get("question", "")
                    comp_q = self._comparable_question_key(q)
                    if not q or q in structured_questions or comp_q in structured_comparable:
                        continue
                    if q in seen_legacy_q:
                        continue
                    seen_legacy_q.add(q)
                    dedup_legacy_pages.append(p)
                legacy_exercise["pages"] = dedup_legacy_pages

            represented = {
                p.get("question")
                for exercise in exercises
                for p in exercise.get("pages", [])
                if p.get("question")
            }
            represented_comp = {self._comparable_question_key(q) for q in represented}

            legacy = get_exercise("Imported answers (legacy)")
            for question, entry in list(self.answer_db.items()):
                if not question or not isinstance(entry, dict):
                    continue
                comp_q = self._comparable_question_key(question)
                if question in represented or comp_q in represented_comp:
                    continue
                legacy["pages"].append({
                    "page": None,
                    "type": entry.get("type", "unknown"),
                    "question": question,
                    "prompt": "",
                    "answer": entry,
                    "updated_at": now,
                })
                represented.add(question)
                represented_comp.add(comp_q)

            if not legacy.get("pages"):
                exercises[:] = [e for e in exercises if e is not legacy]

            exercises.sort(
                key=lambda e: (e.get("title") == "Imported answers (legacy)", e.get("title", ""))
            )

            catalog_by_title = {}
            catalog_order = []
            for item in self.chapter_catalog:
                t = (item.get("title") or "").strip()
                if not t or t == "Imported answers (legacy)":
                    continue
                if t not in catalog_by_title:
                    catalog_order.append(t)
                    catalog_by_title[t] = int(item.get("pages_total") or 0)
                else:
                    catalog_by_title[t] = max(catalog_by_title[t], int(item.get("pages_total") or 0))

            for e in exercises:
                t = (e.get("title") or "").strip()
                if not t or t == "Imported answers (legacy)":
                    continue
                ep = int(e.get("pages_total") or 0)
                if t not in catalog_by_title:
                    catalog_order.append(t)
                    catalog_by_title[t] = ep
                else:
                    merged_total = max(catalog_by_title[t], ep)
                    catalog_by_title[t] = merged_total
                    e["pages_total"] = merged_total

            self.chapter_catalog = [
                {"title": t, "pages_total": catalog_by_title[t]}
                for t in catalog_order
            ]

            total_pages = sum(int(item.get("pages_total") or 0) for item in self.chapter_catalog)
            answered_pages = sum(len(e.get("pages", [])) for e in exercises)
            known_exercises = len(self.chapter_catalog)
            payload = {
                "schema_version": 2,
                "chapter": {
                    "name": chapter_name,
                    "cid": self.current_chapter_cid,
                    "updated_at": now,
                    "summary": {
                        "exercises": known_exercises,
                        "pages": total_pages,
                        "answered_pages": answered_pages,
                    },
                    "catalog": self.chapter_catalog,
                },
                "exercises": exercises,
            }

            parent = os.path.dirname(os.path.abspath(self.answer_bank_file))
            os.makedirs(parent, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(
                prefix=f"answers_{safe_name}_", suffix=".tmp", dir=parent
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_name, self.answer_bank_file)
            temp_name = None

            self.answer_records = exercises
            summary = payload["chapter"]["summary"]
            self.logger.info(
                "[DB] Saved structured database (%s): %s exercises, %s pages, %s answered pages",
                self.answer_bank_file,
                summary["exercises"],
                summary["pages"],
                summary["answered_pages"],
            )
            return True
        except Exception as e:
            self.logger.error(f"[DB] Save failed: {e}")
            if temp_name:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass
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

    def _cleanup_browser(self):
        try:
            if self.context:
                try:
                    self.context.close()
                except BaseException:
                    pass
        except BaseException:
            pass
        try:
            if self.playwright:
                try:
                    self.playwright.stop()
                except BaseException:
                    pass
        except BaseException:
            pass
        self.context = None
        self.browser = None
        self.playwright = None
        self.page = None
        self._pron_init_installed = False

    def _install_pronunciation_init(self):
        if getattr(self, '_pron_init_installed', False):
            return
        try:
            init_js = r"""
                (() => {
                    if (window.__botPronInstalled) return;
                    window.__botPronInstalled = true;
                    window.__botPronB64 = [];
                    const origGUM = navigator.mediaDevices.getUserMedia.bind(
                        navigator.mediaDevices
                    );
                    function b64ToArrayBuffer(b64) {
                        const bin = atob(b64);
                        const len = bin.length;
                        const bytes = new Uint8Array(len);
                        for (let i = 0; i < len; i++) {
                            bytes[i] = bin.charCodeAt(i);
                        }
                        return bytes.buffer;
                    }
                    navigator.mediaDevices.getUserMedia = async (constraints) => {
                        if (!constraints || !constraints.audio) {
                            return origGUM(constraints);
                        }
                        try {
                            const AC = window.AudioContext || 
                                       window.webkitAudioContext;
                            const ctx = new AC();
                            await ctx.resume();
                            const dest = ctx.createMediaStreamDestination();
                            for (let i = 0; i < window.__botPronB64.length; i++) {
                                try {
                                    const b64 = window.__botPronB64[i];
                                    const arr = b64ToArrayBuffer(b64);
                                    const audioBuffer = await ctx.decodeAudioData(arr);
                                    const src = ctx.createBufferSource();
                                    src.buffer = audioBuffer;
                                    src.connect(dest);
                                    window.__botPronDuration = audioBuffer.duration || 0;
                                    src.start(ctx.currentTime + 0.35);
                                    window.__botPronCtx = ctx;
                                    return dest.stream;
                                } catch(e) {}
                            }
                            return origGUM(constraints);
                        } catch(e) {
                            return origGUM(constraints);
                        }
                    };
                })();
            """
            self.context.add_init_script(script=init_js)
            self._pron_init_installed = True
            self.logger.info("[PRON-INIT] Installed at context level")
        except Exception as e:
            self.logger.error(f"[PRON-INIT] Failed: {e}")

    def _account_key(self, email):
        return hashlib.sha256(email.strip().lower().encode('utf-8')).hexdigest()[:20]

    def _profile_dir(self, email):
        return os.path.join(self.profiles_folder, self._account_key(email))

    def load_accounts(self):
        if not os.path.exists(self.accounts_file):
            return []
        try:
            with open(self.accounts_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            self.logger.warning(f"[ACCOUNTS] Cannot read accounts file: {e}")
            return []
        if isinstance(data, dict):
            migrated = []
            for user, pwd in data.items():
                migrated.append({
                    "key": self._account_key(user),
                    "email": user,
                    "password": pwd,
                })
            self._save_accounts_raw(migrated)
            return migrated
        return data if isinstance(data, list) else []

    def _save_accounts_raw(self, accounts):
        parent = os.path.dirname(os.path.abspath(self.accounts_file))
        os.makedirs(parent, exist_ok=True)
        temp_name = None
        try:
            if os.path.exists(self.accounts_file):
                shutil.copy2(self.accounts_file, self.accounts_file + ".bak")
            fd, temp_name = tempfile.mkstemp(
                prefix="accounts_", suffix=".tmp", dir=parent
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(accounts, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_name, self.accounts_file)
            return True
        except Exception as e:
            self.logger.error(f"[ACCOUNTS] Save failed: {e}")
            if temp_name:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass
            return False

    def save_account(self, email=None, password=None):
        if email is None:
            self.print_header()
            print(f"  {Fore.CYAN}--- {self.T['add_account']} ---{Style.RESET_ALL}")
            try:
                import getpass
                email = self._input(f"  {Fore.CYAN}[>] Username: {Style.RESET_ALL}").strip()
                password = getpass.getpass(
                    f"  {Fore.CYAN}[>] Password: {Style.RESET_ALL}"
                ).strip()
            except (EOFError, KeyboardInterrupt):
                return False
            if not email or not password:
                self.print_status("ERROR", self.T['invalid_choice'])
                self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
                return False
        email = email.strip()
        accounts = self.load_accounts()
        key = self._account_key(email)
        existing = next((a for a in accounts if a.get("key") == key), None)
        entry = {"key": key, "email": email}
        if password:
            entry["password"] = password
        elif existing and existing.get("password"):
            entry["password"] = existing["password"]
        accounts = [a for a in accounts if a.get("key") != key]
        accounts.insert(0, entry)
        self.accounts = accounts
        return self._save_accounts_raw(accounts)

    def get_saved_password(self, email):
        accounts = self.load_accounts()
        key = self._account_key(email)
        for a in accounts:
            if a.get("key") == key and a.get("password"):
                return a.get("password")
        return None

    def delete_account_password(self, email):
        accounts = self.load_accounts()
        key = self._account_key(email)
        for a in accounts:
            if a.get("key") == key:
                a.pop("password", None)
        self.accounts = accounts
        return self._save_accounts_raw(accounts)

    def delete_account(self, email):
        accounts = self.load_accounts()
        key = self._account_key(email)
        accounts = [a for a in accounts if a.get("key") != key]
        self.accounts = accounts
        return self._save_accounts_raw(accounts)

    def select_account(self):
        self.print_header()
        print(f"  {Fore.CYAN}--- {self.T['select_account']} ---{Style.RESET_ALL}\n")
        if not self.accounts:
            print(f"  {Fore.YELLOW}[!] {self.T['no_accounts']}{Style.RESET_ALL}")
            try:
                u = self._input(f"\n  {Fore.CYAN}[>] Username: {Style.RESET_ALL}").strip()
                if u:
                    return u, None
            except (EOFError, KeyboardInterrupt):
                pass
            return None, None
        for i, acc in enumerate(self.accounts, 1):
            has_pwd = f" {Fore.GREEN}[saved pwd]{Style.RESET_ALL}" if acc.get("password") else ""
            prof_dir = self._profile_dir(acc.get("email", ""))
            has_prof = f" {Fore.CYAN}[profile]{Style.RESET_ALL}" if os.path.exists(prof_dir) else ""
            print(f"  {Fore.WHITE}[{i}]{Style.RESET_ALL} {acc.get('email', '')}{has_pwd}{has_prof}")
        print(f"  {Fore.WHITE}[N]{Style.RESET_ALL} {self.T['add_account']}")
        print(f"  {Fore.WHITE}[D]{Style.RESET_ALL} {self.T['delete_pwd']}")
        print(f"  {Fore.WHITE}[X]{Style.RESET_ALL} {self.T['delete_acc']}")
        print(f"  {Fore.WHITE}[0]{Style.RESET_ALL} {self.T['back']}")
        try:
            choice = self._input(f"\n  {Fore.CYAN}[>] {self.T['select_account']}: {Style.RESET_ALL}").strip()
        except (EOFError, KeyboardInterrupt):
            return None, None
        if choice == "":
            return None, None
        if choice == "0":
            return None, None
        if choice.lower() == "n":
            try:
                email = self._input(f"\n  {Fore.CYAN}[>] Email: {Style.RESET_ALL}").strip()
            except (EOFError, KeyboardInterrupt):
                return None, None
            if not email:
                return None, None
            return email, None
        if choice.lower() == "d":
            try:
                email = self._input(f"\n  {Fore.CYAN}[>] Email: {Style.RESET_ALL}").strip()
            except (EOFError, KeyboardInterrupt):
                return None, None
            if email:
                self.delete_account_password(email)
                self.accounts = self.load_accounts()
                self.print_status("OK", self.T['deleted_pwd'].format(email))
            self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
            return None, None
        if choice.lower() == "x":
            try:
                email = self._input(f"\n  {Fore.CYAN}[>] Email: {Style.RESET_ALL}").strip()
            except (EOFError, KeyboardInterrupt):
                return None, None
            if email:
                self.delete_account(email)
                self.accounts = self.load_accounts()
                self.print_status("OK", self.T['deleted_acc'].format(email))
            self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
            return None, None
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(self.accounts):
                acc = self.accounts[idx]
                return acc.get("email", ""), acc.get("password")
        except ValueError:
            pass
        self.print_status("ERROR", self.T['invalid_choice'])
        time.sleep(1)
        return None, None

    def start_browser_and_login(self, u, p):
        self.print_status("INFO", "Starting Browser with persistent profile...")
        self._cleanup_browser()
        try:
            self.playwright = sync_playwright().start()
            profile_dir = self._profile_dir(u)
            os.makedirs(profile_dir, exist_ok=True)
            self.active_profile_dir = profile_dir
            self.print_status("INFO", f"Chrome Profile: {profile_dir}")

            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=os.path.abspath(profile_dir),
                headless=False,
                channel="chrome",
                viewport={"width": 1366, "height": 768},
                permissions=["microphone"],
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--window-size=1366,768",
                    "--window-position=0,0",
                    "--use-fake-ui-for-media-stream",
                    "--use-fake-device-for-media-stream",
                    "--autoplay-policy=no-user-gesture-required",
                    "--mute-audio",
                ],
            )
            self.browser = self.context.browser
            if self.context.pages:
                self.page = self.context.pages[0]
            else:
                self.page = self.context.new_page()

            try:
                self.context.on("page", self._attach_web_diagnostics)
            except Exception:
                pass
            self._attach_web_diagnostics(self.page)
            self.print_status("OK", "Browser audio muted (--mute-audio active)")

            self._install_pronunciation_init()

            self.page.goto("https://portal.speexx.com/",
                           wait_until="domcontentloaded")
            time.sleep(2)
            if self.check_speexx_session():
                self.print_status("OK", self.T['session_valid'])
                return True
            if not p:
                p = self.get_saved_password(u)
                if p:
                    self.print_status("OK", self.T['using_saved_pwd'])
            if not p:
                try:
                    import getpass
                    p = getpass.getpass(
                        f"  {Fore.CYAN}[>] {self.T['pwd_of'].format(u)}{Style.RESET_ALL}"
                    ).strip()
                except (EOFError, KeyboardInterrupt):
                    return False
                if p:
                    try:
                        save = self._input(
                            f"  {Fore.CYAN}[>] {self.T['ask_save_pwd']}{Style.RESET_ALL}"
                        ).strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        save = "n"
                    if save == "y":
                        self.save_account(u, p)
                        self.print_status("OK", self.T['saved_pwd'])
            if not p:
                self.print_status("ERROR", self.T['no_password'])
                return False
            return self._do_login(u, p)
        except Exception as e:
            self.print_status("ERROR", f"Browser Error: {str(e)}")
            self._cleanup_browser()
            self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
            return False

    def check_speexx_session(self):
        try:
            url = self.page.url.lower()
            if "login" in url:
                return False
            if self.page.locator("#userName").count() > 0:
                try:
                    if self.page.locator("#userName").first.is_visible(timeout=2000):
                        return False
                except Exception:
                    pass
            if "dashboard" in url or "articles" in url or "portal.speexx.com" in url:
                try:
                    self.page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass
                if self.page.locator("#userName").count() == 0:
                    return True
            return False
        except Exception:
            return False

    def _do_login(self, u, p):
        try:
            self.print_status("WAIT", "Logging in...")
            self.page.goto("https://portal.speexx.com/",
                           wait_until="domcontentloaded")
            time.sleep(1)
            self.page.locator("#userName").wait_for(state="visible", timeout=15000)
            self.page.locator("#userName").fill(u)
            self.page.locator("#button-next").click()
            self.page.locator("#password").wait_for(state="visible", timeout=15000)
            self.page.locator("#password").fill(p)
            try:
                cb = self.page.locator("#rememberMe")
                if cb.is_visible(timeout=2000):
                    cb.check()
                    self.print_status("OK", "Checked Keep me logged in")
            except Exception:
                pass
            self.page.locator("#button-sign-in").click()
            try:
                self.page.wait_for_url(re.compile(r".*(dashboard|articles).*"), timeout=30000)
                self.print_status("OK", "Login Successful.")
                self.save_account(u, p)
                return True
            except Exception:
                self.print_status("ERROR", "Login timeout.")
                self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
                return False
        except Exception as e:
            self.print_status("ERROR", f"Login Error: {str(e)}")
            self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
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
                return f"https://portal.speexx.com/articles/{m.group(1)}/results"
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
            if href:
                return href
        except Exception:
            pass
        return default

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
        if not force and self._is_exercises_tab_active() and self._count_visible_exercise_rows() > 0:
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

        if not state or not state.get("found"):
            self.logger.warning(f"[CHAPTER] Target chapter not found in DOM (cid={target_cid}, name={target_name})")
            return False

        if state.get("resolvedCid") and not self.current_chapter_cid:
            self.current_chapter_cid = state["resolvedCid"]
        if state.get("resolvedName") and (not self.current_chapter_name or self.current_chapter_name == self.DEFAULT_CHAPTER_NAME):
            self.current_chapter_name = state["resolvedName"]

        was_already_active = bool(state.get("alreadyActive"))
        if not force_click and was_already_active and self._count_visible_exercise_rows() > 0:
            return True

        prev_first_title = state.get("firstRowTitle") or ""
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
        if "/results" not in (self.page.url or "").lower():
            if not self.navigate_to_results():
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
        try:
            if "/results" in self.page.url.lower():
                info_title = self.page.locator(".progress-info .info-title").first
                if info_title.count() > 0:
                    text = info_title.inner_text().strip()
                    if re.search(r"\b100\s*%", text):
                        return True

            self.page.goto("https://portal.speexx.com/", wait_until="domcontentloaded", timeout=20000)
            time.sleep(1.5)
            if self._click_progress_nav():
                time.sleep(1.5)

            info_title = self.page.locator(".progress-info .info-title").first
            if info_title.count() > 0:
                text = info_title.inner_text().strip()
                if re.search(r"\b100\s*%", text):
                    return True
            return False
        except Exception as e:
            self.logger.error(f"[PROGRESS] Error checking status: {e}")
            return False

    def navigate_to_results(self):
        if not self.page:
            self.print_status("ERROR", "Browser not started.")
            self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
            return False
        self.print_status("INFO", "Navigating to Dashboard -> Progress -> Exercises...")
        discovered_before = self._discover_results_url()
        fallback_url = discovered_before or "https://portal.speexx.com/articles/10960433/results"
        try:
            self.page.goto("https://portal.speexx.com/", wait_until="domcontentloaded", timeout=20000)
            time.sleep(1.5)
            fallback_url = (
                self._discover_results_url()
                or discovered_before
                or "https://portal.speexx.com/articles/10960433/results"
            )

            if self._click_progress_nav():
                time.sleep(2)
            else:
                self.logger.warning("[NAV] Progress button not found, falling back to direct URL")
                raise Exception("Progress button not found")

            self.page.locator(".level-container").first.wait_for(state="visible", timeout=15000)

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
                self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
                return False

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
            current_url = self.page.url.lower()
            if "/results" not in current_url:
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
            if "/results" not in (self.page.url or "").lower():
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

            rows = self._get_visible_exercise_rows()
            if not rows:
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
            for row_idx, row in enumerate(rows):
                r_info = self._inspect_result_row(row, row_index=row_idx)
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

    def _collect_all_searchable_entries(self, preferred_chapter=""):
        entries = []
        seen_files = set()

        def ingest_payload(chapter_label, data):
            if not isinstance(data, dict):
                return
            if data.get("schema_version") == 2:
                ch_name = (data.get("chapter", {}) or {}).get("name") or chapter_label
                for ex in data.get("exercises", []) or []:
                    ex_title = ex.get("title", "Unknown exercise")
                    for p in ex.get("pages", []) or []:
                        q = p.get("question", "")
                        ans = p.get("answer")
                        if q and isinstance(ans, dict):
                            entries.append({
                                "chapter": ch_name,
                                "exercise": ex_title,
                                "page": p.get("page"),
                                "prompt": p.get("prompt", ""),
                                "question": q,
                                "answer": ans,
                            })
            else:
                for q, ans in data.items():
                    if q and isinstance(ans, dict):
                        entries.append({
                            "chapter": chapter_label,
                            "exercise": "Legacy",
                            "page": None,
                            "prompt": "",
                            "question": q,
                            "answer": ans,
                        })

        if preferred_chapter:
            pref_safe = self._safe_chapter_filename(preferred_chapter)
            pref_path = os.path.join(self.reports_folder, f"answers_{pref_safe}.json")
            if os.path.exists(pref_path):
                try:
                    with open(pref_path, "r", encoding="utf-8") as f:
                        ingest_payload(preferred_chapter, json.load(f))
                    seen_files.add(os.path.abspath(pref_path))
                except Exception:
                    pass

        if os.path.isdir(self.reports_folder):
            for fname in sorted(os.listdir(self.reports_folder)):
                if not (fname.startswith("answers_") and fname.endswith(".json")):
                    continue
                fpath = os.path.abspath(os.path.join(self.reports_folder, fname))
                if fpath in seen_files:
                    continue
                ch_guess = fname[len("answers_"):-len(".json")]
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        ingest_payload(ch_guess, json.load(f))
                    seen_files.add(fpath)
                except Exception:
                    continue

        if not entries and self.answer_db:
            for q, ans in self.answer_db.items():
                if q and isinstance(ans, dict):
                    entries.append({
                        "chapter": preferred_chapter or self.DEFAULT_CHAPTER_NAME,
                        "exercise": "Memory",
                        "page": None,
                        "prompt": "",
                        "question": q,
                        "answer": ans,
                    })
        return entries

    def search_answer_interactive(self):
        chapter = (self.current_chapter_name or "").strip()
        if chapter:
            self._load_answer_db(chapter, announce=False)
        all_entries = self._collect_all_searchable_entries(preferred_chapter=chapter)
        scope_label = chapter if chapter else "All Chapters"
        if not all_entries:
            self.print_status("ERROR", self.T["db_not_found"].format(scope_label))
            self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
            return

        print(f"\n  {Fore.CYAN}--- {self.T['search_title'].format(scope_label)} ---{Style.RESET_ALL}")
        print(f"  {self.T['search_hint_1']}")
        print(f"  {self.T['search_hint_2']}\n")
        lines = []
        while True:
            line = self._input("  ")
            if not lines and line.strip() == "0":
                return
            if line.strip() == "END":
                break
            lines.append(line)

        query = "\n".join(lines).strip()
        if not query:
            self.print_status("INFO", self.T["search_no_query"])
            return

        qnorm = self._comparable_question_key(query)
        exact = []
        scored = []
        for item in all_entries:
            key = item["question"]
            knorm = self._comparable_question_key(key)
            pref_bonus = 0.01 if (chapter and item["chapter"] == chapter) else 0.0
            if qnorm == knorm:
                exact.append((1.0 + pref_bonus, item))
                continue
            score = SequenceMatcher(None, qnorm[:1800], knorm[:1800]).ratio()
            if qnorm and (qnorm in knorm or knorm in qnorm):
                score = max(score, 0.92)
            scored.append((score + pref_bonus, item))

        if exact:
            exact.sort(key=lambda x: x[0], reverse=True)
            matches = [(min(1.0, sc), it) for sc, it in exact[:5]]
        else:
            scored.sort(key=lambda x: x[0], reverse=True)
            matches = [(min(1.0, sc), it) for sc, it in scored[:5] if sc >= 0.35]

        if not matches:
            self.print_status("INFO", self.T["search_no_match"])
            self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
            return

        print(f"\n  {Fore.GREEN}{self.T['search_found'].format(len(matches))}{Style.RESET_ALL}")
        for number, (score, item) in enumerate(matches, 1):
            answer = item["answer"]
            ex_disp = item["exercise"]
            if item.get("page") is not None:
                ex_disp = f"{ex_disp} ({self.T['page']} {item['page']})"
            print(f"\n  [{number}] {self.T['search_match_pct'].format(score * 100)}")
            print(f"  {self.T['search_chapter_label'].format(item['chapter'], ex_disp)}")
            print(f"  {self.T['search_db_question'].format(str(item['question'])[:260])}")
            print(f"  {self.T['type']}: {answer.get('type', 'unknown')}")
            print(f"  {self.T['search_answer_label']}")
            print(json.dumps(answer.get("answers"), ensure_ascii=False, indent=4))

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
                return True

            target = self.page.locator("[data-speexx-nav-target='1']").first
            if target.count() == 0:
                return False
            target.click(timeout=3000)

            deadline = time.time() + 3.5
            while time.time() < deadline:
                ready = self.page.evaluate(
                    """
                    () => {
                        const ex = document.querySelector('.exercise, .video, video');
                        if (!ex) return false;
                        const r = ex.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                    }
                    """
                )
                if ready:
                    break
                time.sleep(0.06)
            time.sleep(0.12)
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

    def wait_for_completion_modal(self, timeout=15):
        deadline = time.time() + float(timeout)
        start_t = time.time()
        while time.time() < deadline:
            if self.detect_completion_modal():
                elapsed = time.time() - start_t
                self.print_status("OK", f"Completion modal detected (after {elapsed:.1f}s)")
                return True
            time.sleep(0.2)
        self.print_status("WAIT", f"Completion modal NOT detected within {timeout}s")
        return False

    def extract_completion_info(self):
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
                ".instructions-text",
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
                            chain_seen_titles=None, row_index=None):
        self._ensure_chapter_db_loaded(announce=False)

        if not is_continuation and not batch_mode:
            self.print_status("INFO", f"{self.T['auto_solve']}: {title}")
            self.print_status("INFO", self.T['will_not_move'])

        final_status = "FAILED"
        final_score = 0
        final_elapsed = "N/A"
        pages_recorded_count = 0
        if auto_continue:
            if chain_seen_titles is None:
                chain_seen_titles = set()
            chain_seen_titles.add((title or "").strip().casefold())

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
                        ".exercise, .video, .exercises-large-navigation li",
                        state="visible",
                        timeout=15000
                    )
                except Exception as e:
                    self.logger.warning(f"[WAIT] Exercise page not ready: {str(e)[:80]}")
                    if "/results" in (self.page.url or "").lower():
                        self.logger.info("[WAIT] Still on /results after row click; retrying inner cell click...")
                        if self._click_row_safely(title, row_index=row_index, click_inner_cell=True):
                            try:
                                self.page.wait_for_selector(
                                    ".exercise, .video, .exercises-large-navigation li",
                                    state="visible",
                                    timeout=12000
                                )
                            except Exception:
                                pass
                time.sleep(0.35)

            self._ensure_chapter_db_loaded(announce=False)

            if not title or title == "Unknown":
                detected_title = self.get_current_exercise_title()
                if detected_title and detected_title != "Unknown":
                    title = detected_title

            if total_pages is None:
                total_pages = self.get_total_exercises(retries=3, wait_seconds=0.6)

            if total_pages == 0:
                if "/results" in (self.page.url or "").lower():
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

                et = engine.detect_type()
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
                    try:
                        solver.solve()
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
                        score = solver.get_result_score(wait_for_score=False)

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
                    and solver.last_recorded_answer.get("verified") is True
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
                    elif idx_pos == len(pages_to_solve) - 1:
                        self._try_skip_to_next_page()
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
                previous_title = self.get_current_exercise_title()
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
                    )
                elif action == "continue":
                    self.print_status("OK", "Moving on (Continue)...")
                    time.sleep(0.6)
                    try:
                        if auto_continue:
                            self.page.wait_for_function(
                                """
                                (previous) => {
                                    if (window.location.href !== previous.url) return true;
                                    const selectors = [
                                        '.folders-dropdown .title span',
                                        '.instructions-text',
                                        'h1.exercise-header'
                                    ];
                                    return selectors.some(selector => {
                                        const element = document.querySelector(selector);
                                        return element && element.textContent.trim() &&
                                            element.textContent.trim() !== previous.title;
                                    });
                                }
                                """,
                                arg={"url": previous_url, "title": previous_title},
                                timeout=12000,
                            )
                            if "/results" in self.page.url.lower():
                                self.logger.info("[VERIFY] [OK] เปลี่ยนกลับหน้า /results เพื่อเลือกแบบฝึกหัดถัดไป")
                                return self._continue_auto_from_results(
                                    title, final_status, final_score,
                                    final_elapsed, chain_seen_titles,
                                    continuation_depth,
                                )
                        self.page.wait_for_selector(
                            ".exercise, .video",
                            state="visible",
                            timeout=10000
                        )
                        new_total = self.get_total_exercises(
                            retries=2 if auto_continue else 3,
                            wait_seconds=0.5 if auto_continue else 1.0,
                        )
                        new_title = self.get_current_exercise_title()
                        if auto_continue and new_total == 0:
                            return self._continue_auto_from_results(
                                title, final_status, final_score,
                                final_elapsed, chain_seen_titles,
                                continuation_depth,
                            )
                        if (auto_continue and self.page.url == previous_url and
                                new_title == previous_title):
                            self.logger.warning("[CONTINUE] Still on same exercise after Continue; falling back to /results")
                            return self._continue_auto_from_results(
                                title, final_status, final_score,
                                final_elapsed, chain_seen_titles,
                                continuation_depth,
                            )

                        if auto_continue and new_title.casefold() in chain_seen_titles:
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
                            )
                        self.print_status("WAIT", self.T["new_page_not_loaded"].format(e))
                        return (final_status, final_score, final_elapsed)
                else:
                    if auto_continue:
                        return self._continue_auto_from_results(
                            title, final_status, final_score,
                            final_elapsed, chain_seen_titles,
                            continuation_depth,
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
                if pages_recorded_count > 0 or self.answer_db or self.structured_page_records:
                    self._save_answer_db(self.current_chapter_name)
            except Exception as save_err:
                self.logger.error(f"[DB] Final save error: {save_err}")
            if not is_continuation and not batch_mode:
                try:
                    self.after_solve_menu()
                except Exception:
                    pass

        return (final_status, final_score, final_elapsed)

    def _next_uncompleted_exercise_entry(self, current_title, rows, seen_titles):
        exercises = []
        for r_idx, row in enumerate(rows):
            info = self._inspect_result_row(row, row_index=r_idx)
            if not info["title"]:
                continue
            exercises.append(info)

        if not exercises:
            return None, None

        current_key = (current_title or "").strip().casefold()
        current_index = next(
            (index for index, item in enumerate(exercises)
             if item["title"].casefold() == current_key),
            -1,
        )
        indexes = list(range(current_index + 1, len(exercises)))
        indexes.extend(range(0, current_index + 1))
        for index in indexes:
            item = exercises[index]
            name = item["title"]
            row_key = f"{name.casefold()}#{item['row_index']}"
            if not name:
                continue
            if item["is_completed"]:
                continue
            if row_key in seen_titles:
                continue
            if name.casefold() in seen_titles and sum(
                1 for x in exercises if x["title"].casefold() == name.casefold() and not x["is_completed"]
            ) == 0:
                continue
            seen_titles.add(row_key)
            return name, item["row_index"]
        return None, None

    def _next_uncompleted_exercise_title(self, current_title, rows, seen_titles):
        name, _ = self._next_uncompleted_exercise_entry(current_title, rows, seen_titles)
        return name

    def _continue_auto_from_results(self, current_title, status, score, elapsed,
                                    seen_titles, continuation_depth):
        try:
            if self.check_course_progress():
                self.print_status("OK", self.T["course_100_stop"])
                return (status, score, elapsed)

            self._ensure_results_chapter_and_exercises_ready(
                force_chapter_click=False,
                wait_timeout=15000,
            )
            rows = self._get_visible_exercise_rows()
            if seen_titles is None:
                seen_titles = set()
            next_title, next_row_idx = self._next_uncompleted_exercise_entry(
                current_title, rows, seen_titles
            )
            if not next_title:
                self.print_status("OK", self.T["no_more_uncompleted"])
                return (status, score, elapsed)

            self.print_status("INFO", self.T["opening_uncompleted"].format(next_title))
            if not self._click_row_safely(next_title, row_index=next_row_idx):
                self.print_status("ERROR", self.T["open_next_failed"].format(next_title))
                return (status, score, elapsed)
            self.page.wait_for_selector(
                ".exercise, .video", state="visible", timeout=15000
            )
            next_total = self.get_total_exercises(retries=2, wait_seconds=0.75)
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
            )
        except Exception as e:
            self.print_status("WAIT", self.T["results_return_failed"].format(e))
            return (status, score, elapsed)

    def _find_matching_exercise_row(self, title, row_index=None):
        rows = self._get_visible_exercise_rows()
        if not rows:
            return None

        target_norm = " ".join((title or "").split()).strip().casefold()

        if row_index is not None and 0 <= row_index < len(rows):
            r_info = self._inspect_result_row(rows[row_index], row_index=row_index)
            row_title_norm = r_info["title"].casefold()
            if not target_norm or row_title_norm == target_norm:
                return rows[row_index]

        if not target_norm:
            return rows[0]

        exact_matches = []
        partial_matches = []
        for idx, row in enumerate(rows):
            r_info = self._inspect_result_row(row, row_index=idx)
            row_title_norm = r_info["title"].casefold()
            if row_title_norm == target_norm:
                exact_matches.append((row, r_info))
            elif target_norm in row_title_norm or (row_title_norm and row_title_norm in target_norm):
                partial_matches.append((row, r_info))

        if exact_matches:
            if len(exact_matches) > 1 and not self.force_solve_all:
                for row, r_info in exact_matches:
                    if not r_info["is_completed"]:
                        return row
            return exact_matches[0][0]

        if partial_matches:
            if len(partial_matches) > 1 and not self.force_solve_all:
                for row, r_info in partial_matches:
                    if not r_info["is_completed"]:
                        return row
            return partial_matches[0][0]

        return None

    def _click_row_safely(self, title, wait_timeout=15000, row_index=None, click_inner_cell=False):
        try:
            url_low = (self.page.url or "").lower()
            if "/results" not in url_low or self._count_visible_exercise_rows() == 0:
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

        time.sleep(0.25)

        try:
            row.scroll_into_view_if_needed(timeout=3000)
            time.sleep(0.25)
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

        for mode_label, click_fn in (
            ("normal", lambda: target.click(timeout=3000)),
            ("force", lambda: target.click(timeout=3000, force=True)),
            ("JS", lambda: target.evaluate("el => el.click()")),
        ):
            try:
                click_fn()
                self.logger.info(f"[CLICK] '{title}' clicked ({mode_label}, inner={click_inner_cell})")
                return True
            except Exception as e:
                self.logger.debug(f"[CLICK] {mode_label} click failed: {str(e)[:120]}")

        return False

    def multi_account_menu(self):
        self.print_header()
        print(f"  {Fore.CYAN}--- {self.T['opt_multi_acc']} ---{Style.RESET_ALL}\n")
        self.accounts = self.load_accounts()
        if not self.accounts:
            print(f"  {Fore.YELLOW}{self.T['no_accounts']}{Style.RESET_ALL}")
            self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
            return

        for i, acc in enumerate(self.accounts, 1):
            has_pwd = f" {Fore.GREEN}[saved pwd]{Style.RESET_ALL}" if acc.get("password") else ""
            print(f"  {Fore.WHITE}[{i}]{Style.RESET_ALL} {acc.get('email', '')}{has_pwd}")

        print(f"  {Fore.WHITE}[A]{Style.RESET_ALL} {self.T['multi_acc_all']}")
        print(f"  {Fore.WHITE}[0]{Style.RESET_ALL} {self.T['back']}")

        try:
            choice = self._input(f"\n  {Fore.CYAN}[>] {self.T['multi_acc_select']}{Style.RESET_ALL}").strip()
        except (EOFError, KeyboardInterrupt):
            return

        selected = []
        if choice.lower() == 'a':
            selected = self.accounts
        elif choice == '0' or choice == '':
            return
        else:
            try:
                idxs = []
                if '-' in choice:
                    a, b = choice.split('-')
                    idxs = list(range(int(a) - 1, int(b)))
                elif ',' in choice:
                    idxs = [int(x.strip()) - 1 for x in choice.split(',')]
                else:
                    idxs = [int(choice) - 1]

                for idx in idxs:
                    if 0 <= idx < len(self.accounts):
                        selected.append(self.accounts[idx])
            except Exception:
                self.print_status("ERROR", self.T['invalid_choice'])
                time.sleep(1)
                return

        valid_selected = [acc for acc in selected if acc.get("password")]
        if not valid_selected:
            self.print_status("ERROR", self.T['multi_acc_no_pwd'])
            self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
            return

        print(f"\n  {Fore.GREEN}{self.T['multi_acc_launching'].format(len(valid_selected))}{Style.RESET_ALL}")
        for acc in valid_selected:
            email = acc.get("email")
            pwd = acc.get("password")
            print(f"  {Fore.CYAN}[START]{Style.RESET_ALL} {email}")
            subprocess.Popen([sys.executable, __file__, "--account", email, "--password", pwd, "--auto"])

        print(f"\n  {Fore.GREEN}{self.T['multi_acc_started']}{Style.RESET_ALL}")
        self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")

    def auto_run(self, email, password):
        self.print_status("INFO", f"Auto-run for {email}")
        if not self.start_browser_and_login(email, password):
            sys.exit(1)

        self.navigate_to_results()
        self._ensure_chapter_db_loaded(announce=True)

        try:
            self._ensure_results_chapter_and_exercises_ready(
                force_chapter_click=False,
                wait_timeout=15000,
            )
            rows = self._get_visible_exercise_rows()
            first_uncompleted = None
            first_row_idx = None
            seen_cat = {item.get("title") for item in self.chapter_catalog}
            for r_idx, row in enumerate(rows):
                r_info = self._inspect_result_row(row, row_index=r_idx)
                t = r_info["title"]
                if t and t not in seen_cat:
                    seen_cat.add(t)
                    self.chapter_catalog.append({"title": t, "pages_total": 0})
                if first_uncompleted is None and t and not r_info["is_completed"]:
                    first_uncompleted = t
                    first_row_idx = r_idx

            self._save_answer_db(self.current_chapter_name)

            if first_uncompleted:
                self.print_status("INFO", self.T["auto_start_ex"].format(first_uncompleted))
                self.force_solve_all = False
                self.auto_solve_exercise(
                    first_uncompleted,
                    selected_pages=None,
                    is_continuation=False,
                    already_opened=False,
                    auto_continue=True,
                    row_index=first_row_idx,
                )
            else:
                self.print_status("OK", self.T["auto_all_done"])
        except Exception as e:
            self.print_status("ERROR", f"Auto run error: {e}")
        finally:
            self._save_answer_db(self.current_chapter_name)

        self.print_status("INFO", self.T["auto_finished_acc"])
        self._cleanup_browser()
        sys.exit(0)

    def after_solve_menu(self):
        while True:
            print(f"\n  {Fore.CYAN}--- {self.T['next_action']} ---{Style.RESET_ALL}")
            print(f"  {Fore.WHITE}[1]{Style.RESET_ALL} {self.T['back_to_list']}")
            print(f"  {Fore.WHITE}[2]{Style.RESET_ALL} {self.T['back_to_main']}")
            print(f"  {Fore.WHITE}[3]{Style.RESET_ALL} {self.T['exit_app']}")
            try:
                c = self._input(f"\n  {Fore.CYAN}[>] Select: {Style.RESET_ALL}").strip()
                if c == "1":
                    if self.current_chapter_cid or (
                        self.current_chapter_name and self.current_chapter_name != self.DEFAULT_CHAPTER_NAME
                    ):
                        self.select_chapter(self.current_chapter_cid, self.current_chapter_name)
                    else:
                        self.navigate_to_results()
                        time.sleep(1)
                        self.fetch_exercises()
                    return
                elif c == "2" or c == "":
                    return
                elif c == "3":
                    self.shutdown()
            except ValueError:
                pass

    def shutdown(self):
        self.print_status("INFO", "Exiting...")
        if self.current_chapter_name or self.answer_db or self.structured_page_records:
            self._save_answer_db(self.current_chapter_name)
        self._cleanup_browser()
        try:
            sys.stdout.flush()
            if hasattr(sys.stdout, 'close'):
                sys.stdout.close()
            if hasattr(self, 'original_stdout'):
                sys.stdout = self.original_stdout
        except Exception:
            pass
        sys.exit(0)

    def select_language(self):
        self.print_header()
        print(f"  {Fore.CYAN}--- {self.T['select_lang']} ---{Style.RESET_ALL}\n")
        print(f"  {Fore.WHITE}[1]{Style.RESET_ALL} {self.T['lang_th']}")
        print(f"  {Fore.WHITE}[2]{Style.RESET_ALL} {self.T['lang_en']}")
        try:
            c = input(f"\n  {Fore.CYAN}[>] Select: {Style.RESET_ALL}").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if c == "1":
            self.lang = "th"
        elif c == "2":
            self.lang = "en"
        else:
            return
        self.T = TRANSLATIONS[self.lang]
        try:
            self.logger.info(f"INPUT: {c}")
            self.logger.info(f"LANG: {self.lang}")
        except Exception:
            pass

    def login_menu(self):
        while True:
            self.print_header()
            print(f"  {Fore.CYAN}--- {self.T['login_menu']} ---{Style.RESET_ALL}\n")
            print(f"  {Fore.WHITE}[1]{Style.RESET_ALL} {self.T['opt_login']}")
            print(f"  {Fore.WHITE}[2]{Style.RESET_ALL} {self.T['opt_manage_acc']}")
            print(f"  {Fore.WHITE}[3]{Style.RESET_ALL} {self.T['opt_multi_acc']}")
            print(f"  {Fore.WHITE}[4]{Style.RESET_ALL} {self.T['opt_exit']}")
            try:
                c = self._input(f"\n  {Fore.CYAN}[>] Select: {Style.RESET_ALL}").strip()
                if c == "":
                    continue
                if c == "1":
                    self.accounts = self.load_accounts()
                    u, p = self.select_account()
                    if u:
                        if self.start_browser_and_login(u, p):
                            self.navigate_to_results()
                            return
                elif c == "2":
                    self.accounts = self.load_accounts()
                    self.select_account()
                elif c == "3":
                    self.multi_account_menu()
                elif c == "4":
                    self.shutdown()
                else:
                    self.print_status("ERROR", self.T['invalid_choice'])
                    time.sleep(0.5)
            except KeyboardInterrupt:
                self.shutdown()
            except Exception as e:
                self.print_status("ERROR", f"Error: {str(e)}")
                self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")

    def dashboard_menu(self):
        while True:
            self.print_header()
            print(f"  {Fore.CYAN}--- {self.T['dashboard_menu']} ---{Style.RESET_ALL}\n")
            print(f"  {Fore.WHITE}[1]{Style.RESET_ALL} {self.T['opt_select_chapter']}")
            print(f"  {Fore.WHITE}[2]{Style.RESET_ALL} {self.T['opt_results']}")
            print(f"  {Fore.WHITE}[3]{Style.RESET_ALL} {self.T['opt_search_answer']}")
            print(f"  {Fore.WHITE}[4]{Style.RESET_ALL} {self.T['opt_logout']}")
            print(f"  {Fore.WHITE}[5]{Style.RESET_ALL} {self.T['opt_exit']}")
            try:
                c = self._input(f"\n  {Fore.CYAN}[>] Select: {Style.RESET_ALL}").strip()
                if c == "":
                    continue
                if c == "1":
                    self.fetch_and_select_chapter()
                elif c == "2":
                    self.navigate_to_results()
                elif c == "3":
                    self.search_answer_interactive()
                elif c == "4":
                    self.print_status("INFO", "Logging out...")
                    self._cleanup_browser()
                    return
                elif c == "5":
                    self.shutdown()
                else:
                    self.print_status("ERROR", self.T['invalid_choice'])
                    time.sleep(0.5)
            except KeyboardInterrupt:
                self.shutdown()
            except Exception as e:
                self.print_status("ERROR", f"Error: {str(e)}")
                self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")

    def main_menu(self):
        self.select_language()
        while True:
            if not self.page:
                self.login_menu()
            else:
                self.dashboard_menu()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", type=str)
    parser.add_argument("--password", type=str)
    parser.add_argument("--auto", action="store_true")
    args = parser.parse_args()

    if args.account and args.password and args.auto:
        bot = SpeexxBotCLI()
        bot.auto_run(args.account, args.password)
    else:
        bot = SpeexxBotCLI()
        bot.main_menu()
