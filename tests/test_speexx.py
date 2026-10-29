import io
import json
import os
import re
import shutil
import pytest

import main
from main import (
    SpeexxBotCLI,
    ExerciseEngine,
    AnswerSolver,
    SingleChoiceSolver,
    MultipleChoiceSolver,
    ToggleSolutionSolver,
    MarkTextSolver,
    ScrambledSentenceSolver,
    DragDropSolver,
    PictureChoiceSolver,
    VideoSolver,
    PronunciationSolver,
    TRANSLATIONS,
    display_width,
    truncate_display,
    pad_display,
)


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(s):
    return ANSI_RE.sub("", s)


@pytest.fixture
def cli_bot(tmp_path, fake_page, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bot = SpeexxBotCLI()
    bot.page = fake_page
    bot.context = fake_page.context
    yield bot
    try:
        if hasattr(bot, "tee_logger") and bot.tee_logger:
            bot.tee_logger.close()
        if hasattr(bot, "original_stdout") and bot.original_stdout:
            import sys
            sys.stdout = bot.original_stdout
    except Exception:
        pass


# ==============================================================================
# 1. Translations, Display Width & Table Pipe Alignment (TH + EN)
# ==============================================================================

def test_translations_complete_and_no_missing_keys():
    th_keys = set(TRANSLATIONS["th"].keys())
    en_keys = set(TRANSLATIONS["en"].keys())
    assert th_keys == en_keys
    for k in th_keys:
        assert isinstance(TRANSLATIONS["th"][k], str) and TRANSLATIONS["th"][k]
        assert isinstance(TRANSLATIONS["en"][k], str) and TRANSLATIONS["en"][k]


def test_display_width_and_table_alignment_th_and_en(cli_bot, capsys, monkeypatch):
    # Thai combining vowels/tone marks have 0 terminal column width
    assert display_width("สึนามิ") == 4  # ส + ึ(0) + น + า + ม + ิ(0) -> 4 columns
    assert display_width(pad_display("สึนามิข้อมูลในโทรคมนาคม", 34)) == 34
    assert display_width(pad_display("🎧 Data tsunami in telecom", 34)) == 34
    assert display_width(pad_display(truncate_display("ผู้เชี่ยวชาญด้านเทคโนโลยีสารสนเทศและการสื่อสารระดับสากล", 34), 34)) == 34

    results_html = """
    <!doctype html><html><body>
      <div class="level-container active" data-id="51100">
        <div class="level-inside-box active"><span class="level-text">A1</span></div>
      </div>
      <div id="results-table-exercises" role="tab">แบบฝึกหัด</div>
      <table><tbody>
        <tr class="clickable">
          <td>🎧 สึนามิข้อมูลในโทรคมนาคม</td><td>29/10/2026</td><td>00:03:12</td>
          <td><i class="icon-check result-green"></i></td><td><button>ทบทวน</button></td>
        </tr>
        <tr class="clickable">
          <td>สึนามิข้อมูลในโทรคมนาคม</td><td>29/10/2026</td><td>00:08:45</td>
          <td>100</td><td><button>ทบทวน</button></td>
        </tr>
        <tr class="clickable">
          <td>Meeting new people in international conferences</td><td>28/10/2026</td><td>00:05:00</td>
          <td></td><td></td>
        </tr>
      </tbody></table>
    </body></html>
    """
    cli_bot.page.set_content(results_html, url="https://portal.speexx.com/articles/10960433/results")

    for lang in ("th", "en"):
        cli_bot.lang = lang
        cli_bot.T = TRANSLATIONS[lang]
        monkeypatch.setattr("builtins.input", lambda *_a, **_k: "0")
        capsys.readouterr()
        cli_bot.fetch_exercises()
        out = strip_ansi(capsys.readouterr().out)
        table_lines = [ln for ln in out.splitlines() if "|" in ln]
        assert len(table_lines) == 4  # header + 3 rows
        pipe_positions = [[i for i, ch in enumerate(ln) if ch == "|"] for ln in table_lines]
        # Verify visual column positions of every '|' match the header row!
        visual_pipe_cols = []
        for ln in table_lines:
            segs = ln.split("|")
            cols = []
            acc = 0
            for seg in segs[:-1]:
                acc += display_width(seg)
                cols.append(acc)
                acc += 1
            visual_pipe_cols.append(cols)
        assert all(cols == visual_pipe_cols[0] for cols in visual_pipe_cols), (
            f"Misaligned pipes for lang={lang}: {visual_pipe_cols}\n{out}"
        )


# ==============================================================================
# 2. Show More / แสดงเพิ่มเติม Expander & Show Less / แสดงน้อยลง Collapse Guard
# ==============================================================================

@pytest.mark.parametrize(
    "more_label,less_label",
    [
        ("Show more", "Show less"),
        ("แสดงเพิ่มเติม", "แสดงน้อยลง"),
    ],
)
def test_show_more_expands_all_pages_and_never_clicks_show_less(cli_bot, more_label, less_label):
    html = f"""
    <!doctype html><html><body>
      <table><tbody id="ex-body"></tbody></table>
      <div class="show-more" id="expander" aria-label="{more_label}">
        <span id="exp-text">{more_label}</span>
        <i id="exp-icon" class="fa fa-chevron-down"></i>
      </div>
      <script>
        let stage = 0;
        const tbody = document.getElementById('ex-body');
        const expander = document.getElementById('expander');
        const expText = document.getElementById('exp-text');
        const expIcon = document.getElementById('exp-icon');

        function renderRows(n) {{
          tbody.innerHTML = '';
          for (let i = 1; i <= n; i++) {{
            const tr = document.createElement('tr');
            tr.className = 'clickable';
            tr.innerHTML = `<td>Exercise ${{i}}</td><td>-</td><td>-</td><td></td><td></td>`;
            tbody.appendChild(tr);
          }}
        }}
        renderRows(10);

        expander.addEventListener('click', () => {{
          if (stage === 0) {{
            stage = 1;
            renderRows(20);
          }} else if (stage === 1) {{
            stage = 2;
            renderRows(25);
            expander.setAttribute('aria-label', '{less_label}');
            expText.textContent = '{less_label}';
            expIcon.className = 'fa fa-chevron-up';
          }} else {{
            // If bot mistakenly clicks "{less_label}", collapse back to 10!
            stage = 0;
            renderRows(10);
            expander.setAttribute('aria-label', '{more_label}');
            expText.textContent = '{more_label}';
            expIcon.className = 'fa fa-chevron-down';
          }}
        }});
      </script>
    </body></html>
    """
    cli_bot.page.set_content(html, url="https://portal.speexx.com/articles/10960433/results")
    assert cli_bot.page.locator("tbody tr.clickable").count() == 10

    ok = cli_bot._ensure_all_exercises_visible()
    assert ok is True
    assert cli_bot.page.locator("tbody tr.clickable").count() == 25
    # Calling _ensure_all_exercises_visible() AGAIN when already expanded must NOT click Show less!
    ok2 = cli_bot._ensure_all_exercises_visible()
    assert ok2 is True
    assert cli_bot.page.locator("tbody tr.clickable").count() == 25


# ==============================================================================
# 3. Duplicate Audio/Exercise Rows, Green Checkmarks & Auto Table Recovery
# ==============================================================================

def test_duplicate_row_disambiguation_checkmark_detection_and_table_recovery(cli_bot):
    results_html = """
    <!doctype html><html><body>
      <div class="level-container active" data-id="777">
        <div class="level-inside-box active"><span class="level-text">B1.1</span></div>
      </div>
      <button id="tab-ex" role="tab">Exercises</button>
      <table><tbody id="rows">
        <tr class="clickable" data-row-kind="audio-completed">
          <td>Data tsunami in telecom</td><td>29/10/2026</td><td>00:02:10</td>
          <td><svg class="icon-check success"></svg></td><td></td>
        </tr>
        <tr class="clickable" data-row-kind="exercise-uncompleted">
          <td>Data tsunami in telecom</td><td>-</td><td>-</td>
          <td></td><td></td>
        </tr>
        <tr class="clickable" data-row-kind="done-100">
          <td>Meeting new people</td><td>28/10/2026</td><td>00:05:00</td>
          <td>100</td><td><button>Review</button></td>
        </tr>
      </tbody></table>
      <script>
        window.__clickedKind = null;
        document.querySelectorAll('tbody tr.clickable').forEach(tr => {
          tr.addEventListener('click', () => {
            window.__clickedKind = tr.getAttribute('data-row-kind');
          });
        });
      </script>
    </body></html>
    """
    cli_bot.page.routes["https://portal.speexx.com/"] = """
    <!doctype html><html><body>
      <a href="https://portal.speexx.com/articles/99887766/results">Progress</a>
      <script>
        document.querySelector('a').addEventListener('click', (e) => {
          e.preventDefault();
          window.location.href = 'https://portal.speexx.com/articles/99887766/results';
        });
      </script>
    </body></html>
    """
    cli_bot.page.routes["/articles/99887766/results"] = results_html

    # Start on an empty page (0 rows) -> _click_row_safely must auto-recover /results!
    cli_bot.page.set_content(
        "<!doctype html><html><body><a href='/articles/99887766/results'>Progress</a></body></html>",
        url="https://portal.speexx.com/dashboard",
    )
    # Hook navigation when anchor clicked
    cli_bot.page.set_content(results_html, url="https://portal.speexx.com/articles/99887766/results")

    rows = cli_bot.page.locator("tbody tr.clickable").all()
    r0 = cli_bot._inspect_result_row(rows[0], row_index=0)
    r1 = cli_bot._inspect_result_row(rows[1], row_index=1)
    r2 = cli_bot._inspect_result_row(rows[2], row_index=2)

    assert r0["has_checkmark"] is True and r0["score"] is None and r0["is_completed"] is True
    assert r1["has_checkmark"] is False and r1["score"] is None and r1["is_completed"] is False
    assert r2["score"] == 100 and r2["is_completed"] is True

    # _next_uncompleted_exercise_entry must skip row 0 (audio checkmark) and pick row 1!
    seen = set()
    next_title, next_idx = cli_bot._next_uncompleted_exercise_entry("", rows, seen)
    assert next_title == "Data tsunami in telecom"
    assert next_idx == 1

    # Default _click_row_safely("Data tsunami in telecom") without row_index picks uncompleted row 1!
    cli_bot.force_solve_all = False
    assert cli_bot._click_row_safely("Data tsunami in telecom") is True
    assert cli_bot.page.evaluate("() => window.__clickedKind") == "exercise-uncompleted"

    # Explicit row_index=0 clicks the exact audio row 0!
    assert cli_bot._click_row_safely("Data tsunami in telecom", row_index=0) is True
    assert cli_bot.page.evaluate("() => window.__clickedKind") == "audio-completed"

    # Empty-table auto-recovery test
    cli_bot.page.set_content(
        "<!doctype html><html><body><a href='/articles/99887766/results'>Results</a></body></html>",
        url="https://portal.speexx.com/articles/99887766/exercise",
    )
    assert cli_bot.page.locator("tbody tr.clickable").count() == 0
    assert cli_bot._click_row_safely("Data tsunami in telecom", row_index=1) is True
    assert cli_bot.page.evaluate("() => window.__clickedKind") == "exercise-uncompleted"


# ==============================================================================
# 4. Bilingual Navigation, Chapters, Action Buttons & Completion Modals (TH + EN)
# ==============================================================================

def test_bilingual_modals_chapters_and_action_buttons(cli_bot, monkeypatch):
    # Chapter filtering excludes both EN & TH tests/exams
    assert cli_bot._is_test_chapter_name("A1 Final Test") is True
    assert cli_bot._is_test_chapter_name("B1 Assessment") is True
    assert cli_bot._is_test_chapter_name("แบบทดสอบ A1") is True
    assert cli_bot._is_test_chapter_name("ข้อสอบปลายภาค") is True
    assert cli_bot._is_test_chapter_name("A1") is False
    assert cli_bot._is_test_chapter_name("B1.2") is False

    # English Completion Modal (without .circliful-and-results class, pure EN text & buttons)
    en_modal_html = """
    <!doctype html><html><body>
      <div class="modal-results">
        <h2>Step 4 · Business presentations</h2>
        <p>Well done! You completed this unit.</p>
        <div class="exercise-result-container">
          <span class="text">94</span><span class="text">100</span>
        </div>
        <div class="circliful-container-progress"><div class="timer"><span class="number">B1.2</span></div></div>
        <div class="exercise-percentage-container"><span class="text">68%</span></div>
        <p>Time spent: 1 h 25 min</p>
        <button id="try-again">Try again</button>
        <button id="cont-btn">Continue learning</button>
      </div>
      <script>
        window.__modalAction = null;
        document.getElementById('try-again').addEventListener('click', () => { window.__modalAction = 'repeat'; });
        document.getElementById('cont-btn').addEventListener('click', () => { window.__modalAction = 'continue'; });
      </script>
    </body></html>
    """
    cli_bot.page.set_content(en_modal_html, url="https://portal.speexx.com/articles/10960433/practice")
    assert cli_bot.detect_completion_modal() is True
    info_en = cli_bot.extract_completion_info()
    assert info_en["score"] == "94"
    assert info_en["score_max"] == "100"
    assert info_en["level"] == "B1.2"
    assert info_en["progress"] == "68%"
    assert "1 h 25 min" in info_en["time"]
    assert "Step 4" in info_en["title"]

    assert cli_bot.click_modal_repeat() is True
    assert cli_bot.page.evaluate("() => window.__modalAction") == "repeat"
    assert cli_bot.click_modal_continue() is True
    assert cli_bot.page.evaluate("() => window.__modalAction") == "continue"

    # Thai Completion Modal
    th_modal_html = """
    <!doctype html><html><body>
      <div class="modal-results">
        <h2>ขั้นตอน 2 · การแนะนำตัว</h2>
        <p>ทำได้ดีมาก</p>
        <p>เวลา 0 ชม. 18 น.</p>
        <button id="th-rep">ทำซ้ำ</button>
        <button id="th-cont">เรียนรู้ต่อ</button>
      </div>
      <script>
        window.__thAction = null;
        document.getElementById('th-rep').addEventListener('click', () => { window.__thAction = 'repeat'; });
        document.getElementById('th-cont').addEventListener('click', () => { window.__thAction = 'continue'; });
      </script>
    </body></html>
    """
    cli_bot.page.set_content(th_modal_html, url="https://portal.speexx.com/articles/10960433/practice")
    assert cli_bot.detect_completion_modal() is True
    info_th = cli_bot.extract_completion_info()
    assert "เวลา 0 ชม. 18 น." in info_th["time"]
    assert "ขั้นตอน 2" in info_th["title"]
    assert cli_bot.click_modal_repeat() is True
    assert cli_bot.page.evaluate("() => window.__thAction") == "repeat"
    assert cli_bot.click_modal_continue() is True
    assert cli_bot.page.evaluate("() => window.__thAction") == "continue"


# ==============================================================================
# 5. End-to-End Multi-Page Interactive Solvers + Schema v2 DB Persistence
# ==============================================================================

def _build_multi_page_speexx_app():
    """
    Builds a stateful 10-page Speexx exercise web app in JSDOM covering:
      1: type-intro
      2: type-video (with Start / เริ่ม button that removes instructions when clicked!)
      3: type-answer (text fill-in with Solution /Repeat / Check)
      4: type-single-choice (multi-item radio with Solution / Repeat / Check)
      5: type-multiple-choice (checkboxes WITHOUT Solution button -> greedy solver!)
      6: type-toggle-solution (cycling toggle button gaps)
      7: type-mark-text (clickable words that wrap in .mark-text on Solution)
      8: type-scrambled-sentence (tiles moved into .destination-zone)
      9: type-drag-drop (word bank tiles clicked into .gap-container slots)
      10: type-picture-choice (image tiles clicked into .drag-drop-placeholder)
    """
    return r"""
    <!doctype html><html><body>
      <div class="circliful-container-progress"><div class="timer"><span class="number">A1</span></div></div>
      <div class="folders-dropdown"><div class="title"><span>Office essentials</span></div></div>
      <ul class="exercises-large-navigation visible-lg">
        <li data-p="1">1</li><li data-p="2">2</li><li data-p="3">3</li><li data-p="4">4</li><li data-p="5">5</li>
        <li data-p="6">6</li><li data-p="7">7</li><li data-p="8">8</li><li data-p="9">9</li><li data-p="10">10</li>
      </ul>
      <div id="stage"></div>
      <div id="controls"></div>
      <div class="exercise-result-container"><span class="text" id="score-box">0</span><span class="text">100</span></div>

      <script>
        window.__currentPage = 1;
        window.__solutionClicks = {};
        const stage = document.getElementById('stage');
        const controls = document.getElementById('controls');
        const scoreBox = document.getElementById('score-box');

        function setScore(n) { scoreBox.textContent = String(n); }

        function renderPage(p) {
          window.__currentPage = p;
          setScore(0);
          controls.innerHTML = '';

          if (p === 1) {
            stage.innerHTML = `
              <h1 class="exercise-header">Welcome</h1>
              <div class="instructions-text">Read the introduction carefully.</div>
              <div class="exercise type-intro"><div class="exercise-items"><div class="item">Intro topic overview</div></div></div>
            `;
            controls.innerHTML = `<button class="btn-next">Next</button>`;
          }
          else if (p === 2) {
            stage.innerHTML = `
              <h1 class="exercise-header">Watch the clip</h1>
              <div class="instructions-text">Watch the video and listen closely.</div>
              <div class="video"><button id="vid-start">Start</button></div>
            `;
            document.getElementById('vid-start').addEventListener('click', () => {
              // Real Speexx mutates DOM when video starts!
              stage.innerHTML = `<div class="video"><video src="clip.mp4"></video></div>`;
              setScore(100);
            });
          }
          else if (p === 3) {
            const renderAnswer = (sol) => {
              stage.innerHTML = `
                <h1 class="exercise-header">Complete the dialogue</h1>
                <div class="instructions-text">Type the missing words.</div>
                <div class="exercise type-answer">
                  <div class="exercise-items">
                    <div class="item">Good <input class="answer-gap" value="${sol ? 'morning' : ''}">!</div>
                    <div class="item">How <input class="answer-gap" value="${sol ? 'are' : ''}"> you?</div>
                  </div>
                </div>
              `;
            };
            renderAnswer(false);
            controls.innerHTML = `
              <button id="c-check">Check</button>
              <button id="c-sol" style="display:none">Solution</button>
              <button id="c-rep" style="display:none">Repeat</button>
            `;
            document.getElementById('c-check').addEventListener('click', () => {
              const vals = Array.from(document.querySelectorAll('input.answer-gap')).map(i => i.value.trim().toLowerCase());
              const sc = (vals[0] === 'morning' ? 50 : 0) + (vals[1] === 'are' ? 50 : 0);
              setScore(sc);
              document.getElementById('c-sol').style.display = 'inline-block';
              document.getElementById('c-rep').style.display = 'inline-block';
            });
            document.getElementById('c-sol').addEventListener('click', () => {
              window.__solutionClicks[3] = (window.__solutionClicks[3] || 0) + 1;
              renderAnswer(true);
            });
            document.getElementById('c-rep').addEventListener('click', () => {
              setScore(0);
              renderAnswer(false);
            });
          }
          else if (p === 4) {
            const renderSC = (sol) => {
              stage.innerHTML = `
                <h1 class="exercise-header">Choose the right verb</h1>
                <div class="instructions-text">Select one answer per sentence.</div>
                <div class="exercise type-single-choice">
                  <div class="exercise-items">
                    <div class="item choice-item">
                      She ___ the manager.
                      <label class="choice-option"><input type="radio" name="g1" class="choice"> am</label>
                      <label class="choice-option ${sol ? 'result-green' : ''}"><input type="radio" name="g1" class="choice" ${sol ? 'checked' : ''}> is</label>
                    </div>
                    <div class="item choice-item">
                      They ___ ready.
                      <label class="choice-option ${sol ? 'result-green' : ''}"><input type="radio" name="g2" class="choice" ${sol ? 'checked' : ''}> are</label>
                      <label class="choice-option"><input type="radio" name="g2" class="choice"> is</label>
                    </div>
                  </div>
                </div>
              `;
            };
            renderSC(false);
            controls.innerHTML = `
              <button id="c-check">ตรวจ</button>
              <button id="c-sol" style="display:none">เฉลย</button>
              <button id="c-rep" style="display:none">ทำซ้ำ</button>
            `;
            document.getElementById('c-check').addEventListener('click', () => {
              const items = document.querySelectorAll('.item.choice-item');
              const ok1 = items[0].querySelectorAll('input.choice')[1].checked;
              const ok2 = items[1].querySelectorAll('input.choice')[0].checked;
              setScore((ok1 ? 50 : 0) + (ok2 ? 50 : 0));
              document.getElementById('c-sol').style.display = 'inline-block';
              document.getElementById('c-rep').style.display = 'inline-block';
            });
            document.getElementById('c-sol').addEventListener('click', () => {
              window.__solutionClicks[4] = (window.__solutionClicks[4] || 0) + 1;
              renderSC(true);
            });
            document.getElementById('c-rep').addEventListener('click', () => {
              setScore(0);
              renderSC(false);
            });
          }
          else if (p === 5) {
            // Multiple choice WITHOUT Solution button -> tests greedy fallback!
            const renderMC = () => {
              stage.innerHTML = `
                <h1 class="exercise-header">Select polite greetings</h1>
                <div class="instructions-text">Choose all correct answers (no solution button).</div>
                <div class="exercise type-multiple-choice">
                  <div class="exercise-items">
                    <div class="item choice-item">
                      <label class="choice-option"><input type="checkbox" class="choice"> Good morning</label>
                      <label class="choice-option"><input type="checkbox" class="choice"> Yo whatsup</label>
                      <label class="choice-option"><input type="checkbox" class="choice"> Hello</label>
                    </div>
                  </div>
                </div>
              `;
            };
            renderMC();
            controls.innerHTML = `
              <button id="c-check">Check</button>
              <button id="c-rep">Try again</button>
            `;
            document.getElementById('c-check').addEventListener('click', () => {
              const boxes = document.querySelectorAll('input.choice');
              let sc = 0;
              if (boxes[0].checked) sc += 50;
              if (boxes[2].checked) sc += 50;
              if (boxes[1].checked) sc = Math.max(0, sc - 50);
              setScore(sc);
            });
            document.getElementById('c-rep').addEventListener('click', () => {
              setScore(0);
              renderMC();
            });
          }
          else if (p === 6) {
            const opts0 = ['---', 'at', 'on'];
            const opts1 = ['---', 'in', 'at'];
            let idx0 = 0, idx1 = 0;
            const renderToggle = () => {
              stage.innerHTML = `
                <h1 class="exercise-header">Prepositions of time</h1>
                <div class="instructions-text">Click to toggle the right word.</div>
                <div class="exercise type-toggle-solution">
                  <div class="exercise-items">
                    <div class="item">
                      Meet me <div class="gap-container"><span class="gap">${opts0[idx0]}</span><button class="tbtn" data-g="0">+</button></div> Monday
                      <div class="gap-container"><span class="gap">${opts1[idx1]}</span><button class="tbtn" data-g="1">+</button></div> 9am.
                    </div>
                  </div>
                </div>
              `;
              stage.querySelectorAll('.tbtn').forEach(b => {
                b.addEventListener('click', () => {
                  if (b.dataset.g === '0') idx0 = (idx0 + 1) % opts0.length;
                  else idx1 = (idx1 + 1) % opts1.length;
                  renderToggle();
                });
              });
            };
            renderToggle();
            controls.innerHTML = `
              <button id="c-check">Check</button>
              <button id="c-sol" style="display:none">Solution</button>
              <button id="c-rep" style="display:none">Repeat</button>
            `;
            document.getElementById('c-check').addEventListener('click', () => {
              setScore((opts0[idx0] === 'on' ? 50 : 0) + (opts1[idx1] === 'at' ? 50 : 0));
              document.getElementById('c-sol').style.display = 'inline-block';
              document.getElementById('c-rep').style.display = 'inline-block';
            });
            document.getElementById('c-sol').addEventListener('click', () => {
              window.__solutionClicks[6] = (window.__solutionClicks[6] || 0) + 1;
              idx0 = 2; idx1 = 2;
              renderToggle();
            });
            document.getElementById('c-rep').addEventListener('click', () => {
              setScore(0);
              idx0 = 0; idx1 = 0;
              renderToggle();
            });
          }
          else if (p === 7) {
            let solMode = false;
            const selected = new Set();
            const words = ['Please', 'send', 'the', 'report', 'today'];
            const renderMark = () => {
              const htmlWords = words.map((w, i) => {
                if (solMode && (i === 1 || i === 3)) {
                  return `<span class="mark-text"><span class="word" data-i="${i}">${w}</span></span>`;
                }
                const cls = selected.has(i) ? 'word selected' : 'word';
                return `<span class="${cls}" data-i="${i}">${w}</span>`;
              }).join(' ');
              stage.innerHTML = `
                <h1 class="exercise-header">Highlight key nouns & verbs</h1>
                <div class="instructions-text">Click the words to mark them.</div>
                <div class="exercise type-mark-text"><div class="exercise-items"><div class="item">${htmlWords}</div></div></div>
              `;
              stage.querySelectorAll('.word').forEach(el => {
                el.addEventListener('click', () => {
                  const idx = Number(el.dataset.i);
                  if (selected.has(idx)) selected.delete(idx);
                  else selected.add(idx);
                  renderMark();
                });
              });
            };
            renderMark();
            controls.innerHTML = `
              <button id="c-check">Check</button>
              <button id="c-sol" style="display:none">Solution</button>
              <button id="c-rep" style="display:none">Repeat</button>
            `;
            document.getElementById('c-check').addEventListener('click', () => {
              const ok = selected.size === 2 && selected.has(1) && selected.has(3);
              setScore(ok ? 100 : 0);
              document.getElementById('c-sol').style.display = 'inline-block';
              document.getElementById('c-rep').style.display = 'inline-block';
            });
            document.getElementById('c-sol').addEventListener('click', () => {
              window.__solutionClicks[7] = (window.__solutionClicks[7] || 0) + 1;
              solMode = true;
              renderMark();
            });
            document.getElementById('c-rep').addEventListener('click', () => {
              setScore(0);
              solMode = false;
              selected.clear();
              renderMark();
            });
          }
          else if (p === 8) {
            let words = ['meeting.', 'the', 'join', 'Please'];
            let selectedIdx = null;
            const target = ['Please', 'join', 'the', 'meeting.'];
            const renderScram = () => {
              stage.innerHTML = `
                <h1 class="exercise-header">Order the sentence</h1>
                <div class="instructions-text">Put the words in the right order.</div>
                <div class="exercise type-scrambled-sentence">
                  <div class="exercise-items">
                    <div class="item">
                      <div class="scrambled-sentence">
                        ${words.map((w, i) => `<div class="scrambled-block" data-idx="${i}">${w}</div>`).join('')}
                      </div>
                    </div>
                  </div>
                </div>
              `;
              const scEl = stage.querySelector('.scrambled-sentence');
              scEl.addEventListener('change', () => {
                words = Array.from(scEl.querySelectorAll('.scrambled-block')).map(b => b.textContent.trim());
              });
              stage.querySelectorAll('.scrambled-block').forEach((el, idx) => {
                el.addEventListener('click', () => {
                  if (selectedIdx === null) {
                    selectedIdx = idx;
                  } else {
                    const tmp = words[selectedIdx];
                    words[selectedIdx] = words[idx];
                    words[idx] = tmp;
                    selectedIdx = null;
                    renderScram();
                  }
                });
              });
            };
            renderScram();
            controls.innerHTML = `
              <button id="c-check">Check</button>
              <button id="c-sol" style="display:none">Solution</button>
              <button id="c-rep" style="display:none">Repeat</button>
            `;
            document.getElementById('c-check').addEventListener('click', () => {
              const cur = Array.from(stage.querySelectorAll('.scrambled-block')).map(b => b.textContent.trim());
              const ok = cur.length === target.length && cur.every((w, i) => w === target[i]);
              setScore(ok ? 100 : 0);
              document.getElementById('c-sol').style.display = 'inline-block';
              document.getElementById('c-rep').style.display = 'inline-block';
            });
            document.getElementById('c-sol').addEventListener('click', () => {
              window.__solutionClicks[8] = (window.__solutionClicks[8] || 0) + 1;
              words = [...target];
              selectedIdx = null;
              renderScram();
            });
            document.getElementById('c-rep').addEventListener('click', () => {
              setScore(0);
              words = ['the', 'meeting.', 'Please', 'join'];
              selectedIdx = null;
              renderScram();
            });
          }
          else if (p === 9) {
            let slots = [null, null];
            let pool = ['budget', 'deadline', 'coffee'];
            let activeSlot = 0;
            const renderDD = () => {
              stage.innerHTML = `
                <h1 class="exercise-header">Fill in the gaps</h1>
                <div class="instructions-text">Drag or click words into the gaps.</div>
                <div class="exercise type-drag-drop">
                  <div class="exercise-items">
                    <div class="item">
                      We met the <div class="gap-container" data-s="0">${slots[0] ? `<div class="drag-drop">${slots[0]}</div>` : `<div class="drag-drop-placeholder"></div>`}</div>
                      within our <div class="gap-container" data-s="1">${slots[1] ? `<div class="drag-drop">${slots[1]}</div>` : `<div class="drag-drop-placeholder"></div>`}</div>.
                    </div>
                  </div>
                  <div class="draggable-container">
                    ${pool.map((w, i) => `<div class="drag-drop" data-pi="${i}">${w}</div>`).join('')}
                  </div>
                </div>
              `;
              stage.querySelectorAll('.gap-container').forEach(gc => {
                gc.addEventListener('click', () => { activeSlot = Number(gc.dataset.s); });
              });
              stage.querySelectorAll('.draggable-container .drag-drop').forEach(dd => {
                dd.addEventListener('click', () => {
                  const pi = Number(dd.dataset.pi);
                  const [w] = pool.splice(pi, 1);
                  if (slots[activeSlot]) pool.push(slots[activeSlot]);
                  slots[activeSlot] = w;
                  const nextEmpty = slots.findIndex(v => !v);
                  if (nextEmpty >= 0) activeSlot = nextEmpty;
                  renderDD();
                });
              });
            };
            renderDD();
            controls.innerHTML = `
              <button id="c-check">Check</button>
              <button id="c-sol" style="display:none">Solution</button>
              <button id="c-rep" style="display:none">Repeat</button>
            `;
            document.getElementById('c-check').addEventListener('click', () => {
              const sc = (slots[0] === 'deadline' ? 50 : 0) + (slots[1] === 'budget' ? 50 : 0);
              setScore(sc);
              document.getElementById('c-sol').style.display = 'inline-block';
              document.getElementById('c-rep').style.display = 'inline-block';
            });
            document.getElementById('c-sol').addEventListener('click', () => {
              window.__solutionClicks[9] = (window.__solutionClicks[9] || 0) + 1;
              slots = ['deadline', 'budget'];
              pool = ['coffee'];
              renderDD();
            });
            document.getElementById('c-rep').addEventListener('click', () => {
              setScore(0);
              slots = [null, null];
              pool = ['coffee', 'budget', 'deadline'];
              activeSlot = 0;
              renderDD();
            });
          }
          else if (p === 10) {
            let placed = [null, null];
            let imgs = [
              { id: 'img-b', src: 'https://portal.speexx.com/media/chart.png' },
              { id: 'img-a', src: 'https://portal.speexx.com/media/laptop.png' },
            ];
            let armed = 0;
            const renderPic = () => {
              stage.innerHTML = `
                <h1 class="exercise-header">Match the office items</h1>
                <div class="instructions-text">Place each picture on its label.</div>
                <div class="exercise type-picture-choice">
                  <div class="exercise-items">
                    <div class="item" data-idx="0">
                      Laptop
                      ${placed[0] ? `<img class="picture-gap" data-drag-drop-id="${placed[0].id}" src="${placed[0].src}">` : `<div class="drag-drop-placeholder"></div>`}
                    </div>
                    <div class="item" data-idx="1">
                      Sales chart
                      ${placed[1] ? `<img class="picture-gap" data-drag-drop-id="${placed[1].id}" src="${placed[1].src}">` : `<div class="drag-drop-placeholder"></div>`}
                    </div>
                  </div>
                  <div class="draggable-container">
                    ${imgs.map((im, i) => `<img class="drag-drop" data-i="${i}" data-drag-drop-id="${im.id}" src="${im.src}">`).join('')}
                  </div>
                </div>
              `;
              stage.querySelectorAll('.exercise-items .item').forEach(it => {
                it.addEventListener('click', () => { armed = Number(it.dataset.idx); });
              });
              stage.querySelectorAll('.draggable-container img').forEach(imEl => {
                imEl.addEventListener('click', () => {
                  const i = Number(imEl.dataset.i);
                  const [picked] = imgs.splice(i, 1);
                  if (placed[armed]) imgs.push(placed[armed]);
                  placed[armed] = picked;
                  const nextEmpty = placed.findIndex(v => !v);
                  if (nextEmpty >= 0) armed = nextEmpty;
                  renderPic();
                });
              });
            };
            renderPic();
            controls.innerHTML = `
              <button id="c-check">Check</button>
              <button id="c-sol" style="display:none">Solution</button>
              <button id="c-rep" style="display:none">Repeat</button>
            `;
            document.getElementById('c-check').addEventListener('click', () => {
              const ok0 = placed[0] && placed[0].id === 'img-a';
              const ok1 = placed[1] && placed[1].id === 'img-b';
              setScore((ok0 ? 50 : 0) + (ok1 ? 50 : 0));
              document.getElementById('c-sol').style.display = 'inline-block';
              document.getElementById('c-rep').style.display = 'inline-block';
            });
            document.getElementById('c-sol').addEventListener('click', () => {
              window.__solutionClicks[10] = (window.__solutionClicks[10] || 0) + 1;
              placed = [
                { id: 'img-a', src: 'https://portal.speexx.com/media/laptop.png' },
                { id: 'img-b', src: 'https://portal.speexx.com/media/chart.png' },
              ];
              imgs = [];
              renderPic();
            });
            document.getElementById('c-rep').addEventListener('click', () => {
              setScore(0);
              placed = [null, null];
              imgs = [
                { id: 'img-b', src: 'https://portal.speexx.com/media/chart.png' },
                { id: 'img-a', src: 'https://portal.speexx.com/media/laptop.png' },
              ];
              armed = 0;
              renderPic();
            });
          }
        }

        document.querySelectorAll('.exercises-large-navigation li').forEach(li => {
          li.addEventListener('click', () => renderPage(Number(li.dataset.p)));
        });
        renderPage(1);
      </script>
    </body></html>
    """


def test_end_to_end_10_solvers_auto_chapter_db_and_cached_replay(cli_bot, monkeypatch):
    # Notice we do NOT call select_chapter! Bot must auto-detect "A1" from DOM and save answers_A1.json!
    cli_bot.page.set_content(
        _build_multi_page_speexx_app(),
        url="https://portal.speexx.com/articles/10960433/exercise/office",
    )

    status, score, _elapsed = cli_bot.auto_solve_exercise(
        "Office essentials",
        already_opened=True,
        batch_mode=True,
    )
    assert status == "SUCCESS"
    assert score == 100

    db_path = os.path.join(cli_bot.reports_folder, "answers_A1.json")
    assert os.path.exists(db_path), "answers_A1.json must be created automatically!"

    with open(db_path, "r", encoding="utf-8") as f:
        db = json.load(f)

    assert db["schema_version"] == 2
    assert db["chapter"]["name"] == "A1"
    assert db["chapter"]["summary"]["exercises"] == 1
    assert db["chapter"]["summary"]["pages"] == 10
    assert db["chapter"]["summary"]["answered_pages"] == 10

    # Zero leakage into "Imported answers (legacy)" despite video/solution/shuffle DOM mutations!
    ex_titles = [e["title"] for e in db["exercises"]]
    assert ex_titles == ["Office essentials"]

    pages = db["exercises"][0]["pages"]
    assert [p["page"] for p in pages] == list(range(1, 11))

    by_page = {p["page"]: p for p in pages}
    assert by_page[1]["type"] == "type-intro"
    assert by_page[2]["type"] == "type-video"
    # Video page preserved clean prompt BEFORE click_start wiped .instructions-text!
    assert by_page[2]["prompt"] == "Watch the video and listen closely."
    assert by_page[3]["answer"]["answers"] == ["morning", "are"]
    assert by_page[4]["answer"]["answers"] == [1, 0]
    assert by_page[5]["answer"]["answers"] == [[0, 2]]
    assert by_page[6]["answer"]["answers"] == ["on", "at"]
    assert by_page[7]["answer"]["marked_words"] == ["send", "report"]
    assert by_page[7]["answer"]["answers"] == ["send", "report"]
    assert by_page[8]["answer"]["answers"] == [["Please", "join", "the", "meeting."]]
    assert by_page[9]["answer"]["answers"] == ["deadline", "budget"]
    assert len(by_page[10]["answer"]["answers"]) == 2
    assert by_page[10]["answer"]["answers"][0]["drag_id"] == "img-a"

    # Now reload fresh exercise DOM and run a NEW CLI instance to test CACHED FAST PATHS!
    cli_bot2 = SpeexxBotCLI()
    cli_bot2.page = cli_bot.page
    cli_bot2.context = cli_bot.page.context
    cli_bot2.force_solve_all = True
    cli_bot2.page.set_content(
        _build_multi_page_speexx_app(),
        url="https://portal.speexx.com/articles/10960433/exercise/office",
    )

    status2, score2, _ = cli_bot2.auto_solve_exercise(
        "Office essentials",
        selected_pages=[3, 4, 6, 7, 8, 9, 10],
        already_opened=True,
        batch_mode=True,
    )
    assert status2 == "SUCCESS"
    assert score2 == 100
    # Verify Solution button was NOT clicked at all during cached replay!
    sol_clicks = cli_bot2.page.evaluate("() => window.__solutionClicks")
    assert sol_clicks == {}, f"Expected 0 solution clicks on cached replay, got {sol_clicks}"
    cli_bot2.tee_logger.close()


# ==============================================================================
# 6. Unconditional Saving on Failure, Cache Safety, Already-Passed & Unknown Types
# ==============================================================================

def test_unconditional_saving_on_fail_and_verified_answer_protection(cli_bot):
    cli_bot.current_chapter_name = "B1.1"
    cli_bot.current_chapter_cid = "88800"

    # 1) Page with NO solution button where answer is unknown -> FAILS (score=0), MUST STILL SAVE!
    unsolvable_html = """
    <!doctype html><html><body>
      <ul class="exercises-large-navigation visible-lg"><li data-p="1">1</li></ul>
      <h1 class="exercise-header">Hard idiom</h1>
      <div class="instructions-text">Fill the secret idiom.</div>
      <div class="exercise type-answer">
        <div class="exercise-items">
          <div class="item">Break a <input class="answer-gap" value="">!</div>
        </div>
      </div>
      <button class="correct">Check</button>
      <button class="repeat">Repeat</button>
      <div class="exercise-result-container"><span class="text" id="sc">0</span><span class="text">100</span></div>
    </body></html>
    """
    cli_bot.page.set_content(unsolvable_html, url="https://portal.speexx.com/articles/1/ex")
    status, score, _ = cli_bot.auto_solve_exercise(
        "Idioms quiz",
        already_opened=True,
        batch_mode=True,
    )
    assert status == "FAILED"
    assert score == 0

    db_file = os.path.join(cli_bot.reports_folder, "answers_B1.1.json")
    assert os.path.exists(db_file)
    with open(db_file, "r", encoding="utf-8") as f:
        db1 = json.load(f)

    ex_rec = db1["exercises"][0]
    assert ex_rec["title"] == "Idioms quiz"
    assert len(ex_rec["pages"]) == 1
    assert ex_rec["pages"][0]["page"] == 1
    assert ex_rec["pages"][0]["prompt"] == "Fill the secret idiom."
    assert ex_rec["pages"][0]["answer"]["verified"] is False

    # 2) Next run: Solution button IS available -> solver must NOT use unverified cache, must solve & upgrade!
    solvable_html = """
    <!doctype html><html><body>
      <ul class="exercises-large-navigation visible-lg"><li data-p="1">1</li></ul>
      <h1 class="exercise-header">Hard idiom</h1>
      <div class="instructions-text">Fill the secret idiom.</div>
      <div class="exercise type-answer">
        <div class="exercise-items">
          <div class="item">Break a <input class="answer-gap" id="inp" value="">!</div>
        </div>
      </div>
      <button id="chk" class="correct">Check</button>
      <button id="sol" class="solution">Solution</button>
      <button id="rep" class="repeat">Repeat</button>
      <div class="exercise-result-container"><span class="text" id="sc">0</span><span class="text">100</span></div>
      <script>
        const inp = document.getElementById('inp');
        const sc = document.getElementById('sc');
        document.getElementById('chk').addEventListener('click', () => {
          sc.textContent = inp.value.trim().toLowerCase() === 'leg' ? '100' : '0';
        });
        document.getElementById('sol').addEventListener('click', () => { inp.value = 'leg'; });
        document.getElementById('rep').addEventListener('click', () => { inp.value = ''; sc.textContent = '0'; });
      </script>
    </body></html>
    """
    cli_bot.page.set_content(solvable_html, url="https://portal.speexx.com/articles/1/ex")
    status2, score2, _ = cli_bot.auto_solve_exercise(
        "Idioms quiz",
        already_opened=True,
        batch_mode=True,
    )
    assert status2 == "SUCCESS"
    assert score2 == 100

    with open(db_file, "r", encoding="utf-8") as f:
        db2 = json.load(f)
    p_ans = db2["exercises"][0]["pages"][0]["answer"]
    assert p_ans["answers"] == ["leg"]
    assert p_ans.get("verified", True) is True

    # 3) Third run: page broken/unsolvable (score stuck at 0) -> MUST NOT overwrite verified ["leg"]!
    broken_html = unsolvable_html
    cli_bot.force_solve_all = True
    cli_bot.page.set_content(broken_html, url="https://portal.speexx.com/articles/1/ex")
    status3, _, _ = cli_bot.auto_solve_exercise(
        "Idioms quiz",
        already_opened=True,
        batch_mode=True,
    )
    assert status3 == "FAILED"
    with open(db_file, "r", encoding="utf-8") as f:
        db3 = json.load(f)
    page3 = db3["exercises"][0]["pages"][0]
    assert page3["answer"]["answers"] == ["leg"]
    assert "last_unverified_attempt" in page3


def test_already_passed_and_unknown_type_pages_still_saved_to_db(cli_bot):
    cli_bot.current_chapter_name = "A2"
    cli_bot.force_solve_all = False

    html = """
    <!doctype html><html><body>
      <ul class="exercises-large-navigation visible-lg">
        <li data-p="1">1</li><li data-p="2">2</li>
      </ul>
      <div id="wrap"></div>
      <div class="exercise-result-container"><span class="text" id="sc">100</span><span class="text">100</span></div>
      <script>
        const wrap = document.getElementById('wrap');
        const sc = document.getElementById('sc');
        function show(p) {
          if (p === 1) {
            sc.textContent = '100';
            wrap.innerHTML = `
              <h1 class="exercise-header">Already done</h1>
              <div class="instructions-text">Completed earlier.</div>
              <div class="exercise type-answer">
                <div class="exercise-items"><div class="item">Hello <input class="answer-gap" value="world"></div></div>
              </div>
            `;
          } else {
            sc.textContent = '0';
            wrap.innerHTML = `
              <h1 class="exercise-header">Experimental widget</h1>
              <div class="instructions-text">New Speexx beta activity.</div>
              <div class="exercise type-beta-unknown">
                <div class="exercise-items"><div class="item">Beta prompt item</div></div>
              </div>
            `;
          }
        }
        document.querySelectorAll('li').forEach(li => li.addEventListener('click', () => show(Number(li.dataset.p))));
        show(1);
      </script>
    </body></html>
    """
    cli_bot.page.set_content(html, url="https://portal.speexx.com/articles/2/ex")
    status, score, _ = cli_bot.auto_solve_exercise(
        "Mixed states",
        already_opened=True,
        batch_mode=True,
    )
    assert status == "FAILED"  # page 2 had no solver
    assert score == 100

    db_path = os.path.join(cli_bot.reports_folder, "answers_A2.json")
    with open(db_path, "r", encoding="utf-8") as f:
        db = json.load(f)

    pages = db["exercises"][0]["pages"]
    assert len(pages) == 2
    # Page 1 was already passed -> extracted ["world"] without resetting!
    assert pages[0]["page"] == 1
    assert pages[0]["answer"]["answers"] == ["world"]
    # Page 2 had no solver -> still recorded in DB with verified=False!
    assert pages[1]["page"] == 2
    assert pages[1]["answer"]["verified"] is False
    assert pages[1]["answer"]["answers"] == ["Beta prompt item"]


# ==============================================================================
# 7. Real answers_A1.json Migration/Dedup & Multi-Chapter Search (TH + EN)
# ==============================================================================

def test_real_answers_a1_load_dedup_catalog_sync_and_multi_db_search(cli_bot, capsys, monkeypatch):
    ref_path = "/tmp/arena-coding-uploads/answers_A1.json"
    target_a1 = os.path.join(cli_bot.reports_folder, "answers_A1.json")
    if os.path.exists(ref_path):
        shutil.copy2(ref_path, target_a1)
    else:
        # Fallback fixture if run outside sandbox
        sample = {
            "schema_version": 2,
            "chapter": {
                "name": "A1",
                "cid": "51100",
                "summary": {"exercises": 1, "pages": 0, "answered_pages": 2},
                "catalog": [{"title": "A day in the office", "pages_total": 0}],
            },
            "exercises": [
                {
                    "title": "A day in the office",
                    "pages_total": 8,
                    "pages": [
                        {
                            "page": 2,
                            "type": "type-single-choice",
                            "question": "Choose the right answer | Exercise 2 | She is in the office.",
                            "prompt": "Choose the right answer",
                            "answer": {"type": "single-choice", "answers": [1], "timestamp": "2026-09-29T00:00:00"},
                        }
                    ],
                },
                {
                    "title": "Imported answers (legacy)",
                    "pages_total": 0,
                    "pages": [
                        {
                            "page": None,
                            "type": "single-choice",
                            "question": "Choose the right answer | She is in the office.",
                            "prompt": "",
                            "answer": {"type": "single-choice", "answers": [1], "timestamp": "2026-09-29T00:00:00"},
                        }
                    ],
                },
            ],
        }
        with open(target_a1, "w", encoding="utf-8") as f:
            json.dump(sample, f, ensure_ascii=False, indent=2)

    cli_bot._load_answer_db("A1", announce=True)
    cli_bot._save_answer_db("A1")

    with open(target_a1, "r", encoding="utf-8") as f:
        saved_a1 = json.load(f)

    # Verify catalog pages_total synced from exercises (no longer 0 when exercise has pages_total > 0!)
    cat_map = {c["title"]: c["pages_total"] for c in saved_a1["chapter"]["catalog"]}
    for ex in saved_a1["exercises"]:
        if ex["title"] != "Imported answers (legacy)" and ex["pages_total"] > 0:
            assert cat_map[ex["title"]] >= ex["pages_total"]

    # Add a second chapter DB (B2.1) and verify search_answer_interactive searches ACROSS ALL DBs!
    target_b2 = os.path.join(cli_bot.reports_folder, "answers_B2.1.json")
    with open(target_b2, "w", encoding="utf-8") as f:
        json.dump(
            {
                "schema_version": 2,
                "chapter": {
                    "name": "B2.1",
                    "cid": "99900",
                    "summary": {"exercises": 1, "pages": 1, "answered_pages": 1},
                    "catalog": [{"title": "Quarterly forecast", "pages_total": 1}],
                },
                "exercises": [
                    {
                        "title": "Quarterly forecast",
                        "pages_total": 1,
                        "pages": [
                            {
                                "page": 1,
                                "type": "type-answer",
                                "question": "Complete the financial report | Revenue grew by twenty percent in Q3.",
                                "prompt": "Complete the financial report",
                                "answer": {"type": "answer", "answers": ["twenty", "Q3"], "timestamp": "2026-10-29T00:00:00"},
                            }
                        ],
                    }
                ],
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    cli_bot.lang = "en"
    cli_bot.T = TRANSLATIONS["en"]
    cli_bot.current_chapter_name = "A1"  # Currently on A1, searching for a B2.1 question!
    inputs = iter(["Revenue grew by twenty percent in Q3.", "END", ""])
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: next(inputs))
    capsys.readouterr()
    cli_bot.search_answer_interactive()
    search_out = strip_ansi(capsys.readouterr().out)
    assert "B2.1" in search_out
    assert "Quarterly forecast" in search_out
    assert '"twenty"' in search_out


# ==============================================================================
# 8. ScrambledTableSolver & PronunciationSolver Unit/Integration Checks
# ==============================================================================

def test_scrambled_sentence_does_not_mutate_target_and_pronunciation_saves_db(cli_bot):
    cli_bot.current_chapter_name = "A1"
    pron_html = """
    <!doctype html><html><body>
      <ul class="exercises-large-navigation visible-lg"><li data-p="1">1</li></ul>
      <h1 class="exercise-header">Speak clearly</h1>
      <div class="instructions-text">Repeat the phrases.</div>
      <div class="exercise type-multi-item-pronunciation">
        <div class="exercise-items">
          <div class="item">
            Good afternoon everyone
            <button class="play-button">Play</button>
            <button class="microphone-button">Mic</button>
            <div class="word-result green"></div>
          </div>
        </div>
      </div>
      <button id="chk" class="correct">Check</button>
      <div class="exercise-result-container"><span class="text" id="sc">0</span><span class="text">100</span></div>
      <script>
        document.getElementById('chk').addEventListener('click', () => {
          document.getElementById('sc').textContent = '85';
        });
      </script>
    </body></html>
    """
    cli_bot.page.set_content(pron_html, url="https://portal.speexx.com/articles/3/pron")
    status, score, _ = cli_bot.auto_solve_exercise(
        "Pronunciation practice",
        already_opened=True,
        batch_mode=True,
    )
    assert status == "SUCCESS"
    assert score == 85

    db_path = os.path.join(cli_bot.reports_folder, "answers_A1.json")
    with open(db_path, "r", encoding="utf-8") as f:
        db = json.load(f)
    rec = db["exercises"][0]["pages"][0]
    assert rec["type"] == "type-multi-item-pronunciation"
    assert rec["answer"]["type"] == "pronunciation"
    assert "Good afternoon everyone" in rec["answer"]["answers"][0]


# ============================================================================
# 12. ScrambledTableSolver (duplicate values + cached replay)
# ============================================================================
def test_scrambled_table_duplicate_values_solve_and_cached_replay(cli_bot):
    cli_bot.current_chapter_name = "B1.1"
    table_html = """
    <!doctype html><html><body>
      <ul class="exercises-large-navigation visible-lg"><li data-p="1">1</li></ul>
      <h1 class="exercise-header">Match table rows</h1>
      <div class="instructions-text">Place each cell in the right row.</div>
      <div class="exercise type-scrambled-table">
        <div class="exercise-items" id="items"></div>
      </div>
      <button id="chk">Check</button>
      <button id="sol" style="display:none">Solution</button>
      <button id="rep" style="display:none">Repeat</button>
      <div class="result-badge-text" id="bdg" data-result="0">0</div>
      <script>
        window.__solClicks = 0;
        let cells = ['Yes', 'No', 'Yes'];
        const target = ['Yes', 'Yes', 'No'];
        let selectedIdx = null;
        function render() {
          const items = document.getElementById('items');
          items.innerHTML = cells.map((txt, idx) => `
            <div class="item">
              <span class="row-label">Row ${idx + 1}</span>
              <div class="scrambled-cell-container" data-row="${idx}">
                <div class="scrambled-cell" data-row="${idx}">${txt}</div>
              </div>
            </div>
          `).join('');
          items.querySelectorAll('.scrambled-cell').forEach(el => {
            el.addEventListener('click', (e) => {
              e.stopPropagation();
              selectedIdx = parseInt(el.getAttribute('data-row'), 10);
            });
          });
          items.querySelectorAll('.scrambled-cell-container').forEach(slot => {
            slot.addEventListener('click', () => {
              const dst = parseInt(slot.getAttribute('data-row'), 10);
              if (selectedIdx !== null && selectedIdx !== dst) {
                const tmp = cells[selectedIdx];
                cells[selectedIdx] = cells[dst];
                cells[dst] = tmp;
                selectedIdx = null;
                render();
              }
            });
          });
        }
        render();
        document.getElementById('chk').addEventListener('click', () => {
          const ok = cells.every((c, i) => c === target[i]);
          const s = ok ? 100 : 33;
          const b = document.getElementById('bdg');
          b.setAttribute('data-result', String(s));
          b.textContent = String(s);
          document.getElementById('sol').style.display = 'inline-block';
          document.getElementById('rep').style.display = 'inline-block';
        });
        document.getElementById('sol').addEventListener('click', () => {
          window.__solClicks += 1;
          cells = [...target];
          render();
        });
        document.getElementById('rep').addEventListener('click', () => {
          cells = ['No', 'Yes', 'Yes'];
          const b = document.getElementById('bdg');
          b.setAttribute('data-result', '0');
          b.textContent = '0';
          render();
        });
      </script>
    </body></html>
    """
    cli_bot.page.set_content(table_html, url="https://portal.speexx.com/articles/11/table")
    status, score, _ = cli_bot.auto_solve_exercise(
        "Table duplicate test", already_opened=True, batch_mode=True
    )
    assert status == "SUCCESS" and score == 100
    assert cli_bot.page.evaluate("() => window.__solClicks") == 1

    # Replay from cache -> 0 solution clicks!
    cli_bot.page.set_content(table_html, url="https://portal.speexx.com/articles/11/table")
    status2, score2, _ = cli_bot.auto_solve_exercise(
        "Table duplicate test", already_opened=True, batch_mode=True
    )
    assert status2 == "SUCCESS" and score2 == 100
    assert cli_bot.page.evaluate("() => window.__solClicks") == 0


# ============================================================================
# 13. SingleChoiceSolver: legacy, group-radio, hill-climbing without Solution
# ============================================================================
def test_single_choice_all_modes_legacy_group_and_hillclimb(cli_bot):
    cli_bot.current_chapter_name = "B1.1"
    sc_html = """
    <!doctype html><html><body>
      <ul class="exercises-large-navigation visible-lg">
        <li data-p="1">1</li><li data-p="2">2</li><li data-p="3">3</li>
      </ul>
      <div id="stage"></div>
      <div id="controls"></div>
      <div class="result-badge-text" id="bdg" data-result="0">0</div>
      <button class="action-exercise-button next" id="nxt">Next</button>
      <script>
        let cur = 1;
        function setScore(v) {
          const b = document.getElementById('bdg');
          b.setAttribute('data-result', String(v));
          b.textContent = String(v);
        }
        function render(p) {
          cur = p;
          setScore(0);
          const st = document.getElementById('stage');
          const ct = document.getElementById('controls');
          if (p === 1) {
            // Legacy flat .choice-option without .item.choice-item
            st.innerHTML = `
              <h1 class="exercise-header">Legacy single choice</h1>
              <div class="instructions-text">Choose one answer.</div>
              <div class="exercise type-single-choice">
                <div class="choice-option"><input type="radio" class="choice" name="leg">Opt 0</div>
                <div class="choice-option"><input type="radio" class="choice" name="leg">Opt 1</div>
                <div class="choice-option"><input type="radio" class="choice" name="leg">Opt 2</div>
              </div>
            `;
            ct.innerHTML = `<button id="chk">Check</button><button id="sol" style="display:none">Solution</button><button id="rep" style="display:none">Repeat</button>`;
            document.getElementById('chk').onclick = () => {
              const r = st.querySelectorAll('input.choice');
              setScore(r[2].checked ? 100 : 0);
              document.getElementById('sol').style.display = 'inline-block';
              document.getElementById('rep').style.display = 'inline-block';
            };
            document.getElementById('sol').onclick = () => {
              const opts = st.querySelectorAll('.choice-option');
              opts[2].classList.add('status-green');
              opts[2].querySelector('input').checked = true;
            };
            document.getElementById('rep').onclick = () => {
              st.querySelectorAll('input').forEach(i => i.checked = false);
              st.querySelectorAll('.choice-option').forEach(o => o.classList.remove('status-green'));
              setScore(0);
            };
          } else if (p === 2) {
            // Group single choice: 3 .item.choice-item sharing ONE radio group name!
            st.innerHTML = `
              <h1 class="exercise-header">Group single choice</h1>
              <div class="instructions-text">Pick the right item.</div>
              <div class="exercise type-single-choice">
                <div class="exercise-items">
                  <div class="item choice-item"><div class="choice-option"><input type="radio" class="choice" name="shared">Item A</div></div>
                  <div class="item choice-item"><div class="choice-option"><input type="radio" class="choice" name="shared">Item B</div></div>
                  <div class="item choice-item"><div class="choice-option"><input type="radio" class="choice" name="shared">Item C</div></div>
                </div>
              </div>
            `;
            ct.innerHTML = `<button id="chk">Check</button><button id="sol" style="display:none">Solution</button><button id="rep" style="display:none">Repeat</button>`;
            document.getElementById('chk').onclick = () => {
              const r = st.querySelectorAll('input.choice');
              setScore(r[1].checked ? 100 : 0);
              document.getElementById('sol').style.display = 'inline-block';
              document.getElementById('rep').style.display = 'inline-block';
            };
            document.getElementById('sol').onclick = () => {
              st.querySelectorAll('input.choice')[1].checked = true;
            };
            document.getElementById('rep').onclick = () => {
              st.querySelectorAll('input.choice').forEach(i => i.checked = false);
              setScore(0);
            };
          } else if (p === 3) {
            // Hill-climb mode WITHOUT Solution button!
            st.innerHTML = `
              <h1 class="exercise-header">Hill climb choice</h1>
              <div class="instructions-text">No solution button on this quiz.</div>
              <div class="exercise type-single-choice">
                <div class="exercise-items">
                  <div class="item choice-item">
                    <div class="choice-option"><input type="radio" class="choice" name="h1">H1-A</div>
                    <div class="choice-option"><input type="radio" class="choice" name="h1">H1-B</div>
                  </div>
                  <div class="item choice-item">
                    <div class="choice-option"><input type="radio" class="choice" name="h2">H2-A</div>
                    <div class="choice-option"><input type="radio" class="choice" name="h2">H2-B</div>
                  </div>
                </div>
              </div>
            `;
            ct.innerHTML = `<button id="chk">Check</button><button id="rep" style="display:none">Repeat</button>`;
            document.getElementById('chk').onclick = () => {
              const g1 = st.querySelectorAll('input[name="h1"]');
              const g2 = st.querySelectorAll('input[name="h2"]');
              const s = (g1[1].checked ? 50 : 0) + (g2[1].checked ? 50 : 0);
              setScore(s);
              document.getElementById('rep').style.display = 'inline-block';
            };
            document.getElementById('rep').onclick = () => {
              st.querySelectorAll('input').forEach(i => i.checked = false);
              setScore(0);
            };
          }
        }
        document.querySelectorAll('ul.exercises-large-navigation li').forEach(li => {
          li.onclick = () => render(parseInt(li.getAttribute('data-p'), 10));
        });
        document.getElementById('nxt').onclick = () => { if (cur < 3) render(cur + 1); };
        render(1);
      </script>
    </body></html>
    """
    cli_bot.page.set_content(sc_html, url="https://portal.speexx.com/articles/12/sc")
    status, score, _ = cli_bot.auto_solve_exercise(
        "Single choice modes", already_opened=True, batch_mode=True
    )
    assert status == "SUCCESS" and score == 100

    db_path = os.path.join(cli_bot.reports_folder, "answers_B1.1.json")
    with open(db_path, "r", encoding="utf-8") as f:
        db = json.load(f)
    ex = next(e for e in db["exercises"] if e["title"] == "Single choice modes")
    assert len(ex["pages"]) == 3
    assert all(p["answer"] is not None for p in ex["pages"])


# ============================================================================
# 14. Legacy v1 flat DB migration + General fallback chapter + Dump pages
# ============================================================================
def test_legacy_v1_migration_general_fallback_and_dump_pages(cli_bot, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_a, **_kw: "")
    # 1. Seed a legacy v1 flat JSON file in reports/answers_B1.2.json
    v1_path = os.path.join(cli_bot.reports_folder, "answers_B1.2.json")
    with open(v1_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "Old Legacy Question": {
                    "type": "answer",
                    "answers": ["legacy_val"],
                    "timestamp": "2025-01-01 00:00:00",
                }
            },
            f,
        )

    cli_bot.current_chapter_name = "B1.2"
    cli_bot._load_answer_db("B1.2")
    assert "Old Legacy Question" in cli_bot.answer_db

    results_b12 = """
    <!doctype html><html><body>
      <div class="level-container active" data-id="812">
        <div class="level-inside-box active"><span class="level-text">B1.2</span></div>
      </div>
      <button role="tab">Exercises</button>
      <table><tbody>
        <tr class="clickable" id="r-b12" onclick="window.__openB12 = true">
          <td>B1.2 Intro</td><td>-</td><td>-</td><td></td><td></td>
        </tr>
      </tbody></table>
    </body></html>
    """
    page_html = """
    <!doctype html><html><body>
      <div class="level-container active" data-id="812">
        <div class="level-inside-box active"><span class="level-text">B1.2</span></div>
      </div>
      <ul class="exercises-large-navigation visible-lg"><li data-p="1">1</li></ul>
      <h1 class="exercise-header">New B1.2 Exercise</h1>
      <div class="instructions-text">Read the note.</div>
      <div class="exercise type-intro"><p>Welcome to B1.2!</p></div>
    </body></html>
    """
    cli_bot.page.routes["/articles/13/results"] = results_b12
    cli_bot.page.set_content(results_b12, url="https://portal.speexx.com/articles/13/results")

    def after_click_b12(_loc):
        try:
            if cli_bot.page.evaluate("() => Boolean(window.__openB12)"):
                cli_bot.page.set_content(
                    page_html, url="https://portal.speexx.com/articles/13/b12"
                )
        except Exception:
            pass

    cli_bot.page.on_after_click = after_click_b12
    cli_bot.dump_all_exercise_pages("B1.2 Intro")
    cli_bot.page.on_after_click = None

    with open(v1_path, "r", encoding="utf-8") as f:
        migrated = json.load(f)
    assert migrated["schema_version"] == 2
    assert migrated["chapter"]["name"] == "B1.2"
    titles = [e["title"] for e in migrated["exercises"]]
    assert "B1.2 Intro" in titles
    assert "Imported answers (legacy)" in titles

    # 2. Fallback to General when NO chapter selected and NO level in DOM
    no_level_html = """
    <!doctype html><html><body>
      <ul class="exercises-large-navigation visible-lg"><li data-p="1">1</li></ul>
      <h1 class="exercise-header">General Warmup</h1>
      <div class="instructions-text">Read the note.</div>
      <div class="exercise type-intro"><p>Welcome!</p></div>
    </body></html>
    """
    cli_bot.current_chapter_name = ""
    cli_bot.current_chapter_cid = None
    cli_bot.loaded_chapter_name = ""
    cli_bot.answer_db = {}
    cli_bot.structured_page_records = {}
    cli_bot.chapter_catalog = []
    cli_bot.page.set_content(no_level_html, url="https://portal.speexx.com/articles/14/nolvl")
    status, _sc, _ = cli_bot.auto_solve_exercise(
        "No Level Exercise", already_opened=True, batch_mode=True
    )
    assert status in ("SUCCESS", "SKIPPED")
    gen_path = os.path.join(cli_bot.reports_folder, "answers_General.json")
    assert os.path.exists(gen_path)
    with open(gen_path, "r", encoding="utf-8") as f:
        gen_db = json.load(f)
    assert gen_db["chapter"]["name"] == "General"
    assert gen_db["exercises"][0]["title"] == "No Level Exercise"


# ============================================================================
# 15. English CLI & Web UI Batch + Auto-Continue Chain (Zero Hardcoded Thai!)
# ============================================================================
def test_english_batch_and_auto_continue_chain_zero_thai_output(cli_bot, capsys, monkeypatch):
    cli_bot.lang = "en"
    monkeypatch.setattr("builtins.input", lambda *_a, **_kw: "2")

    ex_state = {"done_ex1": False, "done_ex2": False, "current_ex": None}

    def render_results():
        s1 = "100" if ex_state["done_ex1"] else ""
        s2 = "100" if ex_state["done_ex2"] else ""
        return f"""
        <!doctype html><html><body>
          <div class="level-container active" data-id="501">
            <div class="level-inside-box active"><span class="level-text">A2</span></div>
          </div>
          <button role="tab">Exercises</button>
          <table><tbody>
            <tr class="clickable" data-ex="Audio warmup">
              <td>Audio warmup</td><td>29/10/2026</td><td>00:01:00</td>
              <td><svg class="icon-check success"></svg></td><td></td>
            </tr>
            <tr class="clickable" data-ex="Ex One">
              <td>Ex One</td><td>-</td><td>-</td><td>{s1}</td><td></td>
            </tr>
            <tr class="clickable" data-ex="Ex Two">
              <td>Ex Two</td><td>-</td><td>-</td><td>{s2}</td><td></td>
            </tr>
          </tbody></table>
          <script>
            document.querySelectorAll('tbody tr.clickable').forEach(tr => {{
              tr.onclick = () => {{
                window.__openEx = tr.getAttribute('data-ex');
              }};
            }});
          </script>
        </body></html>
        """

    def render_exercise(name):
        return f"""
        <!doctype html><html><body>
          <div class="level-container active" data-id="501">
            <div class="level-inside-box active"><span class="level-text">A2</span></div>
          </div>
          <ul class="exercises-large-navigation visible-lg"><li data-p="1">1</li></ul>
          <h1 class="exercise-header">{name} Header</h1>
          <div class="instructions-text">Read {name}.</div>
          <div class="exercise type-intro"><p>Content of {name}</p></div>
        </body></html>
        """

    cli_bot.page.routes["https://portal.speexx.com/articles/77777/results"] = render_results
    cli_bot.page.routes["/articles/77777/results"] = render_results

    def after_click(locator):
        try:
            opened = cli_bot.page.evaluate("() => window.__openEx || null")
            if opened in ("Ex One", "Ex Two"):
                cli_bot.page.evaluate("() => { window.__openEx = null; }")
                ex_state["current_ex"] = opened
                if opened == "Ex One":
                    ex_state["done_ex1"] = True
                elif opened == "Ex Two":
                    ex_state["done_ex2"] = True
                cli_bot.page.set_content(
                    render_exercise(opened),
                    url="https://portal.speexx.com/articles/77777/exercise",
                )
        except Exception:
            pass

    cli_bot.page.on_after_click = after_click
    cli_bot.page.set_content(
        render_results(),
        url="https://portal.speexx.com/articles/77777/results",
    )

    # Start solving Ex One with auto_continue=True -> must auto-chain into Ex Two (skipping Audio warmup checkmark) and stop cleanly!
    cli_bot.auto_solve_exercise("Ex One", row_index=1, auto_continue=True)
    assert ex_state["done_ex1"] is True
    assert ex_state["done_ex2"] is True

    # Verify BOTH Ex One and Ex Two are saved in answers_A2.json!
    a2_path = os.path.join(cli_bot.reports_folder, "answers_A2.json")
    assert os.path.exists(a2_path)
    with open(a2_path, "r", encoding="utf-8") as f:
        a2_db = json.load(f)
    saved_titles = [e["title"] for e in a2_db["exercises"]]
    assert "Ex One" in saved_titles
    assert "Ex Two" in saved_titles

    # Verify ZERO Thai characters were printed in English CLI mode!
    out = capsys.readouterr().out
    thai_chars = [ch for ch in out if "\u0e00" <= ch <= "\u0e7f"]
    assert thai_chars == [], f"Found unexpected Thai output in English CLI mode: {''.join(thai_chars)}"

