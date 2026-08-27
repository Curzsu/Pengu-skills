import json
import re
import unittest
from pathlib import Path

import yaml


SKILL_DIR = Path(__file__).resolve().parents[1]
SKILL_FILE = SKILL_DIR / "SKILL.md"
OPENAI_CONFIG = SKILL_DIR / "agents" / "openai.yaml"

EXPECTED_QUESTION = (
    "\u8bf7\u786e\u8ba4 PRD \u6587\u4ef6\u548c\u539f\u4ed3\u5e93\uff08\u53ef\u9009\uff09"
    "\u5df2\u7ecf\u63d0\u4f9b\u3002\u56de\u590d\u201c\u786e\u5b9a\u201d\u7ee7\u7eed\uff0c"
    "\u56de\u590d\u201c\u53d6\u6d88\u201d\u9000\u51fa\u3002"
)
EXPECTED_CANCELLATION_RESPONSE = (
    "\u5df2\u53d6\u6d88\u3002\u672c\u6b21\u672a\u8bfb\u53d6 PRD \u6216\u4ed3\u5e93\uff0c"
    "\u4e5f\u672a\u751f\u6210\u4efb\u4f55\u6587\u4ef6\u3002"
)
EXPECTED_AMBIGUOUS_REPROMPT = (
    "\u6211\u8fd8\u6ca1\u6709\u5f00\u59cb\u5de5\u4f5c\u3002\u8bf7\u56de\u590d\u201c\u786e\u5b9a\u201d"
    "\u7ee7\u7eed\uff0c\u6216\u56de\u590d\u201c\u53d6\u6d88\u201d\u9000\u51fa\u3002"
)
EXPECTED_AMBIGUOUS_EXIT = (
    "\u672a\u6536\u5230\u660e\u786e\u9009\u62e9\uff0c\u672c\u6b21\u5df2\u7ed3\u675f\u4e14"
    "\u672a\u5f00\u59cb\u4efb\u4f55\u5de5\u4f5c\u3002\u51c6\u5907\u597d\u540e\u8bf7\u91cd\u65b0"
    "\u8c03\u7528\u3002"
)
REQUIRED_AFFIRMATIVE_REPLIES = {
    "\u786e\u5b9a",
    "\u786e\u8ba4",
    "\u662f\u7684",
    "\u597d\u7684",
    "\u7ee7\u7eed",
    "ok",
    "ok\u4e86",
    "okay",
    "yes",
}
REQUIRED_CANCELLATION_REPLIES = {
    "\u53d6\u6d88",
    "\u505c\u6b62",
    "\u9000\u51fa",
    "\u4e0d\u7528\u4e86",
    "\u5148\u4e0d\u505a",
    "cancel",
    "stop",
    "no",
}


class SkillEncodingTests(unittest.TestCase):
    def test_loader_facing_files_are_ascii_safe(self):
        for path in (SKILL_FILE, OPENAI_CONFIG):
            with self.subTest(path=path):
                self.assertTrue(path.read_bytes().isascii(), f"{path} contains non-ASCII bytes")

    def test_confirmation_protocol_literals_decode_to_user_visible_text(self):
        skill_text = SKILL_FILE.read_text(encoding="ascii")

        def decode(name: str):
            match = re.search(
                rf"^{re.escape(name)} = (.+)$",
                skill_text,
                re.MULTILINE,
            )
            self.assertIsNotNone(match, f"missing {name}")
            return json.loads(match.group(1))

        self.assertEqual(decode("CONFIRMATION_QUESTION_JSON"), EXPECTED_QUESTION)
        self.assertEqual(
            decode("CANCELLATION_RESPONSE_JSON"),
            EXPECTED_CANCELLATION_RESPONSE,
        )
        self.assertEqual(
            decode("AMBIGUOUS_REPROMPT_JSON"),
            EXPECTED_AMBIGUOUS_REPROMPT,
        )
        self.assertEqual(decode("AMBIGUOUS_EXIT_JSON"), EXPECTED_AMBIGUOUS_EXIT)

    def test_reply_examples_cover_common_confirmation_and_exit_language(self):
        skill_text = SKILL_FILE.read_text(encoding="ascii")

        def decode_set(name: str) -> set[str]:
            match = re.search(
                rf"^{re.escape(name)} = (.+)$",
                skill_text,
                re.MULTILINE,
            )
            self.assertIsNotNone(match, f"missing {name}")
            return set(json.loads(match.group(1)))

        self.assertLessEqual(
            REQUIRED_AFFIRMATIVE_REPLIES,
            decode_set("AFFIRMATIVE_REPLIES_JSON"),
        )
        self.assertLessEqual(
            REQUIRED_CANCELLATION_REPLIES,
            decode_set("CANCELLATION_REPLIES_JSON"),
        )

    def test_openai_config_is_utf8_yaml_after_ascii_transport(self):
        config = yaml.safe_load(OPENAI_CONFIG.read_text(encoding="ascii"))
        self.assertIn("interface", config)
        self.assertIn("$generate-openapi-from-prd", config["interface"]["default_prompt"])


if __name__ == "__main__":
    unittest.main()
