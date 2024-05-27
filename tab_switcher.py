import argparse
import json
import math
import re
from itertools import islice
from typing import Any, Dict, List

from kittens.tui.handler import Handler
from kittens.tui.loop import Loop
from kittens.tui.operations import repeat, styled
from kitty.key_encoding import RELEASE
from kitty.remote_control import CommandEncrypter, NoEncryption, create_basic_command, encode_send, get_pubkey
from kitty.typing import KeyEventType

from utils import Ansi, windows_filter

parser = argparse.ArgumentParser(description="kitty-mux")
parser.add_argument(
    "--password",
    dest="password",
    action="append",
    default=[],
    help="remote control password",
)


class TabSwitcher(Handler):

    def __init__(self, password: str):
        v, pubkey = get_pubkey()
        self.tabs = []
        self.selected_tab_idx = -1
        self.selected_win_idx = -1
        self.selected_entry_type = "tab"
        self.cmds = []
        self.windows_text = {}
        self.last_active_tab = {"id": None, "layout": None}
        self.encrypter = (
            CommandEncrypter(pubkey=pubkey, encryption_version=v, password=password) if password else NoEncryption()
        )

    def initialize(self) -> None:
        self.cmd.set_cursor_visible(False)
        self.draw_screen()
        self.send_rc_cmd(name="ls", payload=None, encrypter=self.encrypter, no_response=False)
        self.cmds.append({"type": "ls"})

    # send remote control command with password option
    def send_rc_cmd(self, name: str, payload: Any, encrypter: CommandEncrypter, no_response=True) -> None:
        send = encrypter(create_basic_command(name, payload, no_response))
        self.write(encode_send(send))

    # this assumes that communication via kitty cmds in synchronous...
    def on_kitty_cmd_response(self, response: Dict[str, Any]) -> None:
        cmd = self.cmds.pop()
        if cmd["type"] == "ls":
            if not response.get("ok"):
                err = response["error"]
                if response.get("tb"):
                    err += "\n" + response["tb"]
                self.print_on_fail = err
                self.quit_loop(1)
                return
            res = response.get("data")
            os_windows = json.loads(res)
            active_os_window = next(w for w in os_windows if w["is_active"])
            self.tabs = active_os_window["tabs"]
            active_tab = next(t for t in self.tabs if t["is_active"])
            self.selected_tab_idx = self.tabs.index(active_tab)

            # change the kitten overlay window to stack layout
            if active_tab["layout"] != "stack":
                self.last_active_tab = {"id": active_tab["id"], "layout": active_tab["layout"]}
                self.send_rc_cmd(
                    "goto-layout",
                    {"match": f'id:{active_tab["id"]}', "layout": "stack"},
                    self.encrypter,
                    no_response=True,
                )

            cmds = []
            for tab in self.tabs:
                for w in tab["windows"]:
                    wid = w["id"]
                    self.send_rc_cmd(
                        "get-text",
                        {"match": f"id:{wid}", "ansi": True},
                        self.encrypter,
                        no_response=False,
                    )
                    self.cmds.insert(
                        0,
                        {
                            "type": "get-text",
                            "os_window_id": active_os_window["id"],
                            "tab_id": tab["id"],
                            "window_id": wid,
                        },
                    )
            self.cmds = self.cmds + cmds
            # self.draw_screen()

        if cmd["type"] == "get-text":
            # replace tabs with two spaces because having a character that spans multiple columns messes up computations, and replace '\x1b[m' with \n in order to break lines
            lines = [
                Ansi(f"{line}")
                for line in re.sub(r"[\r\n]*(\x1b\[m)", "\n", response["data"]).replace("\t", "  ").split("\n")
            ]
            self.windows_text[cmd["window_id"]] = lines
            self.draw_screen()

    def on_exit(self) -> None:
        # recover the last layout of the active tab
        if self.last_active_tab["layout"]:
            self.send_rc_cmd(
                "goto-layout",
                {
                    "match": f'id:{self.last_active_tab["id"]}',
                    "layout": f'{self.last_active_tab["layout"]}',
                },
                self.encrypter,
                no_response=True,
            )
        self.quit_loop(0)

    def on_key_event(self, key_event: KeyEventType, in_bracketed_paste: bool = False) -> None:
        if key_event.type == RELEASE:
            return

        if key_event.matches("esc") or key_event.key == "q":
            self.on_exit()

        if key_event.matches("enter"):
            self.switch_to_entry()

        if key_event.key == "l":
            if self.selected_entry_type == "tab":
                tab = self.tabs[self.selected_tab_idx]
                wins_num = len(windows_filter(tab["windows"]))
                if not tab.get("expanded") and wins_num > 1:
                    tab["expanded"] = True
                    self.draw_screen()
            return

        if key_event.key == "h":
            tab = self.tabs[self.selected_tab_idx]
            if tab.get("expanded"):
                tab["expanded"] = False
                self.selected_entry_type = "tab"
                self.selected_win_idx = -1
                self.draw_screen()
            return

        if key_event.key == "j":
            tab = self.tabs[self.selected_tab_idx]
            wins_num = len(windows_filter(tab["windows"]))
            if tab.get("expanded") and self.selected_win_idx < wins_num - 1:
                self.selected_entry_type = "win"
                self.selected_win_idx += 1
            else:
                self.selected_entry_type = "tab"
                self.selected_tab_idx = (self.selected_tab_idx + 1) % len(self.tabs)
                self.selected_win_idx = -1
            self.draw_screen()

        if key_event.key == "k":
            tab = self.tabs[self.selected_tab_idx]
            previous_tab_idx = (self.selected_tab_idx - 1 + len(self.tabs)) % len(self.tabs)
            previous_tab = self.tabs[previous_tab_idx]
            previous_tab_wins_num = len(windows_filter(previous_tab["windows"]))
            if self.selected_entry_type == "tab":
                self.selected_tab_idx = previous_tab_idx
                if not previous_tab.get("expanded"):
                    self.selected_entry_type = "tab"
                else:
                    self.selected_entry_type = "win"
                    self.selected_win_idx = previous_tab_wins_num - 1
            else:
                if self.selected_win_idx == 0:
                    self.selected_entry_type = "tab"
                else:
                    self.selected_entry_type = "win"
                self.selected_win_idx -= 1
            self.draw_screen()

        if key_event.key == "g":
            self.selected_tab_idx = 0
            self.selected_entry_type = "tab"
            self.draw_screen()

        if key_event.matches("shift+g"):
            self.selected_tab_idx = len(self.tabs) - 1
            self.selected_entry_type = "tab"
            tab = self.tabs[self.selected_tab_idx]
            if tab.get("expanded"):
                self.selected_entry_type = "win"
                self.selected_win_idx = len(tab["windows"]) - 1
            self.draw_screen()

    def switch_to_entry(self) -> None:
        window_id = None
        tab = self.tabs[self.selected_tab_idx]
        windows = windows_filter(tab["windows"])
        if self.selected_entry_type == "tab":
            if tab["is_active"]:
                self.on_exit()
                return
            window_id = next(w for w in windows if w["is_active"] or w["is_focused"])["id"]
        else:
            window_id = windows[self.selected_win_idx]["id"]
        self.send_rc_cmd("focus-window", {"match": f"id:{window_id}"}, self.encrypter, no_response=True)
        self.quit_loop(0)

    def draw_screen(self) -> None:
        entry_num = 0
        self.cmd.clear_screen()
        draw = self.print
        if not self.tabs:
            return
        for i, tab in enumerate(self.tabs):
            entry_num += 1
            active_arrow = " "
            active_group = []
            if tab["is_active"]:
                active_arrow = "➜"
                active_group = next(g for g in tab["groups"] if len(g["windows"]) > 1)["windows"]
            windows = windows_filter(tab["windows"])
            wins_num = len(windows)
            expanded = tab.get("expanded")
            expand_icon = " " if wins_num <= 1 else "" if expanded else ""
            tab_name = f'({i+1}) {active_arrow} {tab["title"]} - {wins_num} windows {expand_icon}'
            # Draw tab entries
            tab_entry = (
                styled(tab_name, bg=8, fg="blue")
                if self.selected_entry_type == "tab" and i == self.selected_tab_idx
                else tab_name
            )
            draw(tab_entry)
            # Draw window entries if tab expanded
            if expanded:
                for n, w in enumerate(windows):
                    entry_num += 1
                    active_window = active_arrow if w["id"] in active_group else " "
                    win_name = f'{" "*(len(str(i+1))+ 5)}{active_window} {n+1}: {w["title"]}'
                    win_entry = (
                        styled(win_name, bg=8, fg="blue")
                        if i == self.selected_tab_idx
                        and self.selected_entry_type == "win"
                        and n == self.selected_win_idx
                        else win_name
                    )
                    draw(win_entry)

        # don't draw anything if we have nothing to show, otherwise we can see the borders for
        # a couple of ms. this is an approximation since we might get some text data for another
        # window than the one we're showing, but it seems to do the job.
        if not self.windows_text:
            return

        wins_by_selected_tab = windows_filter(self.tabs[self.selected_tab_idx]["windows"])
        wins_to_display = (
            [wins_by_selected_tab[self.selected_win_idx]]
            if self.selected_entry_type == "win"
            else list(islice(wins_by_selected_tab, 0, 4))
        )
        wins_num = len(wins_to_display)
        win_height = math.floor(self.screen_size.rows / 2 - 2)

        # 2 for borders, 1 for the tab_bar
        for _ in range(self.screen_size.rows - entry_num - win_height - 2 - 1):
            draw("")

        def print_horizontal_border(left_corner: str, middle_corner: str, right_corner: str):
            border = left_corner
            for idx in range(wins_num):
                width = window_width(self.screen_size.cols, wins_num, idx)
                border += repeat("─", width)
                if idx < wins_num - 1:
                    border += middle_corner
                else:
                    border += right_corner
            draw(border)

        print_horizontal_border("┌", "┬", "┐")

        # messy code for window preview display
        lines_by_win = []
        for idx, win in enumerate(wins_to_display):
            new_line = []
            lines = self.windows_text.get(win["id"], "")
            width = window_width(self.screen_size.cols, wins_num, idx)
            for line in islice(lines, 0, win_height):
                line = line.slice(width - 2).ljust(width - 2)
                new_line.append(line)
            lines_by_win.append(new_line)

        for line in zip(*lines_by_win):
            draw("│ " + "\x1b[0m │ ".join([l.get_raw_text() for l in line]) + " \x1b[0m│")

        print_horizontal_border("└", "┴", "┘")


# the last tab must sometimes be padded by 1 column so that the preview fits the whole width
def window_width(cols, win_count, idx):
    border_count = win_count + 1
    win_width = math.floor((cols - border_count) / win_count)
    if idx == win_count - 1 and win_count % 2 == cols % 2 and win_count > 1:
        return win_width + 1
    else:
        return win_width


def main(args: List[str]) -> str:
    loop = Loop()
    opts = parser.parse_args(args[1:])
    handler = TabSwitcher(opts.password[0])
    loop.loop(handler)
