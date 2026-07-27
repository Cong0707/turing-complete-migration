"""Command-line and interactive user interface."""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from datetime import datetime
from pathlib import Path
import json
import sys

from . import __version__
from .migration import (
    install_prepared,
    postflight_check,
    prepare_migration,
    rollback_backup,
    verify_save,
)
from .saves import DEFAULT_GAME_DIR, DEFAULT_SAVE_ROOTS, inspect_save


def _print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _ask_path(prompt: str, default: Path | None = None) -> Path:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return Path(value) if value else Path(default) if default else Path()


def _confirm_exact(prompt: str, phrase: str) -> bool:
    print(prompt)
    return input(f"请输入 {phrase} 继续: ").strip() == phrase


def _ask_yes_no(prompt: str, *, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    value = input(f"{prompt} {suffix}: ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes", "是", "好"}


def _choose_source() -> Path:
    print("\n选择源存档：")
    print(f"1. 0.1059  {DEFAULT_SAVE_ROOTS['0.1059']}")
    print(f"2. 2.0.16  {DEFAULT_SAVE_ROOTS['2.0.16']}")
    print("3. 自定义路径")
    choice = input("选择 [1]: ").strip() or "1"
    if choice == "2":
        return DEFAULT_SAVE_ROOTS["2.0.16"]
    if choice == "3":
        return _ask_path("源存档路径")
    return DEFAULT_SAVE_ROOTS["0.1059"]


def interactive() -> int:
    while True:
        print(f"\n=== Turing Complete 存档迁移工具 {__version__} ===")
        print("1. 检查存档")
        print("2. 准备迁移（只写新目录）")
        print("3. 验证迁移目录/存档")
        print("4. 安装已准备的迁移存档")
        print("5. 从备份回滚")
        print("6. 游戏运行后的迁移复检")
        print("0. 退出")
        choice = input("选择: ").strip()
        try:
            if choice == "0":
                return 0
            if choice == "1":
                _print_json(inspect_save(_ask_path("存档路径", DEFAULT_SAVE_ROOTS["2.1.276"])).to_dict())
            elif choice == "2":
                source = _choose_source()
                target = _ask_path("最新版目标存档路径", DEFAULT_SAVE_ROOTS["2.1.276"])
                default_output = Path.cwd() / f"migration-output-{datetime.now():%Y%m%d-%H%M%S}"
                output = _ask_path("迁移输出目录", default_output)
                game_dir = _ask_path("最新版游戏目录", DEFAULT_GAME_DIR)
                archive_source = _ask_yes_no("在输出目录保存一份私密源存档归档？")
                preserve_original = _ask_yes_no("在每个迁移方案中保留旧格式电路副本？")
                include_backups = _ask_yes_no("导入并转换旧 circuit_backup_*.data？")
                report = prepare_migration(
                    source,
                    target,
                    output,
                    game_dir=game_dir,
                    archive_source=archive_source,
                    preserve_original=preserve_original,
                    include_circuit_backups=include_backups,
                )
                print(f"\n迁移准备完成：{output / 'save'}")
                print(f"报告：{output / 'migration-report.json'}")
                _print_json(report.get("verification"))
            elif choice == "3":
                _print_json(verify_save(_ask_path("要验证的存档或输出/save 路径")))
            elif choice == "4":
                prepared = _ask_path("已准备的 output/save 路径")
                target = _ask_path("最新版目标存档路径", DEFAULT_SAVE_ROOTS["2.1.276"])
                create_backup = _ask_yes_no("安装前保留当前目标存档备份？")
                steam_cloud_disabled = _ask_yes_no(
                    "如果 Steam 仍在运行，是否已确认关闭本游戏的 Steam Cloud？",
                    default=False,
                )
                action = (
                    "安装会先把当前目标目录重命名为带时间戳的备份，然后替换目标。"
                    if create_backup
                    else "安装不会留下目标存档备份；已有目标将在安装成功后删除。"
                )
                if _confirm_exact(
                    action,
                    "安装迁移存档",
                ):
                    _print_json(
                        install_prepared(
                            prepared,
                            target,
                            create_backup=create_backup,
                            steam_cloud_disabled=steam_cloud_disabled,
                        )
                    )
                else:
                    print("已取消。")
            elif choice == "5":
                backup = _ask_path("要恢复的 .tcm-backup-* 目录")
                target = _ask_path("最新版目标存档路径", DEFAULT_SAVE_ROOTS["2.1.276"])
                if _confirm_exact("回滚前仍会备份当前目录。", "回滚存档"):
                    _print_json(rollback_backup(backup, target))
                else:
                    print("已取消。")
            elif choice == "6":
                _print_json(postflight_check(_ask_path("游戏运行后的存档路径", DEFAULT_SAVE_ROOTS["2.1.276"])))
            else:
                print("无效选择。")
        except (OSError, ValueError, RuntimeError) as exc:
            print(f"错误：{exc}", file=sys.stderr)


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="tcmigrate", description="Turing Complete save migration toolkit")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")
    inspect_parser = sub.add_parser("inspect", help="passively inspect a save root")
    inspect_parser.add_argument("path", type=Path)

    prepare_parser = sub.add_parser("prepare", help="prepare a migration in a new directory")
    prepare_parser.add_argument("source", type=Path)
    prepare_parser.add_argument("target", type=Path)
    prepare_parser.add_argument("output", type=Path)
    prepare_parser.add_argument("--game-dir", type=Path, default=DEFAULT_GAME_DIR)
    prepare_parser.add_argument(
        "--no-archive",
        action="store_true",
        help="do not copy the complete source save into output/archive",
    )
    prepare_parser.add_argument(
        "--no-preserve-original",
        action="store_true",
        help=f"do not keep legacy circuit bytes beside converted circuit.data",
    )
    prepare_parser.add_argument(
        "--no-circuit-backups",
        action="store_true",
        help="omit legacy circuit_backup_*.data files from the prepared save",
    )

    verify_parser = sub.add_parser("verify", help="verify a prepared or installed save")
    verify_parser.add_argument("path", type=Path)

    install_parser = sub.add_parser("install", help="install a prepared save with backup")
    install_parser.add_argument("prepared", type=Path)
    install_parser.add_argument("target", type=Path)
    install_parser.add_argument("--yes", action="store_true")
    install_parser.add_argument(
        "--no-backup",
        action="store_true",
        help="replace the target without leaving a .tcm-backup-* directory",
    )
    install_parser.add_argument(
        "--steam-cloud-disabled",
        action="store_true",
        help="confirm Steam Cloud is disabled even if Steam is still running",
    )

    rollback_parser = sub.add_parser("rollback", help="restore a backup")
    rollback_parser.add_argument("backup", type=Path)
    rollback_parser.add_argument("target", type=Path)
    rollback_parser.add_argument("--yes", action="store_true")

    post_parser = sub.add_parser("postflight", help="detect game-side destructive rewrites")
    post_parser.add_argument("path", type=Path)
    return parser


def run_command(args: Namespace) -> int:
    if args.command == "inspect":
        _print_json(inspect_save(args.path).to_dict())
    elif args.command == "prepare":
        _print_json(
            prepare_migration(
                args.source,
                args.target,
                args.output,
                game_dir=args.game_dir,
                archive_source=not args.no_archive,
                preserve_original=not args.no_preserve_original,
                include_circuit_backups=not args.no_circuit_backups,
            )
        )
    elif args.command == "verify":
        _print_json(verify_save(args.path))
    elif args.command == "install":
        if not args.yes:
            raise SystemExit("install requires --yes in non-interactive mode")
        _print_json(
            install_prepared(
                args.prepared,
                args.target,
                create_backup=not args.no_backup,
                steam_cloud_disabled=args.steam_cloud_disabled,
            )
        )
    elif args.command == "rollback":
        if not args.yes:
            raise SystemExit("rollback requires --yes in non-interactive mode")
        _print_json(rollback_backup(args.backup, args.target))
    elif args.command == "postflight":
        _print_json(postflight_check(args.path))
    else:
        return interactive()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run_command(args)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(2, f"error: {exc}\n")
