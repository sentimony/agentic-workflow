"""Exercise real install, child-hook, launcher and cache writes in local clones."""
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

from dependency_isolation import prepare_environment


# This install fixture writes through a dependency link before running its child hook.
INSTALL = '''from pathlib import Path
import os, subprocess, sys
p = Path("deps/installed")
p.write_bytes(b"installed by clone")
subprocess.run([sys.executable, "hook.py"], check=True)
'''
HOOK = '''from pathlib import Path
import os
p = Path("deps/launcher")
p.write_bytes(b"launcher rewritten by child hook")
p.chmod(0o700)
for name in ("HOME", "XDG_CACHE_HOME", "npm_config_cache", "UV_CACHE_DIR", "TMPDIR"):
    root = Path(os.environ.get(name, os.environ["HOME"]))
    root.mkdir(parents=True, exist_ok=True)
    (root / "cache-entry").write_bytes(b"child cache write")
'''


def snapshot(root):
    """Include ignored file bytes and permission modes, which Git status omits."""
    return {str(p.relative_to(root)): (stat.S_IMODE(p.stat().st_mode),
                                     p.read_bytes() if p.is_file() else None)
            for p in sorted(root.rglob("*"))}


class DependencyIsolationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.tools = self.root / "tools"
        self.tools.mkdir()
        self.git = shutil.which("git")
        self.assertIsNotNone(self.git)
        # Deliberately expose only Git and Python, never host agent/provider CLIs.
        (self.tools / "git").symlink_to(self.git)
        (self.tools / "python3").symlink_to(sys.executable)
        self.env = {"HOME": str(self.root / "bootstrap-home"), "PATH": str(self.tools),
                    "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
                    "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}
        Path(self.env["HOME"]).mkdir()
        self.sibling = self.root / "sibling"
        self.sibling.mkdir()
        self.run_git(self.sibling, "init", "-q")
        (self.sibling / ".gitignore").write_text("deps\nhome/\ncache/\n")
        (self.sibling / "install.py").write_text(INSTALL)
        (self.sibling / "hook.py").write_text(HOOK)
        self.run_git(self.sibling, "add", ".")
        self.run_git(self.sibling, "commit", "-qm", "Fixture")
        self.sha = self.run_git(self.sibling, "rev-parse", "HEAD").strip()
        self.tree = self.run_git(self.sibling, "rev-parse", "HEAD^{tree}").strip()
        for name in ("deps", "home", "cache"):
            (self.sibling / name).mkdir()
        (self.sibling / "deps/launcher").write_bytes(b"original launcher")
        (self.sibling / "deps/launcher").chmod(0o755)
        self.clone = self.root / "clone"
        self.run_git(self.root, "clone", "-q", "--no-checkout", str(self.sibling), str(self.clone))
        self.run_git(self.clone, "checkout", "-q", "--detach", self.sha)

    def run_git(self, cwd, *args):
        return subprocess.run([self.git, *args], cwd=cwd, env=self.env,
                              check=True, text=True, capture_output=True).stdout

    def install(self, env):
        subprocess.run([sys.executable, "install.py"], cwd=self.clone,
                       env=env, check=True, capture_output=True)

    def test_shared_dependencies_reproduce_hidden_cross_checkout_writes(self):
        (self.clone / "deps").symlink_to(self.sibling / "deps", target_is_directory=True)
        before = snapshot(self.sibling / "deps")
        self.install(dict(self.env, HOME=str(self.sibling / "home"),
                          XDG_CACHE_HOME=str(self.sibling / "cache")))
        self.assertNotEqual(snapshot(self.sibling / "deps"), before)
        self.assertEqual((self.sibling / "deps/launcher").read_bytes(),
                         b"launcher rewritten by child hook")
        self.assertEqual(stat.S_IMODE((self.sibling / "deps/launcher").stat().st_mode), 0o700)
        self.assertTrue((self.sibling / "cache/cache-entry").exists())
        self.assertEqual(self.run_git(self.sibling, "status", "--porcelain"), "")
        self.assertEqual(self.run_git(self.clone, "status", "--porcelain"), "")

    def test_private_dependencies_preserve_sibling_bytes_and_modes(self):
        shutil.copytree(self.sibling / "deps", self.clone / "deps", symlinks=False)
        before = {name: snapshot(self.sibling / name) for name in ("deps", "home", "cache")}
        env = prepare_environment(self.root / "private", self.tools)
        self.install(env)
        self.assertEqual({name: snapshot(self.sibling / name)
                          for name in ("deps", "home", "cache")}, before)
        self.assertEqual((self.clone / "deps/installed").read_bytes(), b"installed by clone")
        self.assertEqual((self.clone / "deps/launcher").read_bytes(),
                         b"launcher rewritten by child hook")
        for name in ("HOME", "XDG_CACHE_HOME", "npm_config_cache", "UV_CACHE_DIR", "TMPDIR"):
            self.assertTrue((Path(env[name]) / "cache-entry").exists(), name)
        self.assertEqual(self.run_git(self.clone, "rev-parse", "HEAD").strip(), self.sha)
        self.assertEqual(self.run_git(self.clone, "rev-parse", "HEAD^{tree}").strip(), self.tree)
        self.assertEqual(self.run_git(self.clone, "status", "--porcelain"), "")

    def test_existing_private_root_is_refused_without_modification(self):
        root = self.root / "private"
        root.mkdir()
        (root / "keep").write_bytes(b"existing attempt")
        before = snapshot(root)
        with self.assertRaises(FileExistsError):
            prepare_environment(root, self.tools)
        self.assertEqual(snapshot(root), before)

    def test_environment_is_private_and_does_not_inherit_host_configuration(self):
        env = prepare_environment(self.root / "private", self.tools)
        for name in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "TMPDIR",
                     "npm_config_cache", "npm_config_prefix", "UV_CACHE_DIR",
                     "PIP_CACHE_DIR", "PYTHONPYCACHEPREFIX", "CARGO_HOME", "GRADLE_USER_HOME"):
            self.assertTrue(Path(env[name]).is_relative_to(self.root / "private"), name)
            self.assertTrue(Path(env[name]).is_dir(), name)
        self.assertEqual(env["PATH"], str(self.tools))
        self.assertNotIn("SSH_AUTH_SOCK", env)
        self.assertNotIn("GIT_ASKPASS", env)
        for cli in ("codex", "claude", "agy"):
            self.assertIsNone(shutil.which(cli, path=env["PATH"]))


if __name__ == "__main__":
    unittest.main()
