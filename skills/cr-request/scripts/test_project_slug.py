#!/usr/bin/env python3
"""Tests for project_slug.py: the same slug algorithm as context-transfer."""

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import project_slug  # noqa: E402

ENV = dict(os.environ, GIT_AUTHOR_NAME="T", GIT_AUTHOR_EMAIL="t@e.test",
           GIT_COMMITTER_NAME="T", GIT_COMMITTER_EMAIL="t@e.test")


def git(path, *args):
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, env=ENV)


class ProjectSlugTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp(prefix="crr-slug-")))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_root_and_digest(self):
        self.assertEqual(project_slug.slug("/"), "root-8a5edab28263")

    def test_long_unicode_name_is_cut_on_a_character_boundary(self):
        path = self.tmp / ("щ" * 100)
        path.mkdir()
        result = project_slug.slug(path)
        name, _, digest = result.rpartition("-")
        self.assertEqual(digest, hashlib.sha256(os.fsencode(str(path))).hexdigest()[:12])
        self.assertEqual(name, "щ" * 32)
        self.assertLessEqual(len(os.fsencode(name)), 64)

    def test_symlink_gives_the_target_slug(self):
        target = self.tmp / "real"
        target.mkdir()
        link = self.tmp / "link"
        link.symlink_to(target, target_is_directory=True)
        self.assertEqual(project_slug.slug(link), project_slug.slug(target))

    def test_worktrees_share_the_main_checkout_key(self):
        main = self.tmp / "main"
        main.mkdir()
        git(main, "init", "-q")
        (main / "f").write_text("x")
        git(main, "add", "f")
        git(main, "commit", "-qm", "c")
        tree = self.tmp / "linked"
        git(main, "worktree", "add", "-q", str(tree), "-b", "other")
        self.assertEqual(project_slug.project_key(str(tree)), main)
        self.assertEqual(project_slug.project_key(str(main / ".")), main)

    def test_non_git_directory_uses_itself(self):
        self.assertEqual(project_slug.project_key(str(self.tmp)), self.tmp)

    def test_bare_common_dir_is_its_own_key(self):
        bare = self.tmp / "x.git"
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
        self.assertEqual(project_slug.project_key(str(bare)), bare)

    def test_archive_root_lives_under_home(self):
        home = self.tmp / "home"
        home.mkdir()
        project = self.tmp / "proj"
        project.mkdir()
        root = project_slug.archive_root(str(project), home=home)
        self.assertEqual(root.parent, home / ".sentimony" / "agentflow" / "cr-request")
        self.assertEqual(root.name, project_slug.slug(project))
        self.assertFalse(root.exists())

    def test_missing_or_unusable_home_is_refused_without_a_fallback(self):
        for value in (None, "", "relative", str(self.tmp / "missing")):
            with self.subTest(value=value):
                environ = {} if value is None else {"HOME": value}
                with unittest.mock.patch.dict(os.environ, environ, clear=True):
                    with self.assertRaises(project_slug.StateError):
                        project_slug.archive_root(str(self.tmp))

    def test_git_failures_are_not_mistaken_for_a_plain_directory(self):
        with self.assertRaises(project_slug.StateError):
            project_slug.project_key(str(self.tmp / "missing"))
        with unittest.mock.patch.object(project_slug.subprocess, "run", side_effect=OSError("no git")):
            with self.assertRaises(project_slug.StateError):
                project_slug.project_key(str(self.tmp))
        broken = self.tmp / "broken"
        broken.mkdir()
        (broken / ".git").write_text("gitdir: /nonexistent\n")
        with self.assertRaises(project_slug.StateError):
            project_slug.project_key(str(broken))

    def test_trailing_whitespace_in_a_bare_common_dir_name_is_kept(self):
        bare = self.tmp / "bare "
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
        self.assertEqual(project_slug.project_key(str(bare)), bare)

    def test_git_environment_does_not_redirect_the_key(self):
        other = self.tmp / "other"
        other.mkdir()
        git(other, "init", "-q")
        mine = self.tmp / "mine"
        mine.mkdir()
        git(mine, "init", "-q")
        with unittest.mock.patch.dict(os.environ, {"GIT_DIR": str(other / ".git")}):
            self.assertEqual(project_slug.project_key(str(mine)), mine)

    def test_dangling_git_symlink_is_not_a_plain_directory(self):
        broken = self.tmp / "dangling"
        broken.mkdir()
        (broken / ".git").symlink_to(self.tmp / "nowhere")
        with self.assertRaises(project_slug.StateError):
            project_slug.project_key(str(broken))

    def test_home_inside_the_project_is_refused(self):
        project = self.tmp / "proj2"
        project.mkdir()
        git(project, "init", "-q")
        home = project / "home"
        home.mkdir()
        with self.assertRaises(project_slug.StateError):
            project_slug.archive_root(str(project), home=home)

    def test_home_inside_a_linked_worktree_is_refused(self):
        main = self.tmp / "main3"
        main.mkdir()
        git(main, "init", "-q")
        (main / "f").write_text("x")
        git(main, "add", "f")
        git(main, "commit", "-qm", "c")
        tree = self.tmp / "tree3"
        git(main, "worktree", "add", "-q", str(tree), "-b", "wt3")
        home = tree / "home"
        home.mkdir()
        with self.assertRaises(project_slug.StateError):
            project_slug.archive_root(str(tree), home=home)


if __name__ == "__main__":
    unittest.main()
