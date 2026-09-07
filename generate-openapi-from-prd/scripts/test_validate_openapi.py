from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import yaml


SCRIPT = Path(__file__).with_name("validate_openapi.py")


def run_validator(document: str) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as temp_dir:
        spec_path = Path(temp_dir) / "openapi.yaml"
        spec_path.write_text(textwrap.dedent(document), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(spec_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )


VALID_SPEC = """
openapi: 3.0.3
info:
  title: Todo API
  version: 1.0.0
paths:
  /todos/{todoId}:
    get:
      operationId: getTodo
      parameters:
        - name: todoId
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: OK
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Todo'
components:
  schemas:
    Todo:
      type: object
      required: [id]
      properties:
        id:
          type: string
"""


class ValidateOpenApiTests(unittest.TestCase):
    def test_rejects_invalid_openapi_structures(self) -> None:
        for case in ("schema_type", "null_response", "missing_description", "invalid_parameter"):
            with self.subTest(case=case):
                document = yaml.safe_load(VALID_SPEC)
                response = document["paths"]["/todos/{todoId}"]["get"]["responses"]
                if case == "schema_type":
                    document["components"]["schemas"]["Todo"]["type"] = "nonsense"
                elif case == "null_response":
                    response["200"] = None
                elif case == "missing_description":
                    del response["200"]["description"]
                else:
                    document["paths"]["/todos/{todoId}"]["get"]["parameters"][0]["in"] = "invalid"
                result = run_validator(yaml.safe_dump(document))
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("[OPENAPI_STANDARD]", result.stdout)
                self.assertNotIn("Traceback", result.stderr)

    def test_reports_schema_error_location_before_project_rules(self) -> None:
        document = yaml.safe_load(VALID_SPEC)
        document["components"]["schemas"]["Todo"]["type"] = "nonsense"
        document["x-ai-assumptions"] = "invalid"
        result = run_validator(yaml.safe_dump(document))
        self.assertEqual(result.returncode, 1)
        self.assertIn("/components/schemas/Todo", result.stdout)
        self.assertNotIn("x-ai-assumptions", result.stdout)

    def test_accepts_no_content_response(self) -> None:
        document = yaml.safe_load(VALID_SPEC)
        document["paths"]["/todos/{todoId}"]["get"]["responses"] = {
            "204": {"description": "No content"}
        }
        result = run_validator(yaml.safe_dump(document))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_rejects_external_references_without_resolving_them(self) -> None:
        for reference in ("missing.yaml#/Todo", "https://example.invalid/spec.yaml#/Todo"):
            with self.subTest(reference=reference):
                result = run_validator(VALID_SPEC.replace("#/components/schemas/Todo", reference))
                self.assertEqual(result.returncode, 1)
                self.assertIn("[REFERENCE]", result.stdout)
                self.assertIn("local", result.stdout)
                self.assertNotIn("Traceback", result.stderr)

    def test_requires_exact_contract_version(self) -> None:
        result = run_validator(VALID_SPEC.replace("3.0.3", "3.0.2"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("3.0.3", result.stdout)

    def test_project_rules_still_require_operation_id(self) -> None:
        result = run_validator(VALID_SPEC.replace("      operationId: getTodo\n", ""))
        self.assertEqual(result.returncode, 1)
        self.assertIn("operationId is required", result.stdout)

    def test_accepts_minimal_valid_contract(self) -> None:
        result = run_validator(VALID_SPEC)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OK", result.stdout)

    def test_rejects_duplicate_operation_ids(self) -> None:
        result = run_validator(
            VALID_SPEC.replace(
                "components:\n",
                """
  /duplicate:
    get:
      operationId: getTodo
      responses:
        '200':
          description: OK
components:
""",
            )
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("[OPENAPI_STANDARD]", result.stdout)
        self.assertIn("getTodo", result.stdout)

    def test_rejects_undefined_path_parameter(self) -> None:
        result = run_validator(
            """
            openapi: 3.0.3
            info: {title: Broken API, version: 1.0.0}
            paths:
              /todos/{todoId}:
                get:
                  operationId: getTodo
                  responses:
                    '200': {description: OK}
            """
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("[OPENAPI_STANDARD]", result.stdout)
        self.assertIn("todoId", result.stdout)

    def test_rejects_unresolved_local_reference(self) -> None:
        result = run_validator(VALID_SPEC.replace("#/components/schemas/Todo", "#/components/schemas/Missing"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unresolved $ref", result.stdout)

    def test_rejects_operation_without_success_response(self) -> None:
        result = run_validator(VALID_SPEC.replace("'200':", "'400':"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("2xx response", result.stdout)

    def test_rejects_todo_placeholders(self) -> None:
        result = run_validator(VALID_SPEC.replace("description: OK", "description: TODO define response"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("placeholder text", result.stdout)

    def test_rejects_malformed_assumptions_extension(self) -> None:
        result = run_validator(
            VALID_SPEC.replace(
                "info:\n",
                "x-ai-assumptions: hidden assumption\ninfo:\n",
            )
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("x-ai-assumptions", result.stdout)


if __name__ == "__main__":
    unittest.main()
