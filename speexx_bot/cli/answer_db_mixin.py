"""AnswerDatabaseMixin: Schema v2 reports/answers_<chapter>.json persistence and interactive search."""

import copy
import json
import os
import re
import tempfile
from datetime import datetime
from difflib import SequenceMatcher

from ..ui_utils import Fore, Style, truncate_display


class AnswerDatabaseMixin:
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
