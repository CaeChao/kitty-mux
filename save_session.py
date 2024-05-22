#!/usr/bin/env python3

import argparse
import json
import subprocess
from typing import List
import os
from os.path import expanduser
from utils import windows_filter
from kitty.boss import Boss
from kittens.tui.handler import result_handler

parser = argparse.ArgumentParser(description="kitty-mux")
parser.add_argument(
    "--password",
    dest="password",
    action="append",
    default=[],
    help="remote control password",
)


# Convert an env list to a series of '--env key=value' parameters and return as a string
def env_to_str(env):
    s = ""
    for key in env:
        s += f"--env {key}={env[key]} "

    return s.strip()


#Convert a cmdline list to a space separated string.
def cmdline_to_str(cmdline):
    s = ""
    for e in cmdline:
        s += f"{e} "

    return s.strip()


# Convert a foreground_processes list to a space separated string."""
def fg_proc_to_str(fg):
    s = ""
    fg = fg[0]

    s += f"{cmdline_to_str(fg['cmdline'])}"

    if s == "kitty @ ls":
        return os.getenv("SHELL")
    return s

#Convert a kitty session json, into a kitty session text.
def convert(os_windows):
    output = ''
    active_os_window = next(w for w in os_windows if w['is_active'])

    for tab in active_os_window["tabs"]:
        output += "\n"
        output += f"new_tab {tab['title']}\n"
        output += f"layout {tab['layout']}\n"

        windows = windows_filter(tab['windows'])

        for w in windows:
            output += f"title {w['title']}\n"
            output += f"cd {w['cwd']}\n"

            output += f"launch {env_to_str(w['env'])} {fg_proc_to_str(w['foreground_processes'])}\n"

            if w["is_focused"]:
                output += "focus\n"

    return output


def main(args: List[str]) -> str:
    opts = parser.parse_args(args[1:])
    kitty_ls = json.loads(
        subprocess.run(
            ["kitty", "@", "--password="f'{opts.password[0]}'"", "ls"], capture_output=True, text=True
        ).stdout.strip("\n")
    )
    session = convert(kitty_ls)
    return session


def handle_result(args: List[str], answer: str, target_window_id: int, boss: Boss) -> None:
    with open(f"{expanduser('~')}/.config/kitty/kitty-mux/kitty-session", "w") as f:
        f.write(answer)
