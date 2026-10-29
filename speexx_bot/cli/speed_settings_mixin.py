"""SpeedSettingsMixin — granular per-point timing editor (no preset profiles)."""

import os
import time

from ..ui_utils import Fore, Style
from ..speed_config import DEFAULTS, DESCRIPTIONS, GROUPS, get, get_all, set_value, reset_defaults, get_default

class SpeedSettingsMixin:
    def speed_settings_menu(self):
        while True:
            self.print_header()
            print(f"  {Fore.CYAN}--- {self.T.get('speed_menu_title', 'ตั้งค่าความเร็วแบบละเอียด')} ---{Style.RESET_ALL}\n")
            print(f"  {Fore.YELLOW}{self.T.get('speed_menu_hint', 'แต่ละจุดตั้งค่าได้ละเอียดเป็นวินาที/ครั้ง — ไม่ใช่เลือกโปรไฟล์สำเร็จรูป')}{Style.RESET_ALL}\n")

            all_vals = get_all()
            # Show groups summary
            print(f"  {Fore.WHITE}หมวดหมู่:{Style.RESET_ALL}")
            group_list = list(GROUPS.keys())
            for idx, gname in enumerate(group_list, 1):
                keys = GROUPS[gname]
                # Show current vs default compact
                vals_str = ", ".join([f"{k.split('_')[0][:3]}:{all_vals[k]:.2f}" for k in keys[:3]])
                if len(keys) > 3:
                    vals_str += f" +{len(keys)-3}"
                print(f"    {Fore.WHITE}[{idx}]{Style.RESET_ALL} {gname} ({len(keys)} จุด) — {Fore.CYAN}{vals_str}{Style.RESET_ALL}")
            print(f"    {Fore.WHITE}[0]{Style.RESET_ALL} {self.T.get('back', 'ย้อนกลับ')}")
            print(f"    {Fore.WHITE}[R]{Style.RESET_ALL} {self.T.get('speed_reset', 'รีเซ็ตเป็นค่าเริ่มต้น')}")
            print(f"    {Fore.WHITE}[S]{Style.RESET_ALL} {self.T.get('speed_show_all', 'ดูค่าทั้งหมด')}")

            try:
                choice = self._input(f"\n  {Fore.CYAN}[>] เลือกหมวด (เช่น 1) หรือ R/S/0: {Style.RESET_ALL}").strip()
            except (EOFError, KeyboardInterrupt):
                return
            if choice == "" or choice == "0":
                return
            if choice.lower() == "r":
                reset_defaults()
                self.print_status("OK", self.T.get("speed_reset_done", "รีเซ็ตเป็นค่าเริ่มต้นแล้ว"))
                time.sleep(0.8)
                continue
            if choice.lower() == "s":
                self._show_all_speeds()
                continue
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(group_list):
                    self._edit_speed_group(group_list[idx])
            except ValueError:
                self.print_status("ERROR", self.T.get("invalid_choice", "ตัวเลือกไม่ถูกต้อง"))
                time.sleep(0.6)

    def _show_all_speeds(self):
        self.print_header()
        print(f"  {Fore.CYAN}--- ค่าทั้งหมด ({len(DEFAULTS)} จุด) ---{Style.RESET_ALL}\n")
        all_vals = get_all()
        for gname, keys in GROUPS.items():
            print(f"  {Fore.YELLOW}{gname}:{Style.RESET_ALL}")
            for k in keys:
                cur = all_vals[k]
                default = get_default(k)
                desc = DESCRIPTIONS.get(k, "")
                marker = f"{Fore.GREEN}*" if cur == default else f"{Fore.YELLOW}≠{Style.RESET_ALL}"
                print(f"    {marker} {Fore.WHITE}{k}{Style.RESET_ALL} = {Fore.CYAN}{cur}{Style.RESET_ALL} (default {default}) — {desc}")
            print()
        self._input(f"  {Fore.CYAN}[>] {self.T.get('press_enter', 'กด Enter เพื่อดำเนินการต่อ...')}{Style.RESET_ALL}")

    def _edit_speed_group(self, group_name):
        keys = GROUPS[group_name]
        while True:
            self.print_header()
            print(f"  {Fore.CYAN}--- หมวด: {group_name} ({len(keys)} จุด) ---{Style.RESET_ALL}\n")
            all_vals = get_all()
            for idx, k in enumerate(keys, 1):
                cur = all_vals[k]
                default = get_default(k)
                desc = DESCRIPTIONS.get(k, "")
                is_default = "✔" if cur == default else "★ แก้แล้ว"
                color = Fore.GREEN if cur == default else Fore.YELLOW
                print(f"  {Fore.WHITE}[{idx}]{Style.RESET_ALL} {color}{k}{Style.RESET_ALL} = {Fore.CYAN}{cur}{Style.RESET_ALL} (default {default}) {Fore.CYAN}{is_default}{Style.RESET_ALL}")
                print(f"       {Fore.CYAN}↳ {desc}{Style.RESET_ALL}")
            print(f"\n  {Fore.WHITE}[0]{Style.RESET_ALL} กลับ")
            print(f"  {Fore.WHITE}[R]{Style.RESET_ALL} รีเซ็ตหมวดนี้")
            print(f"  {Fore.YELLOW}พิมพ์เลขแล้วใส่ค่าใหม่ เช่น 2 → 1.2 (วินาที) หรือ 1,3 → 0.8,1.5{Style.RESET_ALL}")

            try:
                choice = self._input(f"\n  {Fore.CYAN}[>] เลือกจุดที่แก้ (0=กลับ): {Style.RESET_ALL}").strip()
            except (EOFError, KeyboardInterrupt):
                return
            if choice == "" or choice == "0":
                return
            if choice.lower() == "r":
                for k in keys:
                    set_value(k, get_default(k))
                self.print_status("OK", f"รีเซ็ตหมวด {group_name} แล้ว")
                time.sleep(0.8)
                continue
            # Handle batch: "2" or "1,3" or "2=1.2"
            try:
                # If contains "=", it's single assignment: "2=1.5" or "NAME=1.5"
                if "=" in choice:
                    left, right = choice.split("=", 1)
                    left = left.strip()
                    right = right.strip()
                    target_keys = []
                    if left.isdigit():
                        idx = int(left) - 1
                        if 0 <= idx < len(keys):
                            target_keys = [keys[idx]]
                    elif left.upper() in [k.upper() for k in keys] or left in keys:
                        # find matching key case-insensitive
                        for k in keys:
                            if k.upper() == left.upper():
                                target_keys = [k]
                                break
                    else:
                        # try comma list left
                        for part in left.split(","):
                            part = part.strip()
                            if part.isdigit():
                                idx = int(part) - 1
                                if 0 <= idx < len(keys):
                                    target_keys.append(keys[idx])
                    if not target_keys:
                        self.print_status("ERROR", "ไม่พบคีย์ที่ระบุ")
                        time.sleep(0.8)
                        continue
                    vals = [v.strip() for v in right.split(",")]
                    for tk, vstr in zip(target_keys, vals):
                        try:
                            v = float(vstr) if "." in vstr else int(vstr)
                            if set_value(tk, v):
                                self.print_status("OK", f"{tk} = {v}")
                            else:
                                self.print_status("ERROR", f"ตั้ง {tk} ไม่สำเร็จ")
                        except ValueError:
                            self.print_status("ERROR", f"ค่า '{vstr}' ไม่ใช่ตัวเลข")
                    time.sleep(0.8)
                    continue

                # Simple single selection: "2"
                if "," not in choice and choice.isdigit():
                    idx = int(choice) - 1
                    if 0 <= idx < len(keys):
                        k = keys[idx]
                        cur = get(k)
                        default = get_default(k)
                        desc = DESCRIPTIONS.get(k, "")
                        print(f"\n  แก้ไข {Fore.CYAN}{k}{Style.RESET_ALL} — {desc}")
                        print(f"  ปัจจุบัน {Fore.CYAN}{cur}{Style.RESET_ALL} | ค่าเริ่มต้น {default}")
                        try:
                            new_val = self._input(f"  {Fore.CYAN}[>] ใส่ค่าใหม่ (วินาที/ครั้ง) หรือ Enter=ข้าม: {Style.RESET_ALL}").strip()
                            if new_val == "":
                                continue
                            v = float(new_val) if "." in new_val or "e" in new_val.lower() else int(new_val)
                            if v < 0:
                                self.print_status("ERROR", "ค่าต้อง >= 0")
                                time.sleep(0.8)
                                continue
                            if v > 120 and "TIME" in k:
                                self.print_status("WAIT", "ค่าสูงมาก — จะช้ามาก!")
                                time.sleep(0.6)
                            if set_value(k, v):
                                self.print_status("OK", f"{k} = {v} แล้ว (default {default})")
                            else:
                                self.print_status("ERROR", "บันทึกไม่สำเร็จ")
                            time.sleep(0.8)
                        except ValueError:
                            self.print_status("ERROR", "ต้องเป็นตัวเลขเท่านั้น")
                            time.sleep(0.8)
                    continue

                # Batch comma: "1,3,5"
                if "," in choice:
                    parts = [p.strip() for p in choice.split(",") if p.strip()]
                    # Ask for values
                    print(f"\n  จะแก้ {len(parts)} จุด: {', '.join(parts)}")
                    for part in parts:
                        if part.isdigit():
                            idx = int(part) - 1
                            if 0 <= idx < len(keys):
                                k = keys[idx]
                                cur = get(k)
                                print(f"    {k} ตอนนี้ {cur} → ", end="")
                                try:
                                    nv = self._input("").strip()
                                    if nv == "":
                                        continue
                                    v = float(nv) if "." in nv else int(nv)
                                    set_value(k, v)
                                    print(f"      → OK {k}={v}")
                                except ValueError:
                                    self.print_status("ERROR", f"'{nv}' ไม่ใช่ตัวเลข")
                            else:
                                self.print_status("ERROR", f"เลข {part} เกินช่วง")
                    time.sleep(0.8)
                    continue

                self.print_status("ERROR", "รูปแบบไม่ถูกต้อง — ลอง 2 หรือ 2=1.5 หรือ 1,3")
                time.sleep(0.8)
            except Exception as e:
                self.print_status("ERROR", f"Error: {e}")
                time.sleep(0.8)
