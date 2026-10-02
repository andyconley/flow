from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli"))

from macos_sandbox import confined_argv  # noqa: E402


@unittest.skipUnless(sys.platform == "darwin", "macOS sandbox contract")
class MacOSSandboxTests(unittest.TestCase):
    def _run_or_skip_nested(self, argv: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(argv, cwd=cwd, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if "sandbox_apply: Operation not permitted" in result.stderr:
            self.skipTest(
                "outer process sandbox forbids nested sandbox-exec; "
                "effective confinement remains unverified in this environment"
            )
        return result

    def _disposable_provider(self, root: Path, body: str) -> Path:
        executable = root / "disposable-provider"
        executable.write_text(f"#!{sys.executable}\n{body}\n")
        executable.chmod(0o755)
        return executable

    def test_staged_worker_cannot_read_sibling_user_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            private_home = root / "home"
            workspace.mkdir()
            private_home.mkdir()
            allowed = workspace / "allowed.txt"
            denied = root / "denied.txt"
            allowed.write_text("allowed")
            denied.write_text("secret")
            script = ("from pathlib import Path; import sys; "
                      "print(Path(sys.argv[1]).read_text()); "
                      "print(Path(sys.argv[2]).read_text())")
            argv = confined_argv(
                [sys.executable, "-c", script, str(allowed), str(denied)],
                workspace=workspace, private_home=private_home,
            )
            result = self._run_or_skip_nested(argv, cwd=workspace)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("allowed", result.stdout)
            self.assertNotIn("secret", result.stdout)

    def test_profile_names_only_staging_home_and_system_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace, private_home = root / "workspace", root / "home"
            workspace.mkdir()
            private_home.mkdir()
            argv = confined_argv([sys.executable, "-c", "pass"], workspace=workspace,
                                 private_home=private_home)
            profile = argv[2]
            self.assertIn(str(workspace), profile)
            self.assertIn(str(private_home), profile)
            self.assertNotIn(str(root) + '\")', profile)

    def test_profile_allows_only_the_resolved_provider_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace, private_home = root / "workspace", root / "home"
            workspace.mkdir()
            private_home.mkdir()
            executable = root / "provider"
            executable.write_bytes(b"provider")
            with patch("macos_sandbox.shutil.which", return_value=str(executable)):
                argv = confined_argv(["provider"], workspace=workspace, private_home=private_home)
            profile = argv[2]
            self.assertIn(f'(require-not (literal "{executable.resolve()}"))', profile)
            self.assertNotIn(f'(require-not (subpath "{root}"))', profile)

    def test_profile_exempts_provider_executable_from_reads_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace, private_home = root / "workspace", root / "home"
            workspace.mkdir()
            private_home.mkdir()
            executable = root / "provider"
            executable.write_bytes(b"provider")
            with patch("macos_sandbox.shutil.which", return_value=str(executable)):
                profile = confined_argv(
                    ["provider"], workspace=workspace, private_home=private_home
                )[2]

            executable_exception = (
                f'(require-not (literal "{executable.resolve()}"))'
            )
            read_rule, write_rule = profile.split("(deny file-write*", maxsplit=1)
            self.assertIn("(deny file-read-data", read_rule)
            self.assertIn(executable_exception, read_rule)
            self.assertNotIn(executable_exception, write_rule)
            self.assertIn(str(workspace.resolve()), write_rule)
            self.assertIn(str(private_home.resolve()), write_rule)

    def test_disposable_provider_can_launch_read_self_and_write_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace, private_home = root / "workspace", root / "home"
            workspace.mkdir()
            private_home.mkdir()
            output = workspace / "result.txt"
            executable = self._disposable_provider(
                root,
                "import pathlib, sys\n"
                "source = pathlib.Path(__file__).read_text()\n"
                "pathlib.Path(sys.argv[1]).write_text('workspace-ok')\n"
                "print('self-read-ok' if 'workspace-ok' in source else 'bad')",
            )
            argv = confined_argv(
                [str(executable), str(output)],
                workspace=workspace,
                private_home=private_home,
            )
            result = self._run_or_skip_nested(argv, cwd=workspace)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("self-read-ok", result.stdout)
            self.assertEqual(output.read_text(), "workspace-ok")

    def test_disposable_provider_cannot_modify_itself(self) -> None:
        operations = {
            "truncate": "os.truncate(target, 0)",
            "replace": "shutil.copyfile(replacement, target)",
            "rename-over": "os.rename(replacement, target)",
            "chmod": "os.chmod(target, 0o700)",
        }
        for operation, statement in operations.items():
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                workspace, private_home = root / "workspace", root / "home"
                workspace.mkdir()
                private_home.mkdir()
                replacement = workspace / "replacement"
                replacement.write_text("replacement")
                executable = self._disposable_provider(
                    root,
                    "import os, shutil, sys\n"
                    "target = os.path.realpath(__file__)\n"
                    "replacement = sys.argv[1]\n"
                    f"{statement}\n"
                    "print('unexpected-success')",
                )
                original = executable.read_bytes()
                original_mode = executable.stat().st_mode
                argv = confined_argv(
                    [str(executable), str(replacement)],
                    workspace=workspace,
                    private_home=private_home,
                )
                result = self._run_or_skip_nested(argv, cwd=workspace)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertNotIn("unexpected-success", result.stdout)
                self.assertEqual(executable.read_bytes(), original)
                self.assertEqual(executable.stat().st_mode, original_mode)


if __name__ == "__main__":
    unittest.main()
