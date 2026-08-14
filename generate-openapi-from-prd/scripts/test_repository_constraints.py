import unittest
from pathlib import Path


SKILL_FILE = Path(__file__).resolve().parents[1] / "SKILL.md"


class RepositoryConstraintInstructionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill_text = SKILL_FILE.read_text(encoding="ascii")

    def test_requires_evidence_based_repository_constraint_scan(self) -> None:
        required_instructions = (
            "## Inspect repository constraints",
            "production and deployment configuration",
            "runtime and toolchain versions",
            "dependency manifests and lockfiles",
            "CI configuration",
            "Record the source path for every verified constraint",
        )
        for instruction in required_instructions:
            with self.subTest(instruction=instruction):
                self.assertIn(instruction, self.skill_text)

    def test_does_not_hard_code_a_technology_or_version(self) -> None:
        self.assertIn(
            "Do not hard-code any language, framework, runtime, package manager, or version",
            self.skill_text,
        )
        for incident_specific_value in ("Python 3.9", "python:3.9-slim", "eval_type_backport"):
            with self.subTest(value=incident_specific_value):
                self.assertNotIn(incident_specific_value, self.skill_text)

    def test_handoff_carries_constraints_without_polluting_openapi(self) -> None:
        for instruction in (
            "**Repository constraints:**",
            "**Conflicts or unknowns:**",
            "Keep repository implementation constraints out of `openapi.yaml`",
        ):
            with self.subTest(instruction=instruction):
                self.assertIn(instruction, self.skill_text)

    def test_agents_verify_against_the_detected_target_environment(self) -> None:
        for instruction in (
            "unsupported by the verified target runtime or toolchain",
            "exact deployment runtime or container",
            "application import or equivalent startup preflight",
            "service startup and health check",
        ):
            with self.subTest(instruction=instruction):
                self.assertIn(instruction, self.skill_text)

    def test_missing_or_conflicting_constraints_are_not_guessed(self) -> None:
        for instruction in (
            "Do not guess missing repository constraints",
            "report the conflict",
            "runtime constraints are unknown",
        ):
            with self.subTest(instruction=instruction):
                self.assertIn(instruction, self.skill_text)


if __name__ == "__main__":
    unittest.main()
