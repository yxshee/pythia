// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "./PythiaVault.sol";

/// @title DevUSDC
/// @notice Test/dev USDC stand-in with **EIP-3009 transferWithAuthorization** support,
///         so x402 nanopayments can settle off a signed authorization without a
///         separate `approve()` step.
/// @dev Open mint. Do NOT deploy to mainnet. The EIP-712 `name`/`version` constants
///      below are what x402's runtime asset override must be configured with.
contract DevUSDC is IERC20 {
    string public constant name = "Pythia Dev USDC";
    string public constant symbol = "pUSDC";
    string public constant version = "1";
    uint8 public constant decimals = 6;

    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    /// @notice Per-authorizer nonce usage map. EIP-3009 nonces are arbitrary bytes32
    ///         chosen by the signer (NOT monotonic), so we store them as keys.
    mapping(address => mapping(bytes32 => bool)) private _authorizationStates;

    bytes32 private immutable _DEPLOYED_DOMAIN_SEPARATOR;
    uint256 private immutable _DEPLOYED_CHAIN_ID;

    bytes32 private constant _EIP712_DOMAIN_TYPEHASH =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");

    bytes32 private constant _TRANSFER_WITH_AUTHORIZATION_TYPEHASH = keccak256(
        "TransferWithAuthorization(address from,address to,uint256 value,uint256 validAfter,uint256 validBefore,bytes32 nonce)"
    );

    bytes32 private constant _CANCEL_AUTHORIZATION_TYPEHASH =
        keccak256("CancelAuthorization(address authorizer,bytes32 nonce)");

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
    event AuthorizationUsed(address indexed authorizer, bytes32 indexed nonce);
    event AuthorizationCanceled(address indexed authorizer, bytes32 indexed nonce);

    constructor() {
        _DEPLOYED_CHAIN_ID = block.chainid;
        _DEPLOYED_DOMAIN_SEPARATOR = _buildDomainSeparator();
        balanceOf[msg.sender] = 1_000_000 * 1e6;
        totalSupply = 1_000_000 * 1e6;
        emit Transfer(address(0), msg.sender, totalSupply);
    }

    function DOMAIN_SEPARATOR() public view returns (bytes32) {
        // Forked / fuzzed test environments can change chainid; rebuild on mismatch.
        if (block.chainid == _DEPLOYED_CHAIN_ID) return _DEPLOYED_DOMAIN_SEPARATOR;
        return _buildDomainSeparator();
    }

    function authorizationState(address authorizer, bytes32 nonce) external view returns (bool) {
        return _authorizationStates[authorizer][nonce];
    }

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
        totalSupply += amount;
        emit Transfer(address(0), to, amount);
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        _transfer(msg.sender, to, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        uint256 allowed = allowance[from][msg.sender];
        if (allowed != type(uint256).max) {
            require(allowed >= amount, "pUSDC: allowance");
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

    /// @notice EIP-3009: spend `from`'s balance based on an off-chain signature.
    ///         Used by x402 nanopayments so the payer signs once and pays in one tx.
    function transferWithAuthorization(
        address from,
        address to,
        uint256 value,
        uint256 validAfter,
        uint256 validBefore,
        bytes32 nonce,
        uint8 v,
        bytes32 r,
        bytes32 s
    ) external {
        require(block.timestamp > validAfter, "pUSDC: auth not yet valid");
        require(block.timestamp < validBefore, "pUSDC: auth expired");
        require(!_authorizationStates[from][nonce], "pUSDC: auth used");

        bytes32 structHash = keccak256(
            abi.encode(
                _TRANSFER_WITH_AUTHORIZATION_TYPEHASH, from, to, value, validAfter, validBefore, nonce
            )
        );
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", DOMAIN_SEPARATOR(), structHash));
        address signer = ecrecover(digest, v, r, s);
        require(signer != address(0) && signer == from, "pUSDC: bad signature");

        _authorizationStates[from][nonce] = true;
        emit AuthorizationUsed(from, nonce);
        _transfer(from, to, value);
    }

    /// @notice EIP-3009: cancel a not-yet-used authorization nonce.
    function cancelAuthorization(address authorizer, bytes32 nonce, uint8 v, bytes32 r, bytes32 s)
        external
    {
        require(!_authorizationStates[authorizer][nonce], "pUSDC: auth used");
        bytes32 structHash = keccak256(abi.encode(_CANCEL_AUTHORIZATION_TYPEHASH, authorizer, nonce));
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", DOMAIN_SEPARATOR(), structHash));
        address signer = ecrecover(digest, v, r, s);
        require(signer != address(0) && signer == authorizer, "pUSDC: bad signature");

        _authorizationStates[authorizer][nonce] = true;
        emit AuthorizationCanceled(authorizer, nonce);
    }

    function _buildDomainSeparator() private view returns (bytes32) {
        return keccak256(
            abi.encode(
                _EIP712_DOMAIN_TYPEHASH,
                keccak256(bytes(name)),
                keccak256(bytes(version)),
                block.chainid,
                address(this)
            )
        );
    }

    function _transfer(address from, address to, uint256 amount) internal {
        require(balanceOf[from] >= amount, "pUSDC: balance");
        unchecked {
            balanceOf[from] -= amount;
            balanceOf[to] += amount;
        }
        emit Transfer(from, to, amount);
    }
}
