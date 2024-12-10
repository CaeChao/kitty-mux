import re
from typing import Any, Dict

from wcwidth.wcwidth import wcswidth


def windows_filter(windows: Dict[str, Any]):
    return [w for w in windows if w["env"].get("KITTY_SHELL_INTEGRATION") == "enabled"]


class Ansi:
    # Ansi escaping mostly stolen from
    # https://github.com/getcuia/stransi/blob/main/src/stransi/

    PATTERN = re.compile(r"(\N{ESC}\[[\d;|:]*[a-zA-Z]|\N{ESC}\]133;[A-Z]\N{ESC}\\)")
    # ansi--^     shell prompt OSC 133--^

    def __init__(self, text):
        self.raw_text = text
        self.parsed = list(self.parse_ansi_colors(self.raw_text))

    def parse_ansi_colors(self, text: str):
        prev_end = 0
        for match in re.finditer(self.PATTERN, text):
            # Yield the text before escape sequence.
            yield text[prev_end : match.start()]

            if escape_sequence := match.group(0):
                yield EscapeSequence(escape_sequence)

            # Update the start position.
            prev_end = match.end()

        # Yield the text after the last escape sequence.
        yield text[prev_end:]

    def __str__(self):
        return f"Ansi({[str(c) for c in self.parsed]}, {self.raw_text})"

    def get_raw_text(self):
        return self.raw_text

    def slice(self, n):
        chars = 0
        text = ""
        for token in self.parsed:
            if isinstance(token, EscapeSequence):
                text += token.get_sequence()
            else:
                # recompute the real width of characters
                real_n = n + len(token) - wcswidth(token) - chars
                if real_n > 0:
                    sliced = token[:real_n]
                    text += sliced
                    chars += wcswidth(sliced)
        return Ansi(text)

    def ljust(self, n):
        chars = 0
        text = ""
        for token in self.parsed:
            if isinstance(token, EscapeSequence):
                text += token.get_sequence()
            else:
                text += token
                chars += wcswidth(token)
        text += " " * (n - chars)
        return Ansi(text)


class EscapeSequence:
    def __init__(self, sequence: str):
        self.sequence = sequence

    def __str__(self):
        return f"EscapeSequence({self.sequence})"

    def get_sequence(self):
        return self.sequence
