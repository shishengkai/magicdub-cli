"""Interactive ``magicdub config``: pick one adapter per slot and save slots only."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import questionary
from questionary import Choice, Style

from magicdub_cli import constants as C
from magicdub_cli.adapters.registry import adapter_ids_for_slot
from magicdub_cli.config import load_config, update_slots_in_config_file

_BACK = "__back__"

# Menu order: translation → sep → asr → tts → done (per product spec).
_SLOT_MENU: tuple[tuple[str, str], ...] = (
    ("translation", "翻译模型"),
    ("sep", "声音分离模型"),
    ("asr", "语音识别模型"),
    ("tts", "语音合成模型"),
)

_STYLE = Style(
    [
        ("qmark", "fg:cyan bold"),
        ("question", "bold"),
        ("answer", "fg:cyan"),
        ("pointer", "fg:cyan bold"),
        ("highlighted", "fg:cyan bold"),
        ("selected", "fg:green"),
    ]
)


def _is_interactive_tty() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _current_adapter_id(slots: dict[str, list[str]], slot: str) -> str:
    order = slots.get(slot) or list(C.SLOT_DEFAULTS[slot])
    return str(order[0])


def _select_adapter(slot: str, label: str, current: str) -> str | None:
    """Return selected adapter_id, or None if user chose 返回 / cancelled."""
    ids = adapter_ids_for_slot(slot)
    if not ids:
        print(f"没有已注册的 {label} adapter。", file=sys.stderr)
        return None

    choices: list[Choice] = []
    for aid in ids:
        title = f"✓ {aid}" if aid == current else aid
        choices.append(Choice(title=title, value=aid))
    choices.append(Choice(title="返回", value=_BACK))

    selected = questionary.select(
        f"{label}（当前：{current}）",
        choices=choices,
        default=current if current in ids else ids[0],
        style=_STYLE,
        instruction="(↑↓ 选择，Enter 确认)",
    ).ask()

    if selected is None or selected == _BACK:
        return None
    return str(selected)


def run_config(*, config_path: Path | None = None) -> int:
    """Interactive slot picker. Exit 0 on success / cancel without save; 2 if not a TTY."""
    if not _is_interactive_tty():
        print(
            "magicdub config 需要在可交互终端中运行（支持方向键与 Enter）。",
            file=sys.stderr,
        )
        return 2

    path = config_path or (C.cli_config_dir() / C.CONFIG_FILENAME)
    cfg = load_config(path)
    initial: dict[str, list[str]] = {
        name: list(cfg["slots"][name]) for name in C.SLOT_DEFAULTS
    }
    working: dict[str, list[str]] = copy.deepcopy(initial)

    while True:
        top = questionary.select(
            "配置模型",
            choices=[
                *(_label for _, _label in _SLOT_MENU),
                "完成",
            ],
            style=_STYLE,
            instruction="(↑↓ 选择，Enter 进入)",
        ).ask()

        if top is None:
            # Ctrl-C / Esc: treat as no save if unchanged, else still no save on cancel.
            return 0

        if top == "完成":
            if working == initial:
                print("未更改，不保存。")
                return 0
            update_slots_in_config_file(working, path=path)
            print(f"已保存 slots 到 {path}")
            return 0

        slot = next(s for s, label in _SLOT_MENU if label == top)
        label = top
        current = _current_adapter_id(working, slot)
        chosen = _select_adapter(slot, label, current)
        if chosen is not None:
            working[slot] = [chosen]
