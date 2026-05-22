// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {UnlockMarket} from "../src/UnlockMarket.sol";
import {IERC20} from "../src/PythiaVault.sol";
import {MockUSDC} from "./MockUSDC.sol";

contract ReentrantUSDC {
    UnlockMarket public target;
    uint256 public traceId;
    bool public attempted;
    bool public reentered;
    bool public reenterReverted;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    function setTarget(UnlockMarket _target, uint256 _traceId) external {
        target = _target;
        traceId = _traceId;
    }

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        require(allowance[from][msg.sender] >= amount, "rUSDC: insufficient allowance");
        require(balanceOf[from] >= amount, "rUSDC: insufficient balance");

        if (!attempted) {
            attempted = true;
            try target.unlock(traceId) returns (uint256) {
                reentered = true;
            } catch {
                reenterReverted = true;
            }
        }

        allowance[from][msg.sender] -= amount;
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}

contract UnlockMarketTest is Test {
    UnlockMarket market;
    MockUSDC usdc;

    address owner = makeAddr("owner");
    address treasury = makeAddr("treasury");
    address alice = makeAddr("alice");
    address bob = makeAddr("bob");
    address stranger = makeAddr("stranger");

    uint256 constant ONE_USDC = 1e6;
    uint256 constant DEFAULT_PRICE = 100_000; // 0.10 USDC

    function setUp() public {
        usdc = new MockUSDC();
        market = new UnlockMarket(IERC20(address(usdc)), owner, treasury, DEFAULT_PRICE);
        vm.prank(owner);
        market.registerTraces(_traceIds(1, 5, 7, 8, 11, 42, 99_999_999));

        usdc.mint(alice, 10 * ONE_USDC);
        usdc.mint(bob, 10 * ONE_USDC);
    }

    function _traceIds(
        uint256 a,
        uint256 b,
        uint256 c,
        uint256 d,
        uint256 e,
        uint256 f,
        uint256 g
    ) internal pure returns (uint256[] memory ids) {
        ids = new uint256[](7);
        ids[0] = a;
        ids[1] = b;
        ids[2] = c;
        ids[3] = d;
        ids[4] = e;
        ids[5] = f;
        ids[6] = g;
    }

    function _approveAndUnlock(address buyer, uint256 traceId) internal returns (uint256 priced) {
        priced = market.priceFor(traceId);
        vm.startPrank(buyer);
        usdc.approve(address(market), priced);
        market.unlock(traceId);
        vm.stopPrank();
    }

    // ------------------------------------------------------------------
    //  Pricing reads
    // ------------------------------------------------------------------
    function test_priceFor_defaultsWhenNoOverride() public view {
        assertEq(market.priceFor(1), DEFAULT_PRICE);
        assertEq(market.priceFor(99_999_999), DEFAULT_PRICE);
    }

    function test_priceFor_usesOverrideWhenSet() public {
        vm.prank(owner);
        market.setPriceOverride(7, 500_000); // 0.50 USDC
        assertEq(market.priceFor(7), 500_000);
        assertEq(market.priceFor(8), DEFAULT_PRICE, "other traces unaffected");
    }

    // ------------------------------------------------------------------
    //  Unlock flow
    // ------------------------------------------------------------------
    function test_unlock_atDefaultPrice() public {
        uint256 priced = _approveAndUnlock(alice, 1);
        assertEq(priced, DEFAULT_PRICE);
        assertTrue(market.isUnlocked(1, alice));
        assertEq(usdc.balanceOf(treasury), DEFAULT_PRICE, "treasury paid");
        assertEq(usdc.balanceOf(alice), 10 * ONE_USDC - DEFAULT_PRICE, "alice debited");
        assertEq(market.revenuePerTrace(1), DEFAULT_PRICE);
        assertEq(market.unlockCount(1), 1);
    }

    function test_unlock_atOverridePrice() public {
        vm.prank(owner);
        market.setPriceOverride(42, 250_000);
        uint256 priced = _approveAndUnlock(alice, 42);
        assertEq(priced, 250_000);
        assertEq(usdc.balanceOf(treasury), 250_000);
    }

    function test_unlock_doubleUnlockReverts() public {
        _approveAndUnlock(alice, 1);
        vm.startPrank(alice);
        usdc.approve(address(market), DEFAULT_PRICE);
        vm.expectRevert(bytes("UM: already unlocked"));
        market.unlock(1);
        vm.stopPrank();
    }

    function test_unlock_distinctBuyersBothCount() public {
        _approveAndUnlock(alice, 1);
        _approveAndUnlock(bob, 1);
        assertEq(market.unlockCount(1), 2);
        assertEq(market.revenuePerTrace(1), 2 * DEFAULT_PRICE);
        assertTrue(market.isUnlocked(1, alice));
        assertTrue(market.isUnlocked(1, bob));
    }

    function test_unlock_revertsOnZeroPrice() public {
        // Owner clears the default by setting it to a non-zero value first,
        // then we test the path where priceFor returns zero. Since defaultPrice
        // is constructor-set non-zero, the only path to a zero price is a per-trace
        // override of 0 which `setPriceOverride` rejects. The remaining edge case is
        // a freshly-deployed market with defaultPrice=0, which we test directly.
        UnlockMarket freeMarket = new UnlockMarket(IERC20(address(usdc)), owner, treasury, 0);
        vm.prank(owner);
        freeMarket.registerTrace(1);
        vm.startPrank(alice);
        usdc.approve(address(freeMarket), 1);
        vm.expectRevert(bytes("UM: price zero"));
        freeMarket.unlock(1);
        vm.stopPrank();
    }

    function test_unlock_nonexistentTraceReverts() public {
        vm.startPrank(alice);
        usdc.approve(address(market), DEFAULT_PRICE);
        vm.expectRevert(bytes("UM: unknown trace"));
        market.unlock(999);
        vm.stopPrank();
    }

    function test_unlock_reentrantTokenCannotUnlockTwice() public {
        ReentrantUSDC reentrantUsdc = new ReentrantUSDC();
        UnlockMarket reentrantMarket = new UnlockMarket(
            IERC20(address(reentrantUsdc)),
            owner,
            treasury,
            DEFAULT_PRICE
        );
        vm.prank(owner);
        reentrantMarket.registerTrace(1);
        reentrantUsdc.setTarget(reentrantMarket, 1);
        reentrantUsdc.mint(alice, ONE_USDC);

        vm.startPrank(alice);
        reentrantUsdc.approve(address(reentrantMarket), DEFAULT_PRICE);
        reentrantMarket.unlock(1);
        vm.stopPrank();

        assertTrue(reentrantUsdc.attempted(), "token attempted reentry");
        assertTrue(reentrantUsdc.reenterReverted(), "reentry reverted");
        assertFalse(reentrantUsdc.reentered(), "reentry did not unlock");
        assertTrue(reentrantMarket.isUnlocked(1, alice));
        assertEq(reentrantMarket.unlockCount(1), 1);
        assertEq(reentrantUsdc.balanceOf(treasury), DEFAULT_PRICE);
    }

    function test_unlock_revertsOnInsufficientAllowance() public {
        vm.startPrank(alice);
        // No approve.
        vm.expectRevert(bytes("UM: USDC transfer failed"));
        market.unlock(1);
        vm.stopPrank();
    }

    // ------------------------------------------------------------------
    //  Admin
    // ------------------------------------------------------------------
    function test_setDefaultPrice_onlyOwner() public {
        vm.prank(stranger);
        vm.expectRevert(bytes("UM: not owner"));
        market.setDefaultPrice(200_000);

        vm.prank(owner);
        market.setDefaultPrice(200_000);
        assertEq(market.defaultPrice(), 200_000);
        assertEq(market.priceFor(1), 200_000);
    }

    function test_setPriceOverride_zeroRejected() public {
        vm.startPrank(owner);
        vm.expectRevert(bytes("UM: use clearPriceOverride"));
        market.setPriceOverride(1, 0);
        vm.stopPrank();
    }

    function test_registerTrace_onlyOwnerAndRejectsZero() public {
        vm.prank(stranger);
        vm.expectRevert(bytes("UM: not owner"));
        market.registerTrace(123);

        vm.prank(owner);
        vm.expectRevert(bytes("UM: trace zero"));
        market.registerTrace(0);

        vm.prank(owner);
        market.registerTrace(123);
        assertTrue(market.traceExists(123));
    }

    function test_clearPriceOverride_revertsToDefault() public {
        vm.startPrank(owner);
        market.setPriceOverride(5, 999_999);
        assertEq(market.priceFor(5), 999_999);
        market.clearPriceOverride(5);
        assertEq(market.priceFor(5), DEFAULT_PRICE);
        vm.stopPrank();
    }

    function test_setTreasury_routesToNewAddress() public {
        address newTreasury = makeAddr("newTreasury");
        vm.prank(owner);
        market.setTreasury(newTreasury);
        _approveAndUnlock(alice, 11);
        assertEq(usdc.balanceOf(newTreasury), DEFAULT_PRICE);
        assertEq(usdc.balanceOf(treasury), 0, "old treasury untouched");
    }

    function test_transferOwnership_transfersAdminAuthority() public {
        address newOwner = makeAddr("newOwner");
        vm.prank(owner);
        market.transferOwnership(newOwner);
        assertEq(market.owner(), newOwner);

        // Old owner is now powerless.
        vm.prank(owner);
        vm.expectRevert(bytes("UM: not owner"));
        market.setDefaultPrice(1);

        // New owner can administer.
        vm.prank(newOwner);
        market.setDefaultPrice(777);
        assertEq(market.defaultPrice(), 777);
    }
}
