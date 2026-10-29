"""Granular speed/timing configuration — every wait is Tunable individually."""

import json
import os

CONFIG_PATH = os.path.join("config", "speed_config.json")

# Default timings - tuned to be reliable, user can override each one individually
DEFAULTS = {
    # === Base action settles ===
    "ACTION_SETTLE_SECONDS": 0.9,
    "FAST_ACTION_SETTLE_SECONDS": 0.45,
    "EXERCISE_STEP_PAUSE_SECONDS": 0.55,

    # === Page readiness ===
    "PAGE_READY_TIMEOUT": 12.0,
    "PAGE_READY_JS_TIMEOUT": 5.0,
    "PAGE_READY_SETTLE": 0.45,
    "WAIT_EXERCISE_CONTENT_READY_TIMEOUT": 8.5,
    "WAIT_EXERCISE_CONTENT_READY_SETTLE": 0.45,
    "WAIT_EXERCISE_CONTENT_INTERVAL": 0.18,

    # === Navigation ===
    "NAVIGATE_PAGE_TIMEOUT": 8.0,
    "NAVIGATE_PAGE_SETTLE": 0.3,
    "NAVIGATE_URL_WAIT": 4.0,
    "NAVIGATE_URL_INTERVAL": 0.12,
    "GET_TOTAL_RETRIES": 4,
    "GET_TOTAL_WAIT_SECONDS": 1.5,
    "CLICK_ROW_SLEEP_BEFORE": 0.15,
    "CLICK_ROW_SLEEP_AFTER_SCROLL": 0.15,

    # === Detection ===
    "DETECT_TYPE_TIMEOUT": 7.5,
    "DETECT_TYPE_RECHECK_TIMEOUT": 6.0,
    "DETECT_TYPE_INTERVAL": 0.2,

    # === Correction / Solution / Repeat ===
    "CLICK_CORRECTION_SETTLE": 0.35,
    "CLICK_CORRECTION_WAIT": 6.5,
    "CLICK_CORRECTION_RETRY_WAIT": 2.0,
    "CLICK_CORRECTION_INTERVAL": 0.12,
    "CLICK_SOLUTION_TIMEOUT": 3.5,
    "CLICK_SOLUTION_SETTLE": 0.30,
    "CLICK_SOLUTION_JS_WAIT": 2.0,
    "CLICK_REPEAT_SETTLE": 0.45,
    "CLICK_REPEAT_WAIT": 3.5,
    "CLICK_NEXT_SETTLE": 0.45,
    "CLICK_NEXT_TIMEOUT": 3.0,

    # === Scoring ===
    "GET_RESULT_SCORE_WAIT": 4.0,
    "GET_RESULT_SCORE_INTERVAL": 0.15,
    "POST_CORRECTION_POLL_INTERVAL": 0.12,

    # === Modal ===
    "MODAL_WAIT_TIMEOUT": 15.0,
    "MODAL_SETTLED_TIMEOUT": 5.0,
    "MODAL_SETTLED_INTERVAL": 0.18,
    "CONTINUE_SETTLE": 0.6,

    # === Solver specifics ===
    "DRAG_SYNC_INTERVAL": 0.045,
    "DRAG_CLICK_SETTLE": 0.08,
    "DRAG_PLACE_SETTLE": 0.03,
    "FILL_BLANK_WAIT": 1.5,
    "PRON_RECORD_DURATION": 8.0,
    "PRON_MIC_SETTLE": 0.5,
    "VIDEO_SEEK_INTERVAL": 0.15,

    # === Runner ===
    "RUNNER_MAX_RETRIES": 3,
    "RUNNER_MAX_TIME_PER_PAGE": 300,
    "RUNNER_RETRY_SLEEP": 0.8,
    "RUNNER_BATCH_SLEEP": 1.5,
}

# Human-readable descriptions for UI
DESCRIPTIONS = {
    "ACTION_SETTLE_SECONDS": "ดีเลย์หลักหลังกดปุ่ม (Correction/Solution/Repeat)",
    "FAST_ACTION_SETTLE_SECONDS": "ดีเลย์เร็ว (Next / Drag)",
    "EXERCISE_STEP_PAUSE_SECONDS": "พักระหว่างขั้นตอนในข้อเดียว",
    "PAGE_READY_TIMEOUT": "รอหน้าโหลด (wait_for_selector)",
    "PAGE_READY_JS_TIMEOUT": "รอ JS ตรวจว่า exercise-items พร้อม",
    "PAGE_READY_SETTLE": "พักหลังหน้า ready",
    "WAIT_EXERCISE_CONTENT_READY_TIMEOUT": "รอเนื้อหาแบบฝึกหัดขึ้นครบ",
    "WAIT_EXERCISE_CONTENT_READY_SETTLE": "พักหลังเนื้อหาพร้อม",
    "WAIT_EXERCISE_CONTENT_INTERVAL": "ช่วงเวลาตรวจเนื้อหาพร้อม",
    "NAVIGATE_PAGE_TIMEOUT": "รอเปลี่ยนหน้าแบบฝึกหัด",
    "NAVIGATE_PAGE_SETTLE": "พักหลังเปลี่ยนหน้า",
    "NAVIGATE_URL_WAIT": "รอ URL เปลี่ยนเป็น /exercise/N",
    "NAVIGATE_URL_INTERVAL": "ช่วงตรวจ URL",
    "GET_TOTAL_RETRIES": "ลองหาจำนวนหน้าใหม่กี่ครั้ง",
    "GET_TOTAL_WAIT_SECONDS": "พักระหว่างลองหาจำนวนหน้า",
    "CLICK_ROW_SLEEP_BEFORE": "พักก่อนคลิกแถวแบบฝึกหัด",
    "CLICK_ROW_SLEEP_AFTER_SCROLL": "พักหลัง scroll ไปแถว",
    "DETECT_TYPE_TIMEOUT": "รอตรวจชนิดแบบฝึกหัด",
    "DETECT_TYPE_RECHECK_TIMEOUT": "รอตรวจซ้ำหลัง video→type เปลี่ยน",
    "DETECT_TYPE_INTERVAL": "ช่วงตรวจชนิด",
    "CLICK_CORRECTION_SETTLE": "พักหลังกด Correction",
    "CLICK_CORRECTION_WAIT": "รอผลตรวจหลังกด Correction",
    "CLICK_CORRECTION_RETRY_WAIT": "รอรอบสองถ้ายังไม่ ready",
    "CLICK_CORRECTION_INTERVAL": "ช่วงตรวจ post-correction ready",
    "CLICK_SOLUTION_TIMEOUT": "รอปุ่ม Solution",
    "CLICK_SOLUTION_SETTLE": "พักหลังกด Solution",
    "CLICK_SOLUTION_JS_WAIT": "รอ JS เฉลยโหลด",
    "CLICK_REPEAT_SETTLE": "พักหลังกด Repeat",
    "CLICK_REPEAT_WAIT": "รอหน้าพร้อมหลัง Repeat",
    "CLICK_NEXT_SETTLE": "พักหลังกด Next",
    "CLICK_NEXT_TIMEOUT": "รอปุ่ม Next",
    "GET_RESULT_SCORE_WAIT": "รอคะแนนขึ้น (รอ spinner)",
    "GET_RESULT_SCORE_INTERVAL": "ช่วงตรวจคะแนน",
    "POST_CORRECTION_POLL_INTERVAL": "ช่วงตรวจว่า grading เสร็จ",
    "MODAL_WAIT_TIMEOUT": "รอ Completion Modal",
    "MODAL_SETTLED_TIMEOUT": "รอ Modal โหลดคะแนน+ปุ่มเสร็จ",
    "MODAL_SETTLED_INTERVAL": "ช่วงตรวจ Modal settled",
    "CONTINUE_SETTLE": "พักหลังกด Continue",
    "DRAG_SYNC_INTERVAL": "ช่วงซิงค์ drag-drop DOM",
    "DRAG_CLICK_SETTLE": "พักหลังคลิก tile",
    "DRAG_PLACE_SETTLE": "พักหลังวาง tile",
    "FILL_BLANK_WAIT": "รอช่องกรอกพร้อม",
    "PRON_RECORD_DURATION": "เวลาอัดเสียง (วินาที)",
    "PRON_MIC_SETTLE": "พักหลังกดไมค์",
    "VIDEO_SEEK_INTERVAL": "ช่วงตรวจวิดีโอจบ",
    "RUNNER_MAX_RETRIES": "ลองทำหน้าเดิมซ้ำสูงสุดกี่ครั้ง",
    "RUNNER_MAX_TIME_PER_PAGE": "เวลาสูงสุดต่อหน้า (วินาที)",
    "RUNNER_RETRY_SLEEP": "พักก่อนลองใหม่",
    "RUNNER_BATCH_SLEEP": "พักระหว่างแบบฝึกหัดใน batch",
}

# Groups for UI
GROUPS = {
    "พื้นฐาน": ["ACTION_SETTLE_SECONDS", "FAST_ACTION_SETTLE_SECONDS", "EXERCISE_STEP_PAUSE_SECONDS"],
    "หน้าโหลด": ["PAGE_READY_TIMEOUT", "PAGE_READY_JS_TIMEOUT", "PAGE_READY_SETTLE", "WAIT_EXERCISE_CONTENT_READY_TIMEOUT", "WAIT_EXERCISE_CONTENT_READY_SETTLE", "WAIT_EXERCISE_CONTENT_INTERVAL"],
    "นำทาง": ["NAVIGATE_PAGE_TIMEOUT", "NAVIGATE_PAGE_SETTLE", "NAVIGATE_URL_WAIT", "NAVIGATE_URL_INTERVAL", "GET_TOTAL_RETRIES", "GET_TOTAL_WAIT_SECONDS", "CLICK_ROW_SLEEP_BEFORE", "CLICK_ROW_SLEEP_AFTER_SCROLL"],
    "ตรวจชนิด": ["DETECT_TYPE_TIMEOUT", "DETECT_TYPE_RECHECK_TIMEOUT", "DETECT_TYPE_INTERVAL"],
    "ปุ่มหลัก": ["CLICK_CORRECTION_SETTLE", "CLICK_CORRECTION_WAIT", "CLICK_CORRECTION_RETRY_WAIT", "CLICK_CORRECTION_INTERVAL", "CLICK_SOLUTION_TIMEOUT", "CLICK_SOLUTION_SETTLE", "CLICK_SOLUTION_JS_WAIT", "CLICK_REPEAT_SETTLE", "CLICK_REPEAT_WAIT", "CLICK_NEXT_SETTLE", "CLICK_NEXT_TIMEOUT"],
    "คะแนน": ["GET_RESULT_SCORE_WAIT", "GET_RESULT_SCORE_INTERVAL", "POST_CORRECTION_POLL_INTERVAL"],
    "Modal": ["MODAL_WAIT_TIMEOUT", "MODAL_SETTLED_TIMEOUT", "MODAL_SETTLED_INTERVAL", "CONTINUE_SETTLE"],
    "ลากวาง/กรอก": ["DRAG_SYNC_INTERVAL", "DRAG_CLICK_SETTLE", "DRAG_PLACE_SETTLE", "FILL_BLANK_WAIT"],
    "เสียง/วิดีโอ": ["PRON_RECORD_DURATION", "PRON_MIC_SETTLE", "VIDEO_SEEK_INTERVAL"],
    "Runner": ["RUNNER_MAX_RETRIES", "RUNNER_MAX_TIME_PER_PAGE", "RUNNER_RETRY_SLEEP", "RUNNER_BATCH_SLEEP"],
}

_cache = None

def _ensure_file():
    if os.path.exists(CONFIG_PATH):
        return
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(DEFAULTS, f, ensure_ascii=False, indent=2)

def load():
    global _cache
    _ensure_file()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Merge with defaults for new keys
        merged = dict(DEFAULTS)
        for k, v in data.items():
            if k in DEFAULTS:
                try:
                    # Keep type of default
                    if isinstance(DEFAULTS[k], int) and not isinstance(DEFAULTS[k], bool):
                        merged[k] = int(v)
                    else:
                        merged[k] = float(v)
                except Exception:
                    merged[k] = v
        _cache = merged
        return merged
    except Exception:
        _cache = dict(DEFAULTS)
        return _cache

def get(key, default=None):
    if _cache is None:
        load()
    if default is None:
        default = DEFAULTS.get(key)
    return _cache.get(key, default)

def get_all():
    if _cache is None:
        load()
    return dict(_cache)

def set_value(key, value):
    if _cache is None:
        load()
    if key not in DEFAULTS:
        return False
    try:
        if isinstance(DEFAULTS[key], int) and not isinstance(DEFAULTS[key], bool):
            _cache[key] = int(value)
        else:
            _cache[key] = float(value)
        save()
        return True
    except Exception:
        return False

def save():
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(_cache, f, ensure_ascii=False, indent=2)

def reset_defaults():
    global _cache
    _cache = dict(DEFAULTS)
    save()
    return _cache

def get_default(key):
    return DEFAULTS.get(key)

def get_description(key):
    return DESCRIPTIONS.get(key, "")

def get_group(key):
    for g, keys in GROUPS.items():
        if key in keys:
            return g
    return "อื่นๆ"
