// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "./PythiaVault.sol";

/// @title UnlockMarket
/// @notice Pay-per-unlock for full Pythia reasoning traces.
///         A user pays USDC to unlock a specific `traceId`; an off-chain API
///         (the Agora Alpha web app) verifies the on-chain `Unlocked` event
///         before serving the private full payload.
/// @dev Pricing has two tiers: a flat `defaultPrice`, and an optional
///      per-trace override set by the owner. Unlocks are idempotent in
///      the storage mapping but `unlock()` reverts on double-pay so users
///      don't accidentally pay twice.
contract UnlockMarket {
    IERC20 public immutable usdc;

    address public owner;
    address public treasury;

    /// @notice Default price (USDC base units) when no per-trace override is set.
    uint256 public defaultPrice;

    /// @notice Per-trace pricing override. 0 means "use defaultPrice".
    mapping(uint256 => uint256) public priceOverride;

    /// @notice Trace IDs that the web app can actually serve after unlock.
    mapping(uint256 => bool) public traceExists;

    /// @notice Whether `buyer` has unlocked `traceId`.
    mapping(uint256 => mapping(address => bool)) public isUnlocked;

    /// @notice Running total of USDC paid for unlocks per trace (for the leaderboard).
    mapping(uint256 => uint256) public revenuePerTrace;

    /// @notice Running count of unique buyers per trace.
    mapping(uint256 => uint256) public unlockCount;

    event Unlocked(uint256 indexed traceId, address indexed buyer, uint256 price);
    event PriceOverrideSet(uint256 indexed traceId, uint256 price);
    event TraceRegistered(uint256 indexed traceId);
    event DefaultPriceSet(uint256 previousPrice, uint256 newPrice);
    event TreasurySet(address indexed previous, address indexed current);
    event OwnerTransferred(address indexed previous, address indexed current);

    uint256 private _locked = 1;

    modifier onlyOwner() {
        require(msg.sender == owner, "UM: not owner");
        _;
    }

    modifier nonReentrant() {
        require(_locked == 1, "UM: reentrant");
        _locked = 2;
        _;
        _locked = 1;
    }

    constructor(IERC20 _usdc, address _owner, address _treasury, uint256 _defaultPrice) {
        require(address(_usdc) != address(0), "UM: usdc zero");
        require(_owner != address(0), "UM: owner zero");
        require(_treasury != address(0), "UM: treasury zero");
        usdc = _usdc;
        owner = _owner;
        treasury = _treasury;
        defaultPrice = _defaultPrice;
        emit OwnerTransferred(address(0), _owner);
        emit TreasurySet(address(0), _treasury);
        emit DefaultPriceSet(0, _defaultPrice);
    }

    // ------------------------------------------------------------------
    //  Reads
    // ------------------------------------------------------------------

    /// @notice Effective price for `traceId`: override if set, else default.
    function priceFor(uint256 traceId) public view returns (uint256) {
        uint256 override_ = priceOverride[traceId];
        return override_ > 0 ? override_ : defaultPrice;
    }

    // ------------------------------------------------------------------
    //  Buyer flow
    // ------------------------------------------------------------------

    /// @notice Pay `priceFor(traceId)` in USDC to unlock the full trace.
    ///         The buyer must have approved this contract for at least that amount.
    function unlock(uint256 traceId) external nonReentrant returns (uint256 pricePaid) {
        require(traceExists[traceId], "UM: unknown trace");
        require(!isUnlocked[traceId][msg.sender], "UM: already unlocked");
        pricePaid = priceFor(traceId);
        require(pricePaid > 0, "UM: price zero");

        isUnlocked[traceId][msg.sender] = true;
        revenuePerTrace[traceId] += pricePaid;
        unlockCount[traceId] += 1;

        _safeTransferFrom(msg.sender, treasury, pricePaid);

        emit Unlocked(traceId, msg.sender, pricePaid);
    }

    // ------------------------------------------------------------------
    //  Admin
    // ------------------------------------------------------------------

    /// @notice Set a per-trace price (USDC base units). 0 reverts; use `clearPriceOverride`.
    function setPriceOverride(uint256 traceId, uint256 price) external onlyOwner {
        require(price > 0, "UM: use clearPriceOverride");
        priceOverride[traceId] = price;
        emit PriceOverrideSet(traceId, price);
    }

    function registerTrace(uint256 traceId) public onlyOwner {
        require(traceId != 0, "UM: trace zero");
        if (!traceExists[traceId]) {
            traceExists[traceId] = true;
            emit TraceRegistered(traceId);
        }
    }

    function registerTraces(uint256[] memory traceIds) external onlyOwner {
        for (uint256 i = 0; i < traceIds.length; i++) {
            registerTrace(traceIds[i]);
        }
    }

    function clearPriceOverride(uint256 traceId) external onlyOwner {
        delete priceOverride[traceId];
        emit PriceOverrideSet(traceId, 0);
    }

    function setDefaultPrice(uint256 price) external onlyOwner {
        require(price > 0, "UM: default zero");
        emit DefaultPriceSet(defaultPrice, price);
        defaultPrice = price;
    }

    function setTreasury(address newTreasury) external onlyOwner {
        require(newTreasury != address(0), "UM: treasury zero");
        emit TreasurySet(treasury, newTreasury);
        treasury = newTreasury;
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "UM: owner zero");
        emit OwnerTransferred(owner, newOwner);
        owner = newOwner;
    }

    function _safeTransferFrom(address from, address to, uint256 amount) internal {
        (bool ok, bytes memory ret) = address(usdc).call(
            abi.encodeWithSelector(IERC20.transferFrom.selector, from, to, amount)
        );
        require(ok && (ret.length == 0 || abi.decode(ret, (bool))), "UM: USDC transfer failed");
    }
}
