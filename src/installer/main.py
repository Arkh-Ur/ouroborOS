"""main.py — ouroborOS installer entry point.

Parses command-line arguments and delegates to the Installer FSM.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from installer.config import validate_config
from installer.state_machine import Installer

import yaml


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ouroborOS-installer",
        description="ouroborOS interactive/unattended system installer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive installation
  ouroborOS-installer

  # Resume interrupted installation
  ouroborOS-installer --resume

  # Unattended installation from config file
  ouroborOS-installer --config /path/to/config.yaml

  # Validate a config file without installing
  ouroborOS-installer --validate-config /path/to/config.yaml
""",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume a previously interrupted installation from the last checkpoint",
    )
    parser.add_argument(
        "--config",
        type=Path,
        metavar="FILE",
        help="Path to unattended installation config YAML file",
    )
    parser.add_argument(
        "--validate-config",
        type=Path,
        metavar="FILE",
        help="Validate a config file and exit (does not install)",
    )
    parser.add_argument(
        "--target",
        type=str,
        default="/mnt",
        metavar="PATH",
        help="Installation target mount point (default: /mnt)",
    )
    return parser


def cmd_validate_config(path: Path) -> int:
    """Validate an installer config file and report the result.

    Returns:
        0 if valid, 1 if invalid.
    """
    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        return 1

    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        validate_config(data)
        print(f"Config valid: {path}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Config invalid: {exc}", file=sys.stderr)
        return 1


def main() -> int:
    """Main entry point for the installer CLI.

    Returns:
        Exit code: 0 success, 1 failure.
    """
    parser = _build_parser()
    args = parser.parse_args()

    # Validate-only mode
    if args.validate_config:
        return cmd_validate_config(args.validate_config)

    # Run installer
    installer = Installer(
        resume=args.resume,
        config_path=args.config,
    )

    if args.target != "/mnt":
        installer.config.install_target = args.target

    return installer.run()


if __name__ == "__main__":
    sys.exit(main())
