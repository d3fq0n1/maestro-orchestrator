"""
Interactive mode selector for Maestro-Orchestrator.

Renders a terminal-based arrow-key selector with colored highlights,
letting users pick a launch mode without memorizing commands.

Falls back to a simple numbered prompt when the terminal doesn't
support raw input (e.g. piped stdin, Windows without msvcrt).
"""

import sys


# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------

_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"
_CYAN = "\033[36m"
_YELLOW = "\033[33m"
_GREEN = "\033[32m"
_WHITE = "\033[97m"
_BG_CYAN = "\033[46m"
_BG_DEFAULT = "\033[49m"
_HIDE_CURSOR = "\033[?25l"
_SHOW_CURSOR = "\033[?25h"
_CLEAR_LINE = "\033[2K"


# ---------------------------------------------------------------------------
# Option dataclass-like container
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
        if ch in ("\x03",):  # Ctrl+C
            return "quit"
        if ch in ("\x04",):  # Ctrl+D
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
# Rendering
# ---------------------------------------------------------------------------

def _render_selector(options: list[Option], selected: int, title: str) -> str:
    """Build the selector display string."""
    lines = []
    lines.append("")
    lines.append(f"  {_BOLD}{_CYAN}{'─' * 50}{_RESET}")
    lines.append(f"  {_BOLD}{_WHITE}  {title}{_RESET}")
    lines.append(f"  {_BOLD}{_CYAN}{'─' * 50}{_RESET}")
    lines.append("")

    for i, opt in enumerate(options):
        if i == selected:
            pointer = f"{_BOLD}{_GREEN}  ▸ {_RESET}"
            label = f"{_BOLD}{_WHITE}{_BG_CYAN} {opt.label} {_BG_DEFAULT}{_RESET}"
            desc = f"  {_DIM}{opt.description}{_RESET}"
        else:
            pointer = f"  {_DIM}  {_RESET}"
            label = f"  {_DIM}{opt.label}{_RESET}"
            desc = f"  {_DIM}{opt.description}{_RESET}"
        lines.append(f"{pointer}{label}{desc}")

    lines.append("")
    lines.append(f"  {_DIM}  ↑/↓ Navigate  •  Enter Select  •  Ctrl+C Quit{_RESET}")
    lines.append(f"  {_BOLD}{_CYAN}{'─' * 50}{_RESET}")
    lines.append("")
    return "\n".join(lines)


def _count_render_lines(options: list[Option]) -> int:
    """Count how many lines _render_selector produces."""
    # header(1 blank + 3 box lines + 1 blank) + options + footer(1 blank + 1 hint + 1 line + 1 blank)
    return 5 + len(options) + 4


# ---------------------------------------------------------------------------
# Interactive selector (arrow keys)
# ---------------------------------------------------------------------------

def interactive_select(
    options: list[Option] | None = None,
    title: str = "Maestro-Orchestrator  —  Select Mode",
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
    total_lines = _count_render_lines(options)

    # Initial render
    sys.stdout.write(_HIDE_CURSOR)
    sys.stdout.write(_render_selector(options, selected, title))
    sys.stdout.flush()

    try:
        while True:
            key = _read_key_unix()

            if key == "up":
                selected = (selected - 1) % len(options)
            elif key == "down":
                selected = (selected + 1) % len(options)
            elif key == "enter":
                break
            elif key == "quit" or key == "escape":
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

            # Move cursor up and redraw
            sys.stdout.write(f"\033[{total_lines}A")
            sys.stdout.write(_render_selector(options, selected, title))
            sys.stdout.flush()
    finally:
        sys.stdout.write(_SHOW_CURSOR)
        sys.stdout.flush()

    chosen = options[selected]
    # Replace the selector with a confirmation line
    sys.stdout.write(f"\033[{total_lines}A")
    for _ in range(total_lines):
        sys.stdout.write(f"{_CLEAR_LINE}\n")
    sys.stdout.write(f"\033[{total_lines}A")
    print(f"  {_BOLD}{_GREEN}▸{_RESET} Selected: {_BOLD}{chosen.label}{_RESET}")
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
        print(f"    {i + 1}) {opt.label}  —  {opt.description}")
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
