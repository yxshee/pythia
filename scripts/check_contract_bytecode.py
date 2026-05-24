#!/usr/bin/env python3
"""Compare deployed Arc bytecode with local Foundry artifacts.

Block explorers often show a mismatch when Solidity metadata hashes differ or
constructor-set immutable slots are embedded in runtime bytecode. This script
normalizes both before comparing, proving whether the deployed runtime logic
matches the local source artifact even when Arcscan source verification is not
available yet.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

CONTRACTS = (
    (
        "TraceLog",
        "TRACE_LOG_ADDRESS",
        "contracts/out/TraceLog.sol/TraceLog.json",
        "0x48Af95Ed6F1E4dF73Dd62CE17731084a5E98AFB4",
    ),
    (
        "UnlockMarket",
        "UNLOCK_MARKET_ADDRESS",
        "contracts/out/UnlockMarket.sol/UnlockMarket.json",
        "0xD8af5ebe36AC9eA736f40D749674FF1B0f4bd3cA",
    ),
    (
        "DevUSDC",
        "USDC_ADDRESS_ARC",
        "contracts/out/DevUSDC.sol/DevUSDC.json",
        "0x6d3bda6e93dd02a1c237642C5af837796bF47511",
    ),
)


def _strip_0x(value: str) -> str:
    return value[2:] if value.startswith("0x") else value


def _strip_solidity_metadata(hexstr: str) -> str:
    if len(hexstr) < 4:
        return hexstr
    metadata_bytes = int(hexstr[-4:], 16)
    metadata_chars = metadata_bytes * 2 + 4
    if metadata_chars <= 0 or metadata_chars >= len(hexstr):
        return hexstr
    return hexstr[:-metadata_chars]


def _zero_immutable_references(hexstr: str, immutable_refs: dict[str, Any]) -> str:
    chars = list(hexstr)
    for entries in immutable_refs.values():
        for ref in entries:
            start = int(ref["start"]) * 2
            length = int(ref["length"]) * 2
            chars[start : start + length] = "0" * length
    return "".join(chars)


def normalize_bytecode(bytecode: str, immutable_refs: dict[str, Any]) -> str:
    without_prefix = _strip_0x(bytecode.strip())
    without_immutables = _zero_immutable_references(without_prefix, immutable_refs)
    return _strip_solidity_metadata(without_immutables)


def _cast_code(address: str, rpc_url: str) -> str:
    return subprocess.check_output(["cast", "code", address, "--rpc-url", rpc_url], text=True).strip()


def compare_contract(name: str, address: str, artifact_path: Path, rpc_url: str) -> tuple[bool, int, int]:
    artifact = json.loads(artifact_path.read_text())
    deployed = artifact["deployedBytecode"]["object"]
    refs = artifact["deployedBytecode"].get("immutableReferences") or {}
    local_normalized = normalize_bytecode(deployed, refs)
    onchain_normalized = normalize_bytecode(_cast_code(address, rpc_url), refs)
    return local_normalized == onchain_normalized, len(local_normalized) // 2, len(onchain_normalized) // 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rpc-url", default=os.environ.get("ARC_RPC_URL"), help="Arc RPC URL")
    args = parser.parse_args(argv)
    if not args.rpc_url:
        print("FAIL: ARC_RPC_URL or --rpc-url is required", file=sys.stderr)
        return 2

    failures: list[str] = []
    for name, env_name, rel_artifact, default_address in CONTRACTS:
        address = os.environ.get(env_name, default_address)
        artifact_path = REPO_ROOT / rel_artifact
        ok, local_len, onchain_len = compare_contract(name, address, artifact_path, args.rpc_url)
        status = "ok" if ok else "mismatch"
        print(f"{name}: {status} address={address} normalized_bytes={local_len}/{onchain_len}")
        if not ok:
            failures.append(name)

    if failures:
        print(f"FAIL: bytecode mismatch for {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

