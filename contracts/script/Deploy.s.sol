// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {DevUSDC} from "../src/DevUSDC.sol";
import {PythiaVault, IERC20} from "../src/PythiaVault.sol";
import {TraceLog} from "../src/TraceLog.sol";
import {UnlockMarket} from "../src/UnlockMarket.sol";

/// @notice Deploys PythiaVault + TraceLog to Arc testnet.
///
///         Usage:
///         export PRIVATE_KEY=0x...
///         export USDC_ADDRESS_ARC=0x...
///         forge script script/Deploy.s.sol \
///             --rpc-url "$ARC_RPC_URL" --broadcast --skip-simulation
///
///         If USDC_ADDRESS_ARC is unset, the script deploys a DevUSDC and uses
///         that address for the vault (useful for the very first dry-run deploy).
contract Deploy is Script {
    function run() external {
        uint256 pk = vm.envUint("PRIVATE_KEY");
        address operator = vm.addr(pk);
        address feeRecipient = vm.envOr("FEE_RECIPIENT", operator);
        address treasury = vm.envOr("UNLOCK_TREASURY", operator);
        address usdc = vm.envOr("USDC_ADDRESS_ARC", address(0));
        // Default unlock price: 0.10 USDC (100_000 in 6-decimal base units).
        uint256 unlockDefaultPrice = vm.envOr("UNLOCK_DEFAULT_PRICE", uint256(100_000));

        vm.startBroadcast(pk);
        if (usdc == address(0)) {
            DevUSDC dev = new DevUSDC();
            usdc = address(dev);
            console2.log("Deployed dev USDC at", usdc);
        }
        PythiaVault vault = new PythiaVault(IERC20(usdc), operator, feeRecipient);
        TraceLog traceLog = new TraceLog(operator, operator);
        UnlockMarket unlocks = new UnlockMarket(IERC20(usdc), operator, treasury, unlockDefaultPrice);
        vm.stopBroadcast();

        console2.log("Operator      :", operator);
        console2.log("Fee recipient :", feeRecipient);
        console2.log("Unlock treasury:", treasury);
        console2.log("Unlock price  :", unlockDefaultPrice);
        console2.log("USDC          :", usdc);
        console2.log("PythiaVault   :", address(vault));
        console2.log("TraceLog      :", address(traceLog));
        console2.log("UnlockMarket  :", address(unlocks));
    }
}
