"""SpeexxBotCLI main application class and CLI entry point."""

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime

from ..constants import MAIN_SCRIPT_PATH
from ..translations import TRANSLATIONS
from ..ui_utils import Fore, Style
from .accounts_browser_mixin import AccountsBrowserMixin
from .answer_db_mixin import AnswerDatabaseMixin
from .diagnostics_mixin import DiagnosticsMixin
from .exercise_list_mixin import ExerciseListMixin
from .modal_page_mixin import ModalAndPageMixin
from .results_nav_mixin import ResultsNavigationMixin
from .runner_mixin import ExerciseRunnerMixin


class SpeexxBotCLI(
    DiagnosticsMixin,
    AccountsBrowserMixin,
    AnswerDatabaseMixin,
    ResultsNavigationMixin,
    ExerciseListMixin,
    ModalAndPageMixin,
    ExerciseRunnerMixin,
):
    MAX_NEW_EXERCISE_CHAIN = 300
    DEFAULT_CHAPTER_NAME = "General"

    def __init__(self):
        self.config_folder = "config"
        self.logs_folder = "logs"
        self.dump_folder = "webpagedump"
        self.reports_folder = "reports"
        self.profiles_folder = "chrome_profiles"
        self.accounts_file = os.path.join(self.config_folder, "accounts.json")

        self.current_chapter_cid = None
        self.current_chapter_name = ""
        self.loaded_chapter_name = ""
        self.answer_bank_file = ""
        self.last_results_url = None
        self._chapter_live_titles = {}

        self.lang = "th"

        self.ensure_folders()
        self.setup_logging()

        self.accounts = self.load_accounts()
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.active_profile_dir = None
        self.current_chapters = []
        self.force_solve_all = False
        self.answer_db = {}

        self.answer_records = []
        self.answer_page_contexts = {}
        self.page_answer_index = {}
        self.structured_page_records = {}
        self.chapter_catalog = []

    @property
    def T(self):
        return TRANSLATIONS.get(self.lang, TRANSLATIONS["th"])

    @T.setter
    def T(self, value):
        for code, table in TRANSLATIONS.items():
            if value is table:
                self.lang = code
                return

    def _input(self, prompt="", sensitive=False):
        value = input(prompt)
        try:
            self.logger.info(f"INPUT: {'<redacted>' if sensitive else value}")
        except Exception:
            pass
        return value

    def multi_account_menu(self):
        self.print_header()
        print(f"  {Fore.CYAN}--- {self.T['opt_multi_acc']} ---{Style.RESET_ALL}\n")
        self.accounts = self.load_accounts()
        if not self.accounts:
            print(f"  {Fore.YELLOW}{self.T['no_accounts']}{Style.RESET_ALL}")
            self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
            return

        for i, acc in enumerate(self.accounts, 1):
            has_pwd = f" {Fore.GREEN}[saved pwd]{Style.RESET_ALL}" if acc.get("password") else ""
            print(f"  {Fore.WHITE}[{i}]{Style.RESET_ALL} {acc.get('email', '')}{has_pwd}")

        print(f"  {Fore.WHITE}[A]{Style.RESET_ALL} {self.T['multi_acc_all']}")
        print(f"  {Fore.WHITE}[0]{Style.RESET_ALL} {self.T['back']}")

        try:
            choice = self._input(f"\n  {Fore.CYAN}[>] {self.T['multi_acc_select']}{Style.RESET_ALL}").strip()
        except (EOFError, KeyboardInterrupt):
            return

        selected = []
        if choice.lower() == 'a':
            selected = self.accounts
        elif choice == '0' or choice == '':
            return
        else:
            try:
                idxs = []
                if '-' in choice:
                    a, b = choice.split('-')
                    idxs = list(range(int(a) - 1, int(b)))
                elif ',' in choice:
                    idxs = [int(x.strip()) - 1 for x in choice.split(',')]
                else:
                    idxs = [int(choice) - 1]

                for idx in idxs:
                    if 0 <= idx < len(self.accounts):
                        selected.append(self.accounts[idx])
            except Exception:
                self.print_status("ERROR", self.T['invalid_choice'])
                time.sleep(1)
                return

        valid_selected = [acc for acc in selected if acc.get("password")]
        if not valid_selected:
            self.print_status("ERROR", self.T['multi_acc_no_pwd'])
            self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")
            return

        print(f"\n  {Fore.GREEN}{self.T['multi_acc_launching'].format(len(valid_selected))}{Style.RESET_ALL}")
        for acc in valid_selected:
            email = acc.get("email")
            pwd = acc.get("password")
            print(f"  {Fore.CYAN}[START]{Style.RESET_ALL} {email}")
            subprocess.Popen([sys.executable, MAIN_SCRIPT_PATH, "--account", email, "--password", pwd, "--auto"])

        print(f"\n  {Fore.GREEN}{self.T['multi_acc_started']}{Style.RESET_ALL}")
        self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")

    def auto_run(self, email, password):
        self.print_status("INFO", f"Auto-run for {email}")
        if not self.start_browser_and_login(email, password):
            sys.exit(1)

        self.navigate_to_results()
        self._ensure_chapter_db_loaded(announce=True)

        try:
            self._ensure_results_chapter_and_exercises_ready(
                force_chapter_click=False,
                wait_timeout=15000,
            )
            row_infos = self._inspect_all_visible_result_rows()
            first_uncompleted = None
            first_row_idx = None
            seen_cat = {item.get("title") for item in self.chapter_catalog}
            for r_info in row_infos:
                t = r_info["title"]
                if t and t not in seen_cat:
                    seen_cat.add(t)
                    self.chapter_catalog.append({"title": t, "pages_total": 0})
                if first_uncompleted is None and t and not r_info["is_completed"]:
                    first_uncompleted = t
                    first_row_idx = r_info["row_index"]

            self._save_answer_db(self.current_chapter_name)

            if first_uncompleted:
                self.print_status("INFO", self.T["auto_start_ex"].format(first_uncompleted))
                self.force_solve_all = False
                self.auto_solve_exercise(
                    first_uncompleted,
                    selected_pages=None,
                    is_continuation=False,
                    already_opened=False,
                    auto_continue=True,
                    row_index=first_row_idx,
                )
            else:
                self.print_status("OK", self.T["auto_all_done"])
        except Exception as e:
            self.print_status("ERROR", f"Auto run error: {e}")
        finally:
            self._save_answer_db(self.current_chapter_name)

        self.print_status("INFO", self.T["auto_finished_acc"])
        self._cleanup_browser()
        sys.exit(0)

    def after_solve_menu(self):
        while True:
            print(f"\n  {Fore.CYAN}--- {self.T['next_action']} ---{Style.RESET_ALL}")
            print(f"  {Fore.WHITE}[1]{Style.RESET_ALL} {self.T['back_to_list']}")
            print(f"  {Fore.WHITE}[2]{Style.RESET_ALL} {self.T['back_to_main']}")
            print(f"  {Fore.WHITE}[3]{Style.RESET_ALL} {self.T['exit_app']}")
            try:
                c = self._input(f"\n  {Fore.CYAN}[>] Select: {Style.RESET_ALL}").strip()
                if c == "1":
                    if self.current_chapter_cid or (
                        self.current_chapter_name and self.current_chapter_name != self.DEFAULT_CHAPTER_NAME
                    ):
                        self.select_chapter(self.current_chapter_cid, self.current_chapter_name)
                    else:
                        self.navigate_to_results()
                        time.sleep(1)
                        self.fetch_exercises()
                    return
                elif c == "2" or c == "":
                    return
                elif c == "3":
                    self.shutdown()
            except ValueError:
                pass

    def shutdown(self):
        self.print_status("INFO", "Exiting...")
        if self.current_chapter_name or self.answer_db or self.structured_page_records:
            self._save_answer_db(self.current_chapter_name)
        self._cleanup_browser()
        try:
            sys.stdout.flush()
            if hasattr(sys.stdout, 'close'):
                sys.stdout.close()
            if hasattr(self, 'original_stdout'):
                sys.stdout = self.original_stdout
        except Exception:
            pass
        sys.exit(0)

    def select_language(self):
        self.print_header()
        print(f"  {Fore.CYAN}--- {self.T['select_lang']} ---{Style.RESET_ALL}\n")
        print(f"  {Fore.WHITE}[1]{Style.RESET_ALL} {self.T['lang_th']}")
        print(f"  {Fore.WHITE}[2]{Style.RESET_ALL} {self.T['lang_en']}")
        try:
            c = input(f"\n  {Fore.CYAN}[>] Select: {Style.RESET_ALL}").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if c == "1":
            self.lang = "th"
        elif c == "2":
            self.lang = "en"
        else:
            return
        self.T = TRANSLATIONS[self.lang]
        try:
            self.logger.info(f"INPUT: {c}")
            self.logger.info(f"LANG: {self.lang}")
        except Exception:
            pass

    def login_menu(self):
        while True:
            self.print_header()
            print(f"  {Fore.CYAN}--- {self.T['login_menu']} ---{Style.RESET_ALL}\n")
            print(f"  {Fore.WHITE}[1]{Style.RESET_ALL} {self.T['opt_login']}")
            print(f"  {Fore.WHITE}[2]{Style.RESET_ALL} {self.T['opt_manage_acc']}")
            print(f"  {Fore.WHITE}[3]{Style.RESET_ALL} {self.T['opt_multi_acc']}")
            print(f"  {Fore.WHITE}[4]{Style.RESET_ALL} {self.T['opt_exit']}")
            try:
                c = self._input(f"\n  {Fore.CYAN}[>] Select: {Style.RESET_ALL}").strip()
                if c == "":
                    continue
                if c == "1":
                    self.accounts = self.load_accounts()
                    u, p = self.select_account()
                    if u:
                        if self.start_browser_and_login(u, p):
                            self.navigate_to_results()
                            return
                elif c == "2":
                    self.accounts = self.load_accounts()
                    self.select_account()
                elif c == "3":
                    self.multi_account_menu()
                elif c == "4":
                    self.shutdown()
                else:
                    self.print_status("ERROR", self.T['invalid_choice'])
                    time.sleep(0.5)
            except KeyboardInterrupt:
                self.shutdown()
            except Exception as e:
                self.print_status("ERROR", f"Error: {str(e)}")
                self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")

    def dashboard_menu(self):
        while True:
            self.print_header()
            print(f"  {Fore.CYAN}--- {self.T['dashboard_menu']} ---{Style.RESET_ALL}\n")
            print(f"  {Fore.WHITE}[1]{Style.RESET_ALL} {self.T['opt_select_chapter']}")
            print(f"  {Fore.WHITE}[2]{Style.RESET_ALL} {self.T['opt_results']}")
            print(f"  {Fore.WHITE}[3]{Style.RESET_ALL} {self.T['opt_search_answer']}")
            print(f"  {Fore.WHITE}[4]{Style.RESET_ALL} {self.T['opt_logout']}")
            print(f"  {Fore.WHITE}[5]{Style.RESET_ALL} {self.T['opt_exit']}")
            try:
                c = self._input(f"\n  {Fore.CYAN}[>] Select: {Style.RESET_ALL}").strip()
                if c == "":
                    continue
                if c == "1":
                    self.fetch_and_select_chapter()
                elif c == "2":
                    self.navigate_to_results()
                elif c == "3":
                    self.search_answer_interactive()
                elif c == "4":
                    self.print_status("INFO", "Logging out...")
                    self._cleanup_browser()
                    return
                elif c == "5":
                    self.shutdown()
                else:
                    self.print_status("ERROR", self.T['invalid_choice'])
                    time.sleep(0.5)
            except KeyboardInterrupt:
                self.shutdown()
            except Exception as e:
                self.print_status("ERROR", f"Error: {str(e)}")
                self._input(f"\n  {Fore.CYAN}[>] {self.T['press_enter']}{Style.RESET_ALL}")

    def main_menu(self):
        self.select_language()
        while True:
            if not self.page:
                self.login_menu()
            else:
                self.dashboard_menu()


def run_cli(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", type=str)
    parser.add_argument("--password", type=str)
    parser.add_argument("--auto", action="store_true")
    args = parser.parse_args(argv)

    bot = SpeexxBotCLI()
    if args.account and args.password and args.auto:
        bot.auto_run(args.account, args.password)
    else:
        bot.main_menu()
