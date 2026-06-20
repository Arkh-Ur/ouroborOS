"""dots_profiles.py — Dotfiles pack catalog reader for the ouroborOS installer."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

MANIFEST_DIR = Path(os.environ.get("OUR_DOTS_MANIFEST_DIR", "/usr/local/lib/ouroboros/dots/packs"))


@dataclass
class DotsPack:
    id: str
    name: str
    description: str
    author: str
    homepage: str
    compatibility: str          # "low" | "medium" | "high" | "critical"
    profiles: list[str]
    has_stable: bool
    has_git: bool
    stable_version_hint: str = ""
    git_version_hint: str = ""


def load_catalog(manifest_dir: Path = MANIFEST_DIR) -> list[DotsPack]:
    """Load all pack manifests from canonical nested schema. Returns empty list if directory missing."""
    if not manifest_dir.exists():
        return []

    packs: list[DotsPack] = []
    for manifest_path in sorted(manifest_dir.glob("*.yaml")):
        try:
            with manifest_path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if not isinstance(data, dict):
                continue
            compat_block = data.get("compatibility") or {}
            credits_block = data.get("credits") or {}
            variants_block = data.get("variants") or {}
            stable_block = variants_block.get("stable") or {}
            git_block = variants_block.get("git") or {}
            pack = DotsPack(
                id=str(data.get("id", manifest_path.stem)),
                name=str(data.get("name", "")),
                description=str(data.get("description", "")),
                author=str(credits_block.get("author", "")),
                homepage=str(credits_block.get("homepage", "")),
                compatibility=str(compat_block.get("immutable", "medium")),
                profiles=list(compat_block.get("profiles") or []),
                has_stable=bool(stable_block),
                has_git=bool(git_block),
                stable_version_hint=str(stable_block.get("version_hint", "")),
                git_version_hint=str(git_block.get("version_hint", "")),
            )
            packs.append(pack)
        except Exception:  # noqa: BLE001
            continue

    return packs


def packs_for_profile(profile: str, manifest_dir: Path = MANIFEST_DIR) -> list[DotsPack]:
    """Return packs compatible with the given desktop profile."""
    return [p for p in load_catalog(manifest_dir) if profile in p.profiles]
