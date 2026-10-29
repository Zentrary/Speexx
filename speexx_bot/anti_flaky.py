"""Anti-flaky detector — catches fake 100/100 and suspicious passes."""

import time

class AntiFlakyDetector:
    """Detects flaky/fake passes (too fast, unstable scoring) and forces re-verification."""

    # Thresholds
    SUSPICIOUS_FAST_SECONDS = 0.5  # 100/100 faster than this is suspicious
    SUSPICIOUS_MIN_SCORE_INTERVAL = 0.3  # Minimum realistic time to solve any page

    def __init__(self, cli):
        self.cli = cli
        self._history = {}  # (title, page) -> list of (score, elapsed, timestamp)
        self._flaky_pages = set()  # pages flagged as flaky
        self._consecutive_fast_passes = 0

    def check_result(self, title, page_num, score, elapsed_str, exercise_type=""):
        """Check if result is suspicious. Returns (is_suspicious, reason)."""
        elapsed = self._parse_elapsed(elapsed_str)
        key = (title.strip().casefold() if title else "unknown", int(page_num or 0))

        # Record history
        if key not in self._history:
            self._history[key] = []
        self._history[key].append((int(score or 0), float(elapsed or 0), time.time()))
        if len(self._history[key]) > 10:
            self._history[key] = self._history[key][-10:]

        # Rule 1: 100/100 in <0.5s is always suspicious (unless already passed detection which we handle separately)
        if int(score or 0) >= 100 and elapsed >= 0 and elapsed < self.SUSPICIOUS_FAST_SECONDS:
            self._flaky_pages.add(key)
            self._consecutive_fast_passes += 1
            if self._consecutive_fast_passes >= 3:
                # 3 fast passes in a row → likely systemic flaky (e.g., wrong badge read)
                reason = f"ติดต่อกัน {self._consecutive_fast_passes} หน้าเร็วผิดปกติ (<{self.SUSPICIOUS_FAST_SECONDS}s ได้ 100) — น่าจะอ่านคะแนนผิด"
                return True, reason
            reason = f"เร็วผิดปกติ {elapsed:.2f}s ได้ 100/100 — น่าจะ fake (ต้อง >= {self.SUSPICIOUS_FAST_SECONDS}s)"
            return True, reason
        else:
            # Reset consecutive if this one was normal
            if elapsed >= self.SUSPICIOUS_FAST_SECONDS or int(score or 0) < 100:
                self._consecutive_fast_passes = 0

        # Rule 2: Same page giving different scores too quickly (unstable)
        hist = self._history[key]
        if len(hist) >= 3:
            recent_scores = [h[0] for h in hist[-3:]]
            recent_elapsed = [h[1] for h in hist[-3:]]
            if len(set(recent_scores)) > 1 and all(e < 1.0 for e in recent_elapsed):
                reason = f"คะแนนแกว่ง {recent_scores} ในเวลาเร็ว {recent_elapsed} — ไม่เสถียร"
                return True, reason

        # Rule 3: Multiple pages same exercise all 100 in <1s each
        # (handled via consecutive check above)

        return False, ""

    def should_force_retry(self, title, page_num, score, elapsed_str):
        is_sus, reason = self.check_result(title, page_num, score, elapsed_str)
        if is_sus:
            try:
                self.cli.logger.warning(f"[ANTI-FLAKY] {reason} — บังคับตรวจใหม่ (title='{title}' page={page_num})")
                self.cli.print_status("WAIT", f"Anti-flaky: {reason} → ตรวจใหม่")
            except Exception:
                pass
            # Capture diagnostic for flaky
            try:
                self.cli.capture_web_error(
                    f"flaky_fake_pass_{score}",
                    exercise_title=title,
                    page_number=page_num,
                    extra={"elapsed": elapsed_str, "reason": reason},
                )
            except Exception:
                pass
            return True
        return False

    def verify_already_passed(self, title, page_num, score):
        """Extra verification for already_passed — if suspicious, force solve."""
        # If already_passed says 100 but we have history of this page being flaky, don't trust
        key = (title.strip().casefold() if title else "unknown", int(page_num or 0))
        if key in self._flaky_pages:
            try:
                self.cli.logger.info(f"[ANTI-FLAKY] Page {page_num} เคย flaky มาก่อน — ไม่ข้าม ให้ทำใหม่")
            except Exception:
                pass
            return False  # Don't consider already passed
        return True

    def _parse_elapsed(self, elapsed_str):
        if not elapsed_str or elapsed_str == "N/A":
            return 0.0
        try:
            s = str(elapsed_str).strip()
            if "m" in s:
                parts = s.replace("m", " ").replace("s", " ").split()
                return float(parts[0]) * 60 + float(parts[1]) if len(parts) >= 2 else 0.0
            return float(s.replace("s", "").strip())
        except Exception:
            return 0.0

    def get_flaky_count(self):
        return len(self._flaky_pages)

    def reset(self):
        self._history.clear()
        self._flaky_pages.clear()
        self._consecutive_fast_passes = 0
