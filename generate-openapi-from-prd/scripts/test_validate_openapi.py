from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


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
        self.assertIn("duplicate operationId", result.stdout)

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
        self.assertIn("path parameter 'todoId'", result.stdout)

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
