// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title TraceLog
/// @notice On-chain anchor for off-chain reasoning traces. Each Pythia decision
///         emits one event with the content hash of the private reasoning trace
///         plus a compact decision summary. IPFS/Irys pinning is planned; this
///         contract is the verifiable, monotonic ledger.
/// @dev Cheap by design - sub-second Arc finality + ~$0.01 fees means publishing
///      a trace per decision does not erode strategy PnL.
contract TraceLog {
    /// @notice Decision categories the agent can record.
    enum Decision {
        HOLD, // 0 - no action this cycle
        BUY_YES, // 1
        BUY_NO, // 2
        SELL_YES, // 3
        SELL_NO // 4
    }

    /// @notice Auto-incrementing trace id. Starts at 1.
    uint256 public nextTraceId = 1;

    /// @notice Authorized publishers (agent operator keys).
    mapping(address => bool) public isPublisher;

    /// @notice Multisig/EOA that can add/remove publishers.
    address public admin;

    /// @notice Emitted on every recorded trace.
    /// @param traceId Monotonic id assigned by the contract.
    /// @param publisher Address that submitted the trace.
    /// @param marketId Indexed Polymarket question id (or other venue id).
    /// @param decision Compact decision code.
    /// @param positionUsdc Size in USDC base units (0 for HOLD).
    /// @param confidenceBps Agent's stated confidence in basis points (0-10000).
    /// @param ipfsCid Content hash today; CIDv1 once IPFS/Irys pinning is wired.
    /// @param parentTraceId 0 for new threads; otherwise the trace this follows up on (revisions, exits, etc.).
    event Trace(
        uint256 indexed traceId,
        address indexed publisher,
        bytes32 indexed marketId,
        Decision decision,
        uint256 positionUsdc,
        uint16 confidenceBps,
        bytes32 ipfsCid,
        uint256 parentTraceId
    );

    event PublisherSet(address indexed publisher, bool authorized);
    event AdminTransferred(address indexed previous, address indexed current);

    modifier onlyAdmin() {
        require(msg.sender == admin, "TL: not admin");
        _;
    }

    modifier onlyPublisher() {
        require(isPublisher[msg.sender], "TL: not publisher");
        _;
    }

    constructor(address _admin, address initialPublisher) {
        require(_admin != address(0), "TL: admin zero");
        admin = _admin;
        emit AdminTransferred(address(0), _admin);
        if (initialPublisher != address(0)) {
            isPublisher[initialPublisher] = true;
            emit PublisherSet(initialPublisher, true);
        }
    }

    /// @notice Publish a new reasoning trace. Returns the assigned trace id.
    function publish(
        bytes32 marketId,
        Decision decision,
        uint256 positionUsdc,
        uint16 confidenceBps,
        bytes32 ipfsCid,
        uint256 parentTraceId
    ) external onlyPublisher returns (uint256 traceId) {
        require(confidenceBps <= 10000, "TL: confidence > 10000");
        traceId = nextTraceId++;
        emit Trace(
            traceId, msg.sender, marketId, decision, positionUsdc, confidenceBps, ipfsCid, parentTraceId
        );
    }

    /// @notice Admin can add/remove publishers (e.g. when rotating the agent key).
    function setPublisher(address publisher, bool authorized) external onlyAdmin {
        require(publisher != address(0), "TL: publisher zero");
        isPublisher[publisher] = authorized;
        emit PublisherSet(publisher, authorized);
    }

    function transferAdmin(address newAdmin) external onlyAdmin {
        require(newAdmin != address(0), "TL: admin zero");
        emit AdminTransferred(admin, newAdmin);
        admin = newAdmin;
    }
}
