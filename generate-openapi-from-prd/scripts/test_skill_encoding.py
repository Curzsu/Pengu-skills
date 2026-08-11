import json
import re
import unittest
from pathlib import Path

import yaml


SKILL_DIR = Path(__file__).resolve().parents[1]
SKILL_FILE = SKILL_DIR / "SKILL.md"
OPENAI_CONFIG = SKILL_DIR / "agents" / "openai.yaml"

EXPECTED_QUESTION = (
    "\u8bf7\u786e\u8ba4prd\u6587\u4ef6+\u539f\u4ed3\u5e93\uff08\u53ef\u9009\uff09"
    "\u5df2\u7ecf\u63d0\u4f9b\uff0c\u5982\u679c\u5df2\u7ecf\u63d0\u4f9b\u8bf7\u56de\u7b54"
    "\u201c\u786e\u5b9a\u201d"
)
EXPECTED_TOKEN = "\u786e\u5b9a"


class SkillEncodingTests(unittest.TestCase):
    def test_loader_facing_files_are_ascii_safe(self):
        for path in (SKILL_FILE, OPENAI_CONFIG):
            with self.subTest(path=path):
                self.assertTrue(path.read_bytes().isascii(), f"{path} contains non-ASCII bytes")

    def test_confirmation_literals_decode_to_exact_chinese_text(self):
        skill_text = SKILL_FILE.read_text(encoding="ascii")
        question_match = re.search(
            r'^CONFIRMATION_QUESTION_JSON = ("(?:\\.|[^"\\])*")$',
            skill_text,
            re.MULTILINE,
        )
        token_match = re.search(
            r'^CONFIRMATION_TOKEN_JSON = ("(?:\\.|[^"\\])*")$',
            skill_text,
            re.MULTILINE,
        )

        self.assertIsNotNone(question_match)
        self.assertIsNotNone(token_match)
        self.assertEqual(json.loads(question_match.group(1)), EXPECTED_QUESTION)
        self.assertEqual(json.loads(token_match.group(1)), EXPECTED_TOKEN)

    def test_openai_config_is_utf8_yaml_after_ascii_transport(self):
        config = yaml.safe_load(OPENAI_CONFIG.read_text(encoding="ascii"))
        self.assertIn("interface", config)
        self.assertIn("$generate-openapi-from-prd", config["interface"]["default_prompt"])


if __name__ == "__main__":
    unittest.main()
