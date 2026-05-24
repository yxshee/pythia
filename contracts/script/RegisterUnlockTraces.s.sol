// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {UnlockMarket} from "../src/UnlockMarket.sol";

/// @notice Register public trace IDs on an existing UnlockMarket deploy.
///
/// Usage:
///   UNLOCK_MARKET_ADDRESS=0x... REGISTER_TRACE_IDS=24,25,26,27,28,29,30,31 \
///   forge script script/RegisterUnlockTraces.s.sol --rpc-url "$ARC_RPC_URL" --broadcast --skip-simulation
contract RegisterUnlockTraces is Script {
    function run() external {
        uint256 pk = vm.envUint("PRIVATE_KEY");
        address unlockMarket = vm.envAddress("UNLOCK_MARKET_ADDRESS");
        uint256[] memory traceIds = vm.envUint("REGISTER_TRACE_IDS", ",");

        vm.startBroadcast(pk);
        UnlockMarket(unlockMarket).registerTraces(traceIds);
        vm.stopBroadcast();

        console2.log("UnlockMarket:", unlockMarket);
        console2.log("Registered  :", traceIds.length);
    }
}
