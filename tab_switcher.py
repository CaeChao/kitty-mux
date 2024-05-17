import json
import math
import re

from os.path import expanduser
from itertools import islice
from typing import List, Dict, Any
from kitty.boss import Boss
from kitty.remote_control import create_basic_command, encode_send
from kitty.typing import KeyEventType
from kitty.fast_data_types import current_focused_os_window_id
from kitty.key_encoding import RELEASE
from kittens.tui.handler import Handler
from kittens.tui.loop import Loop
from kittens.tui.operations import styled, repeat


class TabSwitcher(Handler):

    def __init__(self):
        self.tabs = []
        self.selected_tab_idx = -1
        self.selected_win_idx = -1
        self.selected_entry_type = 'tab'
        self.cmds = []
        self.windows_text = {}

    def initialize(self) -> None:
        self.cmd.set_cursor_visible(False)
        self.draw_screen()
        ls = create_basic_command('ls', no_response=False)
        self.write(encode_send(ls))
        self.cmds.append({'type': 'ls'})

    # this assumes that communication via kitty cmds in synchronous...

    def on_kitty_cmd_response(self, response: Dict[str, Any]) -> None:
        cmd = self.cmds.pop()
        if cmd['type'] == 'ls':
            if not response.get('ok'):
                err = response['error']
                if response.get('tb'):
                    err += '\n' + response['tb']
                self.print_on_fail = err
                self.quit_loop(1)
                return
            res = response.get('data')
            os_windows = json.loads(res)
            active_window = next(w for w in os_windows if w['is_active'])
            self.tabs = active_window['tabs']
            self.options_num = len(active_window['tabs'])
            active_tab = next(t for t in self.tabs if t['is_active'])
            self.selected_tab_idx = self.tabs.index(active_tab)
            cmds = []
            for tab in self.tabs:
                for w in tab['windows']:
                    wid = w['id']
                    get_text = create_basic_command(
                        'get-text', {'match': f'id:{wid}', 'ansi': True}, no_response=False)
                    self.write(encode_send(get_text))
                    self.cmds.insert(0, {
                        'type': 'get-text',
                        'os_window_id': active_window['id'],
                        'tab_id': tab['id'],
                        'window_id': wid,
                    })
            self.cmds = self.cmds + cmds
            self.draw_screen()

        if cmd['type'] == 'get-text':
            # replace tabs with two spaces because having a character that spans multiple columns messes up computations
            lines = [Ansi(f'{line}') for line in response['data'].replace(
                '\t', '  ').split('\n')]
            self.windows_text[cmd['window_id']] = lines
            self.draw_screen()

    def on_key_event(self, key_event: KeyEventType, in_bracketed_paste: bool = False) -> None:
        if key_event.type == RELEASE:
            return

        if key_event.matches('esc') or key_event.key == 'q':
            self.quit_loop(0)

        if key_event.matches('enter'):
            self.switch_to_entry()

        if key_event.key == 'l':
            if self.selected_entry_type == 'tab':
                tab = self.tabs[self.selected_tab_idx]
                wins_num = len(tab['windows'])
                display_wins_num = wins_num - \
                    1 if tab['is_active'] else wins_num
                if not tab.get('expanded') and display_wins_num > 1:
                    tab['expanded'] = True
                    self.draw_screen()
            return

        if key_event.key == 'h':
            tab = self.tabs[self.selected_tab_idx]
            if tab.get('expanded'):
                tab['expanded'] = False
                self.selected_entry_type = 'tab'
                self.selected_win_idx = -1
                self.draw_screen()
            return

        if key_event.key == 'j':
            tab = self.tabs[self.selected_tab_idx]
            wins_num = len([w for w in tab['windows'] if w['at_prompt']])
            if tab.get('expanded') and self.selected_win_idx < wins_num - 1:
                self.selected_entry_type = 'win'
                self.selected_win_idx += 1
            else:
                self.selected_entry_type = 'tab'
                self.selected_tab_idx = (
                    self.selected_tab_idx + 1) % len(self.tabs)
                self.selected_win_idx = -1
            self.draw_screen()

        if key_event.key == 'k':
            tab = self.tabs[self.selected_tab_idx]
            previous_tab_idx = (self.selected_tab_idx - 1 +
                                len(self.tabs)) % len(self.tabs)
            previous_tab = self.tabs[previous_tab_idx]
            previous_tab_wins_num = len([
                w for w in previous_tab['windows'] if w['at_prompt']])
            if self.selected_entry_type == 'tab':
                self.selected_tab_idx = previous_tab_idx
                if not previous_tab.get('expanded'):
                    self.selected_entry_type = 'tab'
                else:
                    self.selected_entry_type = 'win'
                    self.selected_win_idx = previous_tab_wins_num - 1
            else:
                if self.selected_win_idx == 0:
                    self.selected_entry_type = 'tab'
                else:
                    self.selected_entry_type = 'win'
                self.selected_win_idx -= 1
            self.draw_screen()

        if key_event.key == 'g':
            self.selected_tab_idx = 0
            self.selected_entry_type = 'tab'
            self.draw_screen()

        if key_event.matches('shift+g'):
            self.selected_tab_idx = len(self.tabs) - 1
            self.selected_entry_type = 'tab'
            tab = self.tabs[self.selected_tab_idx]
            if tab.get('expanded'):
                self.selected_entry_type = 'win'
                self.selected_win_idx = len(tab['windows']) - 1
            self.draw_screen()

    def switch_to_entry(self) -> None:
        window_id = None
        tab = self.tabs[self.selected_tab_idx]
        windows = [w for w in tab['windows'] if w['at_prompt']]
        if self.selected_entry_type == 'tab':
            if tab['is_active']:
                self.quit_loop(0)
                return
            window_id = next(w for w in windows if w['is_active'] or w['is_focused'])['id']
        else: 
            window_id = windows[self.selected_win_idx]['id']
        focus_window = create_basic_command(
            'focus_window', {'match': f'id:{window_id}'}, no_response=True)
        self.write(encode_send(focus_window))
        self.quit_loop(0)

    def draw_screen(self) -> None:
        entry_num = 0
        self.cmd.clear_screen()
        print = self.print
        if not self.tabs:
            return
        for i, tab in enumerate(self.tabs):
            entry_num += 1
            tid = tab['id']
            windows = [w for w in tab['windows'] if w['at_prompt']]
            wins_num = len(windows)
            active_arrow = '➜' if tab['is_active'] else ' '
            expanded = tab.get('expanded')
            expand_icon = ' ' if wins_num <= 1 else '' if expanded else ''
            tab_name = f'({i+1}) {active_arrow} {tab["title"]} - {wins_num} windows {expand_icon}'
            if self.selected_entry_type == 'tab' and i == self.selected_tab_idx:
                print(styled(tab_name, bg='gray', fg='blue'))
            else:
                print(tab_name)
            if expanded:
                for n, w in enumerate(windows):
                    entry_num += 1
                    active_window = '➜' if w['is_active'] else ' '
                    win_name = f'    {active_window} {n+1}: {w["title"]}'
                    if self.selected_entry_type == 'win' and n == self.selected_win_idx:
                        print(styled(win_name, bg='gray', fg='blue'))
                    else:
                        print(win_name)

        # don't draw anything if we have nothing to show, otherwise we can see the borders for
        # a couple of ms. this is an approximation since we might get some text data for another
        # window than the one we're showing, but it seems to do the job.
        if not self.windows_text:
            return

        wins_by_selected_tab = [
            w for w in self.tabs[self.selected_tab_idx]['windows'] if w['at_prompt']]
        wins_to_display = wins_by_selected_tab[self.selected_win_idx] if self.selected_entry_type == 'win' else list(
            islice(wins_by_selected_tab, 0, 4))
        wins_num = len(wins_to_display)
        win_height = math.floor(self.screen_size.rows / 2 - 2)

        # 2 for borders, 1 for the tab_bar
        for _ in range(self.screen_size.rows - entry_num - win_height - 2 - 1):
            print('')

        def print_horizontal_border(left_corner: str, middle_corner: str, right_corner: str):
            border = left_corner
            for idx, win in enumerate(wins_to_display):
                width = tab_width(self.screen_size.cols, wins_num, idx)
                border += repeat('─', width)
                if (idx < wins_num - 1):
                    border += middle_corner
                else:
                    border += right_corner
            print(border)

        print_horizontal_border('┌', '┬', '┐')

        # messy code for window preview display
        lines_by_win = []
        for idx, win in enumerate(wins_to_display):
            new_line = []
            lines = self.windows_text.get(win['id'], '')
            width = tab_width(self.screen_size.cols, wins_num, idx)
            for line in islice(lines, 0, win_height):
                new_line.append(line.slice(width - 2).ljust(width - 2))
            lines_by_win.append(new_line)

        for line in zip(*lines_by_win):
            print('│ ' + '\x1b[0m │ '.join([l.get_raw_text()
                  for l in line]) + ' \x1b[0m│')

        print_horizontal_border('└', '┴', '┘')


# Ansi escaping mostly stolen from
# https://github.com/getcuia/stransi/blob/main/src/stransi/

PATTERN = re.compile(
    r"(\N{ESC}\[[\d;|:]*[a-zA-Z]|\N{ESC}\]133;[A-Z]\N{ESC}\\)")
# ansi--^     shell prompt OSC 133--^


class Ansi:
    def __init__(self, text):
        self.raw_text = text
        self.parsed = list(parse_ansi_colors(self.raw_text))

    def __str__(self):
        return f'Ansi({[str(c) for c in self.parsed]}, {self.raw_text})'

    def get_raw_text(self):
        return self.raw_text

    def slice(self, n):
        chars = 0
        text = ''
        for token in self.parsed:
            if isinstance(token, EscapeSequence):
                text += token.get_sequence()
            else:
                sliced = token[:n - chars]
                text += sliced
                chars += len(sliced)
        return Ansi(text)

    def ljust(self, n):
        chars = 0
        text = ''
        for token in self.parsed:
            if isinstance(token, EscapeSequence):
                text += token.get_sequence()
            else:
                text += token
                chars += len(token)
        for i in range(0, n - chars):
            text += ' '
        return Ansi(text)


class EscapeSequence:
    def __init__(self, sequence: str):
        self.sequence = sequence

    def __str__(self):
        return f'EscapeSequence({self.sequence})'

    def get_sequence(self):
        return self.sequence


def parse_ansi_colors(text: str):
    prev_end = 0
    for match in re.finditer(PATTERN, text):
        # Yield the text before escape sequence.
        yield text[prev_end: match.start()]

        if escape_sequence := match.group(0):
            yield EscapeSequence(escape_sequence)

        # Update the start position.
        prev_end = match.end()

    # Yield the text after the last escape sequence.
    yield text[prev_end:]

# the last tab must sometimes be padded by 1 column so that the preview fits the whole width


def tab_width(cols, tab_count, idx):
    border_count = tab_count + 1
    tab_width = math.floor((cols - border_count)/tab_count)
    if tab_count == 1:
        return tab_width
    if idx == tab_count - 1 and tab_count % 2 == cols % 2:
        return tab_width + 1
    else:
        return tab_width


def main(args: List[str]) -> str:
    loop = Loop()
    handler = TabSwitcher()
    loop.loop(handler)
