from __future__ import annotations

import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class UnlockButtonSafetyTests(unittest.TestCase):
    def test_contract_read_failures_block_unlock_state_machine(self) -> None:
        source = (ROOT / "web" / "components" / "unlock-button.tsx").read_text()

        self.assertIn('"read-error"', source)
        for query in ("priceQuery", "isUnlockedQuery", "balanceQuery", "allowanceQuery"):
            self.assertIn(f"{query}.isError", source)

        state_block = re.search(
            r"const state: UiState = \(\(\) => \{(?P<body>.*?)\n  \}\)\(\);",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(state_block)
        if state_block is None:
            return

        body = state_block.group("body")
        loading_index = body.index('return "loading"')
        read_error_index = body.index('return "read-error"')
        self.assertGreater(
            read_error_index,
            loading_index,
            "read errors should be checked after loading settles",
        )
        self.assertLess(
            read_error_index,
            body.index("if (isUnlocked)"),
            "read errors must block unlocked/funds/approve/ready fallbacks",
        )

    def test_contract_read_error_copy_is_user_actionable(self) -> None:
        source = (ROOT / "web" / "components" / "unlock-button.tsx").read_text()

        self.assertIn("Could not read Arc state", source)
        self.assertIn("Check your network connection", source)


if __name__ == "__main__":
    unittest.main()
