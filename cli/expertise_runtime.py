"""Explicit verified installation and readiness for the local expertise model."""
from __future__ import annotations

import hashlib
import base64
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen
from urllib.parse import urlparse
import re
import stat
import zipfile

from expertise_model import canonical_json, digest
from expertise_projection import cache_root
from expertise_ranker import FastEmbedProvider
from expertise_paths import PrivatePathError, checked_path


class ExpertiseRuntimeError(ValueError):
    def __init__(self, reason: str, remedy: str) -> None:
        self.reason = reason
        self.remedy = remedy
        super().__init__(reason)


def data_root() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "expertise"


def model_manifest_path() -> Path:
    return data_root() / "model-manifest.json"


def runtime_lock_path() -> Path:
    return data_root() / "runtime-lock.json"


def current_environment_id() -> str:
    version = platform.python_version()
    machine = platform.machine().lower()
    # Keep the public support-matrix vocabulary stable across Python and OS
    # implementations. Linux commonly reports x86_64 for the architecture the
    # release contract names x64.
    machine = {"x86_64": "x64", "amd64": "x64"}.get(machine, machine)
    if platform.system() == "Darwin":
        return f"macos-{platform.mac_ver()[0]}-{machine}-python-{version}"
    if platform.system() == "Linux":
        release = {}
        try:
            for line in Path("/etc/os-release").read_text().splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    release[key] = value.strip('"')
        except OSError:
            pass
        os_id = "ubuntu" if release.get("ID") == "ubuntu" else release.get("ID", "linux")
        os_version = release.get("VERSION_ID", platform.release())
        return f"{os_id}-{os_version}-{machine}-python-{version}"
    return f"{platform.system().lower()}-{platform.release()}-{machine}-python-{version}"


def _read(path: Path) -> dict:
    try:
        if path.stat().st_size > 4 * 1024 * 1024:
            raise ExpertiseRuntimeError("manifest_too_large", "restore the shipped expertise manifests")
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ExpertiseRuntimeError("manifest_invalid", "restore the shipped expertise manifests") from error
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ExpertiseRuntimeError("manifest_invalid", "restore the shipped expertise manifests")
    return value


def _sha(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def _reject_symlinks(root: Path) -> None:
    if root.is_symlink():
        raise ExpertiseRuntimeError("unsafe_permissions", "replace the symlink with a private directory")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ExpertiseRuntimeError("unsafe_permissions", "remove symlinks from the expertise runtime")


def _verify_model(root: Path, manifest: dict) -> None:
    _reject_symlinks(root)
    expected_paths = {item["path"] for item in manifest["model"]["files"]}
    actual_paths = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if actual_paths != expected_paths:
        raise ExpertiseRuntimeError("corrupt_artifact", "rerun flow expertise model install")
    for item in manifest["model"]["files"]:
        path = root / item["path"]
        if path.stat().st_size != item["bytes"] or _sha(path) != item["sha256"]:
            raise ExpertiseRuntimeError("hash_mismatch", "rerun flow expertise model install")


def _safe_relative(value: object, label: str, *, suffix: str | None = None) -> str:
    if not isinstance(value, str) or not value or Path(value).is_absolute() or ".." in Path(value).parts or "\\" in value:
        raise ExpertiseRuntimeError("manifest_invalid", f"{label} must be a safe relative path")
    if suffix and not value.endswith(suffix):
        raise ExpertiseRuntimeError("manifest_invalid", f"{label} must end with {suffix}")
    return value


def _pinned_artifact(item: object, label: str, *, filename: bool = False) -> dict:
    if not isinstance(item, dict):
        raise ExpertiseRuntimeError("manifest_invalid", f"{label} must be an object")
    path_field = "filename" if filename else "path"
    required = {path_field, "bytes", "sha256", "url" if filename else "download_url"}
    if not required.issubset(item):
        raise ExpertiseRuntimeError("manifest_invalid", f"{label} is incomplete")
    _safe_relative(item[path_field], f"{label}.{path_field}", suffix=".whl" if filename else None)
    if "/" in item[path_field]:
        raise ExpertiseRuntimeError("manifest_invalid", f"{label}.{path_field} must name one file")
    if not isinstance(item["bytes"], int) or isinstance(item["bytes"], bool) or not 0 < item["bytes"] < 1024 * 1024 * 1024:
        raise ExpertiseRuntimeError("manifest_invalid", f"{label}.bytes must be pinned below one GB")
    if not isinstance(item["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
        raise ExpertiseRuntimeError("manifest_invalid", f"{label}.sha256 must be lowercase SHA-256")
    artifact_url = item["url" if filename else "download_url"]
    if not isinstance(artifact_url, str) or not artifact_url.startswith("https://") or not _approved_artifact_host(urlparse(artifact_url).hostname):
        raise ExpertiseRuntimeError("manifest_invalid", f"{label} URL is not an approved HTTPS origin")
    return item


def _validate_contracts(model: dict, lock: dict) -> None:
    model_rows = model.get("model", {}).get("files")
    if not isinstance(model_rows, list) or not model_rows:
        raise ExpertiseRuntimeError("manifest_invalid", "model manifest has no files")
    model_paths = []
    for index, item in enumerate(model_rows):
        model_paths.append(_pinned_artifact(item, f"model.files[{index}]")["path"])
    if len(model_paths) != len(set(model_paths)):
        raise ExpertiseRuntimeError("manifest_invalid", "model manifest repeats a path")
    notices = model.get("notices")
    if not isinstance(notices, dict) or set(notices) != {"path", "sha256"}:
        raise ExpertiseRuntimeError("manifest_invalid", "model manifest does not bind its notices")
    notice_path = Path(__file__).resolve().parents[1] / _safe_relative(notices["path"], "notices.path")
    if not notice_path.is_file() or _sha(notice_path) != notices["sha256"]:
        raise ExpertiseRuntimeError("manifest_invalid", "bundled runtime notices do not match the manifest")
    environments = lock.get("environments")
    if not isinstance(environments, dict) or not environments:
        raise ExpertiseRuntimeError("manifest_invalid", "runtime lock has no environments")
    for environment_id, environment in environments.items():
        if not isinstance(environment_id, str) or not isinstance(environment, dict):
            raise ExpertiseRuntimeError("manifest_invalid", "runtime environment is invalid")
        rows = environment.get("requirements")
        if not isinstance(rows, list) or not rows:
            raise ExpertiseRuntimeError("manifest_invalid", f"{environment_id} has no pinned wheels")
        filenames = []
        total = 0
        for index, item in enumerate(rows):
            wheel = _pinned_artifact(item, f"{environment_id}.requirements[{index}]", filename=True)
            if not isinstance(wheel.get("name"), str) or not wheel["name"] or not isinstance(wheel.get("version"), str) or not wheel["version"]:
                raise ExpertiseRuntimeError("manifest_invalid", "every wheel requires name and version")
            filenames.append(wheel["filename"])
            total += wheel["bytes"]
        if len(filenames) != len(set(filenames)) or total >= 1024 * 1024 * 1024:
            raise ExpertiseRuntimeError("manifest_invalid", f"{environment_id} wheel set is duplicated or too large")
        if environment.get("persistent_wheel_bytes") != total:
            raise ExpertiseRuntimeError("manifest_invalid", f"{environment_id} wheel byte total is stale")


def _trusted_wheel_files(wheel_cache: Path, environment: dict) -> tuple[dict[str, tuple[int, str]], set[str]]:
    """Derive installed-byte expectations from wheels bound to the shipped lock."""
    expected: dict[str, tuple[int, str]] = {}
    generated: set[str] = set()
    requirements = environment["requirements"]
    if requirements:
        if wheel_cache.is_symlink() or not wheel_cache.is_dir():
            raise ExpertiseRuntimeError("corrupt_artifact", "rerun flow expertise model install")
        _reject_symlinks(wheel_cache)
    for item in requirements:
        wheel = wheel_cache / item["filename"]
        if wheel.is_symlink() or not wheel.is_file() or wheel.stat().st_size != item["bytes"] or _sha(wheel) != item["sha256"]:
            raise ExpertiseRuntimeError("hash_mismatch", "rerun flow expertise model install from pinned wheels")
        try:
            with zipfile.ZipFile(wheel) as archive:
                members = archive.infolist()
                if len(members) > 20000 or sum(member.file_size for member in members) > 1024 * 1024 * 1024:
                    raise ExpertiseRuntimeError("corrupt_artifact", "pinned wheel exceeds safe expansion limits")
                for member in members:
                    if member.is_dir():
                        continue
                    if member.file_size > 256 * 1024 * 1024 or stat.S_ISLNK(member.external_attr >> 16):
                        raise ExpertiseRuntimeError("corrupt_artifact", "pinned wheel has an unsafe member")
                    parts = Path(member.filename).parts
                    if not parts or Path(member.filename).is_absolute() or ".." in parts or "\\" in member.filename:
                        raise ExpertiseRuntimeError("corrupt_artifact", "pinned wheel has an unsafe path")
                    if parts[0].endswith(".data"):
                        if len(parts) < 3 or parts[1] not in {"purelib", "platlib"}:
                            raise ExpertiseRuntimeError("corrupt_artifact", "pinned wheel has unsupported relocation")
                        relative = "/".join(parts[2:])
                    else:
                        relative = member.filename
                    if relative in expected or relative in generated:
                        raise ExpertiseRuntimeError("corrupt_artifact", "pinned wheels contain duplicate installed paths")
                    if relative.endswith(".dist-info/RECORD"):
                        generated.add(relative)
                        prefix = relative.removesuffix("RECORD")
                        generated.update({prefix + name for name in ("INSTALLER", "REQUESTED", "direct_url.json")})
                        continue
                    with archive.open(member) as stream:
                        hasher = hashlib.sha256()
                        length = 0
                        for block in iter(lambda: stream.read(1024 * 1024), b""):
                            length += len(block)
                            hasher.update(block)
                    if length != member.file_size:
                        raise ExpertiseRuntimeError("corrupt_artifact", "pinned wheel member length changed")
                    expected[relative] = (length, hasher.hexdigest())
        except (OSError, zipfile.BadZipFile) as error:
            raise ExpertiseRuntimeError("corrupt_artifact", "rerun flow expertise model install from pinned wheels") from error
    return expected, generated


def _verify_site(site: Path, environment: dict, wheel_cache: Path) -> None:
    _reject_symlinks(site)
    if any(site.glob("*.pth")):
        raise ExpertiseRuntimeError("corrupt_artifact", "remove executable .pth files and reinstall the isolated runtime")
    if (site / "bin").exists():
        raise ExpertiseRuntimeError("corrupt_artifact", "remove generated console scripts and reinstall the isolated runtime")
    found = {dist.metadata["Name"].casefold().replace("_", "-"): dist.version for dist in metadata.distributions(path=[str(site)])}
    expected = {item["name"].casefold().replace("_", "-"): item["version"] for item in environment["requirements"]}
    if found != expected:
        raise ExpertiseRuntimeError("corrupt_artifact", "rerun flow expertise model install for this interpreter")
    covered: set[Path] = set()
    for dist in metadata.distributions(path=[str(site)]):
        for package_path in dist.files or ():
            installed = Path(dist.locate_file(package_path)).resolve()
            # pip --target records generated console scripts outside the
            # distribution root as ../../../bin/*. They are not used by Flow
            # and are deleted before verification.
            if tuple(package_path.parts[:4]) == ("..", "..", "..", "bin"):
                continue
            if not installed.is_relative_to(site.resolve()) or installed.is_symlink() or not installed.is_file():
                raise ExpertiseRuntimeError("corrupt_artifact", "rerun flow expertise model install for this interpreter")
            relative = installed.relative_to(site.resolve())
            covered.add(relative)
            file_hash = package_path.hash
            if file_hash is None:
                if relative.name != "RECORD":
                    raise ExpertiseRuntimeError("corrupt_artifact", "installed runtime contains an unhashed file")
                continue
            if file_hash.mode != "sha256":
                raise ExpertiseRuntimeError("corrupt_artifact", "installed runtime uses an unsupported file hash")
            actual = hashlib.sha256(installed.read_bytes()).digest()
            expected_hash = base64.urlsafe_b64decode(file_hash.value + "=" * (-len(file_hash.value) % 4))
            if not hmac_compare(actual, expected_hash):
                raise ExpertiseRuntimeError("hash_mismatch", "rerun flow expertise model install for this interpreter")
    actual_files = {path.relative_to(site.resolve()) for path in site.resolve().rglob("*") if path.is_file()}
    if actual_files != covered:
        raise ExpertiseRuntimeError("corrupt_artifact", "installed runtime contains files outside the pinned wheels")
    trusted, generated = _trusted_wheel_files(wheel_cache, environment)
    actual_names = {path.as_posix() for path in actual_files}
    if actual_names != set(trusted).union(generated):
        raise ExpertiseRuntimeError("corrupt_artifact", "installed runtime differs from pinned wheels")
    for relative, (expected_bytes, expected_sha) in trusted.items():
        installed = site / relative
        if installed.stat().st_size != expected_bytes or _sha(installed) != expected_sha:
            raise ExpertiseRuntimeError("hash_mismatch", "rerun flow expertise model install from pinned wheels")


def hmac_compare(left: bytes, right: bytes) -> bool:
    """Constant-time byte comparison without importing the runtime under test."""
    import hmac
    return hmac.compare_digest(left, right)


def _load_contracts() -> tuple[dict, dict, dict]:
    model = _read(model_manifest_path())
    lock = _read(runtime_lock_path())
    _validate_contracts(model, lock)
    environment_id = current_environment_id()
    environment = lock.get("environments", {}).get(environment_id)
    if not isinstance(environment, dict):
        raise ExpertiseRuntimeError("unsupported_runtime", f"use one of: {', '.join(sorted(lock.get('environments', {})))}")
    return model, lock, environment


def install_root(flow_home: Path, environment_id: str, model_digest: str, runtime_digest: str) -> Path:
    safe_environment = environment_id.replace("/", "-")
    return cache_root(flow_home) / "installs" / f"{safe_environment}-{model_digest[:12]}-{runtime_digest[:12]}"


def _private_path(path: Path, root: Path) -> Path:
    try:
        return checked_path(path, root, anchor=Path(root).absolute().parents[1])
    except PrivatePathError as error:
        raise ExpertiseRuntimeError(
            "unsafe_permissions", "replace symlinked expertise cache paths with private directories"
        ) from error


def _require_private(path: Path) -> None:
    if path.stat().st_mode & 0o077:
        raise ExpertiseRuntimeError("unsafe_permissions", "restrict expertise runtime permissions and reinstall")


def _approved_artifact_host(host: str | None) -> bool:
    if not host:
        return False
    host = host.casefold().split(":", 1)[0]
    return host == "huggingface.co" or host == "files.pythonhosted.org" or host.endswith(".hf.co") or host.endswith(".xethub.hf.co")


def _download(url: str, destination: Path, expected_sha: str, expected_bytes: int) -> None:
    if not url.startswith("https://"):
        raise ExpertiseRuntimeError("manifest_invalid", "artifact URLs must use HTTPS")
    if not _approved_artifact_host(urlparse(url).hostname):
        raise ExpertiseRuntimeError("manifest_invalid", "artifact URL host is not approved")
    if not isinstance(expected_bytes, int) or isinstance(expected_bytes, bool) or not 0 < expected_bytes < 1024 * 1024 * 1024:
        raise ExpertiseRuntimeError("manifest_invalid", "artifact size must be pinned below one GB")
    request = Request(url, headers={"User-Agent": "flow-expertise-installer/1"})
    with urlopen(request, timeout=60) as response, destination.open("wb") as stream:
        final_url = response.geturl()
        if not final_url.startswith("https://") or not _approved_artifact_host(urlparse(final_url).hostname):
            raise ExpertiseRuntimeError("network_install_failed", "artifact redirected to an unapproved host")
        remaining = expected_bytes
        while remaining:
            block = response.read(min(1024 * 1024, remaining))
            if not block:
                break
            stream.write(block)
            remaining -= len(block)
        if response.read(1):
            raise ExpertiseRuntimeError("artifact_too_large", "restore the pinned artifact manifest")
    if destination.stat().st_size != expected_bytes:
        raise ExpertiseRuntimeError("hash_mismatch", "retry the explicit model installation")
    if _sha(destination) != expected_sha:
        raise ExpertiseRuntimeError("hash_mismatch", "retry the explicit model installation")


def install(flow_home: Path, *, accept_license: bool, wheel_dir: Path | None = None, model_source: Path | None = None) -> dict:
    if not accept_license:
        raise ExpertiseRuntimeError("license_unaccepted", "rerun with --accept-license after reviewing the bundled notices")
    model, lock, environment = _load_contracts()
    environment_id = current_environment_id()
    model_digest = digest(model["model"])
    runtime_digest = digest(environment)
    target = install_root(flow_home, environment_id, model_digest, runtime_digest)
    root = cache_root(flow_home)
    target = _private_path(target, root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(target.parent, 0o700)
    if target.exists():
        result = status(flow_home)
        if result["state"] == "ready":
            return result | {"changed": False}
    staging = Path(tempfile.mkdtemp(prefix=".expertise-install-", dir=root))
    try:
        model_dir = staging / "model"
        wheel_cache = staging / "wheels"
        site = staging / "site"
        model_dir.mkdir(mode=0o700)
        wheel_cache.mkdir(mode=0o700)
        site.mkdir(mode=0o700)
        for item in model["model"]["files"]:
            destination = model_dir / item["path"]
            if model_source is not None:
                source = Path(model_source) / item["path"]
                if source.is_symlink() or not source.is_file():
                    raise ExpertiseRuntimeError("corrupt_artifact", "supply the complete verified model source")
                shutil.copyfile(source, destination)
                if destination.stat().st_size != item["bytes"] or _sha(destination) != item["sha256"]:
                    raise ExpertiseRuntimeError("hash_mismatch", "supply the pinned model revision")
            else:
                _download(item["download_url"], destination, item["sha256"], item["bytes"])
        wheels = []
        for item in environment["requirements"]:
            destination = wheel_cache / item["filename"]
            if wheel_dir is not None:
                source = Path(wheel_dir) / item["filename"]
                if source.is_symlink() or not source.is_file():
                    raise ExpertiseRuntimeError("corrupt_artifact", f"missing pinned wheel {item['filename']}")
                shutil.copyfile(source, destination)
                if _sha(destination) != item["sha256"]:
                    raise ExpertiseRuntimeError("hash_mismatch", f"wheel hash mismatch: {item['filename']}")
            else:
                _download(item["url"], destination, item["sha256"], item["bytes"])
            wheels.append(str(destination))
        command = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-index", "--no-deps", "--no-compile", "--target", str(site), *wheels]
        completed = subprocess.run(command, text=True, capture_output=True, timeout=300)
        if completed.returncode:
            raise ExpertiseRuntimeError("runtime_install_failed", "retry with a supported Python interpreter")
        generated_scripts = site / "bin"
        if generated_scripts.exists():
            if generated_scripts.is_symlink() or not generated_scripts.is_dir():
                raise ExpertiseRuntimeError("corrupt_artifact", "rerun flow expertise model install")
            shutil.rmtree(generated_scripts)
        _verify_model(model_dir, model)
        _verify_site(site, environment, wheel_cache)
        receipt = {
            "schema_version": 1, "environment_id": environment_id,
            "model_manifest_digest": digest(model), "model_artifact_digest": model_digest,
            "runtime_lock_digest": digest(lock), "runtime_revision": runtime_digest,
            "provider_revision": model["provider"]["revision"], "license_accepted": True,
        }
        (staging / "install.json").write_text(canonical_json(receipt) + "\n")
        os.chmod(staging / "install.json", 0o600)
        os.chmod(staging, 0o700)
        if target.exists():
            shutil.rmtree(staging)
        else:
            os.replace(staging, target)
        active = root / "active.json"
        active = _private_path(active, root)
        temp = root / f".active-{os.getpid()}.json"
        temp.write_text(canonical_json({"schema_version": 1, "install": target.name}) + "\n")
        os.chmod(temp, 0o600)
        os.replace(temp, active)
        return status(flow_home) | {"changed": True}
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def status(flow_home: Path) -> dict:
    try:
        model, lock, environment = _load_contracts()
        root = cache_root(flow_home)
        active = _private_path(root / "active.json", root)
        if not active.is_file() or active.is_symlink():
            raise ExpertiseRuntimeError("model_missing", "run flow expertise model install --accept-license")
        _require_private(active)
        pointer = json.loads(active.read_text())
        if set(pointer) != {"schema_version", "install"} or pointer.get("schema_version") != 1 or not isinstance(pointer.get("install"), str) or "/" in pointer["install"] or "\\" in pointer["install"]:
            raise ExpertiseRuntimeError("corrupt_artifact", "rerun flow expertise model install")
        target = _private_path(root / "installs" / pointer["install"], root)
        if not target.is_dir():
            raise ExpertiseRuntimeError("corrupt_artifact", "rerun flow expertise model install")
        _require_private(target)
        install_receipt = _private_path(target / "install.json", root)
        _require_private(install_receipt)
        receipt = json.loads(install_receipt.read_text())
        expected = {
            "environment_id": current_environment_id(), "model_manifest_digest": digest(model),
            "model_artifact_digest": digest(model["model"]), "runtime_lock_digest": digest(lock),
            "runtime_revision": digest(environment), "provider_revision": model["provider"]["revision"],
            "license_accepted": True,
        }
        if any(receipt.get(key) != value for key, value in expected.items()):
            raise ExpertiseRuntimeError("provider_unapproved", "rerun flow expertise model install --accept-license")
        _verify_model(target / "model", model)
        _verify_site(target / "site", environment, target / "wheels")
        return {
            "state": "ready", "environment_id": current_environment_id(),
            "provider_revision": expected["provider_revision"],
            "model_artifact_digest": expected["model_artifact_digest"],
            "runtime_revision": expected["runtime_revision"],
            "install": str(target.resolve()), "persistent_bytes": sum(path.stat().st_size for path in target.rglob("*") if path.is_file()),
        }
    except ExpertiseRuntimeError as error:
        return {"state": "unavailable", "reason": error.reason, "remedy": error.remedy, "environment_id": current_environment_id()}
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return {"state": "unavailable", "reason": "corrupt_artifact", "remedy": "rerun flow expertise model install --accept-license", "environment_id": current_environment_id()}


def provider(flow_home: Path) -> FastEmbedProvider:
    readiness = status(flow_home)
    if readiness["state"] != "ready":
        raise ExpertiseRuntimeError(readiness["reason"], readiness["remedy"])
    target = Path(readiness["install"])
    return FastEmbedProvider(
        target / "site", target / "model", readiness["model_artifact_digest"],
        readiness["runtime_revision"],
    )
