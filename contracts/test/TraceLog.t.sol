// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {TraceLog} from "../src/TraceLog.sol";

contract TraceLogTest is Test {
    TraceLog traceLog;

    address admin = makeAddr("admin");
    address publisher = makeAddr("publisher");
    address stranger = makeAddr("stranger");

    function setUp() public {
        traceLog = new TraceLog(admin, publisher);
    }

    function test_constructor_authorizesPublisher() public view {
        assertTrue(traceLog.isPublisher(publisher));
        assertEq(traceLog.admin(), admin);
        assertEq(traceLog.nextTraceId(), 1);
    }

    function test_publish_assignsMonotonicIds() public {
        bytes32 market = keccak256("pm:question:abc");
        vm.startPrank(publisher);
        uint256 id1 = traceLog.publish(market, TraceLog.Decision.BUY_YES, 1_000_000, 7500, bytes32("cid1"), 0);
        uint256 id2 = traceLog.publish(market, TraceLog.Decision.HOLD, 0, 4000, bytes32("cid2"), id1);
        vm.stopPrank();

        assertEq(id1, 1);
        assertEq(id2, 2);
        assertEq(traceLog.nextTraceId(), 3);
    }

    function test_publish_revertsForUnauthorized() public {
        vm.prank(stranger);
        vm.expectRevert(bytes("TL: not publisher"));
        traceLog.publish(bytes32("m"), TraceLog.Decision.BUY_YES, 0, 0, bytes32("c"), 0);
    }

    function test_publish_rejectsBadConfidence() public {
        vm.prank(publisher);
        vm.expectRevert(bytes("TL: confidence > 10000"));
        traceLog.publish(bytes32("m"), TraceLog.Decision.BUY_YES, 0, 10001, bytes32("c"), 0);
    }

    function test_setPublisher_onlyAdmin() public {
        address newPub = makeAddr("new");
        vm.prank(admin);
        traceLog.setPublisher(newPub, true);
        assertTrue(traceLog.isPublisher(newPub));

        vm.prank(admin);
        traceLog.setPublisher(newPub, false);
        assertFalse(traceLog.isPublisher(newPub));

        vm.prank(stranger);
        vm.expectRevert(bytes("TL: not admin"));
        traceLog.setPublisher(newPub, true);
    }

    function test_transferAdmin() public {
        address newAdmin = makeAddr("newAdmin");
        vm.prank(admin);
        traceLog.transferAdmin(newAdmin);
        assertEq(traceLog.admin(), newAdmin);

        vm.prank(admin);
        vm.expectRevert(bytes("TL: not admin"));
        traceLog.transferAdmin(stranger);
    }
}
