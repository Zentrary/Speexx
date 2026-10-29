"""Self-healing / Auto-retry engine — transparent recovery without user intervention."""

import time
import random

class SelfHealingEngine:
    """Handles retries with exponential backoff, page reload recovery, and diagnostic capture."""

    def __init__(self, cli):
        self.cli = cli
        self._retry_counts = {}  # (title, page) -> count
        self._page_timings = {}  # (title, page) -> [elapsed]

    def should_retry(self, title, page_num, error_reason=""):
        key = (title, page_num)
        cnt = self._retry_counts.get(key, 0)
        max_retries = int(self._get_speed("RUNNER_MAX_RETRIES", 3))
        return cnt < max_retries

    def record_retry(self, title, page_num):
        key = (title, page_num)
        self._retry_counts[key] = self._retry_counts.get(key, 0) + 1
        return self._retry_counts[key]

    def get_retry_delay(self, attempt):
        base = float(self._get_speed("RUNNER_RETRY_SLEEP", 0.8))
        # Exponential backoff with jitter: base * 1.8^(attempt-1) + random
        delay = base * (1.8 ** max(0, attempt - 1)) + random.uniform(0, 0.4)
        return min(delay, 8.0)

    def attempt_heal(self, title, page_num, exercise_type="", solver_name="", error_reason="", extra=None):
        """Try to heal current page failure. Returns True if heal was attempted (caller should retry solve)."""
        attempt = self.record_retry(title, page_num)
        delay = self.get_retry_delay(attempt)

        try:
            self.cli.logger.warning(f"[SELF-HEAL] Attempt {attempt} for '{title}' page {page_num} ({error_reason}) — waiting {delay:.1f}s")
            self.cli.print_status("WAIT", f"Self-healing ลองใหม่ครั้งที่ {attempt} ({error_reason}) — รอ {delay:.1f}s")
        except Exception:
            pass

        # Capture diagnostic on first failure
        if attempt == 1:
            try:
                self.cli.capture_web_error(
                    f"self_heal_start_{error_reason}"[:48],
                    exercise_title=title,
                    page_number=page_num,
                    exercise_type=exercise_type,
                    solver_name=solver_name,
                    extra=extra,
                )
            except Exception:
                pass

        time.sleep(delay)

        # Healing strategies by attempt number
        healed = False
        if attempt == 1:
            # Strategy 1: Soft reset via Repeat button if visible
            try:
                if self.cli._reset_exercise_page():
                    time.sleep(0.8)
                    healed = True
                else:
                    # Try clicking Repeat via solver method
                    healed = False
            except Exception:
                pass
        elif attempt == 2:
            # Strategy 2: Reload page
            try:
                self.cli.logger.info("[SELF-HEAL] Reloading page...")
                self.cli.page.reload(wait_until="domcontentloaded", timeout=15000)
                time.sleep(1.2)
                self.cli.wait_for_exercise_content_ready(timeout=float(self._get_speed("WAIT_EXERCISE_CONTENT_READY_TIMEOUT", 8.5)))
                time.sleep(0.5)
                healed = True
            except Exception as e:
                try:
                    self.cli.logger.warning(f"[SELF-HEAL] Reload failed: {e}")
                except Exception:
                    pass
        elif attempt >= 3:
            # Strategy 3: Re-navigate to page via nav bar
            try:
                self.cli.logger.info(f"[SELF-HEAL] Re-navigating to page {page_num}...")
                self.cli.navigate_to_exercise_page(page_num)
                time.sleep(0.8)
                healed = True
            except Exception:
                pass
            # Also try re-detecting exercise type after navigation
            try:
                self.cli.page.wait_for_selector(".exercise, video", state="visible", timeout=8000)
            except Exception:
                pass

        return healed

    def record_timing(self, title, page_num, elapsed_seconds):
        key = (title, page_num)
        if key not in self._page_timings:
            self._page_timings[key] = []
        self._page_timings[key].append(float(elapsed_seconds))
        # Keep only last 5
        if len(self._page_timings[key]) > 5:
            self._page_timings[key] = self._page_timings[key][-5:]

    def is_timing_suspicious(self, elapsed_seconds, score):
        """Quick check: suspicious if 100/100 in <0.4s"""
        try:
            return int(score) >= 100 and float(elapsed_seconds) < 0.4
        except Exception:
            return False

    def reset_page(self, title, page_num):
        key = (title, page_num)
        self._retry_counts.pop(key, None)

    def reset_all(self):
        self._retry_counts.clear()

    def _get_speed(self, key, default):
        try:
            from .speed_config import get as speed_get
            return speed_get(key)
        except Exception:
            return default

    def handle_solver_exception(self, title, page_num, exercise_type, solver_name, exc):
        """Unified handler for solver exceptions — logs, captures, and decides retry."""
        try:
            self.cli.capture_web_error(
                "solver_exception",
                exercise_title=title,
                page_number=page_num,
                exercise_type=exercise_type,
                solver_name=solver_name,
                extra={"error": str(exc)[:500]},
            )
        except Exception:
            pass
        return self.should_retry(title, page_num, error_reason="exception")
