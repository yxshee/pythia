// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice Minimal IERC20 used by the vault.
interface IERC20 {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
    function decimals() external view returns (uint8);
}

/// @title PythiaVault
/// @notice Paper-portfolio track-record vault for the Pythia recommendation agent.
///         **Deposits are gated to the operator only**: this vault is not a managed
///         fund and does not custody third-party USDC. The agent posts paper PnL
///         from resolved Polymarket markets via `recordTrade`, producing a public,
///         on-Arc, monotonic record of the agent's claimed track-record.
/// @dev Picks are published off-chain (Telegram, web feed) with a Polymarket
///      `builderCode` link so any follower can trade with their own funds.
///      The vault itself never executes a trade.
contract PythiaVault {
    // ------------------------------------------------------------------
    //  Share-token state (inline ERC20)
    // ------------------------------------------------------------------
    string public constant name = "Pythia Vault Share";
    string public constant symbol = "pPYT";
    uint8 public immutable decimals;

    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    // ------------------------------------------------------------------
    //  Vault state
    // ------------------------------------------------------------------
    IERC20 public immutable asset; // USDC on Arc

    /// @notice Total USDC under management, reported by the operator.
    ///         Increased on deposit/profitable settle, decreased on withdraw/loss.
    uint256 public totalAssets;

    /// @notice Operator address authorized to record settled trades + bridge USDC out.
    address public operator;

    /// @notice Recipient of performance fees (defaults to operator).
    address public feeRecipient;

    /// @notice Performance fee in basis points (10000 = 100%). Default 5%.
    uint256 public performanceFeeBps = 500;
    uint256 public constant MAX_FEE_BPS = 2000; // hard cap 20%

    /// @notice Per-user high-water mark, in NAV-per-share scaled by 1e18.
    mapping(address => uint256) public hwm;

    /// @notice If true, deposits and trade recording are blocked. Withdrawals always allowed.
    bool public paused;

    // ------------------------------------------------------------------
    //  Reentrancy guard
    // ------------------------------------------------------------------
    uint256 private _reentrancyStatus = 1;

    modifier nonReentrant() {
        require(_reentrancyStatus == 1, "PV: reentrancy");
        _reentrancyStatus = 2;
        _;
        _reentrancyStatus = 1;
    }

    modifier onlyOperator() {
        require(msg.sender == operator, "PV: not operator");
        _;
    }

    // ------------------------------------------------------------------
    //  Events
    // ------------------------------------------------------------------
    event Deposit(address indexed sender, address indexed owner, uint256 assets, uint256 shares);
    event Withdraw(
        address indexed sender,
        address indexed receiver,
        address indexed owner,
        uint256 assets,
        uint256 shares,
        uint256 fee
    );
    event TradeRecorded(int256 pnl, uint256 newTotalAssets, bytes32 indexed traceHash);
    event OperatorChanged(address indexed previous, address indexed current);
    event FeeRecipientChanged(address indexed previous, address indexed current);
    event PerformanceFeeChanged(uint256 previousBps, uint256 newBps);
    event PausedChanged(bool paused);

    // ------------------------------------------------------------------
    //  Constructor
    // ------------------------------------------------------------------
    constructor(IERC20 _asset, address _operator, address _feeRecipient) {
        require(address(_asset) != address(0), "PV: asset zero");
        require(_operator != address(0), "PV: operator zero");
        asset = _asset;
        decimals = _asset.decimals();
        operator = _operator;
        feeRecipient = _feeRecipient == address(0) ? _operator : _feeRecipient;
        emit OperatorChanged(address(0), _operator);
        emit FeeRecipientChanged(address(0), feeRecipient);
    }

    // ------------------------------------------------------------------
    //  ERC20 share-token methods
    // ------------------------------------------------------------------
    function transfer(address to, uint256 amount) external returns (bool) {
        _transfer(msg.sender, to, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        uint256 allowed = allowance[from][msg.sender];
        if (allowed != type(uint256).max) {
            require(allowed >= amount, "PV: insufficient allowance");
            allowance[from][msg.sender] = allowed - amount;
        }
        _transfer(from, to, amount);
        return true;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function _transfer(address from, address to, uint256 amount) internal {
        require(to != address(0), "PV: to zero");
        uint256 fromBalance = balanceOf[from];
        require(fromBalance >= amount, "PV: insufficient balance");
        unchecked {
            balanceOf[from] = fromBalance - amount;
            balanceOf[to] += amount;
        }
        emit Transfer(from, to, amount);
    }

    function _mint(address to, uint256 amount) internal {
        totalSupply += amount;
        unchecked {
            balanceOf[to] += amount;
        }
        emit Transfer(address(0), to, amount);
    }

    function _burn(address from, uint256 amount) internal {
        uint256 fromBalance = balanceOf[from];
        require(fromBalance >= amount, "PV: burn exceeds balance");
        unchecked {
            balanceOf[from] = fromBalance - amount;
            totalSupply -= amount;
        }
        emit Transfer(from, address(0), amount);
    }

    // ------------------------------------------------------------------
    //  Vault accounting
    // ------------------------------------------------------------------

    /// @notice Returns NAV-per-share scaled by 1e18. Returns 1e18 if empty.
    function pricePerShare() public view returns (uint256) {
        uint256 supply = totalSupply;
        if (supply == 0) return 1e18;
        return (totalAssets * 1e18) / supply;
    }

    function convertToShares(uint256 assets) public view returns (uint256) {
        uint256 supply = totalSupply;
        if (supply == 0) return assets; // 1:1 on first deposit
        return (assets * supply) / totalAssets;
    }

    function convertToAssets(uint256 shares) public view returns (uint256) {
        uint256 supply = totalSupply;
        if (supply == 0) return 0;
        return (shares * totalAssets) / supply;
    }

    // ------------------------------------------------------------------
    //  Deposit / Withdraw
    // ------------------------------------------------------------------

    /// @notice Deposit USDC; mint shares to `receiver`.
    /// @dev Operator-only. The vault is a paper-portfolio track-record, not a managed fund -
    ///      outside USDC must never enter. The operator may seed real or notional capital
    ///      to anchor the initial NAV.
    function deposit(uint256 assets, address receiver) external nonReentrant returns (uint256 shares) {
        require(msg.sender == operator, "PV: deposits closed");
        require(!paused, "PV: paused");
        require(assets > 0, "PV: zero assets");
        shares = convertToShares(assets);
        require(shares > 0, "PV: zero shares");

        require(asset.transferFrom(msg.sender, address(this), assets), "PV: USDC transfer failed");
        totalAssets += assets;
        _mint(receiver, shares);

        // Set or update the receiver's high-water mark at the current NAV-per-share.
        uint256 currentPps = pricePerShare();
        if (hwm[receiver] < currentPps) hwm[receiver] = currentPps;

        emit Deposit(msg.sender, receiver, assets, shares);
    }

    /// @notice Burn `shares` from `owner`, send USDC to `receiver`.
    ///         Performance fee is taken on profit above the per-user HWM.
    function withdraw(uint256 shares, address receiver, address owner)
        external
        nonReentrant
        returns (uint256 assetsOut)
    {
        require(shares > 0, "PV: zero shares");
        if (msg.sender != owner) {
            uint256 allowed = allowance[owner][msg.sender];
            if (allowed != type(uint256).max) {
                require(allowed >= shares, "PV: insufficient allowance");
                allowance[owner][msg.sender] = allowed - shares;
            }
        }

        uint256 grossAssets = convertToAssets(shares);
        require(grossAssets > 0, "PV: zero assets out");

        // Performance fee on the profit slice above HWM.
        uint256 ownerHwm = hwm[owner];
        uint256 currentPps = pricePerShare();
        uint256 fee = 0;
        if (currentPps > ownerHwm) {
            uint256 profitPerShare = currentPps - ownerHwm;
            uint256 profit = (profitPerShare * shares) / 1e18;
            fee = (profit * performanceFeeBps) / 10000;
        }
        assetsOut = grossAssets - fee;

        _burn(owner, shares);
        totalAssets -= grossAssets;

        if (fee > 0) {
            require(asset.transfer(feeRecipient, fee), "PV: fee transfer failed");
        }
        require(asset.transfer(receiver, assetsOut), "PV: payout failed");

        emit Withdraw(msg.sender, receiver, owner, assetsOut, shares, fee);
    }

    // ------------------------------------------------------------------
    //  Operator (agent) actions
    // ------------------------------------------------------------------

    /// @notice Record the PnL of a settled off-chain trade.
    /// @param pnl Signed PnL in USDC base units. Positive = profit, negative = loss.
    /// @param traceHash IPFS CIDv1 (multihash) of the reasoning trace as bytes32.
    function recordTrade(int256 pnl, bytes32 traceHash) external onlyOperator {
        require(!paused, "PV: paused");
        if (pnl >= 0) {
            totalAssets += uint256(pnl);
        } else {
            uint256 loss = uint256(-pnl);
            require(loss <= totalAssets, "PV: loss exceeds NAV");
            totalAssets -= loss;
        }
        emit TradeRecorded(pnl, totalAssets, traceHash);
    }

    /// @notice Operator pulls USDC out of the vault to bridge to Polymarket via CCTP.
    ///         Reduces totalAssets in-flight; expects `recordTrade` on settlement.
    function bridgeOut(uint256 amount, address to) external onlyOperator nonReentrant {
        require(!paused, "PV: paused");
        require(amount > 0, "PV: zero amount");
        require(amount <= totalAssets, "PV: amount > NAV");
        require(asset.transfer(to, amount), "PV: bridgeOut transfer failed");
        // totalAssets is NOT decremented here - the in-flight USDC is still vault property,
        // and `recordTrade` will reconcile when the position settles back.
    }

    /// @notice Inverse of bridgeOut: pull USDC back into the vault after settlement.
    function bridgeIn(uint256 amount) external onlyOperator nonReentrant {
        require(amount > 0, "PV: zero amount");
        require(asset.transferFrom(msg.sender, address(this), amount), "PV: bridgeIn failed");
    }

    // ------------------------------------------------------------------
    //  Admin (operator)
    // ------------------------------------------------------------------
    function setOperator(address newOperator) external onlyOperator {
        require(newOperator != address(0), "PV: operator zero");
        emit OperatorChanged(operator, newOperator);
        operator = newOperator;
    }

    function setFeeRecipient(address newRecipient) external onlyOperator {
        require(newRecipient != address(0), "PV: recipient zero");
        emit FeeRecipientChanged(feeRecipient, newRecipient);
        feeRecipient = newRecipient;
    }

    function setPerformanceFeeBps(uint256 newBps) external onlyOperator {
        require(newBps <= MAX_FEE_BPS, "PV: fee too high");
        emit PerformanceFeeChanged(performanceFeeBps, newBps);
        performanceFeeBps = newBps;
    }

    function setPaused(bool newPaused) external onlyOperator {
        paused = newPaused;
        emit PausedChanged(newPaused);
    }
}
