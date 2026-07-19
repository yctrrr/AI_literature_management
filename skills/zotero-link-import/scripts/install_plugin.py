#!/usr/bin/env python3
"""Build and install the Zotero linked-file import plugin."""

from __future__ import annotations

import argparse
import configparser
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent.parent
PLUGIN_SOURCE = SKILL_DIR / "assets" / "zotero-plugin"
PLUGIN_ID = "{7f9c5a2e-1d4b-4a8f-9c6e-2b3d5f7a9c10}"
PRIVATE_MODE = 0o600


def make_private(path: Path) -> None:
    os.chmod(path, PRIVATE_MODE)
    if os.name == "nt":
        domain = os.environ.get("USERDOMAIN")
        username = os.environ.get("USERNAME")
        principal = f"{domain}\\{username}" if domain and username else username
        if not principal:
            raise OSError("Could not identify the current Windows account")
        result = subprocess.run(
            [
                "icacls",
                str(path),
                "/inheritance:r",
                "/grant:r",
                f"{principal}:(F)",
            ],
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        if result.returncode != 0:
            raise OSError(f"Could not restrict permissions for {path}")


def atomic_private_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        os.chmod(temp_name, PRIVATE_MODE)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        make_private(path)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        Path(temp_name).unlink(missing_ok=True)
        raise


def file_snapshot(path: Path) -> bytes | None:
    return path.read_bytes() if path.is_file() else None


def restore_private_file(path: Path, snapshot: bytes | None) -> None:
    if snapshot is None:
        path.unlink(missing_ok=True)
    else:
        atomic_private_write(path, snapshot)


def default_config_path() -> Path:
    override = os.environ.get("ZOTERO_LINK_CONFIG")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return root / "ai-literature-management" / "zotero-link-import.json"


def discover_profiles_ini(explicit: Path | None = None) -> Path:
    if explicit:
        path = explicit.expanduser()
        if path.is_file():
            return path
        raise RuntimeError(f"Zotero profiles file not found: {path}")
    candidates = []
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / "Zotero" / "Zotero" / "profiles.ini")
    elif sys.platform == "darwin":
        candidates.append(Path.home() / "Library" / "Application Support" / "Zotero" / "profiles.ini")
    else:
        candidates.extend(
            [
                Path.home() / ".zotero" / "zotero" / "profiles.ini",
                Path.home() / ".mozilla" / "zotero" / "profiles.ini",
            ]
        )
    for path in candidates:
        if path.is_file():
            return path
    raise RuntimeError("Zotero profiles.ini was not found; pass --profiles-ini")


def discover_zotero_exe(explicit: Path | None = None) -> Path | None:
    if explicit:
        path = explicit.expanduser()
        if path.is_file():
            return path
        raise RuntimeError(f"Zotero executable not found: {path}")
    environment = os.environ.get("ZOTERO_EXE")
    if environment:
        return discover_zotero_exe(Path(environment))
    command = shutil.which("zotero") or shutil.which("zotero.exe")
    if command:
        return Path(command)
    candidates = []
    if os.name == "nt":
        for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            root = os.environ.get(variable)
            if root:
                candidates.append(Path(root) / "Zotero" / "zotero.exe")
    elif sys.platform == "darwin":
        candidates.append(Path("/Applications/Zotero.app/Contents/MacOS/zotero"))
    for path in candidates:
        if path.is_file():
            return path
    return None


def active_profile(profiles_ini: Path) -> Path:
    parser = configparser.RawConfigParser()
    if not parser.read(profiles_ini, encoding="utf-8"):
        raise RuntimeError(f"Zotero profiles file could not be read: {profiles_ini}")
    candidates = []
    for section in parser.sections():
        if not section.startswith("Profile"):
            continue
        raw_path = parser.get(section, "Path")
        relative = parser.getboolean(section, "IsRelative", fallback=True)
        path = (profiles_ini.parent / raw_path) if relative else Path(raw_path)
        candidates.append((parser.getboolean(section, "Default", fallback=False), path))
    if not candidates:
        raise RuntimeError("No Zotero profile is configured")
    profile = next((path for is_default, path in candidates if is_default), candidates[0][1])
    if not profile.is_dir():
        raise RuntimeError(f"Configured Zotero profile does not exist: {profile}")
    return profile.resolve()


def existing_token(config_path: Path) -> str | None:
    if not config_path.is_file():
        return None
    try:
        value = json.loads(config_path.read_text(encoding="utf-8")).get("token")
        return value if isinstance(value, str) and len(value) >= 32 else None
    except (OSError, json.JSONDecodeError):
        return None


def build_xpi(token: str, allowed_root: Path, output: Path) -> Path:
    manifest = (PLUGIN_SOURCE / "manifest.json").read_text(encoding="utf-8")
    bootstrap = (PLUGIN_SOURCE / "bootstrap.js").read_text(encoding="utf-8")
    if bootstrap.count("__INSTALL_TOKEN__") != 1:
        raise RuntimeError("Plugin token placeholder is missing or duplicated")
    if bootstrap.count("__ALLOWED_ROOT__") != 1:
        raise RuntimeError("Plugin allowed-root placeholder is missing or duplicated")
    bootstrap = bootstrap.replace("__INSTALL_TOKEN__", token)
    bootstrap = bootstrap.replace("__ALLOWED_ROOT__", json.dumps(str(allowed_root)))
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    os.close(descriptor)
    try:
        make_private(Path(temp_name))
        with zipfile.ZipFile(temp_name, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in (("manifest.json", manifest), ("bootstrap.js", bootstrap)):
                info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, content.encode("utf-8"))
        with Path(temp_name).open("rb+") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, output)
        make_private(output)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise
    return output


def write_config(
    config_path: Path,
    token: str,
    profile: Path,
    allowed_root: Path,
    zotero_exe: Path | None,
) -> None:
    config = {
        "base_url": "http://127.0.0.1:23119",
        "token": token,
        "allowed_root": str(allowed_root),
        "profile": str(profile),
        "plugin_id": PLUGIN_ID,
        "zotero_exe": str(zotero_exe) if zotero_exe else "",
    }
    atomic_private_write(
        config_path,
        (json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )


def distribution_bases(zotero_exe: Path) -> list[Path]:
    return list(dict.fromkeys([zotero_exe.parent, zotero_exe.parent / "app"]))


def write_install_policy(base: Path, install_url: str) -> Path:
    distribution = base / "distribution"
    distribution.mkdir(parents=True, exist_ok=True)
    policy_path = distribution / "policies.json"
    document = (
        json.loads(policy_path.read_text(encoding="utf-8"))
        if policy_path.is_file()
        else {"policies": {}}
    )
    settings = document.setdefault("policies", {}).setdefault("ExtensionSettings", {})
    settings[PLUGIN_ID] = {
        "installation_mode": "normal_installed",
        "install_url": install_url,
    }
    policy_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return policy_path


def install_distribution_policy(zotero_exe: Path, xpi: Path, version: str) -> list[str]:
    paths = []
    for base in distribution_bases(zotero_exe):
        package_directory = base / "distribution" / "packages"
        package_directory.mkdir(parents=True, exist_ok=True)
        package = package_directory / f"zotero-link-import-{version}.xpi"
        atomic_private_write(package, xpi.read_bytes())
        paths.extend([str(package), str(write_install_policy(base, package.as_uri()))])
    return paths


def finalize_install(zotero_exe: Path | None) -> int:
    if zotero_exe is None:
        print(json.dumps({"status": "finalized", "removed": []}, indent=2))
        return 0
    removed = []
    for base in distribution_bases(zotero_exe):
        policy_path = base / "distribution" / "policies.json"
        if policy_path.is_file():
            document = json.loads(policy_path.read_text(encoding="utf-8"))
            policies = document.get("policies", {})
            settings = policies.get("ExtensionSettings", {})
            if settings.pop(PLUGIN_ID, None) is not None:
                if not settings:
                    policies.pop("ExtensionSettings", None)
                if not policies:
                    policy_path.unlink()
                else:
                    policy_path.write_text(
                        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                removed.append(str(policy_path))
        packages = base / "distribution" / "packages"
        if packages.is_dir():
            for package in packages.glob("zotero-link-import-*.xpi"):
                package.unlink()
                removed.append(str(package))
    print(json.dumps({"status": "finalized", "removed": removed}, indent=2))
    return 0


def install(args: argparse.Namespace) -> int:
    allowed_root_value = args.allowed_root or os.environ.get("ZOTERO_LINK_ALLOWED_ROOT")
    if not allowed_root_value:
        raise RuntimeError("Pass --allowed-root or set ZOTERO_LINK_ALLOWED_ROOT")
    allowed_root = Path(allowed_root_value).expanduser().resolve(strict=True)
    if not allowed_root.is_dir():
        raise RuntimeError(f"Allowed root is not a directory: {allowed_root}")
    config_path = (args.config or default_config_path()).expanduser().resolve()
    profiles_ini = discover_profiles_ini(args.profiles_ini)
    profile = active_profile(profiles_ini)
    zotero_exe = discover_zotero_exe(args.zotero_exe)
    if args.install_policy and zotero_exe is None:
        raise RuntimeError("--install-policy requires a detectable Zotero executable")
    token = existing_token(config_path) or secrets.token_urlsafe(32)
    xpi_path = config_path.with_suffix(".xpi")
    xpi_snapshot = file_snapshot(xpi_path)
    xpi = build_xpi(token, allowed_root, xpi_path)
    destination = profile / "extensions" / f"{PLUGIN_ID}.xpi"
    config_snapshot = file_snapshot(config_path)
    destination_snapshot = file_snapshot(destination)
    policy_snapshots: dict[Path, bytes | None] = {}
    version = ""
    if args.install_policy:
        version = json.loads(
            (PLUGIN_SOURCE / "manifest.json").read_text(encoding="utf-8")
        )["version"]
        for base in distribution_bases(zotero_exe):
            package = base / "distribution" / "packages" / f"zotero-link-import-{version}.xpi"
            policy_path = base / "distribution" / "policies.json"
            policy_snapshots[package] = file_snapshot(package)
            policy_snapshots[policy_path] = file_snapshot(policy_path)
    policy_paths = []
    try:
        write_config(config_path, token, profile, allowed_root, zotero_exe)
        atomic_private_write(destination, xpi.read_bytes())
        if args.install_policy:
            policy_paths = install_distribution_policy(zotero_exe, xpi, version)
    except Exception as install_error:
        rollback_actions = []
        for path, snapshot in reversed(policy_snapshots.items()):
            if snapshot is None:
                rollback_actions.append(lambda path=path: path.unlink(missing_ok=True))
            elif path.suffix.lower() == ".xpi":
                rollback_actions.append(
                    lambda path=path, snapshot=snapshot: atomic_private_write(path, snapshot)
                )
            else:
                rollback_actions.append(
                    lambda path=path, snapshot=snapshot: path.write_bytes(snapshot)
                )
        rollback_actions.extend(
            [
                lambda: restore_private_file(destination, destination_snapshot),
                lambda: restore_private_file(config_path, config_snapshot),
                lambda: restore_private_file(xpi_path, xpi_snapshot),
            ]
        )
        for action in rollback_actions:
            try:
                action()
            except Exception as rollback_error:
                install_error.add_note(f"Rollback failed: {rollback_error}")
        raise
    print(
        json.dumps(
            {
                "status": "installed",
                "profile": str(profile),
                "profile_xpi": str(destination),
                "config": str(config_path),
                "install_policy_paths": policy_paths,
                "restart_required": True,
            },
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install the Zotero linked-import plugin")
    parser.add_argument("--allowed-root", help="Root allowed for linked PDF files")
    parser.add_argument("--profiles-ini", type=Path, help="Path to Zotero profiles.ini")
    parser.add_argument("--zotero-exe", type=Path, help="Path to Zotero executable")
    parser.add_argument("--config", type=Path, help="Local client configuration output")
    parser.add_argument(
        "--install-policy",
        action="store_true",
        help="also write a one-time Zotero distribution install policy",
    )
    parser.add_argument(
        "--finalize",
        action="store_true",
        help="remove one-time distribution policies after a successful restart",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.finalize:
            config_path = (args.config or default_config_path()).expanduser()
            configured_exe = None
            if config_path.is_file():
                configured = json.loads(config_path.read_text(encoding="utf-8"))
                if configured.get("zotero_exe"):
                    configured_exe = Path(configured["zotero_exe"])
            return finalize_install(discover_zotero_exe(args.zotero_exe or configured_exe))
        return install(args)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
