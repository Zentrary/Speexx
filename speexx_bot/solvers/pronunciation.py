"""Solver for pronunciation / speaking exercises."""

import base64
import time
import requests

from .base import BaseSolver



class PronunciationSolver(BaseSolver):
    RECORD_DURATION = 8.0
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
