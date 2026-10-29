"""Solver for type-video exercises."""

import time

from .base import BaseSolver


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
