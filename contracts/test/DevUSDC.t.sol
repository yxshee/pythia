// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test, Vm} from "forge-std/Test.sol";
import {DevUSDC} from "../src/DevUSDC.sol";

contract DevUSDCTest is Test {
    DevUSDC dev;

    Vm.Wallet payer;
    address relayer = makeAddr("relayer");
    address payee = makeAddr("payee");

    bytes32 private constant _TRANSFER_WITH_AUTHORIZATION_TYPEHASH = keccak256(
        "TransferWithAuthorization(address from,address to,uint256 value,uint256 validAfter,uint256 validBefore,bytes32 nonce)"
    );

    bytes32 private constant _CANCEL_AUTHORIZATION_TYPEHASH =
        keccak256("CancelAuthorization(address authorizer,bytes32 nonce)");

    function setUp() public {
        dev = new DevUSDC();
        payer = vm.createWallet("payer");
        // Seed the payer with USDC so they have something to spend.
        dev.mint(payer.addr, 100 * 1e6);
        // Move time past zero so block.timestamp > validAfter=0 works on a fresh chain.
        vm.warp(1_000_000);
    }

    // ------------------------------------------------------------------
    //  Helpers
    // ------------------------------------------------------------------
    function _digest(
        address from,
        address to,
        uint256 value,
        uint256 validAfter,
        uint256 validBefore,
        bytes32 nonce
    ) internal view returns (bytes32) {
        bytes32 structHash = keccak256(
            abi.encode(
                _TRANSFER_WITH_AUTHORIZATION_TYPEHASH, from, to, value, validAfter, validBefore, nonce
            )
        );
        return keccak256(abi.encodePacked("\x19\x01", dev.DOMAIN_SEPARATOR(), structHash));
    }

    function _cancelDigest(address authorizer, bytes32 nonce) internal view returns (bytes32) {
        bytes32 structHash = keccak256(abi.encode(_CANCEL_AUTHORIZATION_TYPEHASH, authorizer, nonce));
        return keccak256(abi.encodePacked("\x19\x01", dev.DOMAIN_SEPARATOR(), structHash));
    }

    // ------------------------------------------------------------------
    //  EIP-3009 happy path
    // ------------------------------------------------------------------
    function test_transferWithAuthorization_validSig_transfersAndMarksNonce() public {
        bytes32 nonce = keccak256("nonce-1");
        uint256 value = 10 * 1e6;
        uint256 validAfter = 0;
        uint256 validBefore = block.timestamp + 1 hours;

        bytes32 digest = _digest(payer.addr, payee, value, validAfter, validBefore, nonce);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(payer.privateKey, digest);

        // Anyone can submit - typically a relayer.
        vm.prank(relayer);
        dev.transferWithAuthorization(payer.addr, payee, value, validAfter, validBefore, nonce, v, r, s);

        assertEq(dev.balanceOf(payee), value, "payee credited");
        assertEq(dev.balanceOf(payer.addr), 100 * 1e6 - value, "payer debited");
        assertTrue(dev.authorizationState(payer.addr, nonce), "nonce marked used");
    }

    // ------------------------------------------------------------------
    //  Replay protection + expiry
    // ------------------------------------------------------------------
    function test_transferWithAuthorization_replayReverts() public {
        bytes32 nonce = keccak256("nonce-replay");
        uint256 value = 5 * 1e6;
        uint256 validBefore = block.timestamp + 1 hours;
        bytes32 digest = _digest(payer.addr, payee, value, 0, validBefore, nonce);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(payer.privateKey, digest);

        dev.transferWithAuthorization(payer.addr, payee, value, 0, validBefore, nonce, v, r, s);

        vm.expectRevert(bytes("pUSDC: auth used"));
        dev.transferWithAuthorization(payer.addr, payee, value, 0, validBefore, nonce, v, r, s);
    }

    function test_transferWithAuthorization_expiredReverts() public {
        bytes32 nonce = keccak256("nonce-expired");
        uint256 value = 1 * 1e6;
        uint256 validBefore = block.timestamp - 1; // already expired
        bytes32 digest = _digest(payer.addr, payee, value, 0, validBefore, nonce);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(payer.privateKey, digest);

        vm.expectRevert(bytes("pUSDC: auth expired"));
        dev.transferWithAuthorization(payer.addr, payee, value, 0, validBefore, nonce, v, r, s);
    }

    function test_transferWithAuthorization_prematureReverts() public {
        bytes32 nonce = keccak256("nonce-premature");
        uint256 value = 1 * 1e6;
        uint256 validAfter = block.timestamp + 1 hours;
        uint256 validBefore = block.timestamp + 2 hours;
        bytes32 digest = _digest(payer.addr, payee, value, validAfter, validBefore, nonce);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(payer.privateKey, digest);

        vm.expectRevert(bytes("pUSDC: auth not yet valid"));
        dev.transferWithAuthorization(payer.addr, payee, value, validAfter, validBefore, nonce, v, r, s);
    }

    // ------------------------------------------------------------------
    //  Wrong signer
    // ------------------------------------------------------------------
    function test_transferWithAuthorization_badSigReverts() public {
        Vm.Wallet memory attacker = vm.createWallet("attacker");
        bytes32 nonce = keccak256("nonce-bad");
        uint256 value = 1 * 1e6;
        uint256 validBefore = block.timestamp + 1 hours;

        // Attacker signs an auth that drains payer's balance.
        bytes32 digest = _digest(payer.addr, payee, value, 0, validBefore, nonce);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(attacker.privateKey, digest);

        vm.expectRevert(bytes("pUSDC: bad signature"));
        dev.transferWithAuthorization(payer.addr, payee, value, 0, validBefore, nonce, v, r, s);
    }

    // ------------------------------------------------------------------
    //  Cancellation
    // ------------------------------------------------------------------
    function test_cancelAuthorization_preventsLaterUse() public {
        bytes32 nonce = keccak256("nonce-cancel");
        uint256 value = 1 * 1e6;
        uint256 validBefore = block.timestamp + 1 hours;

        // Payer cancels the nonce up-front.
        bytes32 cancelDigest = _cancelDigest(payer.addr, nonce);
        (uint8 cv, bytes32 cr, bytes32 cs) = vm.sign(payer.privateKey, cancelDigest);
        dev.cancelAuthorization(payer.addr, nonce, cv, cr, cs);
        assertTrue(dev.authorizationState(payer.addr, nonce), "nonce marked used by cancel");

        // Subsequent transferWithAuthorization on the same nonce reverts.
        bytes32 d = _digest(payer.addr, payee, value, 0, validBefore, nonce);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(payer.privateKey, d);
        vm.expectRevert(bytes("pUSDC: auth used"));
        dev.transferWithAuthorization(payer.addr, payee, value, 0, validBefore, nonce, v, r, s);
    }

    function test_cancelAuthorization_alreadyUsedReverts() public {
        bytes32 nonce = keccak256("nonce-already-used");
        uint256 value = 1 * 1e6;
        uint256 validBefore = block.timestamp + 1 hours;
        bytes32 d = _digest(payer.addr, payee, value, 0, validBefore, nonce);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(payer.privateKey, d);
        dev.transferWithAuthorization(payer.addr, payee, value, 0, validBefore, nonce, v, r, s);

        bytes32 cd = _cancelDigest(payer.addr, nonce);
        (uint8 cv, bytes32 cr, bytes32 cs) = vm.sign(payer.privateKey, cd);
        vm.expectRevert(bytes("pUSDC: auth used"));
        dev.cancelAuthorization(payer.addr, nonce, cv, cr, cs);
    }

    // ------------------------------------------------------------------
    //  Domain separator (sanity)
    // ------------------------------------------------------------------
    function test_domainSeparator_isStableAtSameChainId() public view {
        bytes32 a = dev.DOMAIN_SEPARATOR();
        bytes32 b = dev.DOMAIN_SEPARATOR();
        assertEq(a, b);
    }
}
