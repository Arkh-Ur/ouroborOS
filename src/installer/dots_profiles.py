"""dots_profiles.py — Dotfiles pack catalog reader for the ouroborOS installer."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

MANIFEST_DIR = Path("/usr/local/lib/ouroboros/dots/packs")


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
    stable_version_hint: str
    git_version_hint: str = ""


def load_catalog(manifest_dir: Path = MANIFEST_DIR) -> list[DotsPack]:
    """Load all pack manifests. Returns empty list if directory missing."""
    if not manifest_dir.exists():
        return []

    packs: list[DotsPack] = []
    for manifest_path in sorted(manifest_dir.glob("*.yaml")):
        try:
            with manifest_path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if not isinstance(data, dict):
                continue
            pack = DotsPack(
                id=str(data.get("id", manifest_path.stem)),
                name=str(data.get("name", "")),
                description=str(data.get("description", "")),
                author=str(data.get("author", "")),
                homepage=str(data.get("homepage", "")),
                compatibility=str(data.get("compatibility", "medium")),
                profiles=list(data.get("profiles", [])),
                has_stable=bool(data.get("has_stable", True)),
                has_git=bool(data.get("has_git", False)),
                stable_version_hint=str(data.get("stable_version_hint", "")),
                git_version_hint=str(data.get("git_version_hint", "")),
            )
            packs.append(pack)
        except Exception:  # noqa: BLE001
            continue

    return packs


def packs_for_profile(profile: str, manifest_dir: Path = MANIFEST_DIR) -> list[DotsPack]:
    """Return packs compatible with the given desktop profile."""
    return [p for p in load_catalog(manifest_dir) if profile in p.profiles]
