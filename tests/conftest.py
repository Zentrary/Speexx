import json
import os
import subprocess
import sys
import time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


NODE_JSDOM_WORKER = r"""
const readline = require('readline');
let JSDOM;
try {
  ({ JSDOM } = require('jsdom'));
} catch (_e) {
  ({ JSDOM } = require('/tmp/jsdom_runner/node_modules/jsdom'));
}

let dom = null;
let window = null;
let document = null;
let currentUrl = 'about:blank';
let nextHandleId = 1;
const handleMap = new Map();

function patchWindow(win) {
  const doc = win.document;
  // Polyfill innerText on Element / HTMLElement for jsdom
  if (!Object.getOwnPropertyDescriptor(win.HTMLElement.prototype, 'innerText')) {
    Object.defineProperty(win.HTMLElement.prototype, 'innerText', {
      get() {
        if (this.tagName === 'SCRIPT' || this.tagName === 'STYLE') return '';
        return this.textContent || '';
      },
      set(v) {
        this.textContent = v == null ? '' : String(v);
      },
      configurable: true,
    });
  }
  win.HTMLElement.prototype.scrollIntoView = function() {};
  const origGBR = win.Element.prototype.getBoundingClientRect;
  win.Element.prototype.getBoundingClientRect = function() {
    if (this.dataset && this.dataset.hidden === 'true') {
      return { x: 0, y: 0, top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0 };
    }
    const style = win.getComputedStyle(this);
    if (style.display === 'none' || style.visibility === 'hidden') {
      return { x: 0, y: 0, top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0 };
    }
    const bx = Number((this.dataset && this.dataset.boxX) || 20);
    const by = Number((this.dataset && this.dataset.boxY) || 20);
    const bw = Number((this.dataset && this.dataset.boxW) || 120);
    const bh = Number((this.dataset && this.dataset.boxH) || 32);
    return { x: bx, y: by, top: by, left: bx, right: bx + bw, bottom: by + bh, width: bw, height: bh };
  };
}

function loadHtml(html, url) {
  currentUrl = url || currentUrl || 'https://portal.speexx.com/';
  handleMap.clear();
  dom = new JSDOM(html || '<!doctype html><html><body></body></html>', {
    url: currentUrl,
    runScripts: 'dangerously',
    pretendToBeVisual: true,
  });
  window = dom.window;
  document = window.document;
  patchWindow(window);
}

loadHtml('<!doctype html><html><body></body></html>', 'https://portal.speexx.com/');

function isVisibleEl(el) {
  if (!el || !el.isConnected) return false;
  let cur = el;
  while (cur && cur.nodeType === 1) {
    if (cur.hasAttribute('hidden') || (cur.dataset && cur.dataset.hidden === 'true')) return false;
    const st = window.getComputedStyle(cur);
    if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') return false;
    cur = cur.parentElement;
  }
  return true;
}

function splitTopLevelCommas(sel) {
  const parts = [];
  let depthParen = 0;
  let depthBracket = 0;
  let quote = null;
  let cur = '';
  for (let i = 0; i < sel.length; i++) {
    const ch = sel[i];
    if (quote) {
      cur += ch;
      if (ch === quote && sel[i - 1] !== '\\') quote = null;
      continue;
    }
    if (ch === '"' || ch === "'") {
      quote = ch;
      cur += ch;
    } else if (ch === '(') {
      depthParen++;
      cur += ch;
    } else if (ch === ')') {
      depthParen = Math.max(0, depthParen - 1);
      cur += ch;
    } else if (ch === '[') {
      depthBracket++;
      cur += ch;
    } else if (ch === ']') {
      depthBracket = Math.max(0, depthBracket - 1);
      cur += ch;
    } else if (ch === ',' && depthParen === 0 && depthBracket === 0) {
      if (cur.trim()) parts.push(cur.trim());
      cur = '';
    } else {
      cur += ch;
    }
  }
  if (cur.trim()) parts.push(cur.trim());
  return parts;
}

function querySinglePlaywrightSelector(root, rawSel) {
  let sel = rawSel.trim();
  if (!sel) return [];

  if (sel.startsWith('xpath=')) {
    const xp = sel.slice(6);
    const ctxNode = root === document ? document.body : root;
    const res = document.evaluate(xp, ctxNode, null, window.XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
    const out = [];
    for (let i = 0; i < res.snapshotLength; i++) out.push(res.snapshotItem(i));
    return out;
  }

  // Extract :has-text('...') or :has-text("...")
  const hasTextFilters = [];
  sel = sel.replace(/:has-text\(\s*(['"])([\s\S]*?)\1\s*\)/gi, (_, _q, txt) => {
    hasTextFilters.push(txt.toLowerCase());
    return '';
  });

  // Extract case-insensitive attribute selectors like [aria-label*='Show more' i]
  const ciAttrFilters = [];
  sel = sel.replace(/\[\s*([a-zA-Z0-9_-]+)\s*([*~|^$]?=)\s*(['"])([\s\S]*?)\3\s+i\s*\]/g, (_, attr, op, _q, val) => {
    ciAttrFilters.push({ attr, op, val: val.toLowerCase() });
    return `[${attr}]`;
  });

  const css = sel.trim() || '*';
  let candidates = [];
  try {
    candidates = Array.from(root.querySelectorAll(css));
  } catch (e) {
    return [];
  }

  return candidates.filter(el => {
    for (const f of ciAttrFilters) {
      const av = (el.getAttribute(f.attr) || '').toLowerCase();
      if (f.op === '=' && av !== f.val) return false;
      if (f.op === '*=' && !av.includes(f.val)) return false;
      if (f.op === '^=' && !av.startsWith(f.val)) return false;
      if (f.op === '$=' && !av.endsWith(f.val)) return false;
    }
    for (const ht of hasTextFilters) {
      const txt = ((el.innerText !== undefined ? el.innerText : el.textContent) || '').toLowerCase();
      if (!txt.includes(ht)) return false;
    }
    return true;
  });
}

function resolveElements(chain) {
  let current = [document];
  for (const step of chain) {
    if (step.op === 'selector') {
      const parts = splitTopLevelCommas(step.value);
      const next = [];
      const seen = new Set();
      for (const root of current) {
        for (const p of parts) {
          for (const el of querySinglePlaywrightSelector(root, p)) {
            if (!seen.has(el)) {
              seen.add(el);
              next.push(el);
            }
          }
        }
      }
      current = next;
    } else if (step.op === 'handle') {
      const el = handleMap.get(step.id);
      current = (el && el.isConnected) ? [el] : [];
    } else if (step.op === 'nth') {
      const idx = step.index;
      current = (idx >= 0 && idx < current.length) ? [current[idx]] : [];
    } else if (step.op === 'filter_text') {
      const needle = (step.text || '').toLowerCase();
      current = current.filter(el => {
        const txt = ((el.innerText !== undefined ? el.innerText : el.textContent) || '').toLowerCase();
        return txt.includes(needle);
      });
    }
  }
  return current.filter(el => el !== document);
}

function registerHandle(el) {
  const id = nextHandleId++;
  handleMap.set(id, el);
  return id;
}

const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });

rl.on('line', async (line) => {
  if (!line.trim()) return;
  let req;
  try {
    req = JSON.parse(line);
  } catch (err) {
    process.stdout.write(JSON.stringify({ ok: false, error: String(err) }) + '\n');
    return;
  }

  try {
    const cmd = req.cmd;
    if (cmd === 'set_content') {
      loadHtml(req.html, req.url);
      process.stdout.write(JSON.stringify({ ok: true, url: window.location.href }) + '\n');
      return;
    }
    if (cmd === 'get_url') {
      process.stdout.write(JSON.stringify({ ok: true, result: window.location.href }) + '\n');
      return;
    }
    if (cmd === 'content') {
      process.stdout.write(JSON.stringify({ ok: true, result: dom.serialize() }) + '\n');
      return;
    }
    if (cmd === 'page_eval') {
      const fnOrExpr = window.eval('(' + req.script + ')');
      let val;
      if (typeof fnOrExpr === 'function') {
        val = req.hasArg ? await fnOrExpr(req.arg) : await fnOrExpr();
      } else {
        val = await fnOrExpr;
      }
      process.stdout.write(JSON.stringify({ ok: true, result: val === undefined ? null : val }) + '\n');
      return;
    }
    if (cmd === 'count') {
      const els = resolveElements(req.chain);
      process.stdout.write(JSON.stringify({ ok: true, result: els.length }) + '\n');
      return;
    }
    if (cmd === 'all_handles') {
      const els = resolveElements(req.chain);
      const ids = els.map(el => registerHandle(el));
      process.stdout.write(JSON.stringify({ ok: true, result: ids }) + '\n');
      return;
    }
    if (cmd === 'is_visible') {
      const els = resolveElements(req.chain);
      process.stdout.write(JSON.stringify({ ok: true, result: els.length > 0 && isVisibleEl(els[0]) }) + '\n');
      return;
    }
    if (cmd === 'is_disabled') {
      const els = resolveElements(req.chain);
      if (!els.length) throw new Error('Element not found');
      const el = els[0];
      const dis = Boolean(el.disabled) || el.getAttribute('disabled') !== null || (el.className || '').includes('disabled');
      process.stdout.write(JSON.stringify({ ok: true, result: dis }) + '\n');
      return;
    }
    if (cmd === 'is_checked') {
      const els = resolveElements(req.chain);
      if (!els.length) throw new Error('Element not found');
      process.stdout.write(JSON.stringify({ ok: true, result: Boolean(els[0].checked) }) + '\n');
      return;
    }
    if (cmd === 'inner_text') {
      const els = resolveElements(req.chain);
      if (!els.length) throw new Error('Element not found for inner_text');
      const el = els[0];
      const txt = el.innerText !== undefined ? el.innerText : (el.textContent || '');
      process.stdout.write(JSON.stringify({ ok: true, result: txt }) + '\n');
      return;
    }
    if (cmd === 'text_content') {
      const els = resolveElements(req.chain);
      if (!els.length) throw new Error('Element not found for text_content');
      process.stdout.write(JSON.stringify({ ok: true, result: els[0].textContent || '' }) + '\n');
      return;
    }
    if (cmd === 'get_attribute') {
      const els = resolveElements(req.chain);
      if (!els.length) throw new Error('Element not found for get_attribute');
      process.stdout.write(JSON.stringify({ ok: true, result: els[0].getAttribute(req.name) }) + '\n');
      return;
    }
    if (cmd === 'input_value') {
      const els = resolveElements(req.chain);
      if (!els.length) throw new Error('Element not found for input_value');
      process.stdout.write(JSON.stringify({ ok: true, result: els[0].value || '' }) + '\n');
      return;
    }
    if (cmd === 'fill') {
      const els = resolveElements(req.chain);
      if (!els.length) throw new Error('Element not found for fill');
      const el = els[0];
      el.value = req.value;
      el.dispatchEvent(new window.Event('input', { bubbles: true }));
      el.dispatchEvent(new window.Event('change', { bubbles: true }));
      process.stdout.write(JSON.stringify({ ok: true, result: true }) + '\n');
      return;
    }
    if (cmd === 'click') {
      const els = resolveElements(req.chain);
      if (!els.length) throw new Error('Element not found for click');
      const el = els[0];
      if (!req.force && !isVisibleEl(el)) {
        throw new Error('Element is not visible');
      }
      const anchor = el.tagName === 'A' ? el : (el.closest ? el.closest('a[href]') : null);
      const navHref = anchor ? anchor.href : null;
      el.click();
      process.stdout.write(JSON.stringify({ ok: true, result: true, url: window.location.href, navHref }) + '\n');
      return;
    }
    if (cmd === 'check') {
      const els = resolveElements(req.chain);
      if (!els.length) throw new Error('Element not found for check');
      const el = els[0];
      if (!el.checked) el.click();
      el.checked = true;
      process.stdout.write(JSON.stringify({ ok: true, result: true }) + '\n');
      return;
    }
    if (cmd === 'bounding_box') {
      const els = resolveElements(req.chain);
      if (!els.length || !isVisibleEl(els[0])) {
        process.stdout.write(JSON.stringify({ ok: true, result: null }) + '\n');
        return;
      }
      const r = els[0].getBoundingClientRect();
      process.stdout.write(JSON.stringify({
        ok: true,
        result: { x: r.x, y: r.y, width: r.width, height: r.height },
      }) + '\n');
      return;
    }
    if (cmd === 'loc_eval') {
      const els = resolveElements(req.chain);
      if (!els.length) throw new Error('Element not found for locator.evaluate');
      const fn = window.eval('(' + req.script + ')');
      const val = req.hasArg ? await fn(els[0], req.arg) : await fn(els[0]);
      process.stdout.write(JSON.stringify({ ok: true, result: val === undefined ? null : val, url: window.location.href }) + '\n');
      return;
    }
    process.stdout.write(JSON.stringify({ ok: false, error: 'Unknown cmd: ' + cmd }) + '\n');
  } catch (err) {
    process.stdout.write(JSON.stringify({ ok: false, error: String(err && err.stack ? err.stack : err) }) + '\n');
  }
});
"""


class JsdomBridge:
    def __init__(self):
        self.proc = subprocess.Popen(
            ["node", "-e", NODE_JSDOM_WORKER],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    def call(self, payload):
        line = json.dumps(payload, ensure_ascii=False)
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()
        resp_line = self.proc.stdout.readline()
        if not resp_line:
            err = self.proc.stderr.read()
            raise RuntimeError(f"JSDOM worker exited unexpectedly: {err}")
        resp = json.loads(resp_line)
        if not resp.get("ok"):
            raise RuntimeError(resp.get("error", "JSDOM error"))
        return resp

    def close(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.close()
                self.proc.terminate()
                self.proc.wait(timeout=3)
            except Exception:
                self.proc.kill()


class FakeMouse:
    def __init__(self, page):
        self.page = page
        self.pos = (0.0, 0.0)

    def move(self, x, y, steps=1):
        self.pos = (x, y)

    def down(self):
        self.page._drag_start = self.pos

    def up(self):
        start = self.page._drag_start
        end = self.pos
        if getattr(self.page, "_drag_hook", None):
            self.page._drag_hook(start, end)
        if start is not None:
            try:
                self.page.evaluate(
                    """(coords) => {
                        if (typeof window.__onSimulatedDrag === 'function') {
                            window.__onSimulatedDrag(coords.sx, coords.sy, coords.tx, coords.ty);
                        }
                    }""",
                    {"sx": start[0], "sy": start[1], "tx": end[0], "ty": end[1]},
                )
            except Exception:
                pass
        self.page._drag_start = None


class FakeKeyboard:
    def __init__(self, page):
        self.page = page

    def press(self, key):
        if key == "Escape":
            try:
                self.page.evaluate(
                    "() => { document.querySelectorAll('.modal').forEach(m => m.remove()); }"
                )
            except Exception:
                pass
        elif key == "Backspace":
            pass

    def type(self, text, delay=0):
        try:
            self.page.evaluate(
                """(val) => {
                    const el = document.activeElement || document.querySelector('input.answer-gap');
                    if (el) {
                        el.value = (el.value || '') + val;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }""",
                text,
            )
        except Exception:
            pass


class FakeContext:
    def __init__(self):
        self.handlers = {}
        self.init_scripts = []
        self.request = None

    def on(self, event, cb):
        self.handlers.setdefault(event, []).append(cb)

    def add_init_script(self, script=""):
        self.init_scripts.append(script)

    def close(self):
        pass


class FakeLocator:
    def __init__(self, page, chain):
        self.page = page
        self.chain = list(chain)

    def locator(self, selector):
        return FakeLocator(self.page, self.chain + [{"op": "selector", "value": selector}])

    @property
    def first(self):
        return FakeLocator(self.page, self.chain + [{"op": "nth", "index": 0}])

    def nth(self, index):
        return FakeLocator(self.page, self.chain + [{"op": "nth", "index": int(index)}])

    def filter(self, has_text=None):
        if has_text is not None:
            return FakeLocator(self.page, self.chain + [{"op": "filter_text", "text": str(has_text)}])
        return self

    def count(self):
        return self.page.bridge.call({"cmd": "count", "chain": self.chain})["result"]

    def all(self):
        ids = self.page.bridge.call({"cmd": "all_handles", "chain": self.chain})["result"]
        return [FakeLocator(self.page, [{"op": "handle", "id": hid}]) for hid in ids]

    def is_visible(self, timeout=None):
        return self.page.bridge.call({"cmd": "is_visible", "chain": self.chain})["result"]

    def is_disabled(self, timeout=None):
        return self.page.bridge.call({"cmd": "is_disabled", "chain": self.chain})["result"]

    def is_checked(self, timeout=None):
        return self.page.bridge.call({"cmd": "is_checked", "chain": self.chain})["result"]

    def inner_text(self, timeout=None):
        return self.page.bridge.call({"cmd": "inner_text", "chain": self.chain})["result"]

    def text_content(self, timeout=None):
        return self.page.bridge.call({"cmd": "text_content", "chain": self.chain})["result"]

    def get_attribute(self, name, timeout=None):
        return self.page.bridge.call({"cmd": "get_attribute", "chain": self.chain, "name": name})["result"]

    def input_value(self, timeout=None):
        return self.page.bridge.call({"cmd": "input_value", "chain": self.chain})["result"]

    def fill(self, value, timeout=None):
        self.page.bridge.call({"cmd": "fill", "chain": self.chain, "value": str(value)})

    def click(self, timeout=None, force=False):
        resp = self.page.bridge.call({"cmd": "click", "chain": self.chain, "force": bool(force)})
        if resp.get("navHref") and resp["navHref"] != self.page._url:
            self.page.goto(resp["navHref"])
        elif resp.get("url"):
            self.page._url = resp["url"]
        if self.page.on_after_click:
            self.page.on_after_click(self)

    def check(self, timeout=None):
        self.page.bridge.call({"cmd": "check", "chain": self.chain})

    def scroll_into_view_if_needed(self, timeout=None):
        return None

    def wait_for(self, state="visible", timeout=1000):
        if state == "attached":
            if self.count() > 0:
                return
            raise TimeoutError(f"Locator not attached: {self.chain}")
        if state == "visible":
            if self.is_visible():
                return
            raise TimeoutError(f"Locator not visible: {self.chain}")

    def bounding_box(self):
        return self.page.bridge.call({"cmd": "bounding_box", "chain": self.chain})["result"]

    def evaluate(self, script, arg=None):
        payload = {
            "cmd": "loc_eval",
            "chain": self.chain,
            "script": script,
            "hasArg": arg is not None,
            "arg": arg,
        }
        resp = self.page.bridge.call(payload)
        if resp.get("url"):
            self.page._url = resp["url"]
        if self.page.on_after_click:
            self.page.on_after_click(self)
        return resp["result"]


class FakePage:
    def __init__(self, bridge):
        self.bridge = bridge
        self.context = FakeContext()
        self.mouse = FakeMouse(self)
        self.keyboard = FakeKeyboard(self)
        self._url = "https://portal.speexx.com/"
        self._drag_start = None
        self._drag_hook = None
        self.routes = {}
        self.on_after_click = None
        self.handlers = {}

    @property
    def url(self):
        try:
            self._url = self.bridge.call({"cmd": "get_url"})["result"]
        except Exception:
            pass
        return self._url

    def set_content(self, html, url=None):
        if url:
            self._url = url
        resp = self.bridge.call({"cmd": "set_content", "html": html, "url": self._url})
        self._url = resp.get("url", self._url)

    def goto(self, url, wait_until=None, timeout=None):
        self._url = url
        if url in self.routes:
            html_or_fn = self.routes[url]
            html = html_or_fn() if callable(html_or_fn) else html_or_fn
            self.set_content(html, url=url)
        else:
            # Match longest substring route so 'https://portal.speexx.com/' doesn't shadow subpaths
            matching = [
                (len(pat), html_or_fn)
                for pat, html_or_fn in self.routes.items()
                if pat != "https://portal.speexx.com/" and pat in url
            ]
            if matching:
                matching.sort(key=lambda x: x[0], reverse=True)
                html_or_fn = matching[0][1]
                html = html_or_fn() if callable(html_or_fn) else html_or_fn
                self.set_content(html, url=url)

    def reload(self, wait_until=None, timeout=None):
        self.goto(self.url)

    def go_back(self):
        pass

    def content(self):
        return self.bridge.call({"cmd": "content"})["result"]

    def locator(self, selector):
        return FakeLocator(self, [{"op": "selector", "value": selector}])

    def evaluate(self, script, arg=None):
        payload = {
            "cmd": "page_eval",
            "script": script,
            "hasArg": arg is not None,
            "arg": arg,
        }
        return self.bridge.call(payload)["result"]

    def wait_for_selector(self, selector, state="visible", timeout=1000):
        loc = self.locator(selector).first
        loc.wait_for(state=state, timeout=timeout)
        return loc

    def wait_for_load_state(self, state="domcontentloaded", timeout=1000):
        return None

    def wait_for_timeout(self, ms):
        return None

    def wait_for_url(self, pattern, timeout=1000):
        return None

    def wait_for_function(self, script, arg=None, timeout=1000):
        res = self.evaluate(script, arg)
        if not res:
            raise TimeoutError("wait_for_function returned falsy")
        return res

    def on(self, event, cb):
        self.handlers.setdefault(event, []).append(cb)


@pytest.fixture(scope="session")
def jsdom_bridge():
    bridge = JsdomBridge()
    yield bridge
    bridge.close()


@pytest.fixture
def fake_page(jsdom_bridge, monkeypatch):
    # Speed up solver sleeps during unit/integration tests
    monkeypatch.setattr(time, "sleep", lambda *_args, **_kwargs: None)
    page = FakePage(jsdom_bridge)
    page.set_content("<!doctype html><html><body></body></html>", url="https://portal.speexx.com/")
    return page


@pytest.fixture
def cli_bot(tmp_path, fake_page, monkeypatch):
    from main import SpeexxBotCLI

    monkeypatch.chdir(tmp_path)
    bot = SpeexxBotCLI()
    bot.page = fake_page
    bot.context = fake_page.context
    yield bot
    try:
        if hasattr(bot, "tee_logger") and bot.tee_logger:
            bot.tee_logger.close()
        if hasattr(bot, "original_stdout") and bot.original_stdout:
            sys.stdout = bot.original_stdout
    except Exception:
        pass

