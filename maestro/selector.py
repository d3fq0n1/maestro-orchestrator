"""
Interactive mode selector for Maestro-Orchestrator.

Renders a terminal-based arrow-key selector with colored highlights,
letting users pick a launch mode without memorizing commands.

Falls back to a simple numbered prompt when the terminal doesn't
support raw input (e.g. piped stdin, Windows without msvcrt).
"""

import os
import sys


# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------

_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_WHITE = "\033[97m"
_BG_CYAN = "\033[46m"
_BG_DEFAULT = "\033[49m"
_HIDE_CURSOR = "\033[?25l"
_SHOW_CURSOR = "\033[?25h"
_CLEAR_LINE = "\033[2K"
_MOVE_UP = "\033[A"


# ---------------------------------------------------------------------------
# Option container
# ---------------------------------------------------------------------------

class Option:
    __slots__ = ("key", "label", "description", "icon")

    def __init__(self, key: str, label: str, description: str, icon: str = ">"):
        self.key = key
        self.label = label
        self.description = description
        self.icon = icon


# ---------------------------------------------------------------------------
# Default Maestro options
# ---------------------------------------------------------------------------

MODE_OPTIONS = [
    Option("tui", "TUI Dashboard", "Terminal dashboard optimized for SoC / Raspi", icon="[T]"),
    Option("cli", "Interactive CLI", "Command-line REPL with full pipeline access", icon="[C]"),
    Option("web", "Web UI", "Full dashboard (API + React UI on port 8000)", icon="[W]"),
]


# ---------------------------------------------------------------------------
# Terminal helpers
# ---------------------------------------------------------------------------

def _get_term_width() -> int:
    """Get terminal width, defaulting to 80."""
    try:
        return os.get_terminal_size().columns
    except (OSError, ValueError):
        return 80


# ---------------------------------------------------------------------------
# Raw terminal input (Unix)
# ---------------------------------------------------------------------------

def _read_key_unix():
    """Read a single keypress (including arrow keys) on Unix."""
    import tty
    import termios
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            seq = sys.stdin.read(2)
            if seq == "[A":
                return "up"
            if seq == "[B":
                return "down"
            return "escape"
        if ch in ("\r", "\n"):
            return "enter"
        if ch == "\x03":  # Ctrl+C
            return "quit"
        if ch == "\x04":  # Ctrl+D
            return "quit"
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _supports_raw_input() -> bool:
    """Check if we can do raw terminal input."""
    if not sys.stdin.isatty():
        return False
    try:
        import termios  # noqa: F401
        import tty  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Rendering — fixed line count, every line cleared before write
# ---------------------------------------------------------------------------

# Layout (fixed 10 lines regardless of option count up to 5):
#   line 0: blank
#   line 1: top border
#   line 2: title
#   line 3: bottom border
#   line 4: blank
#   line 5..5+N-1: options (one per line)
#   line 5+N: blank
#   line 5+N+1: hint
#   line 5+N+2: blank

_FIXED_CHROME = 8  # non-option lines (3 header + 1 blank + 1 blank + 1 blank + 1 hint + 1 blank)


def _total_lines(n_options: int) -> int:
    return _FIXED_CHROME + n_options


def _render_lines(options: list[Option], selected: int, title: str, width: int) -> list[str]:
    """Build a list of plain-content lines (each will be written after CLEAR_LINE)."""
    # Usable width for visible text (subtract leading 4 chars for indent)
    max_text = width - 2  # leave a little margin

    lines: list[str] = []

    bar = "─" * min(48, width - 6)
    lines.append("")                                                          # 0: blank
    lines.append(f"  {_BOLD}{_CYAN}{bar}{_RESET}")                           # 1: top border
    lines.append(f"  {_BOLD}{_WHITE}  {title}{_RESET}")                      # 2: title
    lines.append(f"  {_BOLD}{_CYAN}{bar}{_RESET}")                           # 3: bottom border
    lines.append("")                                                          # 4: blank

    for i, opt in enumerate(options):
        if i == selected:
            line = (
                f"  {_BOLD}{_GREEN}\u25b8{_RESET} "
                f"{_BOLD}{_WHITE}{_BG_CYAN} {opt.label} {_BG_DEFAULT}{_RESET}"
            )
        else:
            line = f"    {_DIM}{opt.label}{_RESET}"
        lines.append(line)

    lines.append("")                                                          # blank
    lines.append(
        f"  {_DIM}\u2191/\u2193 Navigate  \u2022  Enter Select  "
        f"\u2022  Ctrl+C Quit{_RESET}"
    )
    lines.append("")                                                          # trailing blank

    return lines


def _write_frame(lines: list[str]) -> None:
    """Write all lines, clearing each line first to avoid artifacts."""
    out = sys.stdout
    for line in lines:
        out.write(f"{_CLEAR_LINE}{line}\n")
    out.flush()


def _move_to_top(n: int) -> None:
    """Move cursor up n lines."""
    if n > 0:
        sys.stdout.write(f"\033[{n}A")


# ---------------------------------------------------------------------------
# Interactive selector (arrow keys)
# ---------------------------------------------------------------------------

def interactive_select(
    options: list[Option] | None = None,
    title: str = "Maestro: Orchestrating Persistent AI Infrastructure",
) -> str:
    """
    Show a fancy interactive selector and return the chosen option key.

    Falls back to a plain numbered prompt if raw terminal input is not
    available.

    Returns the ``key`` attribute of the selected :class:`Option`.
    """
    if options is None:
        options = MODE_OPTIONS

    if not _supports_raw_input():
        return _plain_select(options, title)

    selected = 0
    width = _get_term_width()
    n_lines = _total_lines(len(options))

    # Initial render
    sys.stdout.write(_HIDE_CURSOR)
    _write_frame(_render_lines(options, selected, title, width))

    try:
        while True:
            key = _read_key_unix()

            if key == "up":
                selected = (selected - 1) % len(options)
            elif key == "down":
                selected = (selected + 1) % len(options)
            elif key == "enter":
                break
            elif key in ("quit", "escape"):
                sys.stdout.write(_SHOW_CURSOR)
                sys.stdout.flush()
                print(f"\n  {_DIM}[Maestro] Cancelled.{_RESET}")
                raise SystemExit(0)
            else:
                # Number keys for quick selection
                try:
                    num = int(key) - 1
                    if 0 <= num < len(options):
                        selected = num
                        break
                except (ValueError, TypeError):
                    pass
                continue

            # Move cursor back to top of our block and redraw
            _move_to_top(n_lines)
            _write_frame(_render_lines(options, selected, title, width))
    finally:
        sys.stdout.write(_SHOW_CURSOR)
        sys.stdout.flush()

    chosen = options[selected]

    # Clear the selector block and replace with a single confirmation line
    _move_to_top(n_lines)
    for _ in range(n_lines):
        sys.stdout.write(f"{_CLEAR_LINE}\n")
    _move_to_top(n_lines)
    sys.stdout.flush()
    print(f"  {_BOLD}{_GREEN}\u25b8{_RESET} Selected: {_BOLD}{chosen.label}{_RESET}")
    print()

    return chosen.key


# ---------------------------------------------------------------------------
# Plain fallback (numbered prompt)
# ---------------------------------------------------------------------------

def _plain_select(options: list[Option], title: str) -> str:
    """Simple numbered prompt for non-interactive terminals."""
    print()
    print(f"  {'=' * 50}")
    print(f"    {title}")
    print(f"  {'=' * 50}")
    print()
    for i, opt in enumerate(options):
        print(f"    {i + 1}) {opt.label}  \u2014  {opt.description}")
    print()
    try:
        answer = input("  Enter choice [1]: ").strip()
    except (EOFError, KeyboardInterrupt):
        answer = ""

    for i, opt in enumerate(options):
        if answer == str(i + 1):
            return opt.key

    # Default to first option
    return options[0].key
