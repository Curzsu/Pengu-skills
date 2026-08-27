import unittest
from pathlib import Path


SKILL_FILE = Path(__file__).resolve().parents[1] / "SKILL.md"


class BusinessKnowledgeVisibilityInstructionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        skill_text = SKILL_FILE.read_text(encoding="ascii")
        start = skill_text.index("## Optional business knowledge")
        end = skill_text.index("## Inspect repository constraints", start)
        cls.instructions = skill_text[start:end]

    def test_search_results_require_a_user_visible_receipt(self) -> None:
        required_contract = (
            "Immediately before each business knowledge CLI call, tell the user what will be queried or opened",
            "After every `search` or `sections` result, send a compact user-visible retrieval receipt before the next CLI call.",
            "the query or discovery purpose",
            "the result count",
            "every returned `search` heading",
            "candidate `sections` headings selected for inspection",
            "a short snippet for each `search` match",
        )
        for requirement in required_contract:
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, self.instructions)

    def test_section_selection_is_visible_without_blocking_progress(self) -> None:
        required_contract = (
            "After every successful `get`, send another compact receipt",
            "which heading was opened",
            "why it is relevant",
            "After the last `get`, identify which returned matches were not opened",
            "short commit",
            "citation URL",
            "Do not wait for approval after a receipt",
        )
        for requirement in required_contract:
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, self.instructions)

    def test_no_match_stale_warning_and_error_states_are_visible(self) -> None:
        required_contract = (
            "zero matches",
            "stale source or warning",
            "CLI error",
            "continue from the PRD alone",
        )
        for requirement in required_contract:
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, self.instructions)

    def test_receipts_are_background_labeled_and_sanitized(self) -> None:
        required_contract = (
            "background context rather than PRD requirements",
            "Do not paste raw JSON",
            "ranking scores",
            "Git credentials",
            "local cache paths",
            "full section content",
        )
        for requirement in required_contract:
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, self.instructions)


if __name__ == "__main__":
    unittest.main()
