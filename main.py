import os
import sys
import time
import json
import logging
import re
import random
import threading
import hashlib
import base64
import shutil
import tempfile
import requests
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

TRANSLATIONS = {
    "th": {
        "select_lang": "เลือกภาษา / Select Language",
        "lang_th": "ภาษาไทย",
        "lang_en": "English",

        "login_menu": "เมนูเข้าสู่ระบบ",
        "opt_login": "เริ่มต้นเบราว์เซอร์และเข้าสู่ระบบ",
        "opt_manage_acc": "จัดการบัญชี",
        "opt_exit": "ออกจากโปรแกรม",

        "select_account": "เลือกบัญชี",
        "add_account": "เพิ่มบัญชีใหม่",
        "delete_pwd": "ลบรหัสผ่านที่บันทึกไว้",
        "delete_acc": "ลบบัญชี",
        "no_accounts": "ยังไม่มีบัญชีที่บันทึกไว้",
        "saved_pwd": "บันทึกรหัสผ่านแล้ว",
        "deleted_pwd": "ลบรหัสผ่านของ {} แล้ว",
        "deleted_acc": "ลบบัญชี {} แล้ว",

        "dashboard_menu": "เมนูหลัก (Dashboard)",
        "opt_select_chapter": "เลือกบทเรียนและดูแบบฝึกหัด",
        "opt_results": "ไปที่หน้า Results",
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
        "opt_view": "เปิดดูเฉยๆ (Just view)",
        "opt_dump": "Dump ทุกหน้า",
        "opt_auto_solve": "ทำแบบฝึกหัดอัตโนมัติ (Auto Solve)",
        "opt_new_learning_path": "ทำแบบฝึกหัดใหม่ต่อเนื่อง (เริ่มรายการแรกและ Continue อัตโนมัติ)",
        "select_pages": "เลือกข้อที่ต้องการทำ (เช่น 1, 1-5, all): ",

        "auto_solve": "เริ่มทำแบบฝึกหัดอัตโนมัติ",
        "will_not_move": "จะไม่ไปข้อถัดไปจนกว่าจะได้คะแนน >= 65",
        "found_pages": "พบทั้งหมด {} หน้า",
        "page": "หน้า",
        "type": "ประเภท",
        "success": "สำเร็จ",
        "failed": "ล้มเหลว",
        "skipped": "ข้าม",
        "retrying": "กำลังลองใหม่ ครั้งที่ {}/{}...",
        "max_retries": "ลองใหม่ครบกำหนดแล้ว",

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
        "opt_exit": "Exit Program",

        "select_account": "Select Account",
        "add_account": "Add New Account",
        "delete_pwd": "Delete Saved Password",
        "delete_acc": "Delete Account",
        "no_accounts": "No accounts saved yet",
        "saved_pwd": "Password saved",
        "deleted_pwd": "Deleted password for {}",
        "deleted_acc": "Deleted account {}",

        "dashboard_menu": "Dashboard Menu",
        "opt_select_chapter": "Select Chapter & View Exercises",
        "opt_results": "Go to Results Page",
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
        "opt_view": "Open (Just view)",
        "opt_dump": "Dump All Pages",
        "opt_auto_solve": "Auto Solve (Keep trying until 65)",
        "opt_new_learning_path": "New learning path (start at first selected and auto-Continue)",
        "select_pages": "Select pages (e.g. 1, 1-5, all): ",

        "auto_solve": "Auto Solve",
        "will_not_move": "Will NOT move to next page until current page gets >= 65.",
        "found_pages": "Found {} pages.",
        "page": "Page",
        "type": "Type",
        "success": "SUCCESS",
        "failed": "FAILED",
        "skipped": "SKIPPED",
        "retrying": "Retrying Page ({}/{})...",
        "max_retries": "Max retries reached.",

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

        "back": "Back",
        "invalid_choice": "Invalid choice",
        "press_enter": "Press Enter to continue...",
        "cancel": "Cancel",
    }
}

# =========================================================================
# Exercise types which are intentionally skipped by the batch runner.
# Drag/drop is supported by DragDropSolver and must not be listed here.
UNSUPPORTED_TYPES = set()

# =========================================================================
# BaseSolver — คลาสแม่ของ Solver ทุกตัว
# =========================================================================
# =========================================================================
# BaseSolver — คลาสแม่ของ Solver ทุกตัว
# =========================================================================
class BaseSolver:
    PASS_LINE = 65

    def __init__(self, page, logger):
        self.page = page
        self.logger = logger
        self.start_time = None
        self.end_time = None

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

    # ---------------------------------------------------------------------
    # ⭐ NEW: robust click with overlay handling
    # ---------------------------------------------------------------------
    def _safe_click(self, locator, timeout=5000, description=""):
        """คลิกแบบมี fallback 4 ระดับ: normal → remove overlay → force → JS"""
        try:
            if locator.count() == 0:
                return False
            if not locator.is_visible(timeout=2000):
                return False
        except Exception:
            return False

        # 1) normal click
        try:
            locator.click(timeout=timeout)
            return True
        except Exception as e:
            self.logger.debug(f"[SAFE_CLICK] normal fail ({description}): {str(e)[:100]}")

        # 2) remove blocking overlays (.no-editable / opaque boxes)
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

        # 3) force click
        try:
            locator.click(timeout=timeout, force=True)
            return True
        except Exception as e:
            self.logger.debug(f"[SAFE_CLICK] force fail ({description}): {str(e)[:100]}")

        # 4) JS click
        try:
            locator.evaluate("el => el.click()")
            return True
        except Exception as e:
            self.logger.debug(f"[SAFE_CLICK] JS fail ({description}): {str(e)[:100]}")

        return False

    # ---------------------------------------------------------------------
    # ⭐ NEW: check if exercise already passed — ใช้โดยทุก solver
    # ---------------------------------------------------------------------
    def already_passed(self):
        # ⭐ ถ้า force_solve → ถือว่ายังไม่ผ่าน เพื่อให้ทำซ้ำ
        if getattr(self, 'force_solve', False):
            return False
        try:
            score = self.get_result_score()
            return score >= self.PASS_LINE
        except Exception:
            return False

    # ---------------------------------------------------------------------
    # Click helpers — ใช้ _safe_click
    # ---------------------------------------------------------------------
    def click_correction(self):
        try:
            btn = self.page.locator("button.action-exercise-button.correct").first
            if btn.count() > 0 and btn.is_visible(timeout=3000):
                if self._safe_click(btn, timeout=5000, description="correction"):
                    self.step("Clicked [Correction]")
                    time.sleep(1.5)
                    return True
        except Exception as e:
            self.logger.error(f"Failed Correction: {str(e)}")
        return False

    def click_next(self):
        try:
            btn = self.page.locator("button.action-exercise-button.next").first
            if btn.count() > 0 and btn.is_visible(timeout=3000):
                if self._safe_click(btn, timeout=5000, description="next"):
                    self.step("Clicked [Next]")
                    time.sleep(1)
                    return True
        except Exception as e:
            self.logger.error(f"Failed Next: {str(e)}")
        return False

    def click_solution(self):
        try:
            btn = self.page.locator("button.solution").first
            if btn.count() > 0 and btn.is_visible(timeout=3000):
                if self._safe_click(btn, timeout=5000, description="solution"):
                    self.step("Clicked [Solution]")
                    time.sleep(1.5)
                    return True
        except Exception as e:
            self.logger.error(f"Failed Solution: {str(e)}")
        return False

    def click_repeat(self):
        try:
            for sel in ["button.action-exercise-button.repeat",
                        "button.text-button-custom.repeat",
                        "button.repeat"]:
                try:
                    btn = self.page.locator(sel).first
                    if btn.count() > 0 and btn.is_visible(timeout=2000):
                        if self._safe_click(btn, timeout=5000, description="repeat"):
                            self.step("Clicked [Repeat]")
                            time.sleep(1.5)
                            return True
                except Exception:
                    continue
        except Exception as e:
            self.logger.error(f"Failed Repeat: {str(e)}")
        return False

    def click_start(self):
        try:
            btn = self.page.locator("button.start-exercise").first
            if btn.count() > 0 and btn.is_visible(timeout=3000):
                if self._safe_click(btn, timeout=5000, description="start"):
                    self.step("Clicked [Start]")
                    time.sleep(1)
                    return True
        except Exception as e:
            self.logger.error(f"Failed Start: {str(e)}")
        return False

    def has_start_button(self):
        try:
            btn = self.page.locator("button.start-exercise").first
            return btn.count() > 0 and btn.is_visible(timeout=2000)
        except Exception:
            return False

    def get_result_score(self):
        """พยายามดึงคะแนนจากหลายๆ จุดใน DOM"""
        try:
            self.page.wait_for_timeout(800)

            badge = self.page.locator(".result-badge-text").first
            if badge.count() > 0:
                score = badge.get_attribute("data-result")
                if score is not None:
                    try:
                        return int(score)
                    except (ValueError, TypeError):
                        pass

            body_text = self.page.locator("body").inner_text(timeout=2000)
            if any(t in body_text for t in ["Very good!", "Excellent",
                                            "Well done", "Perfect",
                                            "ดีมาก", "ยอดเยี่ยม", "ยอดมาก"]):
                return 100
            if any(t in body_text for t in ["Try again", "ลองอีกครั้ง",
                                            "You can do better"]):
                return 0

            bars = self.page.locator(".score-bar, .result-bar, [class*='bar-']").all()
            if bars:
                green_count = 0
                for bar in bars:
                    cls = (bar.get_attribute("class") or "").lower()
                    if "green" in cls or "success" in cls:
                        green_count += 1
                if green_count == len(bars):
                    return 100
                elif green_count > 0:
                    return int((green_count / len(bars)) * 100)

            greens = self.page.locator(
                ".icon-acepted-checkmark.status-green, "
                "[class*='success'], [class*='correct']"
            ).all()
            if greens:
                return 100

            return 0
        except Exception:
            return 0

    def wait_for_page_ready(self):
        try:
            self.page.wait_for_selector(".exercise, .video", state="visible", timeout=10000)
            time.sleep(0.5)
            return True
        except Exception:
            return False

    def precise_drag(self, source, target):
        for attempt in range(2):
            try:
                try:
                    source.scroll_into_view_if_needed(timeout=2000)
                except Exception:
                    pass
                try:
                    target.scroll_into_view_if_needed(timeout=2000)
                except Exception:
                    pass
                time.sleep(0.15)
                source_box = source.bounding_box()
                target_box = target.bounding_box()
                if not source_box or not target_box:
                    return False
                sx = source_box['x'] + source_box['width'] / 2
                sy = source_box['y'] + source_box['height'] / 2
                tx = target_box['x'] + target_box['width'] / 2
                ty = target_box['y'] + target_box['height'] / 2
                self.page.mouse.move(sx, sy)
                time.sleep(0.15)
                self.page.mouse.down()
                time.sleep(0.15)
                self.page.mouse.move(sx + 5, sy + 5)
                time.sleep(0.1)
                self.page.mouse.move(sx + 10, sy + 10)
                time.sleep(0.1)
                steps = 20
                for step_i in range(1, steps + 1):
                    x = sx + (tx - sx) * step_i / steps
                    y = sy + (ty - sy) * step_i / steps
                    self.page.mouse.move(x, y)
                    time.sleep(0.02)
                self.page.mouse.move(tx, ty)
                time.sleep(0.4)
                self.page.mouse.move(tx + 1, ty)
                time.sleep(0.15)
                self.page.mouse.move(tx, ty)
                time.sleep(0.15)
                self.page.mouse.up()
                time.sleep(0.4)
                return True
            except Exception as e:
                self.logger.error(f"Drag error (attempt {attempt+1}): {str(e)}")
                try:
                    self.page.mouse.up()
                except Exception:
                    pass
                time.sleep(0.3)
        return False


# =========================================================================
# DragDropSolver
# =========================================================================
class DragDropSolver(BaseSolver):
    """Solver for Speexx drag/drop exercises.

    รองรับ 2 รูปแบบ:
    1. มีปุ่ม Solution → อ่าน correct mapping จาก slots
    2. ไม่มีปุ่ม Solution แต่ tile มี `data-group-id` → ใช้ group-id
       จัดเรียง tile เข้าคอลัมน์ที่ถูกต้องโดยตรง
    """

    MAX_ITERATIONS = 3

    @staticmethod
    def _normalise(text):
        return " ".join((text or "").split())

    def _slot_answers(self):
        tiles = self.page.locator(".exercise-items .drag-drop").all()
        if not tiles:
            tiles = self.page.locator(
                ".exercise-items [data-drag-drop-id]"
            ).all()
        return [tile.inner_text().strip() for tile in tiles]

    def _source_tiles(self):
        return self.page.locator(".draggable-container .drag-drop").all()

    def _tile_text(self, tile):
        try:
            return tile.inner_text().strip()
        except Exception:
            return ""

    # ---------------------------------------------------------------------
    # ⭐ NEW: fallback — ใช้ data-group-id จัดวาง tile ตรงคอลัมน์
    # ---------------------------------------------------------------------
    def _restore_by_group_id(self):
        """Place tiles using data-group-id when no Solution button exists."""
        tiles = self._source_tiles()
        if not tiles:
            return []

        # ตรวจว่าทุก tile มี data-group-id
        groups = {}
        for tile in tiles:
            gid = tile.get_attribute("data-group-id")
            if not gid:
                return []  # ไม่สามารถใช้วิธีนี้ได้
            text = self._tile_text(tile)
            groups.setdefault(gid, []).append(text)

        if not groups:
            return []

        # หาจำนวนคอลัมน์จาก placeholder row
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

        # map group-id → column index (1-based → 0-based)
        columns = {}
        for gid, texts in groups.items():
            try:
                col_idx = int(gid) - 1
            except (ValueError, TypeError):
                return []
            if 0 <= col_idx < column_count:
                columns[col_idx] = list(texts)

        # สร้าง answer list — เรียงตาม row, column
        answers = []
        for row in placeholder_rows:
            for col_idx in range(len(row)):
                col_tiles = columns.get(col_idx, [])
                if col_tiles:
                    answers.append(col_tiles.pop(0))
                else:
                    answers.append("")

        return answers

    def _restore_solution(self):
        """Read correct mapping (solution button หรือ group-id fallback)."""
        # Try with Solution button first
        self.click_correction()
        time.sleep(0.6)

        ok = False
        for _ in range(3):
            if self.click_solution():
                ok = True
                break
            time.sleep(0.6)

        if ok:
            self.page.wait_for_timeout(500)
            answers = self._slot_answers()
            self.click_repeat()
            self.page.wait_for_timeout(500)
            if answers and any(answers):
                return answers

        # Fallback: use data-group-id
        self.logger.info("[DND] No solution button, using data-group-id fallback")
        self.click_repeat()
        self.page.wait_for_timeout(500)
        return self._restore_by_group_id()

    def _fill_slots(self, answers):
        slots = self.page.locator(".exercise-items .drag-drop-placeholder").all()
        moved = 0

        for index, answer in enumerate(answers):
            if not answer or index >= len(slots):
                continue
            wanted = self._normalise(answer)
            source = None
            # Prefer exact casing so duplicate tiles like "Will" and "will"
            # stay assigned to the matching sentence position.
            for candidate in self._source_tiles():
                if self._normalise(self._tile_text(candidate)) == wanted:
                    source = candidate
                    break
            if source is None:
                for candidate in self._source_tiles():
                    if self._normalise(self._tile_text(candidate)).casefold() == wanted.casefold():
                        source = candidate
                        break
            if source is None:
                self.logger.warning(
                    "No draggable tile found for slot %s: %r", index, answer)
                continue
            if self.precise_drag(source, slots[index]):
                moved += 1
                self.page.wait_for_timeout(150)
        return moved

    def solve(self):
        self.logger.info("=== Drag & Drop Solver Started ===")
        self.start_timer()

        # ⭐ ถ้าผ่านอยู่แล้ว ข้าม
        if self.already_passed():
            self.logger.info("[DND] Already passed (score >= 65)")
            return True

        try:
            if not self.wait_for_page_ready():
                return False

            answers = self._restore_solution()
            if not answers or not any(answers):
                self.logger.error("Could not extract drag/drop solution mapping")
                return False
            self.step(f"Extracted {len([a for a in answers if a])} drag/drop answers")

            for attempt in range(self.MAX_ITERATIONS):
                moved = self._fill_slots(answers)
                self.step(f"Placed {moved} drag/drop tiles (attempt {attempt + 1})")
                self.click_correction()
                self.page.wait_for_timeout(800)
                if self.get_result_score() >= 100:
                    self.logger.info("Drag/drop completed in %s", self.stop_timer())
                    return True
                if attempt + 1 < self.MAX_ITERATIONS:
                    self.click_repeat()
                    self.page.wait_for_timeout(500)
            return self.get_result_score() >= 100
        except Exception as e:
            self.logger.error(f"Drag/drop error: {e}")
            return False

# =========================================================================
# VideoSolver
# =========================================================================
class VideoSolver(BaseSolver):
    def solve(self):
        self.logger.info("=== Video Solver Started ===")
        self.start_timer()
        try:
            result = self.page.evaluate("""
                () => {
                    const videos = document.querySelectorAll('video');
                    if (videos.length === 0) return 'no-video';
                    let acted = false;
                    videos.forEach(v => {
                        try {
                            v.muted = true;
                            v.playbackRate = 16;
                            if (v.duration && !isNaN(v.duration) && v.duration > 0) {
                                v.currentTime = Math.max(0, v.duration - 0.3);
                                acted = true;
                            }
                            v.play().catch(e => {});
                        } catch(e) {}
                    });
                    return acted ? 'seeked-and-played' : 'playing';
                }
            """)
            self.step(f"Video action: {result}")
            time.sleep(2)
            for i in range(40):
                try:
                    state = self.page.evaluate("""
                        () => {
                            const v = document.querySelector('video');
                            if (!v) return {ended: true, currentTime: 0, duration: 0};
                            return {
                                ended: v.ended || false,
                                currentTime: v.currentTime || 0,
                                duration: v.duration || 0,
                            };
                        }
                    """)
                    if state.get("ended", False):
                        break
                    if state.get("duration", 0) > 0 and state.get("currentTime", 0) >= state.get("duration", 0) - 0.5:
                        break
                except Exception:
                    pass
                time.sleep(0.5)
            time.sleep(2)
            for i in range(20):
                next_btn = self.page.locator("button.action-exercise-button.next").first
                if next_btn.count() > 0:
                    try:
                        if next_btn.is_enabled():
                            break
                    except Exception:
                        pass
                time.sleep(0.5)
            elapsed = self.stop_timer()
            self.logger.info(f"Video done. Time: {elapsed}")
            return True
        except Exception as e:
            self.logger.error(f"Video error: {str(e)}")
            return False

# =========================================================================
# AnswerSolver
# =========================================================================
class AnswerSolver(BaseSolver):
    MAX_ITERATIONS = 10

    def solve(self):
        self.logger.info("=== Answer Solver ===")
        self.start_timer()
        if not self.wait_for_page_ready():
            return False
        if self.has_start_button():
            self.click_start()
            time.sleep(1)
        self.click_correction()
        time.sleep(1)
        if not self.click_solution():
            return False
        time.sleep(1.5)
        correct_answers = self.extract_answers_from_solution()
        if not correct_answers or all(a == "" for a in correct_answers):
            return False
        self.step(f"Extracted {len(correct_answers)} answers: {correct_answers}")
        self.click_repeat()
        time.sleep(1.5)
        if self.has_start_button():
            self.click_start()
            time.sleep(1)
        for iteration in range(self.MAX_ITERATIONS):
            score = self.get_result_score()
            self.logger.info(f"--- Iteration {iteration+1}/{self.MAX_ITERATIONS} | Score: {score} ---")
            if score >= 65:
                return True
            if self.has_start_button():
                self.click_start()
                time.sleep(1)
            self.fill_blanks(correct_answers)
            time.sleep(1)
            self.click_correction()
            time.sleep(1)
        return self.get_result_score() >= 61

    def extract_answers_from_solution(self):
        answers = []
        try:
            for inp in self.page.locator("input.answer").all():
                answers.append(inp.input_value().strip())
        except Exception as e:
            self.logger.error(f"Extract error: {str(e)}")
        return answers

    def fill_blanks(self, answers):
        try:
            inputs = self.page.locator("input.answer").all()
            if len(inputs) == 0:
                return
            for i, ans in enumerate(answers):
                if i >= len(inputs) or not ans:
                    continue
                try:
                    inputs[i].fill(ans)
                    time.sleep(0.1)
                except Exception:
                    pass
        except Exception:
            pass

# =========================================================================
# ScrambledSentenceSolver
# =========================================================================
class ScrambledSentenceSolver(BaseSolver):
    MAX_ITERATIONS = 10

    def solve(self):
        self.logger.info("=== Scrambled Sentence Solver ===")
        self.start_timer()
        if not self.wait_for_page_ready():
            return False
        self.click_correction()
        time.sleep(1)
        target_sentences = None
        if self.click_solution():
            time.sleep(1.5)
            target_sentences = self.extract_solution_sentences()
        if not target_sentences:
            self.logger.warning("Failed to extract solution. Using heuristic fallback.")
            return self._solve_heuristic()
        self.click_repeat()
        time.sleep(1.5)
        for iteration in range(self.MAX_ITERATIONS):
            score = self.get_result_score()
            self.logger.info(f"--- Iteration {iteration+1}/{self.MAX_ITERATIONS} | Score: {score} ---")
            if score >= 65:
                return True
            self.apply_all_targets(target_sentences)
            time.sleep(1)
            self.click_correction()
            time.sleep(1)
        return self.get_result_score() >= 65

    def extract_solution_sentences(self):
        sentences = []
        try:
            items = self.page.locator(".exercise-items .item").all()
            for item in items:
                scrambled = item.locator(".scrambled-sentence").first
                if scrambled.count() == 0:
                    continue
                words = []
                for block in scrambled.locator(".scrambled-block").all():
                    text = block.inner_text().strip()
                    if text:
                        words.append(text)
                if words:
                    sentences.append(words)
        except Exception:
            pass
        return sentences

    def apply_all_targets(self, target_sentences):
        items = self.page.locator(".exercise-items .item").all()
        for idx, target in enumerate(target_sentences):
            if idx >= len(items):
                break
            item = items[idx]
            scrambled = item.locator(".scrambled-sentence").first
            if scrambled.count() == 0:
                continue
            self.apply_target(scrambled, target)

    def apply_target(self, scrambled_element, target):
        moved = False
        try:
            for iteration in range(len(target) * 3):
                blocks = scrambled_element.locator(".scrambled-block").all()
                current = [b.inner_text().strip() for b in blocks]
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
                drag_ok = False
                for drag_attempt in range(3):
                    before = [b.inner_text().strip()
                              for b in scrambled_element.locator(".scrambled-block").all()]
                    self.precise_drag(blocks[source_idx], blocks[mismatch])
                    time.sleep(0.4)
                    after = [b.inner_text().strip()
                             for b in scrambled_element.locator(".scrambled-block").all()]
                    if after != before:
                        drag_ok = True
                        break
                if drag_ok:
                    moved = True
                    time.sleep(0.2)
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
            if score >= 65:
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
        return self.get_result_score() >= 65

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
        return target

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

# =========================================================================
# ScrambledTableSolver
# =========================================================================
class ScrambledTableSolver(BaseSolver):
    MAX_ITERATIONS = 15

    def solve(self):
        self.logger.info("=== Scrambled Table Solver ===")
        self.start_timer()
        if not self.wait_for_page_ready():
            return False

        self.click_correction()
        time.sleep(1)
        if not self.click_solution():
            return False
        time.sleep(2)

        correct_map = self.extract_correct_mapping()
        if not correct_map or all(m.get("text") is None for m in correct_map):
            self.logger.warning("Failed to extract scrambled table mapping")
            return False
        self.step(f"Extracted {len(correct_map)} items")
        for entry in correct_map:
            self.logger.info(f"  item[{entry['idx']}] = {entry['text']}")

        self.click_repeat()
        time.sleep(2)

        for iteration in range(self.MAX_ITERATIONS):
            score = self.get_result_score()
            self.logger.info(f"--- Iteration {iteration+1}/{self.MAX_ITERATIONS} | Score: {score} ---")
            if score >= 65:
                elapsed = self.stop_timer()
                self.logger.info(f"SUCCESS! Time: {elapsed}")
                return True
            self.arrange_cells(correct_map)
            time.sleep(1)
            self.click_correction()
            time.sleep(1)
        return self.get_result_score() >= 65

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

    def arrange_cells(self, correct_map):
        moved = False
        try:
            items = self.page.locator(".exercise-items .item").all()
            for entry in correct_map:
                idx = entry["idx"]
                target_text = entry["text"]
                if not target_text or idx >= len(items):
                    continue
                target_item = items[idx]
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
                all_cells = self.page.locator(".scrambled-cell").all()
                source = None
                for cell in all_cells:
                    try:
                        if cell.inner_text().strip() == target_text:
                            source = cell
                            break
                    except Exception:
                        continue
                if source is None:
                    self.logger.warning(f"Cell '{target_text}' not found in DOM")
                    continue
                if self.precise_drag(source, target_slot):
                    moved = True
                    time.sleep(0.5)
        except Exception as e:
            self.logger.error(f"arrange_cells error: {e}")
        return moved

# =========================================================================
# SingleChoiceSolver
# =========================================================================
# =========================================================================
# SingleChoiceSolver
# =========================================================================
class SingleChoiceSolver(BaseSolver):
    MAX_ITERATIONS = 8

    def solve(self):
        self.logger.info("=== Single Choice Solver ===")
        self.start_timer()

        if not self.wait_for_page_ready():    # ← wait ก่อน
            return False

        if self.already_passed():             # ← แล้วค่อย check
            self.logger.info("[CHOICE] Already passed (score >= 65)")
            return True

        self.click_correction()
        time.sleep(1)

        # ลองใช้ Solution button ก่อน
        has_solution = self.click_solution()
        time.sleep(1.5)

        try:
            item_count = self.page.locator(".exercise-items .item.choice-item").count()
        except Exception:
            item_count = 0

        if item_count == 0:
            return self._solve_single_legacy()

        # ตรวจ single-group vs multi-item
        try:
            group_count = self.page.evaluate("""
                () => new Set(Array.from(document.querySelectorAll(
                    '.exercise-items .item.choice-item input.choice'
                )).map(input => input.name || input.getAttribute('data-group-id') || input.value)).size
            """)
        except Exception:
            group_count = item_count

        if item_count > 1 and group_count == 1:
            return self._solve_single_group_choice()

        # ⭐ ถ้า Solution ไม่มี → ใช้ fallback
        if not has_solution:
            self.logger.info("[CHOICE] No solution button — using fallback")
            return self._solve_without_solution(item_count)

        return self._solve_multi_item(item_count)

    # ---------------------------------------------------------------------
    # ⭐ NEW: fallback เมื่อไม่มี Solution button
    # ---------------------------------------------------------------------
    def _solve_without_solution(self, item_count):
        """Incremental: เริ่มจาก option 0 ทุกข้อ แล้ว flip ทีละข้อถ้าคะแนนดีขึ้น"""
        items = self.page.locator(".exercise-items .item.choice-item").all()
        if not items:
            return False

        # นับจำนวน options ต่อ item (stable)
        opts_counts = []
        for item in items:
            n = item.locator("input.choice").count()
            if n == 0:
                return False
            opts_counts.append(n)

        # Reset ก่อน
        self.click_repeat()
        time.sleep(1.2)

        # Set ทุกข้อเป็น option 0
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
            return True

        max_iter = item_count * 3
        iteration = 0
        improved = True

        while improved and iteration < max_iter and score < self.PASS_LINE:
            improved = False
            iteration += 1

            # ⭐ re-query items ทุก outer loop (กัน stale)
            items = self.page.locator(".exercise-items .item.choice-item").all()
            if len(items) < item_count:
                return score >= self.PASS_LINE

            for i in range(item_count):
                n_opts = opts_counts[i]
                if n_opts <= 1:
                    continue

                new_idx = (current[i] + 1) % n_opts

                # re-query opts ก่อนคลิก
                opts = items[i].locator("input.choice").all()
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
                        return True
                else:
                    # revert — re-query ก่อน
                    items = self.page.locator(
                        ".exercise-items .item.choice-item"
                    ).all()
                    if i < len(items):
                        opts = items[i].locator("input.choice").all()
                        if current[i] < len(opts):
                            try:
                                opts[current[i]].click(force=True, timeout=3000)
                                time.sleep(0.2)
                            except Exception:
                                pass

        return score >= self.PASS_LINE

    # ---------------------------------------------------------------------
    # Multi-item (มี Solution button)
    # ---------------------------------------------------------------------
    def _solve_multi_item(self, item_count):
        correct_per_item = None
        for wait in range(3):
            correct_per_item = self._find_correct_per_item_js()
            if correct_per_item and all(c is not None for c in correct_per_item):
                break
            time.sleep(0.3)
        if not correct_per_item or any(c is None for c in correct_per_item):
            correct_per_item = self._find_correct_per_item()
            if not correct_per_item or any(c is None for c in correct_per_item):
                return False

        normalised = []
        for choices in correct_per_item:
            if isinstance(choices, list):
                if len(choices) != 1 or not isinstance(choices[0], int):
                    # ถ้ามีหลาย correct options ในข้อเดียว ให้เลือกตัวแรก
                    if len(choices) >= 1 and isinstance(choices[0], int):
                        choices = choices[0]
                    else:
                        return False
                else:
                    choices = choices[0]
            if not isinstance(choices, int):
                return False
            normalised.append(choices)
        correct_per_item = normalised
        self.step(f"Detected correct per item: {correct_per_item}")

        if self.get_result_score() >= self.PASS_LINE:
            return True

        self.click_repeat()
        time.sleep(1)

        for iteration in range(self.MAX_ITERATIONS):
            score = self.get_result_score()
            self.logger.info(
                f"--- Iteration {iteration+1}/{self.MAX_ITERATIONS} | Score: {score} ---")
            if score >= self.PASS_LINE:
                return True
            items = self.page.locator(".exercise-items .item.choice-item").all()
            for item_idx, correct_idx in enumerate(correct_per_item):
                if correct_idx is None or item_idx >= len(items):
                    continue
                item = items[item_idx]
                opts = item.locator("input.choice").all()
                if correct_idx < len(opts):
                    try:
                        opts[correct_idx].click(force=True, timeout=3000)
                        time.sleep(0.15)
                    except Exception:
                        pass
            self.click_correction()
            time.sleep(1)
        return self.get_result_score() >= self.PASS_LINE

    def _solve_single_group_choice(self):
        """Solve a dialogue where several rendered rows share one radio group."""
        options = self.page.locator(
            '.exercise-items .item.choice-item input.choice').all()
        correct_index = None
        for index, option in enumerate(options):
            try:
                if option.is_checked(timeout=1000):
                    correct_index = index
                    break
            except Exception:
                continue
        if correct_index is None:
            self.logger.warning('[CHOICE] solution did not expose a selected option')
            return False
        self.step(f'Detected grouped correct option: {correct_index}')
        if self.get_result_score() >= self.PASS_LINE:
            return True
        self.click_repeat()
        time.sleep(1)
        for iteration in range(self.MAX_ITERATIONS):
            score = self.get_result_score()
            self.logger.info(
                f'--- Grouped iteration {iteration+1}/{self.MAX_ITERATIONS} | Score: {score} ---')
            if score >= self.PASS_LINE:
                return True
            current = self.page.locator(
                '.exercise-items .item.choice-item input.choice').all()
            if correct_index >= len(current):
                return False
            try:
                current[correct_index].click(force=True, timeout=3000)
            except Exception:
                return False
            self.click_correction()
            time.sleep(1)
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
        for wait in range(3):
            correct_idx = self.find_correct_option()
            if correct_idx is not None:
                break
            time.sleep(0.3)
        if correct_idx is None:
            return False
        if self.get_result_score() >= self.PASS_LINE:
            return True
        self.click_repeat()
        time.sleep(1)
        for iteration in range(self.MAX_ITERATIONS):
            score = self.get_result_score()
            if score >= self.PASS_LINE:
                return True
            options = self.page.locator(".choice-option").all()
            if correct_idx < len(options):
                inp = options[correct_idx].locator("input.choice").first
                if inp.count() > 0:
                    try:
                        inp.click(force=True, timeout=3000)
                        time.sleep(0.5)
                    except Exception:
                        pass
            self.click_correction()
            time.sleep(1)
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

# =========================================================================
# MultipleChoiceSolver
# =========================================================================
class MultipleChoiceSolver(BaseSolver):
    MAX_ITERATIONS = 8

    def solve(self):
        self.logger.info("=== Multiple Choice Solver ===")
        self.start_timer()
        if not self.wait_for_page_ready():
            return False
        self.click_correction()
        time.sleep(1)
        if not self.click_solution():
            return False
        time.sleep(2.5)
        try:
            item_count = self.page.locator(".exercise-items .item.choice-item").count()
        except Exception:
            item_count = 0
        if item_count == 0:
            return False
        correct_per_item = None
        for wait in range(3):
            correct_per_item = self._find_correct_per_item_js()
            if correct_per_item and any(len(c) > 0 for c in correct_per_item):
                break
            time.sleep(0.3)
        if not correct_per_item or all(len(c) == 0 for c in correct_per_item):
            return False
        if self.get_result_score() >= 65:
            return True
        self.click_repeat()
        time.sleep(1)
        for iteration in range(self.MAX_ITERATIONS):
            score = self.get_result_score()
            if score >= 65:
                return True
            items = self.page.locator(".exercise-items .item.choice-item").all()
            for item_idx, correct_indices in enumerate(correct_per_item):
                if not correct_indices or item_idx >= len(items):
                    continue
                item = items[item_idx]
                opts = item.locator("input.choice").all()
                for correct_idx in correct_indices:
                    if correct_idx < len(opts):
                        try:
                            opts[correct_idx].click(force=True, timeout=3000)
                            time.sleep(0.1)
                        except Exception:
                            pass
            self.click_correction()
            time.sleep(1)
        return self.get_result_score() >= 65

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

# =========================================================================
# PictureChoiceSolver
# =========================================================================
class PictureChoiceSolver(BaseSolver):
    MAX_ITERATIONS = 20

    def solve(self):
        self.logger.info("=== Picture Choice Solver ===")
        self.start_timer()
        if not self.wait_for_page_ready():
            return False
        self.click_correction()
        time.sleep(1)
        if not self.click_solution():
            return False
        time.sleep(1.5)
        mapping = self.extract_solution_mapping()
        if not mapping or all(not m.get("src") for m in mapping):
            return False
        self.click_repeat()
        time.sleep(1.5)
        for iteration in range(self.MAX_ITERATIONS):
            score = self.get_result_score()
            if score >= 65:
                return True
            self.perform_picture_drag(mapping)
            time.sleep(1)
            self.click_correction()
            time.sleep(1)
        return self.get_result_score() >= 65

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

    def perform_picture_drag(self, mapping):
        moved = False
        try:
            items = self.page.locator(".exercise-items .item").all()
            for entry in mapping:
                idx = entry["item_idx"]
                target_src = entry["src"]
                target_id = entry["drag_id"]
                if idx >= len(items) or not target_src:
                    continue
                item = items[idx]
                existing_img = item.locator("img").first
                if existing_img.count() > 0:
                    cur_src = existing_img.get_attribute("src") or ""
                    if cur_src == target_src:
                        continue
                source = None
                if target_id:
                    source = self.page.locator(f"img[data-drag-drop-id='{target_id}']").first
                    if source.count() == 0:
                        source = None
                if source is None and target_src:
                    source = self.page.locator(f"img[src='{target_src}']").first
                    if source.count() == 0:
                        source = None
                if source is None:
                    continue
                placeholder = item.locator(".drag-drop-placeholder").first
                target = placeholder if placeholder.count() > 0 else item
                if self.precise_drag(source, target):
                    moved = True
                    time.sleep(0.3)
        except Exception:
            pass
        return moved

# =========================================================================
# ToggleSolutionSolver
# =========================================================================
class ToggleSolutionSolver(BaseSolver):
    MAX_ITERATIONS = 15
    MAX_TOGGLE_CYCLES = 12

    def solve(self):
        self.logger.info("=== Toggle Solution Solver ===")
        self.start_timer()
        if not self.wait_for_page_ready():
            return False
        self.click_correction()
        time.sleep(1)
        if not self.click_solution():
            return False
        time.sleep(1.5)
        correct_answers = self.extract_correct_answers()
        if not correct_answers or all(a == "" for a in correct_answers):
            return False
        self.click_repeat()
        time.sleep(1.5)
        for iteration in range(self.MAX_ITERATIONS):
            score = self.get_result_score()
            if score >= 65:
                return True
            self.set_all_gaps(correct_answers)
            time.sleep(1)
            self.click_correction()
            time.sleep(1)
        return self.get_result_score() >= 65

    def _norm(self, s):
        return (s or "").replace("\xa0", " ").strip()

    def extract_correct_answers(self):
        answers = []
        try:
            gaps = self.page.locator(".exercise-items .gap").all()
            for g in gaps:
                answers.append(self._norm(g.inner_text()))
        except Exception:
            pass
        return answers

    def set_all_gaps(self, answers):
        try:
            gaps = self.page.locator(".exercise-items .gap").all()
            for i, ans in enumerate(answers):
                if i >= len(gaps) or not ans:
                    continue
                gap = gaps[i]
                try:
                    gap.scroll_into_view_if_needed()
                except Exception:
                    pass
                container = gap.locator("xpath=ancestor::div[contains(@class,'gap-container')]").first
                if container.count() == 0:
                    continue
                toggle = container.locator("button").first
                if toggle.count() == 0:
                    continue
                cur = self._norm(gap.inner_text())
                if cur == ans:
                    continue
                for cycle in range(self.MAX_TOGGLE_CYCLES):
                    try:
                        toggle.click(timeout=2000)
                        time.sleep(0.15)
                    except Exception:
                        break
                    cur = self._norm(gap.inner_text())
                    if cur == ans:
                        break
        except Exception:
            pass

# =========================================================================
# MarkTextSolver
# =========================================================================
class MarkTextSolver(BaseSolver):
    MAX_ITERATIONS = 10

    def solve(self):
        self.logger.info("=== Mark Text Solver ===")
        self.start_timer()
        if not self.wait_for_page_ready():
            return False
        self.click_correction()
        time.sleep(1)
        if not self.click_solution():
            return False
        time.sleep(2)
        group_positions, all_positions = self.extract_correct_positions()
        if not group_positions and not all_positions:
            return False
        self.step(f"Extracted {len(group_positions)} group positions: {group_positions}")
        self.step(f"Extracted {len(all_positions)} word positions: {all_positions}")
        self.click_repeat()
        time.sleep(1.5)
        for approach in ["group", "all"]:
            positions = group_positions if approach == "group" else all_positions
            if not positions:
                continue
            self.logger.info(f"--- Trying approach: {approach} ({len(positions)} clicks) ---")
            for iteration in range(self.MAX_ITERATIONS):
                score = self.get_result_score()
                self.logger.info(f"--- Iteration {iteration+1}/{self.MAX_ITERATIONS} | Score: {score} ---")
                if score >= 65:
                    elapsed = self.stop_timer()
                    self.logger.info(f"SUCCESS! Time: {elapsed}")
                    return True
                self.click_by_positions(positions)
                time.sleep(1)
                self.click_correction()
                time.sleep(1)
            if self.get_result_score() >= 65:
                return True
            self.click_repeat()
            time.sleep(1.5)
        return self.get_result_score() >= 65

    def extract_correct_positions(self):
        try:
            result = self.page.evaluate("""
                () => {
                    const allWords = document.querySelectorAll('.exercise-items .word');
                    const groupPositions = [];
                    const allPositions = [];
                    const seenMarkTexts = new Set();
                    allWords.forEach((w, i) => {
                        const mt = w.closest('.mark-text');
                        if (mt) {
                            allPositions.push(i);
                            if (!seenMarkTexts.has(mt)) {
                                seenMarkTexts.add(mt);
                                groupPositions.push(i);
                            }
                        }
                    });
                    return { groupPositions, allPositions };
                }
            """)
            group_positions = result.get("groupPositions", []) if result else []
            all_positions = result.get("allPositions", []) if result else []
            return group_positions, all_positions
        except Exception as e:
            self.logger.error(f"extract_correct_positions error: {e}")
            return [], []

    def click_by_positions(self, positions):
        try:
            self.page.evaluate("""
                () => {
                    const allWords = document.querySelectorAll('.exercise-items .word');
                    allWords.forEach(w => {
                        const cls = (w.className || '').toLowerCase();
                        if (cls.includes('selected') || cls.includes('marked') ||
                            cls.includes('highlight') || cls.includes('chosen') ||
                            cls.includes('active')) {
                            try { w.click(); } catch(e) {}
                        }
                    });
                }
            """)
            time.sleep(0.3)
            clicked = self.page.evaluate("""
                (positions) => {
                    const allWords = Array.from(
                        document.querySelectorAll('.exercise-items .word')
                    );
                    let clickedCount = 0;
                    positions.forEach(idx => {
                        if (idx < allWords.length) {
                            const el = allWords[idx];
                            try {
                                el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                el.click();
                                clickedCount++;
                            } catch(e) {}
                        }
                    });
                    return clickedCount;
                }
            """, positions)
            self.step(f"Clicked {clicked} words by position")
        except Exception as e:
            self.logger.error(f"click_by_positions error: {e}")

# =========================================================================
# PronunciationSolver
# =========================================================================
class PronunciationSolver(BaseSolver):
    RECORD_DURATION = 8
    PASSING_SCORE = 65
    MAX_CORRECTION_ROUNDS = 3
    _audio_url_cache = []
    _console_done = False
    _net_done = False

    def solve(self):
        self.logger.info("=== Pronunciation Solver ===")
        self.start_timer()
        self._install_console_listener()
        self._install_network_sniffer()
        if not self.wait_for_page_ready():
            return False
        items = self.page.locator(".exercise-items .item").all()
        for idx, item in enumerate(items):
            self._record_item(item, idx)

        self._check_pronunciation_batch()
        for round_number in range(1, self.MAX_CORRECTION_ROUNDS + 1):
            score = self.get_result_score()
            failed_indexes, unknown_indexes = self._pronunciation_item_statuses()
            self.step(
                f"Result: {score}/100 | Failed items: "
                f"{len(failed_indexes)} | Unscored: {len(unknown_indexes)}"
            )
            if not failed_indexes and score >= self.PASSING_SCORE:
                elapsed = self.stop_timer()
                self.logger.info(
                    f"Pronunciation SUCCESS! Time: {elapsed} | Score: {score}"
                )
                return True

            retry_indexes = failed_indexes
            if not retry_indexes and score < self.PASSING_SCORE:
                retry_indexes = unknown_indexes or list(range(len(items)))
            if not retry_indexes:
                break

            self.logger.info(
                f"[PRON] Retry round {round_number}: "
                f"items {[idx + 1 for idx in retry_indexes]}"
            )
            for idx in retry_indexes:
                self._record_item(items[idx], idx)
            self._check_pronunciation_batch()

        score = self.get_result_score()
        failed_indexes, _ = self._pronunciation_item_statuses()
        self.step(f"Final detected score: {score}")
        if score >= self.PASSING_SCORE and not failed_indexes:
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

    def _load_item_reference_audio(self, item):
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
        return self._fetch_audio_as_base64(urls) if urls else []

    def _page_audio_urls(self):
        """Return only audio URLs exposed by the currently rendered DOM."""
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
        """Return audio-like performance resources without treating old ones as current."""
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
        if PronunciationSolver._console_done:
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
            PronunciationSolver._console_done = True
        except Exception as e:
            self.logger.error(f"Console listener: {e}")

    def _install_network_sniffer(self):
        if PronunciationSolver._net_done:
            return
        try:
            context = self.page.context
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
                        if url not in PronunciationSolver._audio_url_cache:
                            PronunciationSolver._audio_url_cache.append(url)
                except Exception:
                    pass
            context.on("response", on_response)
            PronunciationSolver._net_done = True
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
            b64_list = self._load_item_reference_audio(item)
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
            mic.scroll_into_view_if_needed()
            mic.click(timeout=5000)
            self.step("Mic started")
            # getUserMedia decodes the selected reference recording just after
            # the mic click.  Record long enough for its actual duration plus
            # a small tail, instead of truncating longer sentences or adding a
            # large silent gap to short ones.
            time.sleep(0.5)
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
            # Always send the stop click after the recording window.  The
            # visual state of this control is not stable across packets, so it
            # must not be used to decide whether Correction may be pressed.
            mic.click(timeout=3000, force=True)
            self.step("Mic stopped")
            time.sleep(0.5)
            return True
        except Exception as e:
            self.logger.error(f"Record error: {e}")
            return False

# =========================================================================
# ExerciseEngine — ตัวจัดการ Solver
# =========================================================================
class ExerciseEngine:
    def __init__(self, page, logger):
        self.page = page
        self.logger = logger
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
            "type-single-item-pronunciation": PronunciationSolver,
            "type-multi-item-pronunciation": PronunciationSolver,
            "type-multiple-item-pronunciation": PronunciationSolver,
        }

    def detect_type(self):
        try:
            exercise_div = self.page.locator(".exercise").first
            video_div = self.page.locator(".video").first
            if exercise_div.count() == 0:
                if video_div.count() > 0:
                    return "type-video"
                return "unknown"
            cls = exercise_div.get_attribute("class") or ""

            # ⭐ drag-drop: คืนค่าประเภทให้ตรงเพื่อให้ skip logic ทำงาน
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
            if "type-answer" in cls:
                return "type-answer"
            return "unknown"
        except Exception:
            return "unknown"

    def get_solver(self, t, force_solve=False):
        sc = self.solvers.get(t)
        if not sc:
            return None
        solver = sc(self.page, self.logger)
        solver.force_solve = force_solve   # ⭐ NEW: ส่ง flag เข้า solver
        return solver

# =========================================================================
# TeeLogger — log ทั้ง terminal + file
# =========================================================================
class TeeLogger:
    def __init__(self, filename, original_stdout):
        self.terminal = original_stdout
        self.log = open(filename, "a", encoding="utf-8")
        self.lock = threading.Lock()

    def write(self, message):
        with self.lock:
            try:
                self.terminal.write(message)
            except Exception:
                pass
            try:
                clean = re.sub(r'\x1b\[[0-9;]*m', '', message)
                self.log.write(clean)
                self.log.flush()
            except Exception:
                pass

    def flush(self):
        with self.lock:
            try:
                self.terminal.flush()
            except Exception:
                pass
            try:
                self.log.flush()
            except Exception:
                pass

# =========================================================================
# SpeexxBotCLI — คลาสหลักของโปรแกรม
# =========================================================================
class SpeexxBotCLI:
    MAX_NEW_EXERCISE_CHAIN = 100

    def __init__(self):
        self.config_folder = "config"
        self.logs_folder = "logs"
        self.dump_folder = "webpagedump"
        self.reports_folder = "reports"
        self.profiles_folder = "chrome_profiles"
        self.accounts_file = os.path.join(self.config_folder, "accounts.json")

        self.lang = "th"
        self.T = TRANSLATIONS[self.lang]

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

    def _input(self, prompt="", sensitive=False):
        value = input(prompt)
        try:
            self.logger.info(f"INPUT: {'<redacted>' if sensitive else value}")
        except Exception:
            pass
        return value

    def _ensure_all_exercises_visible(self):
        try:
            max_attempts = 5
            for attempt in range(max_attempts):
                btn = None
                try:
                    loc = self.page.locator('div.show-more[aria-label="แสดงเพิ่มเติม"]')
                    total = loc.count()
                    for i in range(total):
                        item = loc.nth(i)
                        try:
                            if item.is_visible(timeout=500):
                                btn = item
                                break
                        except Exception:
                            continue
                except Exception:
                    pass

                if btn is None:
                    self.logger.info("[EXPAND] No visible 'Show more' button")
                    return True

                try:
                    btn.click(timeout=3000, force=True)
                    time.sleep(1.0)
                    self.logger.info(f"[EXPAND] Clicked 'Show more' #{attempt+1}")
                except Exception as e:
                    self.logger.error(f"[EXPAND] Click failed: {e}")
                    return False

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
        self.log_filename = os.path.join(self.logs_folder, f"speexx_{ts}.log")
        logging.basicConfig(
            filename=self.log_filename,
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            encoding='utf-8'
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info("Program started")
        self.logger.info(f"Log: {self.log_filename}")
        self.original_stdout = sys.stdout
        sys.stdout = TeeLogger(self.log_filename, self.original_stdout)

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
                                    const buf = b64ToArrayBuffer(b64);
                                    const audioBuffer = await ctx.decodeAudioData(buf);
                                    const src = ctx.createBufferSource();
                                    src.buffer = audioBuffer;
                                    src.connect(dest);
                                    // Let the page attach MediaRecorder to the
                                    // returned stream before the sentence starts.
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
        """Atomically save accounts and retain one recoverable backup."""
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
                ],
            )
            self.browser = self.context.browser
            if self.context.pages:
                self.page = self.context.pages[0]
            else:
                self.page = self.context.new_page()

            self._install_pronunciation_init()

            self.page.goto("https://portal.speexx.com/",
                           wait_until="domcontentloaded")
            time.sleep(2)
            if self.check_speexx_session():
                self.print_status("OK", "Session ยังใช้ได้ — ข้ามการ Login")
                return True
            if not p:
                p = self.get_saved_password(u)
                if p:
                    self.print_status("OK", "ใช้รหัสผ่านที่บันทึกไว้")
            if not p:
                try:
                    import getpass
                    p = getpass.getpass(f"  {Fore.CYAN}[>] Password ของ {u}: {Style.RESET_ALL}").strip()
                except (EOFError, KeyboardInterrupt):
                    return False
                if p:
                    try:
                        save = self._input(f"  {Fore.CYAN}[>] บันทึกรหัสผ่าน? (y/n): {Style.RESET_ALL}").strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        save = "n"
                    if save == "y":
                        self.save_account(u, p)
                        self.print_status("OK", "บันทึกรหัสผ่านแล้ว")
            if not p:
                self.print_status("ERROR", "ไม่มีรหัสผ่าน")
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

    def navigate_to_results(self):
        if not self.page:
            self.print_status("ERROR", "Browser not started.")
            self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
            return False
        self.print_status("INFO", "Navigating to Results...")
        try:
            self.page.goto(
                "https://portal.speexx.com/articles/10960433/results",
                wait_until="domcontentloaded"
            )
            self.page.locator(".level-container").first.wait_for(
                state="visible", timeout=15000
            )
            try:
                self.page.locator("tbody tr.clickable").first.wait_for(
                    state="attached", timeout=8000
                )
            except Exception:
                self.logger.debug("[NAV] Exercise table not ready yet")
            self.print_status("OK", "Results loaded.")
            return True
        except Exception as e:
            self.print_status("ERROR", f"Failed: {str(e)}")
            self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
            return False

    def fetch_and_select_chapter(self):
        if not self.page:
            return
        self.print_header()
        print(f"  {Fore.CYAN}--- {self.T['available_chapters']} ---{Style.RESET_ALL}\n")
        try:
            current_url = self.page.url.lower()
            if "/results" not in current_url:
                self.print_status("INFO", "Navigating to Results page...")
                try:
                    self.page.goto(
                        "https://portal.speexx.com/articles/10960433/results",
                        wait_until="domcontentloaded",
                        timeout=15000
                    )
                except Exception as nav_e:
                    if "interrupted by another navigation" in str(nav_e):
                        self.logger.info("[NAV] Interrupted by Speexx redirect - OK")
                    else:
                        raise
                time.sleep(2)

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
            self.page.locator(
                f".level-container[data-id='{cid}'] .level-inside-box"
            ).click()
            time.sleep(1)
            tab = self.page.locator("#results-table-exercises")
            tab.scroll_into_view_if_needed()
            time.sleep(0.5)
            tab.click()
            time.sleep(1)
            self.print_status("OK", f"{name} selected.")
            self.fetch_exercises()
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

    def fetch_exercises(self):
        self.print_header()
        print(f"  {Fore.CYAN}--- {self.T['exercise_list']} ---{Style.RESET_ALL}\n")
        try:
            self._ensure_all_exercises_visible()

            self.page.locator("tbody tr.clickable").first.wait_for(
                state="visible", timeout=15000
            )
            rows = self.page.locator("tbody tr.clickable").all()
            if not rows:
                self.print_status("ERROR", self.T['no_exercises'])
                self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
                return
            print(f"  {Fore.CYAN}{'No.':<5}| {self.T['table_title']:<33}| "
                  f"{self.T['table_date']:<13}| {self.T['table_time']:<9}| "
                  f"{self.T['table_score']:<7}| {self.T['table_review']}{Style.RESET_ALL}")
            print(f"  {Fore.CYAN}{'-' * 95}{Style.RESET_ALL}")
            exercises = []
            for i, row in enumerate(rows, 1):
                tds = row.locator("td").all()
                if len(tds) >= 4:
                    title = tds[0].inner_text().strip()
                    date = tds[1].inner_text().strip()
                    t_spent = tds[2].inner_text().strip()
                    score = tds[3].inner_text().strip()
                    rb = ""
                    if len(tds) >= 5:
                        b = tds[4].locator("button").all()
                        if b:
                            rb = b[0].inner_text().strip()
                    exercises.append((title, rb))
                    td = title[:30] + "..." if len(title) > 33 else title
                    score_color = Fore.GREEN if score == "100" else Fore.WHITE
                    print(f"  [{i:<3}]| {td:<33}| {date:<13}| "
                          f"{t_spent:<9}| {score_color}{score:<7}{Style.RESET_ALL}| {rb:<10}")
            print(f"  {Fore.CYAN}{'-' * 95}{Style.RESET_ALL}")
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

                selected_titles = [exercises[idx - 1][0] for idx in selected]

                if len(selected_titles) == 1:
                    self.open_exercise_menu(selected_titles[0])
                else:
                    print(f"\n  {Fore.CYAN}--- เลือกโหมดการทำ ({len(selected)} ข้อ) ---{Style.RESET_ALL}")
                    print(f"  {Fore.WHITE}[1]{Style.RESET_ALL} ทำทีละข้อ")
                    print(f"  {Fore.WHITE}[2]{Style.RESET_ALL} ทำทั้งหมดอัตโนมัติ")
                    print(f"  {Fore.WHITE}[3]{Style.RESET_ALL} {self.T['opt_new_learning_path']}")

                    try:
                        mode = self._input(
                            f"  {Fore.CYAN}[>] เลือกโหมด: {Style.RESET_ALL}"
                        ).strip()
                    except Exception:
                        mode = "1"

                    if mode == "2":
                        self.auto_solve_batch(selected_titles)
                    elif mode == "3":
                        self.start_new_learning_path(selected_titles[0])
                    else:
                        for title in selected_titles:
                            self.open_exercise_menu(title)
                            time.sleep(0.5)

            except ValueError:
                pass
        except Exception as e:
            self.print_status("ERROR", f"Error: {str(e)}")
            self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")

    def open_exercise_menu(self, title):
        self.print_header()
        print(f"  {Fore.CYAN}--- {self.T['exercise_menu']}: {title} ---{Style.RESET_ALL}\n")
        print(f"  {Fore.WHITE}[1]{Style.RESET_ALL} {self.T['opt_view']}")
        print(f"  {Fore.WHITE}[2]{Style.RESET_ALL} {self.T['opt_dump']}")
        print(f"  {Fore.WHITE}[3]{Style.RESET_ALL} {self.T['opt_auto_solve']}")
        print(f"  {Fore.WHITE}[4]{Style.RESET_ALL} {self.T['opt_new_learning_path']}")
        print(f"  {Fore.WHITE}[0]{Style.RESET_ALL} {self.T['back']}")
        try:
            c = self._input(f"\n  {Fore.CYAN}[>] Select: {Style.RESET_ALL}").strip()
            if c == "" or c == "0":
                return
            if c == "1":
                self.click_exercise(title)
            elif c == "2":
                self.dump_all_exercise_pages(title)
            elif c == "3":
                force = self._ask_solve_mode()
                if force is None:
                    return
                self.force_solve_all = force
                self.auto_solve_exercise(
                    title,
                    selected_pages=None,
                    is_continuation=False,
                    already_opened=False,
                )
            elif c == "4":
                self.start_new_learning_path(title)
        except ValueError:
            pass

    def click_exercise(self, title):
        self.print_status("WAIT", f"Opening {title}...")
        try:
            self._ensure_all_exercises_visible()
            row = self.page.locator("tbody tr.clickable").filter(has_text=title).first
            try:
                row.scroll_into_view_if_needed()
                time.sleep(0.3)
            except Exception:
                pass
            row.click(timeout=15000)
            self.print_status("OK", "Opened.")
            self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
        except Exception as e:
            self.print_status("ERROR", f"Error: {str(e)}")
            self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")

    def dump_all_exercise_pages(self, title):
        self.print_status("INFO", f"Dumping {title}...")
        try:
            self._ensure_all_exercises_visible()
            row = self.page.locator("tbody tr.clickable").filter(has_text=title).first
            try:
                row.scroll_into_view_if_needed()
                time.sleep(0.3)
            except Exception:
                pass
            row.click(timeout=15000)
            time.sleep(2)
            total = self.get_total_exercises()
            if total == 0:
                self.print_status("ERROR", "Cannot determine total.")
                self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
                return
            safe = re.sub(r'[\\/*?:"<>|]', "", title).replace(" ", "_")
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            for i in range(1, total + 1):
                self.navigate_to_exercise_page(i)
                time.sleep(1)
                fn = f"{self.dump_folder}/{safe}_exercise_{i}_{ts}.html"
                with open(fn, "w", encoding="utf-8") as f:
                    f.write(self.page.content())
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
            items = self.page.locator(".exercises-large-navigation.visible-lg li").all()
            if not items:
                items = self.page.locator(".exercises-large-navigation.visible-md li").all()
            if not items:
                items = self.page.locator(".exercises-large-navigation.visible-sm li").all()
            if 1 <= num <= len(items):
                items[num - 1].click()
                time.sleep(0.5)
                return True
            return False
        except Exception:
            return False

    def detect_completion_modal(self):
        try:
            circ = self.page.locator(".circliful-and-results").first
            if circ.count() > 0 and circ.is_visible(timeout=2000):
                return True
            next_btn = self.page.locator("#nextButton").first
            if next_btn.count() > 0 and next_btn.is_visible(timeout=2000):
                return True
            repeat_btn = self.page.locator("button.text-button-custom.repeat").first
            if repeat_btn.count() > 0 and repeat_btn.is_visible(timeout=2000):
                return True
            try:
                body_text = self.page.locator("body").inner_text(timeout=2000)
                if "ขั้นตอน" in body_text and "ทำได้ดีมาก" in body_text:
                    return True
            except Exception:
                pass
            return False
        except Exception:
            return False

    def wait_for_completion_modal(self, timeout=20):
        for i in range(timeout * 2):
            if self.detect_completion_modal():
                self.print_status("OK", f"Completion modal detected (after {i*0.5:.1f}s)")
                return True
            time.sleep(0.5)
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
                m = re.search(r"เวลา\s+\d+\s+ชม\.\s+\d+\s+น\.", body_text)
                if m:
                    info["time"] = m.group(0)
                m2 = re.search(r"ขั้นตอน\s+\d+\s*·\s*[^\n]+", body_text)
                if m2:
                    info["title"] = m2.group(0).strip()
            except Exception:
                pass
        except Exception as e:
            self.logger.error(f"extract_completion_info error: {e}")
        return info

    def click_modal_repeat(self):
        try:
            for sel in ["button.text-button-custom.repeat", "button.repeat",
                        "button:has-text('ทำซ้ำ')"]:
                btn = self.page.locator(sel).first
                if btn.count() > 0 and btn.is_visible(timeout=2000):
                    btn.click(timeout=5000, force=True)
                    self.print_status("OK", f"Clicked [{self.T['repeat']}]")
                    time.sleep(1.5)
                    return True
            return False
        except Exception as e:
            self.print_status("ERROR", f"Repeat click failed: {e}")
            return False

    def click_modal_continue(self):
        try:
            for sel in ["#nextButton", "button.block-button.btn-primary.next",
                        "button:has-text('เรียนรู้ต่อ')"]:
                btn = self.page.locator(sel).first
                if btn.count() > 0 and btn.is_visible(timeout=2000):
                    btn.click(timeout=5000, force=True)
                    self.print_status("OK", f"Clicked [{self.T['continue']}]")
                    time.sleep(1.5)
                    return True
            return False
        except Exception as e:
            self.print_status("ERROR", f"Continue click failed: {e}")
            return False

    def _print_summary_report(self, results):
        """⭐ แสดงสรุป — รองรับ SKIPPED"""
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
            if e != "N/A":
                try:
                    if "m" in e:
                        parts = e.replace("m", "").replace("s", "").split()
                        total_time += float(parts[0]) * 60 + float(parts[1])
                    else:
                        total_time += float(e.replace("s", ""))
                except Exception:
                    pass
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
                icon = f"{Fore.RED}[X]{Style.RESET_ALL}"
                status_text = self.T['fail']
            print(f"   [{icon}] {self.T['page']} {pn:<2}  |  {status_text:<8}  |  "
                  f"{self.T['score']} {s:>3}/100  |  {self.T['time_spent']} {e}")
        print(f"  {Fore.CYAN}{'-' * 75}{Style.RESET_ALL}")
        print(f"  {Fore.GREEN}   {self.T['passed_count']} : {success_count}{Style.RESET_ALL}")
        if fail_count > 0:
            print(f"  {Fore.RED}   {self.T['failed_count']} : {fail_count}{Style.RESET_ALL}")
        if skip_count > 0:
            print(f"  {Fore.YELLOW}   {self.T['skipped_count']} : {skip_count}{Style.RESET_ALL}")
        print(f"  {Fore.CYAN}   {self.T['total_time']} : {total_time:.2f} s{Style.RESET_ALL}")
        print(f"  {Fore.CYAN}{'=' * 75}{Style.RESET_ALL}")

    def _write_run_report(self, title, results, status, elapsed):
        """Persist a compact machine-readable report for later diagnosis."""
        safe = re.sub(r"[^A-Za-z0-9ก-๙._-]+", "_", title).strip("._") or "exercise"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        payload = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "title": title,
            "status": status,
            "elapsed": elapsed,
            "pages": [
                {"page": page, "status": page_status, "score": score,
                 "elapsed": page_elapsed}
                for page, page_status, score, page_elapsed in results
            ],
        }
        path = os.path.join(self.reports_folder, f"{safe}_{stamp}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            self.logger.info(f"[REPORT] Saved: {path}")
        except Exception as e:
            self.logger.warning(f"[REPORT] Save failed: {e}")

    def _capture_diagnostic_snapshot(self, title, page_number, exercise_type):
        """Save the current page when no registered solver can handle it."""
        if not self.page:
            return None
        safe = re.sub(r"[^A-Za-z0-9ก-๙._-]+", "_", title).strip("._") or "exercise"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(
            self.dump_folder,
            f"diagnostic_{safe}_page{page_number}_{exercise_type}_{stamp}.html",
        )
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.page.content())
            self.logger.warning(f"[DIAGNOSTIC] Snapshot saved: {path}")
            return path
        except Exception as e:
            self.logger.warning(f"[DIAGNOSTIC] Snapshot failed: {e}")
            return None

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
        while True:
            print(f"\n  {Fore.CYAN}--- {self.T['what_next']} ---{Style.RESET_ALL}")
            print(f"  {Fore.WHITE}[1]{Style.RESET_ALL} {self.T['repeat']}")
            print(f"  {Fore.WHITE}[2]{Style.RESET_ALL} {self.T['continue']}")
            print(f"  {Fore.WHITE}[0]{Style.RESET_ALL} {self.T['nothing']}")
            try:
                c = self._input(f"\n  {Fore.CYAN}[>] เลือก: {Style.RESET_ALL}").strip()
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
            except (ValueError, KeyboardInterrupt):
                return "none"

    def get_current_exercise_title(self):
        try:
            for sel in [".folders-dropdown .title span",
                        ".instructions-text",
                        "h1.exercise-header"]:
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
            for sel in [
                "button.text-button-custom.repeat",
                "button.action-exercise-button.repeat",
                "button.repeat",
                "button:has-text('ทำซ้ำ')",
                "button:has-text('Repeat')",
                "[class*='repeat']",
            ]:
                try:
                    btn = self.page.locator(sel).first
                    if btn.count() > 0 and btn.is_visible(timeout=1500):
                        btn.scroll_into_view_if_needed()
                        time.sleep(0.3)
                        btn.click(timeout=3000, force=True)
                        self.logger.info(f"[RESET] Clicked repeat via: {sel}")
                        time.sleep(2)
                        return True
                except Exception:
                    continue
            self.logger.info("[RESET] No repeat button found")
            return False
        except Exception as e:
            self.logger.error(f"[RESET] Error: {e}")
            return False

    def _try_skip_to_next_page(self):
        try:
            for sel in [
                "button.action-exercise-button.next",
                "button:has-text('ถัดไป')",
                "button:has-text('Next')",
                "#nextButton",
            ]:
                try:
                    btn = self.page.locator(sel).first
                    if btn.count() > 0 and btn.is_visible(timeout=2000):
                        btn.scroll_into_view_if_needed()
                        time.sleep(0.3)
                        btn.click(timeout=5000, force=True)
                        self.logger.info(f"[SKIP] Clicked Next via: {sel}")
                        time.sleep(1.5)
                        return True
                except Exception:
                    continue
            self.logger.info("[SKIP] No Next button found")
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
        for sel in [
            ".modal .close",
            "button.close",
            "[aria-label='Close']",
            ".circliful-and-results .close",
        ]:
            try:
                btn = self.page.locator(sel).first
                if btn.count() > 0 and btn.is_visible(timeout=1000):
                    btn.click(timeout=3000, force=True)
                    self.logger.info(f"[BATCH] Dismissed modal via {sel}")
                    return True
            except Exception:
                continue

        for sel in [
            "button.block-button.btn-primary.next",
            "#nextButton",
            "button:has-text('Continue learning')",
            "button:has-text('เรียนรู้ต่อ')",
        ]:
            try:
                btn = self.page.locator(sel).first
                if btn.count() > 0 and btn.is_visible(timeout=1000):
                    btn.click(timeout=3000, force=True)
                    self.logger.info(f"[BATCH] Dismissed modal via {sel}")
                    return True
            except Exception:
                continue

        try:
            self.page.keyboard.press("Escape")
            time.sleep(0.5)
            return True
        except Exception:
            pass
        return False

    def _ask_solve_mode(self):
        """ถามโหมดการทำ — คืน True (force), False (skip 100), None (ยกเลิก)"""
        print(f"\n  {Fore.CYAN}--- เลือกโหมดการทำ ---{Style.RESET_ALL}")
        print(f"  {Fore.WHITE}[1]{Style.RESET_ALL} ทำทุกข้อ "
              f"(force — ทำแม้ได้ 100 แล้ว)")
        print(f"  {Fore.WHITE}[2]{Style.RESET_ALL} ข้ามข้อที่ได้ 100 แล้ว (default)")
        print(f"  {Fore.WHITE}[0]{Style.RESET_ALL} ยกเลิก")
        try:
            c = self._input(
                f"\n  {Fore.CYAN}[>] เลือกโหมด: {Style.RESET_ALL}"
            ).strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if c == "1":
            return True
        if c == "2" or c == "":
            return False
        if c == "0":
            return None
        # default = skip 100
        return False

    def start_new_learning_path(self, first_title):
        print(f"\n  {Fore.CYAN}--- {self.T['opt_new_learning_path']} ---{Style.RESET_ALL}")
        print(f"  เริ่มจาก: {first_title}")
        force = self._ask_solve_mode()
        if force is None:
            return
        self.force_solve_all = force
        try:
            confirm = self._input(
                f"\n  {Fore.CYAN}[>] เริ่มทำและ Continue อัตโนมัติ? "
                f"(Enter=yes / 0=ยกเลิก): {Style.RESET_ALL}"
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
        )

    def _print_batch_summary_report(self, batch_results):
        """⭐ แสดงสรุป batch — รองรับ SKIPPED"""
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
        print(f"  {Fore.GREEN}   >>> BATCH SUMMARY — สรุปผลรวมทั้งหมด <<<{Style.RESET_ALL}")
        print(f"  {Fore.CYAN}{'=' * 78}{Style.RESET_ALL}")
        print(f"  {Fore.CYAN}   จำนวนแบบฝึกหัดที่เลือก: {len(batch_results)}{Style.RESET_ALL}")
        print(f"  {Fore.CYAN}{'-' * 78}{Style.RESET_ALL}")

        for title, status, score, elapsed in batch_results:
            if status == "SUCCESS":
                icon = f"{Fore.GREEN}[OK]{Style.RESET_ALL}"
                status_text = "ผ่าน"
            elif status == "SKIPPED":
                icon = f"{Fore.YELLOW}[--]{Style.RESET_ALL}"
                status_text = "ข้าม"
            else:
                icon = f"{Fore.RED}[X]{Style.RESET_ALL}"
                status_text = "ไม่ผ่าน"
            td = title[:36] + "..." if len(title) > 39 else title
            score_color = Fore.GREEN if score >= 65 else Fore.RED
            print(f"   [{icon}] {td:<42} | {status_text:<6} | "
                  f"{score_color}{score:>3}/100{Style.RESET_ALL} | {elapsed}")

        print(f"  {Fore.CYAN}{'-' * 78}{Style.RESET_ALL}")
        print(f"  {Fore.GREEN}   ผ่าน      : {success_count}{Style.RESET_ALL}")
        if fail_count > 0:
            print(f"  {Fore.RED}   ไม่ผ่าน   : {fail_count}{Style.RESET_ALL}")
        if skip_count > 0:
            print(f"  {Fore.YELLOW}   ข้าม      : {skip_count}{Style.RESET_ALL}")
        print(f"  {Fore.CYAN}   เวลารวม   : {total_time:.2f}s{Style.RESET_ALL}")
        print(f"  {Fore.CYAN}{'=' * 78}{Style.RESET_ALL}")

        def auto_solve_batch(self, titles):
            if not titles:
                return

            self.print_header()
            print(f"  {Fore.CYAN}=== BATCH MODE: {len(titles)} แบบฝึกหัด ==={Style.RESET_ALL}\n")
            for i, t in enumerate(titles, 1):
                print(f"  {Fore.WHITE}[{i}]{Style.RESET_ALL} {t}")
            print(f"\n  {Fore.YELLOW}โหมดนี้จะทำทุกข้อให้เสร็จโดยไม่ถาม{Style.RESET_ALL}")

            # ⭐ NEW: ถามโหมดการทำก่อนเริ่ม batch
            force = self._ask_solve_mode()
            if force is None:
                return
            self.force_solve_all = force

            try:
                confirm = self._input(
                    f"\n  {Fore.CYAN}[>] เริ่มเลย? (Enter=yes / 0=ยกเลิก): {Style.RESET_ALL}"
                ).strip()
                if confirm == "0":
                    return
            except Exception:
                return

            batch_results = []

            for idx, title in enumerate(titles, 1):
                self.print_header()
                print(f"  {Fore.CYAN}=== [{idx}/{len(titles)}] {title} ==={Style.RESET_ALL}")

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
                    f"[{idx}/{len(titles)}] {title}: {status} ({score}) | {elapsed}"
                )

                # ⭐ NEW: หยุดรอให้ผู้ใช้ดู summary ก่อนไปข้อถัดไป
                if idx < len(titles):
                    try:
                        self._input(
                            f"\n  {Fore.CYAN}[>] กด Enter เพื่อไปข้อถัดไป "
                            f"({idx+1}/{len(titles)})...{Style.RESET_ALL}"
                        )
                    except (EOFError, KeyboardInterrupt):
                        pass

            self._print_batch_summary_report(batch_results)

            # ⭐ NEW: pause หลัง batch summary เสร็จ ก่อนกลับเมนูหลัก
            try:
                self._input(
                    f"\n  {Fore.CYAN}[>] กด Enter เพื่อกลับเมนูหลัก..."
                    f"{Style.RESET_ALL}"
                )
            except (EOFError, KeyboardInterrupt):
                pass

            try:
                self.navigate_to_results()
                time.sleep(1)
            except Exception:
                pass

    # =====================================================================
    # auto_solve_exercise
    # =====================================================================
    def auto_solve_exercise(self, title, selected_pages=None,
                            is_continuation=False, already_opened=False,
                            total_pages=None, batch_mode=False,
                            auto_continue=False, continuation_depth=0,
                            chain_seen_titles=None):
        """
        แก้แบบฝึกหัด (auto-solve)

        Supported exercise types are dispatched through ExerciseEngine.
        """
        if not is_continuation and not batch_mode:
            self.print_status("INFO", f"{self.T['auto_solve']}: {title}")
            self.print_status("INFO", self.T['will_not_move'])

        final_status = "FAILED"
        final_score = 0
        final_elapsed = "N/A"
        if auto_continue:
            if chain_seen_titles is None:
                chain_seen_titles = set()
            chain_seen_titles.add((title or "").strip().casefold())

        try:
            if not already_opened and not is_continuation:
                self._ensure_all_exercises_visible()

                clicked = self._click_row_safely(title)
                if not clicked:
                    self.print_status(
                        "ERROR",
                        f"Cannot open '{title}' — skipping"
                    )
                    if not batch_mode:
                        self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
                    return ("ERROR", 0, "N/A")

                try:
                    self.page.wait_for_selector(
                        ".exercise, .video, .exercises-large-navigation.visible-lg li",
                        state="visible",
                        timeout=15000
                    )
                except Exception as e:
                    self.logger.warning(f"[WAIT] Exercise page not ready: {str(e)[:80]}")
                time.sleep(1.5)

            if total_pages is None:
                total_pages = self.get_total_exercises()

            if total_pages == 0:
                self.logger.warning("[TOTAL] First attempt = 0, retrying with reload...")
                try:
                    self.page.reload(wait_until="domcontentloaded", timeout=15000)
                    time.sleep(2)
                    total_pages = self.get_total_exercises()
                except Exception as e:
                    self.logger.error(f"[TOTAL] Reload failed: {e}")

            if total_pages == 0:
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

            engine = ExerciseEngine(self.page, self.logger)
            results = []
            all_success = True
            has_skipped = False
            PASS_LINE = 65
            MAX_TIME_PER_PAGE = 300

            for i in pages_to_solve:
                self.navigate_to_exercise_page(i)
                time.sleep(1)
                et = engine.detect_type()
                self.print_status("PAGE", f"{self.T['page']} {i}/{total_pages} | {self.T['type']}: {et}")

                # Skip only explicitly unsupported types.
                if et in UNSUPPORTED_TYPES:
                    display_name = UNSUPPORTED_TYPES[et]
                    self.print_status(
                        "SKIP",
                        f"ข้ามข้อนี้: โปรแกรมยังไม่ได้เพิ่มระบบในการทำ"
                        f"แบบฝึกหัดประเภท {display_name} ({et})"
                    )
                    results.append((i, "SKIPPED", 0, "N/A"))
                    has_skipped = True
                    # พยายามกด Next ไปข้อถัดไป (ไม่ถือว่า fail)
                    self._try_skip_to_next_page()
                    time.sleep(1)
                    continue

                solver = engine.get_solver(et, force_solve=effective_force)
                if not solver:
                    snapshot = self._capture_diagnostic_snapshot(title, i, et)
                    detail = f" Snapshot: {snapshot}" if snapshot else ""
                    self.print_status("ERROR", f"No solver for {et}. Skipping.{detail}")
                    results.append((i, "NO SOLVER", 0, "N/A"))
                    all_success = False
                    continue

                page_pass_line = (
                    100 if et in {"type-drag-drop", "type-drag-drop-table"}
                    else PASS_LINE
                )

                # ⭐ Video: ผ่านอัตโนมัติ
                if et == "type-video":
                    try:
                        solver.solve()
                    except Exception as e:
                        self.print_status("ERROR", f"Video solver error: {e}")
                    elapsed = solver.stop_timer() if solver.start_time else "N/A"
                    self.print_status("RESULT", f"{self.T['page']} {i}: {self.T['success']} (video) | {elapsed}")
                    results.append((i, "SUCCESS", 100, elapsed))
                    try:
                        next_btn = self.page.locator("button.action-exercise-button.next").first
                        if next_btn.count() > 0 and next_btn.is_visible(timeout=3000):
                            next_btn.click(timeout=5000)
                            time.sleep(1)
                    except Exception:
                        pass
                    continue

                # ⭐ NEW: เช็คก่อนว่า already passed หรือยัง
                # ถ้าคะแนน >= PASS_LINE อยู่แล้ว ให้ถือว่าผ่านทันที
                # (แก้ปัญหา false negative กรณี solver คืน False แต่คะแนนเต็ม)
                if not effective_force:
                    try:
                        existing_score = solver.get_result_score()
                    except Exception:
                        existing_score = 0

                    if existing_score >= page_pass_line:
                        self.print_status(
                            "RESULT",
                            f"{self.T['page']} {i}: {self.T['success']} "
                            f"({existing_score}) [already passed]"
                        )
                        results.append((i, "SUCCESS", existing_score, "0.00s"))
                        try:
                            next_btn = self.page.locator("button.action-exercise-button.next").first
                            if next_btn.count() > 0 and next_btn.is_visible(timeout=3000):
                                next_btn.click(timeout=5000)
                                time.sleep(1)
                        except Exception:
                            pass
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
                        success = False

                    elapsed = solver.stop_timer() if solver.start_time else "N/A"
                    score = solver.get_result_score()
                    if score > best_score:
                        best_score = score

                    # ⭐ FIX: Score-based pass — ถ้าคะแนนผ่านแล้วถือว่าผ่าน
                    # ไม่ต้องสนใจว่า solver คืน True หรือ False
                    # ป้องกัน false negative กรณีคลิกปุ่มไม่ได้แต่คำตอบถูก
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

                # ⭐ FIX: เช็คจากคะแนนเป็นหลัก (backup อีกชั้น)
                if score >= page_pass_line:
                    self.print_status("RESULT", f"{self.T['page']} {i}: {self.T['success']} ({score}) | {elapsed}")
                    results.append((i, "SUCCESS", score, elapsed))
                    try:
                        next_btn = self.page.locator("button.action-exercise-button.next").first
                        if next_btn.count() > 0 and next_btn.is_visible(timeout=3000):
                            next_btn.click(timeout=5000)
                            time.sleep(1)
                    except Exception:
                        pass
                else:
                    self.print_status("ERROR", f"{self.T['page']} {i}: {self.T['failed']} (Score: {best_score}) | {elapsed}")
                    results.append((i, "FAILED", best_score, elapsed))
                    all_success = False
                    self._try_skip_to_next_page()
                    time.sleep(1)

            self._print_summary_report(results)

            final_status = "SUCCESS" if all_success else "FAILED"
            # ถ้าทุกข้อ skipped → final = SKIPPED
            if has_skipped and all((r[1] == "SKIPPED") for r in results):
                final_status = "SKIPPED"

            for _, _, s, _ in results:
                if isinstance(s, (int, float)) and s > final_score:
                    final_score = s
            total_secs = 0.0
            for _, _, _, e in results:
                total_secs += self._parse_elapsed_seconds(e)
            final_elapsed = f"{total_secs:.2f}s"
            self._write_run_report(title, results, final_status, final_elapsed)

            if batch_mode:
                if not is_full:
                    self.print_status("INFO", self.T['selected_only'])
                self.print_status("INFO", "Done.")
                try:
                    if self.detect_completion_modal():
                        self._auto_dismiss_modal()
                        time.sleep(1)
                except Exception:
                    pass
                return (final_status, final_score, final_elapsed)

            self.print_status("INFO", self.T['selected_only'] if not is_full else "Done.")
            if not is_full:
                self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")

            if not is_full:
                return (final_status, final_score, final_elapsed)

            if all_success:
                if self.wait_for_completion_modal(timeout=20):
                    previous_url = self.page.url
                    previous_title = self.get_current_exercise_title()
                    if auto_continue:
                        if continuation_depth >= self.MAX_NEW_EXERCISE_CHAIN:
                            self.print_status(
                                "ERROR",
                                f"หยุด auto-Continue: ถึงขีดจำกัด "
                                f"{self.MAX_NEW_EXERCISE_CHAIN} แบบฝึกหัดแล้ว"
                            )
                            return (final_status, final_score, final_elapsed)
                        action = "continue" if self.click_modal_continue() else "none"
                    else:
                        action = self.handle_completion_modal(results, skip_summary=True)
                    if action == "repeat":
                        self.print_status("INFO", "Restarting packet (Repeat)...")
                        time.sleep(1.5)
                        try:
                            self.navigate_to_exercise_page(1)
                            time.sleep(1)
                        except Exception:
                            pass
                        return self.auto_solve_exercise(
                            title, selected_pages=None,
                            is_continuation=True, already_opened=True,
                            total_pages=total_pages,
                        )
                    elif action == "continue":
                        self.print_status("OK", "Moving on (Continue)...")
                        time.sleep(2)
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
                                    timeout=15000,
                                )
                                if "/results" in self.page.url.lower():
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
                                retries=2 if auto_continue else 4,
                                wait_seconds=0.75 if auto_continue else 1.5,
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
                                self.print_status(
                                    "WAIT",
                                    "Continue แล้วหน้า/ชื่อแบบฝึกหัดไม่เปลี่ยน จึงหยุดเพื่อป้องกันวนซ้ำ"
                                )
                                return (final_status, final_score, final_elapsed)
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
                            self.print_status("WAIT", f"หน้าใหม่ยังไม่โหลด: {e}")
                            return (final_status, final_score, final_elapsed)
                    else:
                        return (final_status, final_score, final_elapsed)
                else:
                    return (final_status, final_score, final_elapsed)
            else:
                return (final_status, final_score, final_elapsed)

        except Exception as e:
            self.print_status("ERROR", f"Auto solve error: {str(e)}")
        finally:
            if not is_continuation and not batch_mode:
                try:
                    self.after_solve_menu()
                except Exception:
                    pass

        return (final_status, final_score, final_elapsed)

    def _next_uncompleted_exercise_title(self, current_title, rows, seen_titles):
        exercises = []
        for row in rows:
            cells = row.locator("td").all()
            if len(cells) < 4:
                continue
            exercise_title = cells[0].inner_text().strip()
            score_text = cells[3].inner_text().strip()
            score_match = re.search(r"\d+", score_text)
            score = int(score_match.group()) if score_match else None
            exercises.append((exercise_title, score))

        if not exercises:
            return None

        current_key = (current_title or "").strip().casefold()
        current_index = next(
            (index for index, (name, _) in enumerate(exercises)
             if name.casefold() == current_key),
            -1,
        )
        indexes = list(range(current_index + 1, len(exercises)))
        indexes.extend(range(0, current_index + 1))
        for index in indexes:
            name, score = exercises[index]
            if not name or name.casefold() in seen_titles:
                continue
            if score is not None and score >= 65:
                continue
            return name
        return None

    def _continue_auto_from_results(self, current_title, status, score, elapsed,
                                    seen_titles, continuation_depth):
        try:
            if "/results" not in self.page.url.lower():
                self.page.goto(
                    "https://portal.speexx.com/articles/10960433/results",
                    wait_until="domcontentloaded",
                    timeout=15000,
                )
            self.page.locator("tbody tr.clickable").first.wait_for(
                state="visible", timeout=15000
            )
            self._ensure_all_exercises_visible()
            rows = self.page.locator("tbody tr.clickable").all()
            next_title = self._next_uncompleted_exercise_title(
                current_title, rows, seen_titles or set()
            )
            if not next_title:
                self.print_status(
                    "OK",
                    "ไม่มีแบบฝึกหัดใหม่ที่ยังไม่ผ่านในหน้า Results; จบการทำต่อเนื่อง",
                )
                return (status, score, elapsed)

            self.print_status("INFO", f"เปิดแบบฝึกหัดที่ยังไม่ผ่าน: {next_title}")
            if not self._click_row_safely(next_title):
                self.print_status("ERROR", f"เปิดแบบฝึกหัดถัดไปไม่สำเร็จ: {next_title}")
                return (status, score, elapsed)
            self.page.wait_for_selector(
                ".exercise, .video", state="visible", timeout=15000
            )
            next_total = self.get_total_exercises(retries=2, wait_seconds=0.75)
            if next_total == 0:
                self.print_status(
                    "ERROR", f"เปิด {next_title} แล้ว แต่ยังไม่พบหน้าแบบฝึกหัด"
                )
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
            self.print_status("WAIT", f"กลับหน้า Results เพื่อหาแบบฝึกหัดถัดไปไม่สำเร็จ: {e}")
            return (status, score, elapsed)

    def _click_row_safely(self, title, wait_timeout=15000):
        try:
            row = self.page.locator("tbody tr.clickable").filter(has_text=title).first
            row.wait_for(state="attached", timeout=wait_timeout)
        except Exception as e:
            self.logger.warning(
                f"[CLICK] Row not found within {wait_timeout}ms for '{title}'"
            )
            try:
                total = self.page.locator("tbody tr.clickable").count()
                self.logger.warning(f"[CLICK] Current tbody tr.clickable count: {total}")
            except Exception:
                pass
            return False

        time.sleep(0.5)

        try:
            row.scroll_into_view_if_needed(timeout=3000)
            time.sleep(0.4)
        except Exception as e:
            self.logger.debug(f"[CLICK] scroll_into_view failed: {e}")
            try:
                row.evaluate("el => el.scrollIntoView({block: 'center'})")
                time.sleep(0.5)
            except Exception:
                pass

        try:
            row.click(timeout=3000)
            self.logger.info(f"[CLICK] '{title}' clicked (normal)")
            return True
        except Exception as e:
            self.logger.debug(f"[CLICK] normal click failed: {str(e)[:120]}")

        try:
            row.click(timeout=3000, force=True)
            self.logger.info(f"[CLICK] '{title}' clicked (force)")
            return True
        except Exception as e:
            self.logger.debug(f"[CLICK] force click failed: {str(e)[:120]}")

        try:
            row.evaluate("el => el.click()")
            self.logger.info(f"[CLICK] '{title}' clicked (JS)")
            return True
        except Exception as e:
            self.logger.error(f"[CLICK] JS click failed: {e}")

        return False

    def after_solve_menu(self):
        while True:
            print(f"\n  {Fore.CYAN}--- {self.T['next_action']} ---{Style.RESET_ALL}")
            print(f"  {Fore.WHITE}[1]{Style.RESET_ALL} {self.T['back_to_list']}")
            print(f"  {Fore.WHITE}[2]{Style.RESET_ALL} {self.T['back_to_main']}")
            print(f"  {Fore.WHITE}[3]{Style.RESET_ALL} {self.T['exit_app']}")
            try:
                c = self._input(f"\n  {Fore.CYAN}[>] Select: {Style.RESET_ALL}").strip()
                if c == "1":
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
        self._cleanup_browser()
        try:
            sys.stdout.flush()
        except Exception:
            pass
        os._exit(0)

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
            print(f"  {Fore.WHITE}[3]{Style.RESET_ALL} {self.T['opt_exit']}")
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
            print(f"  {Fore.WHITE}[3]{Style.RESET_ALL} {self.T['opt_logout']}")
            print(f"  {Fore.WHITE}[4]{Style.RESET_ALL} {self.T['opt_exit']}")
            try:
                c = self._input(f"\n  {Fore.CYAN}[>] Select: {Style.RESET_ALL}").strip()
                if c == "":
                    continue
                if c == "1":
                    self.fetch_and_select_chapter()
                elif c == "2":
                    self.navigate_to_results()
                elif c == "3":
                    self.print_status("INFO", "Logging out...")
                    self._cleanup_browser()
                    return
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

    def main_menu(self):
        self.select_language()
        while True:
            if not self.page:
                self.login_menu()
            else:
                self.dashboard_menu()

if __name__ == "__main__":
    bot = SpeexxBotCLI()
    bot.main_menu()