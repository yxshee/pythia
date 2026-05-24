// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {IERC20} from "../src/PythiaVault.sol";
import {UnlockMarket} from "../src/UnlockMarket.sol";

/// @notice Deploy only UnlockMarket against an existing DevUSDC/test USDC token.
///
/// Usage:
///   USDC_ADDRESS_ARC=0x... REGISTER_TRACE_IDS=24,25,26,27,28,29,30,31 \
///   forge script script/DeployUnlockMarket.s.sol --rpc-url "$ARC_RPC_URL" --broadcast --skip-simulation
contract DeployUnlockMarket is Script {
    function run() external {
        uint256 pk = vm.envUint("PRIVATE_KEY");
        address operator = vm.addr(pk);
        address treasury = vm.envOr("UNLOCK_TREASURY", operator);
        address usdc = vm.envAddress("USDC_ADDRESS_ARC");
        uint256 unlockDefaultPrice = vm.envOr("UNLOCK_DEFAULT_PRICE", uint256(100_000));
        uint256[] memory traceIds = vm.envOr("REGISTER_TRACE_IDS", ",", new uint256[](0));

        vm.startBroadcast(pk);
        UnlockMarket unlocks = new UnlockMarket(IERC20(usdc), operator, treasury, unlockDefaultPrice);
        if (traceIds.length > 0) {
            unlocks.registerTraces(traceIds);
        }
        vm.stopBroadcast();

        console2.log("Operator      :", operator);
        console2.log("Unlock treasury:", treasury);
        console2.log("Unlock price  :", unlockDefaultPrice);
        console2.log("USDC          :", usdc);
        console2.log("UnlockMarket  :", address(unlocks));
        console2.log("Registered    :", traceIds.length);
    }
}
