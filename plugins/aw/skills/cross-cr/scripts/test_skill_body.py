"""Structural checks for the progressively disclosed cross-cr contract."""

import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
STEP_HEADINGS = (
    "1. Confirm the dependency and the target",
    "2. Select material with secret hygiene",
    "3. Fix the implementation boundary",
    "4. Record the target fingerprint",
    "5. Build the brief",
    "6. Run the reviewer",
    "7. Check and hand off the result",
    "8. Repeat rounds",
    "9. Follow up in the same session",
)


def body(text):
    """Remove only YAML frontmatter, retaining every UTF-8 body byte."""
    if text.startswith("---\n"):
        return text.split("\n---\n", 1)[1]
    return text


def slug(heading):
    return re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")


class SkillBodyTests(unittest.TestCase):
    def test_body_fits_loader_budget(self):
        size = len(body((SKILL / "SKILL.md").read_text()).encode("utf-8"))
        self.assertLessEqual(size, 20_000, "cross-cr body is %s UTF-8 bytes" % size)

    def test_relative_markdown_links_and_fragments_are_live(self):
        for source in [SKILL / "SKILL.md", *sorted((SKILL / "references").glob("*.md"))]:
            for destination in re.findall(r"\[[^]\n]+\]\(([^)]+)\)", source.read_text()):
                if "://" in destination or destination.startswith("mailto:"):
                    continue
                path, _, fragment = destination.partition("#")
                target = source.parent / path if path else source
                with self.subTest(source=source.name, destination=destination):
                    self.assertTrue(target.is_file(), str(target))
                    if fragment and target.is_file():
                        headings = re.findall(r"^#{1,6} (.+)$", target.read_text(), re.M)
                        self.assertIn(fragment, [slug(h) for h in headings])

    def test_every_workflow_step_has_a_live_read_route(self):
        entry = (SKILL / "SKILL.md").read_text()
        details = (SKILL / "references" / "workflow-details.md").read_text()
        for heading in STEP_HEADINGS:
            with self.subTest(heading=heading):
                self.assertEqual(details.count("\n### " + heading + "\n"), 1)
                self.assertIn("references/workflow-details.md#" + slug(heading), entry)
        self.assertIn("before each step", entry.lower())
        self.assertIn("## Security Model\n", entry)

    def test_dependency_extraction_headings_remain_available(self):
        refs = SKILL.parent / "cr-request" / "references"
        for filename, headings in (("brief.md", ("Reviewer instructions", "Result contract", "Severity")),
                                   ("lenses.md", ("Intent", "System", "Craft"))):
            text = (refs / filename).read_text()
            for heading in headings:
                with self.subTest(filename=filename, heading=heading):
                    self.assertEqual(text.count("\n## " + heading + "\n"), 1)


if __name__ == "__main__":
    unittest.main()
