import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILLS = ("verify", "finalize", "cr-request", "cr-received")


class FingerprintCopies(unittest.TestCase):
    def test_copies_are_identical(self):
        texts = {
            s: (ROOT / "skills" / s / "tree-fingerprint.md").read_bytes()
            for s in SKILLS
        }
        reference = texts["verify"]
        for skill, text in texts.items():
            self.assertEqual(text, reference, f"{skill} copy differs from verify")


if __name__ == "__main__":
    unittest.main()
