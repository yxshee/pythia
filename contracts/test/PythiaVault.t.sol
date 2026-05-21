// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test, console2} from "forge-std/Test.sol";
import {PythiaVault, IERC20} from "../src/PythiaVault.sol";
import {MockUSDC} from "./MockUSDC.sol";

contract PythiaVaultTest is Test {
    PythiaVault vault;
    MockUSDC usdc;

    address operator = makeAddr("operator");
    address feeRecipient = makeAddr("feeRecipient");
    address alice = makeAddr("alice");
    address bob = makeAddr("bob");

    uint256 constant ONE_USDC = 1e6; // 6 decimals

    function setUp() public {
        usdc = new MockUSDC();
        vault = new PythiaVault(IERC20(address(usdc)), operator, feeRecipient);

        // The operator is the only authorized depositor; it seeds the paper-portfolio
        // and pays USDC out on share holders' redemptions. Fund it generously here.
        usdc.mint(operator, 500 * ONE_USDC);
    }

    /// @dev Helper. Operator deposits `assets` USDC on behalf of `recipient`, who receives the shares.
    function _deposit(address recipient, uint256 assets) internal returns (uint256 shares) {
        vm.startPrank(operator);
        usdc.approve(address(vault), assets);
        shares = vault.deposit(assets, recipient);
        vm.stopPrank();
    }

    // -------------------------------------------------------------
    //  Deposit
    // -------------------------------------------------------------
    function test_firstDeposit_mintsOneToOne() public {
        uint256 shares = _deposit(alice, 10 * ONE_USDC);
        assertEq(shares, 10 * ONE_USDC, "shares = assets on first deposit");
        assertEq(vault.totalSupply(), 10 * ONE_USDC);
        assertEq(vault.totalAssets(), 10 * ONE_USDC);
        assertEq(vault.pricePerShare(), 1e18, "PPS starts at 1.0");
    }

    function test_secondDeposit_atFlatNav_isProRata() public {
        _deposit(alice, 10 * ONE_USDC);
        uint256 bobShares = _deposit(bob, 5 * ONE_USDC);
        assertEq(bobShares, 5 * ONE_USDC, "flat NAV -> shares == assets");
        assertEq(vault.totalAssets(), 15 * ONE_USDC);
    }

    function test_secondDeposit_afterProfit_getsFewerShares() public {
        _deposit(alice, 10 * ONE_USDC);
        // Operator records a +5 USDC trade -> NAV is 15, supply still 10, PPS = 1.5
        vm.prank(operator);
        vault.recordTrade(int256(5 * ONE_USDC), bytes32("trace-1"));
        assertEq(vault.pricePerShare(), 15e17, "PPS = 1.5");

        uint256 bobShares = _deposit(bob, 6 * ONE_USDC);
        // 6 USDC / 1.5 PPS = 4 shares
        assertEq(bobShares, 4 * ONE_USDC, "post-profit shares are dilution-proof");
    }

    function test_deposit_revertsWhenPaused() public {
        vm.prank(operator);
        vault.setPaused(true);
        vm.startPrank(operator);
        usdc.approve(address(vault), ONE_USDC);
        vm.expectRevert(bytes("PV: paused"));
        vault.deposit(ONE_USDC, alice);
        vm.stopPrank();
    }

    function test_deposit_revertsForNonOperator() public {
        // Outsiders cannot pool capital into the paper-portfolio vault.
        usdc.mint(alice, 100 * ONE_USDC);
        vm.startPrank(alice);
        usdc.approve(address(vault), ONE_USDC);
        vm.expectRevert(bytes("PV: deposits closed"));
        vault.deposit(ONE_USDC, alice);
        vm.stopPrank();
    }

    // -------------------------------------------------------------
    //  Withdraw + performance fee
    // -------------------------------------------------------------
    function test_withdraw_noProfit_noFee() public {
        _deposit(alice, 10 * ONE_USDC);
        uint256 aliceBefore = usdc.balanceOf(alice);
        vm.prank(alice);
        uint256 out = vault.withdraw(10 * ONE_USDC, alice, alice);
        assertEq(out, 10 * ONE_USDC, "full withdraw at flat NAV");
        assertEq(usdc.balanceOf(alice) - aliceBefore, 10 * ONE_USDC, "alice receives the seeded USDC");
        assertEq(vault.totalSupply(), 0);
        assertEq(vault.totalAssets(), 0);
    }

    function test_withdraw_profitTakesFee() public {
        _deposit(alice, 10 * ONE_USDC);
        // Simulate the operator bridging the +10 USDC profit back from Polymarket.
        usdc.mint(address(vault), 10 * ONE_USDC);
        vm.prank(operator);
        vault.recordTrade(int256(10 * ONE_USDC), bytes32("trace-2"));
        assertEq(vault.pricePerShare(), 2e18);

        vm.prank(alice);
        uint256 out = vault.withdraw(10 * ONE_USDC, alice, alice);

        // Gross = 20 USDC. HWM at deposit = 1.0, current = 2.0; profit per share = 1.0.
        // Profit = 1e18 * 10e6 / 1e18 = 10e6 USDC. Fee = 5% = 0.5 USDC.
        uint256 expectedFee = (10 * ONE_USDC * 500) / 10000;
        assertEq(usdc.balanceOf(feeRecipient), expectedFee, "fee paid");
        assertEq(out, 20 * ONE_USDC - expectedFee, "alice receives net");
    }

    function test_withdraw_loss_paysNoFee() public {
        _deposit(alice, 10 * ONE_USDC);
        // Operator bridged 2 USDC out and lost it on a trade. The remaining USDC
        // in the vault is 8; NAV is also 8 after recordTrade.
        vm.prank(operator);
        vault.bridgeOut(2 * ONE_USDC, operator);
        vm.prank(operator);
        vault.recordTrade(-int256(2 * ONE_USDC), bytes32("trace-3"));
        // NAV = 8, supply = 10, PPS = 0.8.
        assertEq(vault.pricePerShare(), 8e17);

        vm.prank(alice);
        uint256 out = vault.withdraw(10 * ONE_USDC, alice, alice);
        assertEq(out, 8 * ONE_USDC, "alice eats the loss");
        assertEq(usdc.balanceOf(feeRecipient), 0, "no fee on a loss");
    }

    // -------------------------------------------------------------
    //  Operator gate
    // -------------------------------------------------------------
    function test_recordTrade_revertsForNonOperator() public {
        _deposit(alice, 10 * ONE_USDC);
        vm.prank(alice);
        vm.expectRevert(bytes("PV: not operator"));
        vault.recordTrade(int256(1 * ONE_USDC), bytes32("trace-x"));
    }

    function test_recordTrade_lossExceedingNav_reverts() public {
        _deposit(alice, 10 * ONE_USDC);
        vm.prank(operator);
        vm.expectRevert(bytes("PV: loss exceeds NAV"));
        vault.recordTrade(-int256(11 * ONE_USDC), bytes32("trace-x"));
    }

    function test_setPerformanceFee_capped() public {
        vm.startPrank(operator);
        vault.setPerformanceFeeBps(2000); // max
        assertEq(vault.performanceFeeBps(), 2000);
        vm.expectRevert(bytes("PV: fee too high"));
        vault.setPerformanceFeeBps(2001);
        vm.stopPrank();
    }

    // -------------------------------------------------------------
    //  Bridge in/out
    // -------------------------------------------------------------
    function test_bridgeOut_thenIn_preservesAccounting() public {
        _deposit(alice, 10 * ONE_USDC);
        uint256 navBefore = vault.totalAssets();

        // Operator bridges 5 USDC out for a Polymarket trade.
        vm.prank(operator);
        vault.bridgeOut(5 * ONE_USDC, operator);
        assertEq(usdc.balanceOf(address(vault)), 5 * ONE_USDC, "vault USDC down");
        assertEq(vault.totalAssets(), navBefore, "totalAssets unchanged while in-flight");

        // Operator returns 6 USDC (settled +1 PnL).
        vm.startPrank(operator);
        usdc.approve(address(vault), 6 * ONE_USDC);
        vault.bridgeIn(6 * ONE_USDC);
        vault.recordTrade(int256(1 * ONE_USDC), bytes32("trace-5"));
        vm.stopPrank();

        assertEq(vault.totalAssets(), navBefore + 1 * ONE_USDC, "NAV reflects +1 PnL");
    }
}
