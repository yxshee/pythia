from __future__ import annotations

import unittest
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from scripts.check_contract_bytecode import normalize_bytecode


class ContractBytecodeCheckTests(unittest.TestCase):
    def test_normalizes_solidity_cbor_metadata(self) -> None:
        logic = "60aa61bb"
        metadata_a = "a2646970667358221220" + "11" * 32
        metadata_b = "a2646970667358221220" + "22" * 32
        # Last two bytes encode metadata byte length. Include the length word.
        meta_len = f"{len(metadata_a) // 2:04x}"

        left = normalize_bytecode("0x" + logic + metadata_a + meta_len, {})
        right = normalize_bytecode("0x" + logic + metadata_b + meta_len, {})

        self.assertEqual(left, right)
        self.assertEqual(left, logic)

    def test_zeroes_immutable_references_before_comparison(self) -> None:
        refs = {"1": [{"start": 2, "length": 2}]}
        left = normalize_bytecode("0x6000aaaaff", refs)
        right = normalize_bytecode("0x6000bbbbff", refs)

        self.assertEqual(left, right)
        self.assertEqual(left, "60000000ff")


if __name__ == "__main__":
    unittest.main()
