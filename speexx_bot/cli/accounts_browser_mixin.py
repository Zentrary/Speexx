"""AccountsBrowserMixin: account persistence, Chrome profile startup (--mute-audio), and Speexx login."""

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from playwright.sync_api import sync_playwright

from ..ui_utils import Fore, Style


class AccountsBrowserMixin:
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
        self._pron_init_installed = False

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
                                    const arr = b64ToArrayBuffer(b64);
                                    const audioBuffer = await ctx.decodeAudioData(arr);
                                    const src = ctx.createBufferSource();
                                    src.buffer = audioBuffer;
                                    src.connect(dest);
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
                    "--mute-audio",
                ],
            )
            self.browser = self.context.browser
            if self.context.pages:
                self.page = self.context.pages[0]
            else:
                self.page = self.context.new_page()

            try:
                self.context.on("page", self._attach_web_diagnostics)
            except Exception:
                pass
            self._attach_web_diagnostics(self.page)
            self.print_status("OK", "Browser audio muted (--mute-audio active)")

            self._install_pronunciation_init()

            self.page.goto("https://portal.speexx.com/",
                           wait_until="domcontentloaded")
            time.sleep(2)
            if self.check_speexx_session():
                self.print_status("OK", self.T['session_valid'])
                return True
            if not p:
                p = self.get_saved_password(u)
                if p:
                    self.print_status("OK", self.T['using_saved_pwd'])
            if not p:
                try:
                    import getpass
                    p = getpass.getpass(
                        f"  {Fore.CYAN}[>] {self.T['pwd_of'].format(u)}{Style.RESET_ALL}"
                    ).strip()
                except (EOFError, KeyboardInterrupt):
                    return False
                if p:
                    try:
                        save = self._input(
                            f"  {Fore.CYAN}[>] {self.T['ask_save_pwd']}{Style.RESET_ALL}"
                        ).strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        save = "n"
                    if save == "y":
                        self.save_account(u, p)
                        self.print_status("OK", self.T['saved_pwd'])
            if not p:
                self.print_status("ERROR", self.T['no_password'])
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
