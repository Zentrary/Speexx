import json
import os
import shutil
import pytest

from main import ExerciseEngine


UI_LANGS = [
    pytest.param(
        {
            "code": "en",
            "check": "Check",
            "solution": "Solution",
            "repeat": "Repeat",
            "start": "Start",
            "close": "Close",
        },
        id="EN-UI",
    ),
    pytest.param(
        {
            "code": "th",
            "check": "ตรวจคำตอบ",
            "solution": "ดูเฉลย",
            "repeat": "ลองอีกครั้ง",
            "start": "เริ่ม",
            "close": "ปิด",
        },
        id="TH-UI",
    ),
]


def _read_db(cli_bot, chapter="A1"):
    path = os.path.join(cli_bot.reports_folder, f"answers_{chapter}.json")
    assert os.path.exists(path), f"Expected DB file {path}"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ==============================================================================
# 0. Registry Audit: Every ExerciseEngine type maps to a working solver
# ==============================================================================
def test_exercise_engine_detects_all_15_types(cli_bot):
    engine = ExerciseEngine(cli_bot.page, cli_bot.logger)
    cases = [
        ('<div class="exercise type-intro"></div>', "type-intro", False),
        ('<div class="video"><video src="a.mp4"></video></div>', "type-video", True),
        ('<div class="exercise type-video"><video src="a.mp4"></video></div>', "type-video", True),
        ('<div class="exercise"><div class="video"></div></div>', "type-video", True),
        ('<div class="exercise type-answer"></div>', "type-answer", True),
        ('<div class="exercise type-drag-drop"></div>', "type-drag-drop", True),
        ('<div class="exercise type-drag-drop layout-table"></div>', "type-drag-drop-table", True),
        ('<div class="exercise type-drag-drop layout-grid-duo"></div>', "type-drag-drop-table", True),
        ('<div class="exercise type-single-choice"></div>', "type-single-choice", True),
        ('<div class="exercise type-multiple-choice"></div>', "type-multiple-choice", True),
        ('<div class="exercise type-scrambled-sentence"></div>', "type-scrambled-sentence", True),
        ('<div class="exercise type-scrambled-table"></div>', "type-scrambled-table", True),
        ('<div class="exercise type-picture-choice"></div>', "type-picture-choice", True),
        ('<div class="exercise type-toggle-solution"></div>', "type-toggle-solution", True),
        ('<div class="exercise type-mark-text"></div>', "type-mark-text", True),
        ('<div class="exercise type-pronunciation"></div>', "type-pronunciation", True),
        ('<div class="exercise type-single-item-pronunciation"></div>', "type-single-item-pronunciation", True),
        ('<div class="exercise type-multi-item-pronunciation"></div>', "type-multi-item-pronunciation", True),
        ('<div class="exercise type-multiple-item-pronunciation"></div>', "type-multiple-item-pronunciation", True),
    ]
    for html_frag, expected_type, has_solver in cases:
        cli_bot.page.set_content(f"<!doctype html><html><body>{html_frag}</body></html>")
        detected = engine.detect_type()
        assert detected == expected_type, f"HTML {html_frag} -> got {detected}, expected {expected_type}"
        solver = engine.get_solver(detected, exercise_title="Audit", page_number=1)
        assert (solver is not None) is has_solver


# ==============================================================================
# 1. type-intro (EN & TH)
# ==============================================================================
@pytest.mark.parametrize("ui", UI_LANGS)
def test_type_01_intro(cli_bot, ui):
    cli_bot.lang = ui["code"]
    cli_bot.current_chapter_name = "A1"
    html = """
    <!doctype html><html><body>
      <ul class="exercises-large-navigation visible-lg"><li data-p="1">1</li></ul>
      <h1 class="exercise-header">Welcome to Unit 1</h1>
      <div class="instructions-text">Read the grammar overview below.</div>
      <div class="exercise type-intro"><p>Present simple overview.</p></div>
    </body></html>
    """
    cli_bot.page.set_content(html, url="https://portal.speexx.com/articles/100/intro")
    status, _score, _ = cli_bot.auto_solve_exercise("Unit 1 Intro", already_opened=True, batch_mode=True)
    assert status == "SKIPPED"
    db = _read_db(cli_bot, "A1")
    rec = db["exercises"][0]["pages"][0]
    assert rec["type"] == "type-intro"
    assert rec["answer"]["type"] == "intro"


# ==============================================================================
# 2. type-video: Start-gated + .exercise.type-video wrapper (EN & TH)
# ==============================================================================
@pytest.mark.parametrize("ui", UI_LANGS)
def test_type_02_video_start_gated_and_exercise_wrapper(cli_bot, ui):
    cli_bot.lang = ui["code"]
    cli_bot.current_chapter_name = "A1"
    html = f"""
    <!doctype html><html><body>
      <ul class="exercises-large-navigation visible-lg"><li data-p="1">1</li></ul>
      <h1 class="exercise-header">Watch the dialogue</h1>
      <div class="instructions-text">Click {ui['start']} to play the video.</div>
      <div class="exercise type-video" id="vid-wrap">
        <button id="start-btn">{ui['start']}</button>
      </div>
      <button class="action-exercise-button next" id="nxt" disabled>Next</button>
      <script>
        document.getElementById('start-btn').onclick = () => {{
          const wrap = document.getElementById('vid-wrap');
          wrap.innerHTML = '<video id="v" src="https://cdn.speexx.com/media/unit1.mp4"></video>';
          const v = document.getElementById('v');
          let ct = 0;
          Object.defineProperty(v, 'duration', {{ get: () => 25 }});
          Object.defineProperty(v, 'currentTime', {{
            get: () => ct,
            set: (val) => {{ ct = val; if (ct >= 24) document.getElementById('nxt').disabled = false; }}
          }});
          Object.defineProperty(v, 'ended', {{ get: () => ct >= 24 }});
          v.play = () => {{ document.getElementById('nxt').disabled = false; return Promise.resolve(); }};
        }};
      </script>
    </body></html>
    """
    cli_bot.page.set_content(html, url="https://portal.speexx.com/articles/100/video")
    status, score, _ = cli_bot.auto_solve_exercise("Unit 1 Video", already_opened=True, batch_mode=True)
    assert status == "SUCCESS" and score == 100
    db = _read_db(cli_bot, "A1")
    rec = db["exercises"][0]["pages"][0]
    assert rec["type"] == "type-video"
    assert "https://cdn.speexx.com/media/unit1.mp4" in rec["answer"]["answers"]


# ==============================================================================
# 3. type-answer: multi-blank + apostrophes + cached replay (EN & TH)
# ==============================================================================
@pytest.mark.parametrize("ui", UI_LANGS)
def test_type_03_answer_fill_blanks_and_cache(cli_bot, ui):
    cli_bot.lang = ui["code"]
    cli_bot.current_chapter_name = "A1"
    html = f"""
    <!doctype html><html><body>
      <ul class="exercises-large-navigation visible-lg"><li data-p="1">1</li></ul>
      <h1 class="exercise-header">Complete the contractions</h1>
      <div class="instructions-text">Type the missing words.</div>
      <div class="exercise type-answer">
        <div class="exercise-items">
          <div class="item"><input class="answer" id="a0" value=""> glad you're here, and we <input class="answer-gap" id="a1" value=""> late.</div>
        </div>
      </div>
      <button id="chk" class="correct">{ui['check']}</button>
      <button id="sol" style="display:none">{ui['solution']}</button>
      <button id="rep" style="display:none">{ui['repeat']}</button>
      <div class="result-badge-text" id="bdg" data-result="0">0</div>
      <script>
        window.__solClicks = 0;
        const setScore = s => {{ const b = document.getElementById('bdg'); b.setAttribute('data-result', s); b.textContent = s; }};
        document.getElementById('chk').onclick = () => {{
          const ok = document.getElementById('a0').value.trim() === "I'm" &&
                     document.getElementById('a1').value.trim() === "aren't";
          setScore(ok ? 100 : 0);
          document.getElementById('sol').style.display = 'inline-block';
          document.getElementById('rep').style.display = 'inline-block';
        }};
        document.getElementById('sol').onclick = () => {{
          window.__solClicks++;
          document.getElementById('a0').value = "I'm";
          document.getElementById('a1').value = "aren't";
        }};
        document.getElementById('rep').onclick = () => {{
          document.getElementById('a0').value = "";
          document.getElementById('a1').value = "";
          setScore(0);
        }};
      </script>
    </body></html>
    """
    cli_bot.page.set_content(html, url="https://portal.speexx.com/articles/100/ans")
    st1, sc1, _ = cli_bot.auto_solve_exercise("Contractions", already_opened=True, batch_mode=True)
    assert st1 == "SUCCESS" and sc1 == 100
    assert cli_bot.page.evaluate("() => window.__solClicks") == 1

    # Cached replay -> 0 solution clicks!
    cli_bot.page.set_content(html, url="https://portal.speexx.com/articles/100/ans")
    st2, sc2, _ = cli_bot.auto_solve_exercise("Contractions", already_opened=True, batch_mode=True)
    assert st2 == "SUCCESS" and sc2 == 100
    assert cli_bot.page.evaluate("() => window.__solClicks") == 0


# ==============================================================================
# 4. type-drag-drop: BOTH click-to-place AND mouse-drag-only + duplicate tiles (EN & TH)
# ==============================================================================
@pytest.mark.parametrize("ui", UI_LANGS)
@pytest.mark.parametrize("drag_only", [False, True], ids=["click-mode", "mouse-drag-only"])
def test_type_04_drag_drop_click_and_mouse_drag_modes(cli_bot, ui, drag_only):
    cli_bot.lang = ui["code"]
    cli_bot.current_chapter_name = "A1"
    html = f"""
    <!doctype html><html><body>
      <ul class="exercises-large-navigation visible-lg"><li data-p="1">1</li></ul>
      <h1 class="exercise-header">Prepositions drag & drop</h1>
      <div class="instructions-text">Place each tile into the right gap.</div>
      <div class="exercise type-drag-drop">
        <div class="exercise-items" id="slots"></div>
        <div class="draggable-container" id="pool"></div>
      </div>
      <button id="chk" class="correct">{ui['check']}</button>
      <button id="sol" style="display:none">{ui['solution']}</button>
      <button id="rep" style="display:none">{ui['repeat']}</button>
      <div class="result-badge-text" id="bdg" data-result="0">0</div>
      <script>
        const DRAG_ONLY = {'true' if drag_only else 'false'};
        const target = ['to', 'from', 'to'];
        let slotVals = [null, 'from', null]; // Middle slot prefilled! Tests destination_armed reset!
        let bank = ['to', 'to'];
        let armedSlot = null;
        function setScore(s) {{ const b = document.getElementById('bdg'); b.setAttribute('data-result', s); b.textContent = s; }}
        function render() {{
          const sDiv = document.getElementById('slots');
          sDiv.innerHTML = slotVals.map((v, idx) => `
            <div class="item">
              <span class="drag-drop-placeholder" data-slot="${{idx}}"
                    data-box-x="${{100 + idx * 150}}" data-box-y="100" data-box-w="100" data-box-h="36">
                ${{v ? `<div class="drag-drop">${{v}}</div>` : ''}}
              </span>
            </div>
          `).join('');
          const pDiv = document.getElementById('pool');
          pDiv.innerHTML = bank.map((w, idx) => `
            <div class="drag-drop" data-bank="${{idx}}"
                 data-box-x="${{100 + idx * 150}}" data-box-y="260" data-box-w="100" data-box-h="36">${{w}}</div>
          `).join('');
          if (!DRAG_ONLY) {{
            sDiv.querySelectorAll('.drag-drop-placeholder').forEach(el => {{
              el.onclick = () => {{ armedSlot = parseInt(el.getAttribute('data-slot'), 10); }};
            }});
            pDiv.querySelectorAll('.drag-drop').forEach(el => {{
              el.onclick = () => {{
                const bIdx = parseInt(el.getAttribute('data-bank'), 10);
                if (armedSlot !== null && slotVals[armedSlot] === null) {{
                  slotVals[armedSlot] = bank.splice(bIdx, 1)[0];
                  // Advance armedSlot to next empty slot
                  const nxt = slotVals.findIndex((x, i) => i > armedSlot && x === null);
                  armedSlot = nxt >= 0 ? nxt : null;
                  render();
                }}
              }};
            }});
          }}
        }}
        window.__onSimulatedDrag = (sx, sy, tx, ty) => {{
          // Hit-test bank item at (sx, sy) and slot at (tx, ty)
          const bIdx = Math.round((sx - 150) / 150);
          const sIdx = Math.round((tx - 150) / 150);
          if (bIdx >= 0 && bIdx < bank.length && sIdx >= 0 && sIdx < slotVals.length && slotVals[sIdx] === null) {{
            slotVals[sIdx] = bank.splice(bIdx, 1)[0];
            render();
          }}
        }};
        render();
        document.getElementById('chk').onclick = () => {{
          const ok = slotVals.every((v, i) => v === target[i]);
          setScore(ok ? 100 : 33);
          document.getElementById('sol').style.display = 'inline-block';
          document.getElementById('rep').style.display = 'inline-block';
        }};
        document.getElementById('sol').onclick = () => {{
          slotVals = [...target];
          bank = [];
          render();
        }};
        document.getElementById('rep').onclick = () => {{
          slotVals = [null, 'from', null];
          bank = ['to', 'to'];
          armedSlot = null;
          setScore(0);
          render();
        }};
      </script>
    </body></html>
    """
    cli_bot.page.set_content(html, url="https://portal.speexx.com/articles/100/dnd")
    status, score, _ = cli_bot.auto_solve_exercise("Prepositions DND", already_opened=True, batch_mode=True)
    assert status == "SUCCESS" and score == 100


# ==============================================================================
# 5. type-drag-drop-table: Sparse columns + data-group-id no-solution fallback
# ==============================================================================
@pytest.mark.parametrize("has_solution_btn", [True, False], ids=["with-solution", "group-id-fallback"])
def test_type_05_drag_drop_table_sparse_columns_and_group_fallback(cli_bot, has_solution_btn):
    cli_bot.current_chapter_name = "A1"
    sol_btn_html = '<button id="sol" style="display:none">Solution</button>' if has_solution_btn else ""
    # 2 rows x 2 cols = 4 placeholders, but Col 0 has 2 items ('apple', 'pear') and Col 1 has 1 item ('milk') -> slot (row 1, col 1) is EMPTY!
    html = f"""
    <!doctype html><html><body>
      <ul class="exercises-large-navigation visible-lg"><li data-p="1">1</li></ul>
      <h1 class="exercise-header">Sort food and drinks</h1>
      <div class="instructions-text">Put each item into Column 1 (Fruit) or Column 2 (Drinks).</div>
      <div class="exercise type-drag-drop layout-table">
        <div class="exercise-items" id="grid"></div>
        <div class="draggable-container" id="pool"></div>
      </div>
      <button id="chk" class="correct">Check</button>
      {sol_btn_html}
      <button id="rep" style="display:none">Repeat</button>
      <div class="result-badge-text" id="bdg" data-result="0">0</div>
      <script>
        // Row-major slots: [r0c0, r0c1, r1c0, r1c1]
        // Expected: r0c0='apple', r0c1='milk', r1c0='pear', r1c1=null (EMPTY!)
        let slots = [null, null, null, null];
        let bank = [
          {{ text: 'milk', gid: '2' }},
          {{ text: 'apple', gid: '1' }},
          {{ text: 'pear', gid: '1' }}
        ];
        let armed = null;
        function setScore(s) {{ const b = document.getElementById('bdg'); b.setAttribute('data-result', s); b.textContent = s; }}
        function render() {{
          const g = document.getElementById('grid');
          g.innerHTML = [0, 1].map(r => `
            <div class="item">
              ${{[0, 1].map(c => {{
                const idx = r * 2 + c;
                const val = slots[idx];
                return `<div class="drag-drop-placeholder" data-idx="${{idx}}">${{val ? `<div class="drag-drop">${{val}}</div>` : ''}}</div>`;
              }}).join('')}}
            </div>
          `).join('');
          const p = document.getElementById('pool');
          p.innerHTML = bank.map((b, i) => `<div class="drag-drop" data-b="${{i}}" data-group-id="${{b.gid}}">${{b.text}}</div>`).join('');
          g.querySelectorAll('.drag-drop-placeholder').forEach(el => {{
            el.onclick = () => {{ armed = parseInt(el.getAttribute('data-idx'), 10); }};
          }});
          p.querySelectorAll('.drag-drop').forEach(el => {{
            el.onclick = () => {{
              const bi = parseInt(el.getAttribute('data-b'), 10);
              if (armed !== null && slots[armed] === null) {{
                slots[armed] = bank.splice(bi, 1)[0].text;
                const nxt = slots.findIndex((x, k) => k > armed && x === null);
                armed = nxt >= 0 ? nxt : null;
                render();
              }}
            }};
          }});
        }}
        render();
        document.getElementById('chk').onclick = () => {{
          const col0 = [slots[0], slots[2]].filter(Boolean).sort().join(',');
          const col1 = [slots[1], slots[3]].filter(Boolean).sort().join(',');
          const ok = col0 === 'apple,pear' && col1 === 'milk';
          setScore(ok ? 100 : 0);
          const sol = document.getElementById('sol');
          if (sol) sol.style.display = 'inline-block';
          document.getElementById('rep').style.display = 'inline-block';
        }};
        const solBtn = document.getElementById('sol');
        if (solBtn) {{
          solBtn.onclick = () => {{
            slots = ['apple', 'milk', 'pear', null];
            bank = [];
            render();
          }};
        }}
        document.getElementById('rep').onclick = () => {{
          slots = [null, null, null, null];
          bank = [
            {{ text: 'milk', gid: '2' }},
            {{ text: 'apple', gid: '1' }},
            {{ text: 'pear', gid: '1' }}
          ];
          armed = null;
          setScore(0);
          render();
        }};
      </script>
    </body></html>
    """
    cli_bot.page.set_content(html, url="https://portal.speexx.com/articles/100/dnd-table")
    title = f"Food Table {'sol' if has_solution_btn else 'gid'}"
    status, score, _ = cli_bot.auto_solve_exercise(title, already_opened=True, batch_mode=True)
    assert status == "SUCCESS" and score == 100


# ==============================================================================
# 6 & 7. type-single-choice & type-multiple-choice (Thai UI + Greedy & Solution)
# ==============================================================================
@pytest.mark.parametrize("ui", UI_LANGS)
def test_type_06_07_single_and_multiple_choice_bilingual(cli_bot, ui):
    cli_bot.lang = ui["code"]
    cli_bot.current_chapter_name = "A1"
    html = f"""
    <!doctype html><html><body>
      <ul class="exercises-large-navigation visible-lg">
        <li data-p="1">1</li><li data-p="2">2</li>
      </ul>
      <div id="stage"></div>
      <div id="controls"></div>
      <div class="result-badge-text" id="bdg" data-result="0">0</div>
      <button class="action-exercise-button next" id="nxt">Next</button>
      <script>
        let cur = 1;
        const setScore = s => {{ const b = document.getElementById('bdg'); b.setAttribute('data-result', s); b.textContent = s; }};
        function render(p) {{
          cur = p; setScore(0);
          const st = document.getElementById('stage');
          const ct = document.getElementById('controls');
          if (p === 1) {{
            st.innerHTML = `
              <h1 class="exercise-header">Single choice</h1>
              <div class="instructions-text">Select one option per sentence.</div>
              <div class="exercise type-single-choice">
                <div class="exercise-items">
                  <div class="item choice-item">
                    <div class="choice-option"><input type="radio" class="choice" name="q1">He go</div>
                    <div class="choice-option"><input type="radio" class="choice" name="q1">He goes</div>
                  </div>
                </div>
              </div>`;
            ct.innerHTML = `<button id="chk" class="correct">{ui['check']}</button><button id="sol" style="display:none">{ui['solution']}</button><button id="rep" style="display:none">{ui['repeat']}</button>`;
            document.getElementById('chk').onclick = () => {{
              setScore(st.querySelectorAll('input.choice')[1].checked ? 100 : 0);
              document.getElementById('sol').style.display = 'inline-block';
              document.getElementById('rep').style.display = 'inline-block';
            }};
            document.getElementById('sol').onclick = () => {{ st.querySelectorAll('input.choice')[1].checked = true; }};
            document.getElementById('rep').onclick = () => {{ st.querySelectorAll('input.choice').forEach(i => i.checked = false); setScore(0); }};
          }} else {{
            // Multi-item multiple-choice with 2 items!
            st.innerHTML = `
              <h1 class="exercise-header">Multiple choice</h1>
              <div class="instructions-text">Select all correct answers.</div>
              <div class="exercise type-multiple-choice">
                <div class="exercise-items">
                  <div class="item choice-item" id="m0">
                    <div class="choice-option"><input type="checkbox" class="choice">Monday</div>
                    <div class="choice-option"><input type="checkbox" class="choice">Table</div>
                    <div class="choice-option"><input type="checkbox" class="choice">Friday</div>
                  </div>
                  <div class="item choice-item" id="m1">
                    <div class="choice-option"><input type="checkbox" class="choice">Blue</div>
                    <div class="choice-option"><input type="checkbox" class="choice">Chair</div>
                  </div>
                </div>
              </div>`;
            ct.innerHTML = `<button id="chk" class="correct">{ui['check']}</button><button id="sol" style="display:none">{ui['solution']}</button><button id="rep" style="display:none">{ui['repeat']}</button>`;
            document.getElementById('chk').onclick = () => {{
              const c0 = document.getElementById('m0').querySelectorAll('input.choice');
              const c1 = document.getElementById('m1').querySelectorAll('input.choice');
              const ok = c0[0].checked && !c0[1].checked && c0[2].checked && c1[0].checked && !c1[1].checked;
              setScore(ok ? 100 : 0);
              document.getElementById('sol').style.display = 'inline-block';
              document.getElementById('rep').style.display = 'inline-block';
            }};
            document.getElementById('sol').onclick = () => {{
              const c0 = document.getElementById('m0').querySelectorAll('input.choice');
              const c1 = document.getElementById('m1').querySelectorAll('input.choice');
              c0[0].checked = true; c0[1].checked = false; c0[2].checked = true;
              c1[0].checked = true; c1[1].checked = false;
            }};
            document.getElementById('rep').onclick = () => {{
              st.querySelectorAll('input.choice').forEach(i => i.checked = false);
              setScore(0);
            }};
          }}
        }}
        document.querySelectorAll('ul.exercises-large-navigation li').forEach(li => {{
          li.onclick = () => render(parseInt(li.getAttribute('data-p'), 10));
        }});
        document.getElementById('nxt').onclick = () => {{ if (cur < 2) render(cur + 1); }};
        render(1);
      </script>
    </body></html>
    """
    cli_bot.page.set_content(html, url="https://portal.speexx.com/articles/100/choices")
    status, score, _ = cli_bot.auto_solve_exercise("Choices Suite", already_opened=True, batch_mode=True)
    assert status == "SUCCESS" and score == 100


# ==============================================================================
# 8. type-scrambled-sentence: Duplicate words ("the ... the") + Heuristic no-sol
# ==============================================================================
def test_type_08_scrambled_sentence_duplicate_words_and_heuristic_fallback(cli_bot):
    cli_bot.current_chapter_name = "B1.1"
    # Page 1: duplicate word 'the' + Solution button
    # Page 2: NO Solution button -> 3rd conditional heuristic ('I would have spent my vacation in the Caribbean .')!
    html = """
    <!doctype html><html><body>
      <ul class="exercises-large-navigation visible-lg"><li data-p="1">1</li><li data-p="2">2</li></ul>
      <div id="stage"></div>
      <div id="controls"></div>
      <div class="result-badge-text" id="bdg" data-result="0">0</div>
      <button class="action-exercise-button next" id="nxt">Next</button>
      <script>
        let cur = 1;
        const setScore = s => { const b = document.getElementById('bdg'); b.setAttribute('data-result', s); b.textContent = s; };
        function mountScrambled(wordsInit, target, allowSolution) {
          let words = [...wordsInit];
          let sel = null;
          const st = document.getElementById('stage');
          const ct = document.getElementById('controls');
          function draw() {
            st.innerHTML = `
              <h1 class="exercise-header">Scrambled ${cur}</h1>
              <div class="instructions-text">Order the blocks.</div>
              <div class="exercise type-scrambled-sentence">
                <div class="exercise-items">
                  <div class="item">
                    <div class="scrambled-sentence">
                      ${words.map((w, i) => `<div class="scrambled-block" data-i="${i}">${w}</div>`).join('')}
                    </div>
                  </div>
                </div>
              </div>`;
            const scEl = st.querySelector('.scrambled-sentence');
            scEl.addEventListener('change', () => {
              words = Array.from(scEl.querySelectorAll('.scrambled-block')).map(b => b.textContent.trim());
            });
            st.querySelectorAll('.scrambled-block').forEach((el, idx) => {
              el.onclick = () => {
                if (sel === null) sel = idx;
                else {
                  const t = words[sel]; words[sel] = words[idx]; words[idx] = t;
                  sel = null; draw();
                }
              };
            });
          }
          draw();
          ct.innerHTML = `<button id="chk" class="correct">Check</button>` +
            (allowSolution ? `<button id="sol" style="display:none">Solution</button>` : '') +
            `<button id="rep" style="display:none">Repeat</button>`;
          document.getElementById('chk').onclick = () => {
            const curWords = Array.from(st.querySelectorAll('.scrambled-block')).map(b => b.textContent.trim());
            const ok = curWords.length === target.length && curWords.every((w, i) => w === target[i]);
            setScore(ok ? 100 : 0);
            const sol = document.getElementById('sol');
            if (sol) sol.style.display = 'inline-block';
            document.getElementById('rep').style.display = 'inline-block';
          };
          const sol = document.getElementById('sol');
          if (sol) sol.onclick = () => { words = [...target]; sel = null; draw(); };
          document.getElementById('rep').onclick = () => { words = [...wordsInit]; sel = null; setScore(0); draw(); };
        }
        function render(p) {
          cur = p; setScore(0);
          if (p === 1) {
            mountScrambled(['door', 'the', 'Close', 'in', 'the', 'office.'], ['Close', 'the', 'door', 'in', 'the', 'office.'], true);
          } else {
            mountScrambled(['.','the Caribbean','in','spent','would','I','have','my','vacation'], ['I','would','have','spent','my','vacation','in','the Caribbean','.'], false);
          }
        }
        document.querySelectorAll('ul.exercises-large-navigation li').forEach(li => {
          li.onclick = () => render(parseInt(li.getAttribute('data-p'), 10));
        });
        document.getElementById('nxt').onclick = () => { if (cur < 2) render(cur + 1); };
        render(1);
      </script>
    </body></html>
    """
    cli_bot.page.set_content(html, url="https://portal.speexx.com/articles/100/scram")
    status, score, _ = cli_bot.auto_solve_exercise("Scrambled Full", already_opened=True, batch_mode=True)
    assert status == "SUCCESS" and score == 100


# ==============================================================================
# 9. type-scrambled-table: Mouse-drag reorder mode (EN & TH)
# ==============================================================================
def test_type_09_scrambled_table_mouse_drag_mode(cli_bot):
    cli_bot.current_chapter_name = "A1"
    html = """
    <!doctype html><html><body>
      <ul class="exercises-large-navigation visible-lg"><li data-p="1">1</li></ul>
      <h1 class="exercise-header">Match phone phrases</h1>
      <div class="instructions-text">Drag the right ending to each row.</div>
      <div class="exercise type-scrambled-table">
        <div class="exercise-items" id="rows"></div>
      </div>
      <button id="chk" class="correct">ตรวจคำตอบ</button>
      <button id="sol" style="display:none">เฉลย</button>
      <button id="rep" style="display:none">ทำซ้ำ</button>
      <div class="result-badge-text" id="bdg" data-result="0">0</div>
      <script>
        let cells = ['hold.', 'line, please.', 'second.'];
        const target = ['line, please.', 'hold.', 'second.'];
        const setScore = s => { const b = document.getElementById('bdg'); b.setAttribute('data-result', s); b.textContent = s; };
        function render() {
          const r = document.getElementById('rows');
          r.innerHTML = cells.map((txt, idx) => `
            <div class="item">
              <div class="scrambled-cell-container" data-r="${idx}"
                   data-box-x="200" data-box-y="${100 + idx * 80}" data-box-w="160" data-box-h="40">
                <div class="scrambled-cell" data-r="${idx}"
                     data-box-x="200" data-box-y="${100 + idx * 80}" data-box-w="160" data-box-h="40">${txt}</div>
              </div>
            </div>
          `).join('');
        }
        window.__onSimulatedDrag = (sx, sy, tx, ty) => {
          const sIdx = Math.round((sy - 120) / 80);
          const tIdx = Math.round((ty - 120) / 80);
          if (sIdx >= 0 && sIdx < cells.length && tIdx >= 0 && tIdx < cells.length && sIdx !== tIdx) {
            const tmp = cells[sIdx]; cells[sIdx] = cells[tIdx]; cells[tIdx] = tmp;
            render();
          }
        };
        render();
        document.getElementById('chk').onclick = () => {
          setScore(cells.every((c, i) => c === target[i]) ? 100 : 0);
          document.getElementById('sol').style.display = 'inline-block';
          document.getElementById('rep').style.display = 'inline-block';
        };
        document.getElementById('sol').onclick = () => { cells = [...target]; render(); };
        document.getElementById('rep').onclick = () => { cells = ['second.', 'hold.', 'line, please.']; setScore(0); render(); };
      </script>
    </body></html>
    """
    cli_bot.page.set_content(html, url="https://portal.speexx.com/articles/100/stbl")
    status, score, _ = cli_bot.auto_solve_exercise("Phone Table", already_opened=True, batch_mode=True)
    assert status == "SUCCESS" and score == 100


# ==============================================================================
# 10. type-picture-choice: Shifted session drag-drop-id collision + CDN change!
# ==============================================================================
def test_type_10_picture_choice_session_id_collision_resistance(cli_bot):
    cli_bot.current_chapter_name = "A1"
    # Seed cached answer from Session 1 where drag-drop-166 was 'office_a.jpg'.
    # In Session 2 HTML below, drag-drop-166 is assigned to 'office_WRONG.jpg' AND CDN domain changed from d111 to d222!
    # PictureChoiceSolver MUST match by image src/basename ('office_a.jpg', 'office_b.jpg'), NOT get tricked by drag-drop-166!
    db_path = os.path.join(cli_bot.reports_folder, "answers_A1.json")
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "schema_version": 2,
                "chapter": {"name": "A1", "cid": "1", "summary": {}, "catalog": []},
                "exercises": [
                    {
                        "title": "Office Pictures",
                        "pages_total": 1,
                        "pages": [
                            {
                                "page": 1,
                                "type": "type-picture-choice",
                                "question": "Match pictures | Desk and Laptop",
                                "prompt": "Match pictures",
                                "answer": {
                                    "type": "picture-choice",
                                    "answers": [
                                        {"item_idx": 0, "src": "https://d111.cloudfront.net/img/office_a.jpg", "drag_id": "drag-drop-166"},
                                        {"item_idx": 1, "src": "https://d111.cloudfront.net/img/office_b.jpg", "drag_id": "drag-drop-167"},
                                    ],
                                    "verified": True,
                                },
                            }
                        ],
                    }
                ],
            },
            f,
        )
    cli_bot._load_answer_db("A1", announce=False)

    html = """
    <!doctype html><html><body>
      <ul class="exercises-large-navigation visible-lg"><li data-p="1">1</li></ul>
      <h1 class="exercise-header">Match pictures</h1>
      <div class="instructions-text">Desk and Laptop</div>
      <div class="exercise type-picture-choice">
        <div class="exercise-items" id="items"></div>
        <div class="draggable-container" id="pool"></div>
      </div>
      <button id="chk" class="correct">Check</button>
      <div class="result-badge-text" id="bdg" data-result="0">0</div>
      <script>
        let placed = [null, null];
        // Notice drag-drop-166 is intentionally on office_b.jpg (collision trap!) and CDN host is d222!
        let pool = [
          { src: 'https://d222.cloudfront.net/img/office_b.jpg', id: 'drag-drop-166' },
          { src: 'https://d222.cloudfront.net/img/office_a.jpg', id: 'drag-drop-999' }
        ];
        let armed = null;
        function render() {
          const it = document.getElementById('items');
          it.innerHTML = [0, 1].map(i => `
            <div class="item">
              <div class="drag-drop-placeholder" data-i="${i}">
                ${placed[i] ? `<img class="picture-gap" src="${placed[i].src}" data-drag-drop-id="${placed[i].id}">` : ''}
              </div>
            </div>
          `).join('');
          const pl = document.getElementById('pool');
          pl.innerHTML = pool.map((p, i) => `<img class="drag-drop" data-pi="${i}" src="${p.src}" data-drag-drop-id="${p.id}">`).join('');
          it.querySelectorAll('.drag-drop-placeholder').forEach(el => {
            el.onclick = () => { armed = parseInt(el.getAttribute('data-i'), 10); };
          });
          pl.querySelectorAll('img').forEach(el => {
            el.onclick = () => {
              const pi = parseInt(el.getAttribute('data-pi'), 10);
              if (armed !== null && !placed[armed]) {
                placed[armed] = pool.splice(pi, 1)[0];
                armed = placed.findIndex(x => x === null);
                if (armed < 0) armed = null;
                render();
              }
            };
          });
        }
        render();
        document.getElementById('chk').onclick = () => {
          const ok = placed[0] && placed[0].src.endsWith('office_a.jpg') &&
                     placed[1] && placed[1].src.endsWith('office_b.jpg');
          const b = document.getElementById('bdg');
          b.setAttribute('data-result', ok ? '100' : '0');
          b.textContent = ok ? '100' : '0';
        };
      </script>
    </body></html>
    """
    cli_bot.page.set_content(html, url="https://portal.speexx.com/articles/100/pic")
    status, score, _ = cli_bot.auto_solve_exercise("Office Pictures", already_opened=True, batch_mode=True)
    assert status == "SUCCESS" and score == 100


# ==============================================================================
# 11. type-toggle-solution: NBSP normalization + DOM re-render (EN & TH)
# ==============================================================================
@pytest.mark.parametrize("ui", UI_LANGS)
def test_type_11_toggle_solution_nbsp_and_rerender(cli_bot, ui):
    cli_bot.lang = ui["code"]
    cli_bot.current_chapter_name = "A1"
    html = f"""
    <!doctype html><html><body>
      <ul class="exercises-large-navigation visible-lg"><li data-p="1">1</li></ul>
      <h1 class="exercise-header">Toggle expressions</h1>
      <div class="instructions-text">Click to cycle each phrase.</div>
      <div class="exercise type-toggle-solution">
        <div class="exercise-items"><div class="item" id="row"></div></div>
      </div>
      <button id="chk" class="correct">{ui['check']}</button>
      <button id="sol" style="display:none">{ui['solution']}</button>
      <button id="rep" style="display:none">{ui['repeat']}</button>
      <div class="result-badge-text" id="bdg" data-result="0">0</div>
      <script>
        const opts0 = ["How\u00a0old", "What's\u00a0your\u00a0name?", "Where\u00a0from"];
        const opts1 = ["Fine,\u00a0thanks.", "See\u00a0you", "Good\u00a0night"];
        let i0 = 0, i1 = 1;
        const setScore = s => {{ const b = document.getElementById('bdg'); b.setAttribute('data-result', s); b.textContent = s; }};
        function draw() {{
          const r = document.getElementById('row');
          r.innerHTML = `
            <div class="gap-container"><span class="gap">${{opts0[i0]}}</span><button id="t0">v</button></div>
            <div class="gap-container"><span class="gap">${{opts1[i1]}}</span><button id="t1">v</button></div>
          `;
          document.getElementById('t0').onclick = () => {{ i0 = (i0 + 1) % 3; draw(); }};
          document.getElementById('t1').onclick = () => {{ i1 = (i1 + 1) % 3; draw(); }};
        }}
        draw();
        document.getElementById('chk').onclick = () => {{
          setScore((i0 === 1 && i1 === 0) ? 100 : 0);
          document.getElementById('sol').style.display = 'inline-block';
          document.getElementById('rep').style.display = 'inline-block';
        }};
        document.getElementById('sol').onclick = () => {{ i0 = 1; i1 = 0; draw(); }};
        document.getElementById('rep').onclick = () => {{ i0 = 0; i1 = 2; setScore(0); draw(); }};
      </script>
    </body></html>
    """
    cli_bot.page.set_content(html, url="https://portal.speexx.com/articles/100/tog")
    status, score, _ = cli_bot.auto_solve_exercise("Toggle NBSP", already_opened=True, batch_mode=True)
    assert status == "SUCCESS" and score == 100


# ==============================================================================
# 12. type-mark-text: Multi-word .mark-text phrase + wrong preselected phrase!
# ==============================================================================
def test_type_12_mark_text_multiword_group_and_wrong_preselected_group(cli_bot):
    cli_bot.current_chapter_name = "A1"
    # Phrase 0 ('human resources') has 2 .word children and starts WRONGLY selected!
    # Phrase 1 ('chief executive') has 2 .word children and is the RIGHT target!
    # Earlier bug would click both words of Phrase 0, toggling it OFF then back ON!
    html = """
    <!doctype html><html><body>
      <ul class="exercises-large-navigation visible-lg"><li data-p="1">1</li></ul>
      <h1 class="exercise-header">Mark job titles</h1>
      <div class="instructions-text">Highlight the CEO title only.</div>
      <div class="exercise type-mark-text">
        <div class="exercise-items">
          <div class="item">
            The <span class="mark-text selected" id="g0"><span class="word selected">human</span> <span class="word selected">resources</span></span>
            met the <span class="mark-text" id="g1"><span class="word">chief</span> <span class="word">executive</span></span> today.
          </div>
        </div>
      </div>
      <button id="chk" class="correct">Check</button>
      <button id="sol" style="display:none">Solution</button>
      <button id="rep" style="display:none">Repeat</button>
      <div class="result-badge-text" id="bdg" data-result="0">0</div>
      <script>
        function toggleGroup(g) {
          const on = !g.classList.contains('selected');
          g.classList.toggle('selected', on);
          g.querySelectorAll('.word').forEach(w => w.classList.toggle('selected', on));
        }
        document.getElementById('g0').querySelectorAll('.word').forEach(w => {
          w.onclick = (e) => { e.stopPropagation(); toggleGroup(document.getElementById('g0')); };
        });
        document.getElementById('g1').querySelectorAll('.word').forEach(w => {
          w.onclick = (e) => { e.stopPropagation(); toggleGroup(document.getElementById('g1')); };
        });
        const setScore = s => { const b = document.getElementById('bdg'); b.setAttribute('data-result', s); b.textContent = s; };
        document.getElementById('chk').onclick = () => {
          const ok = !document.getElementById('g0').classList.contains('selected') &&
                      document.getElementById('g1').classList.contains('selected');
          setScore(ok ? 100 : 0);
          document.getElementById('sol').style.display = 'inline-block';
          document.getElementById('rep').style.display = 'inline-block';
        };
        document.getElementById('sol').onclick = () => {
          document.getElementById('g0').classList.remove('selected');
          document.getElementById('g0').querySelectorAll('.word').forEach(w => w.classList.remove('selected'));
          document.getElementById('g1').classList.add('selected');
          document.getElementById('g1').querySelectorAll('.word').forEach(w => w.classList.add('selected'));
        };
        document.getElementById('rep').onclick = () => {
          // Intentionally re-select wrong 2-word group g0 on Repeat to verify clean deselection!
          document.getElementById('g0').classList.add('selected');
          document.getElementById('g0').querySelectorAll('.word').forEach(w => w.classList.add('selected'));
          document.getElementById('g1').classList.remove('selected');
          document.getElementById('g1').querySelectorAll('.word').forEach(w => w.classList.remove('selected'));
          setScore(0);
        };
      </script>
    </body></html>
    """
    cli_bot.page.set_content(html, url="https://portal.speexx.com/articles/100/mark")
    status, score, _ = cli_bot.auto_solve_exercise("Mark Multiword", already_opened=True, batch_mode=True)
    assert status == "SUCCESS" and score == 100


# ==============================================================================
# 13 & 14. All 4 Pronunciation Types: single-item (no .item), multi-item 60/100
#          score preservation without ref audio, and Thai audio setup modal!
# ==============================================================================
def test_type_13_14_all_pronunciation_variants_and_score_preservation(cli_bot):
    cli_bot.current_chapter_name = "A1"
    # Page 1: type-single-item-pronunciation WITHOUT .item wrapper + Thai audio modal (aria-label="ปิด")
    # Page 2: type-multi-item-pronunciation where Attempt 1 scores 62/100 (item 0 green, item 1 red, NO ref audio)
    #         -> Solver MUST preserve 62/100 and NOT overwrite with 0/100 silence!
    html = """
    <!doctype html><html><body>
      <ul class="exercises-large-navigation visible-lg"><li data-p="1">1</li><li data-p="2">2</li></ul>
      <div class="modal" id="audio-modal">
        <div class="modal-content"><button aria-label="ปิด" id="cls-modal">×</button></div>
      </div>
      <div id="stage"></div>
      <button id="chk" class="correct">ตรวจคำตอบ</button>
      <div class="result-badge-text" id="bdg" data-result="0">0</div>
      <button class="action-exercise-button next" id="nxt">Next</button>
      <script>
        document.getElementById('cls-modal').onclick = () => document.getElementById('audio-modal').remove();
        let cur = 1;
        let p2Checks = 0;
        const setScore = s => { const b = document.getElementById('bdg'); b.setAttribute('data-result', s); b.textContent = s; };
        function render(p) {
          cur = p; setScore(0);
          const st = document.getElementById('stage');
          if (p === 1) {
            st.innerHTML = `
              <h1 class="exercise-header">ออกเสียงประโยคเดียว</h1>
              <div class="instructions-text">พูดตามตัวอย่าง</div>
              <div class="exercise type-single-item-pronunciation">
                <p>Could you repeat that, please?</p>
                <button class="play-button">Play</button>
                <button class="microphone-button" id="mic1">Mic</button>
              </div>`;
            window.__mic1Clicked = 0;
            document.getElementById('mic1').onclick = () => { window.__mic1Clicked++; };
          } else {
            p2Checks = 0;
            st.innerHTML = `
              <h1 class="exercise-header">ออกเสียงหลายประโยค</h1>
              <div class="instructions-text">พูดทั้งสองประโยค</div>
              <div class="exercise type-multi-item-pronunciation">
                <div class="exercise-items">
                  <div class="item">First sentence <button class="play-button">P</button><button class="microphone-button">M</button><div class="word-result green"></div></div>
                  <div class="item">Second sentence <button class="play-button">P</button><button class="microphone-button">M</button><div class="word-result red"></div></div>
                </div>
              </div>`;
          }
        }
        document.getElementById('chk').onclick = () => {
          if (cur === 1) {
            setScore(window.__mic1Clicked > 0 ? 90 : 0);
          } else {
            p2Checks++;
            // First check scores 62/100; if retried without ref audio, score would drop to 5!
            setScore(p2Checks === 1 ? 62 : 5);
          }
        };
        document.querySelectorAll('ul.exercises-large-navigation li').forEach(li => {
          li.onclick = () => render(parseInt(li.getAttribute('data-p'), 10));
        });
        document.getElementById('nxt').onclick = () => { if (cur < 2) render(cur + 1); };
        render(1);
      </script>
    </body></html>
    """
    cli_bot.page.set_content(html, url="https://portal.speexx.com/articles/100/pron")
    status, score, _ = cli_bot.auto_solve_exercise("Pronunciation Suite", already_opened=True, batch_mode=True)
    assert status == "SUCCESS"
    assert score >= 51


# ==============================================================================
# 15. Real answers_A1.json Replay Across All 8 Interactive A1 Exercise Types
# ==============================================================================
@pytest.mark.skipif(
    not os.path.exists("/tmp/arena-coding-uploads/answers_A1.json"),
    reason="Reference answers_A1.json upload only present in Arena workspace",
)
def test_type_15_real_answers_a1_cached_replay_all_8_types(cli_bot):
    target_a1 = os.path.join(cli_bot.reports_folder, "answers_A1.json")
    shutil.copyfile("/tmp/arena-coding-uploads/answers_A1.json", target_a1)
    cli_bot.current_chapter_name = "A1"
    cli_bot._load_answer_db("A1", announce=False)

    # Verify real entries from answers_A1.json are indexed by (exercise_title, page_number) for every type!
    expected_types_found = set()
    for (_title, _pnum), ans in cli_bot.page_answer_index.items():
        if isinstance(ans, dict) and ans.get("type"):
            expected_types_found.add(ans["type"])

    assert {
        "answer",
        "drag-drop",
        "single-choice",
        "multiple-choice",
        "scrambled-sentence",
        "scrambled-table",
        "picture-choice",
        "toggle-solution",
    }.issubset(expected_types_found)

    # Replay an actual "To be" Page 2 (type-drag-drop: ['good morning', 'good afternoon', 'good evening']) directly from answers_A1.json without Solution button!
    html = """
    <!doctype html><html><body>
      <ul class="exercises-large-navigation visible-lg"><li data-p="1">1</li><li data-p="2">2</li></ul>
      <h1 class="exercise-header">To be</h1>
      <div class="instructions-text">Match the greetings.</div>
      <div class="exercise type-drag-drop">
        <div class="exercise-items" id="slots"></div>
        <div class="draggable-container" id="pool"></div>
      </div>
      <button id="chk" class="correct">Check</button>
      <div class="result-badge-text" id="bdg" data-result="0">0</div>
      <script>
        let slots = [null, null, null];
        let pool = ['good evening', 'good morning', 'good afternoon'];
        let armed = null;
        function render() {
          document.getElementById('slots').innerHTML = slots.map((v, i) =>
            `<div class="item"><span class="drag-drop-placeholder" data-i="${i}">${v ? `<div class="drag-drop">${v}</div>` : ''}</span></div>`
          ).join('');
          document.getElementById('pool').innerHTML = pool.map((w, i) =>
            `<div class="drag-drop" data-p="${i}">${w}</div>`
          ).join('');
          document.querySelectorAll('.drag-drop-placeholder').forEach(el => {
            el.onclick = () => { armed = parseInt(el.getAttribute('data-i'), 10); };
          });
          document.querySelectorAll('#pool .drag-drop').forEach(el => {
            el.onclick = () => {
              const pi = parseInt(el.getAttribute('data-p'), 10);
              if (armed !== null && !slots[armed]) {
                slots[armed] = pool.splice(pi, 1)[0];
                const nxt = slots.findIndex((x, k) => k > armed && x === null);
                armed = nxt >= 0 ? nxt : null;
                render();
              }
            };
          });
        }
        render();
        document.getElementById('chk').onclick = () => {
          const ok = slots[0] === 'good morning' && slots[1] === 'good afternoon' && slots[2] === 'good evening';
          const b = document.getElementById('bdg');
          b.setAttribute('data-result', ok ? '100' : '0');
          b.textContent = ok ? '100' : '0';
        };
      </script>
    </body></html>
    """
    cli_bot.page.set_content(html, url="https://portal.speexx.com/articles/100/tobe")
    engine = ExerciseEngine(
        cli_bot.page,
        cli_bot.logger,
        answer_db=cli_bot.answer_db,
        page_answer_index=cli_bot.page_answer_index,
    )
    solver = engine.get_solver("type-drag-drop", exercise_title="To be", page_number=2)
    assert solver.solve() is True
    assert solver.get_result_score() == 100
