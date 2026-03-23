#!/usr/bin/env python3
"""Interactive TUI screens for rerun-failed-checks.

Usage:
  pr-selector.py prs       — PR checklist (toggle which PRs are watched)
  pr-selector.py settings  — General settings (checks mode, interval)

Reads/writes ~/.rerun-failed-checks.json.
"""

import sys
import json
import curses
from pathlib import Path

CONFIG_FILE = Path.home() / ".rerun-failed-checks.json"

INTERVAL_PRESETS = [30, 60, 120, 180, 300, 600]


def load_config():
    if CONFIG_FILE.exists():
        config = json.loads(CONFIG_FILE.read_text())
        # Migrate old flat format (PR keys at top level) to nested "prs" key
        if "prs" not in config:
            prs = {k: v for k, v in config.items() if k not in ("settings", "retries")}
            config = {
                "prs": prs,
                "retries": config.get("retries", {}),
                "settings": config.get("settings", {}),
            }
            save_config(config)
        return config
    return {"prs": {}, "retries": {}, "settings": {}}


def save_config(config):
    CONFIG_FILE.write_text(json.dumps(config, indent=2) + "\n")


def init_colors():
    curses.curs_set(0)
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_CYAN, -1)  # cursor arrow
    curses.init_pair(2, curses.COLOR_GREEN, -1)  # enabled / selected value
    curses.init_pair(3, curses.COLOR_WHITE, -1)  # disabled
    curses.init_pair(4, curses.COLOR_YELLOW, -1)  # header


def format_interval(seconds):
    if seconds < 60:
        return f"{seconds}s"
    mins = seconds // 60
    secs = seconds % 60
    if secs == 0:
        return f"{mins}m"
    return f"{mins}m {secs}s"


# ---------------------------------------------------------------------------
# PR selector screen
# ---------------------------------------------------------------------------
def run_prs(stdscr):
    config = load_config()
    prs = config.get("prs", {})

    if not prs:
        return False, "No PRs tracked yet"

    entries = []
    for pr_number, data in prs.items():
        entries.append(
            {
                "number": pr_number,
                "title": data.get("title", "(no title)"),
                "enabled": data.get("enabled", False),
            }
        )

    cursor = 0
    total = len(entries)

    init_colors()

    def draw():
        stdscr.clear()
        stdscr.addstr(0, 2, "Edit PR auto-rerun settings", curses.A_BOLD | curses.color_pair(4))
        stdscr.addstr(1, 2, "Up/Down: move  |  Space: toggle  |  Enter: save  |  q: cancel", curses.A_DIM)
        stdscr.addstr(2, 2, "─" * 60)

        for i, entry in enumerate(entries):
            y = i + 4
            if i == cursor:
                stdscr.addstr(y, 2, ">", curses.color_pair(1) | curses.A_BOLD)
            else:
                stdscr.addstr(y, 2, " ")

            if entry["enabled"]:
                stdscr.addstr(y, 4, "[x]", curses.color_pair(2) | curses.A_BOLD)
            else:
                stdscr.addstr(y, 4, "[ ]", curses.color_pair(3))

            label = f" #{entry['number']}  {entry['title']}"
            max_width = curses.COLS - 10
            if len(label) > max_width:
                label = label[: max_width - 1] + "…"
            stdscr.addstr(y, 8, label)

        stdscr.addstr(total + 5, 2, "─" * 60)
        stdscr.refresh()

    draw()

    while True:
        key = stdscr.getch()

        if key in (ord("q"), ord("Q"), 27):
            return False, "Edit cancelled"
        elif key in (curses.KEY_UP, ord("k")):
            cursor = max(0, cursor - 1)
        elif key in (curses.KEY_DOWN, ord("j")):
            cursor = min(total - 1, cursor + 1)
        elif key == ord(" "):
            entries[cursor]["enabled"] = not entries[cursor]["enabled"]
        elif key in (10, 13, curses.KEY_ENTER):
            for entry in entries:
                config["prs"][entry["number"]]["enabled"] = entry["enabled"]
            save_config(config)
            return True, entries

        draw()


# ---------------------------------------------------------------------------
# Settings screen
# ---------------------------------------------------------------------------
def run_settings(stdscr):
    config = load_config()
    settings = config.get("settings", {})

    # Current values (with defaults)
    all_checks = settings.get("all_checks", False)
    interval = settings.get("interval", 300)
    max_retries = settings.get("max_retries", 5)

    # Settings rows
    rows = [
        {
            "label": "Checks scope",
            "type": "toggle",
            "values": ["Required only", "All checks"],
            "current": 1 if all_checks else 0,
        },
        {"label": "Max retries", "type": "number", "value": max_retries, "min": 1, "max": 20, "step": 1},
        {"label": "Poll interval", "type": "interval", "value": interval},
    ]

    cursor = 0
    total = len(rows)

    init_colors()

    def draw():
        stdscr.clear()
        stdscr.addstr(0, 2, "Settings", curses.A_BOLD | curses.color_pair(4))
        stdscr.addstr(
            1, 2, "Up/Down: move  |  Space: toggle  |  Left/Right: adjust  |  Enter: save  |  q: cancel", curses.A_DIM
        )
        stdscr.addstr(2, 2, "─" * 60)

        for i, row in enumerate(rows):
            y = i + 4
            if i == cursor:
                stdscr.addstr(y, 2, ">", curses.color_pair(1) | curses.A_BOLD)
            else:
                stdscr.addstr(y, 2, " ")

            label = f"  {row['label']}:"
            stdscr.addstr(y, 3, label)

            value_x = 22
            if row["type"] == "toggle":
                value_str = row["values"][row["current"]]
                stdscr.addstr(y, value_x, value_str, curses.color_pair(2) | curses.A_BOLD)
            elif row["type"] == "number":
                stdscr.addstr(y, value_x, f"◀ {row['value']} ▶", curses.color_pair(2) | curses.A_BOLD)
            elif row["type"] == "interval":
                value_str = format_interval(row["value"])
                stdscr.addstr(y, value_x, f"◀ {value_str} ▶", curses.color_pair(2) | curses.A_BOLD)

        stdscr.addstr(total + 5, 2, "─" * 60)
        stdscr.addstr(total + 6, 2, "Space: cycle value  |  Left/Right: adjust interval", curses.A_DIM)
        stdscr.refresh()

    draw()

    while True:
        key = stdscr.getch()

        if key in (ord("q"), ord("Q"), 27):
            return False, "Settings unchanged"

        elif key in (curses.KEY_UP, ord("k")):
            cursor = max(0, cursor - 1)

        elif key in (curses.KEY_DOWN, ord("j")):
            cursor = min(total - 1, cursor + 1)

        elif key == ord(" "):
            row = rows[cursor]
            if row["type"] == "toggle":
                row["current"] = (row["current"] + 1) % len(row["values"])
            elif row["type"] == "interval":
                try:
                    idx = INTERVAL_PRESETS.index(row["value"])
                    row["value"] = INTERVAL_PRESETS[(idx + 1) % len(INTERVAL_PRESETS)]
                except ValueError:
                    row["value"] = INTERVAL_PRESETS[0]
            elif row["type"] == "number":
                row["value"] = min(row["value"] + row["step"], row["max"])

        elif key == curses.KEY_RIGHT:
            row = rows[cursor]
            if row["type"] == "interval":
                row["value"] = min(row["value"] + 30, 3600)
            elif row["type"] == "toggle":
                row["current"] = (row["current"] + 1) % len(row["values"])
            elif row["type"] == "number":
                row["value"] = min(row["value"] + row["step"], row["max"])

        elif key == curses.KEY_LEFT:
            row = rows[cursor]
            if row["type"] == "interval":
                row["value"] = max(row["value"] - 30, 30)
            elif row["type"] == "toggle":
                row["current"] = (row["current"] - 1) % len(row["values"])
            elif row["type"] == "number":
                row["value"] = max(row["value"] - row["step"], row["min"])

        elif key in (10, 13, curses.KEY_ENTER):
            config["settings"] = {
                "all_checks": rows[0]["current"] == 1,
                "max_retries": rows[1]["value"],
                "interval": rows[2]["value"],
            }
            save_config(config)
            return True, config["settings"]

        draw()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) < 2:
        print("Usage: pr-selector.py [prs|settings]")  # noqa: T201
        sys.exit(1)

    mode = sys.argv[1]

    if mode == "prs":
        saved, result = curses.wrapper(run_prs)
        if saved and isinstance(result, list):
            print("PR settings saved:")  # noqa: T201
            for entry in result:
                status = "ENABLED " if entry["enabled"] else "DISABLED"
                print(f"  {status}  #{entry['number']}  {entry['title']}")  # noqa: T201
        else:
            print(result)  # noqa: T201

    elif mode == "settings":
        saved, result = curses.wrapper(run_settings)
        if saved and isinstance(result, dict):
            checks = "all" if result["all_checks"] else "required only"
            max_r = result["max_retries"]
            print(  # noqa: T201
                f"Settings saved: checks={checks}, max-retries={max_r}, interval={format_interval(result['interval'])}"
            )
        else:
            print(result)  # noqa: T201

    else:
        print(f"Unknown mode: {mode}")  # noqa: T201
        sys.exit(1)


if __name__ == "__main__":
    main()
