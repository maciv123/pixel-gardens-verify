from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3

from nft_collections import Collection, RoleTier

ERC721_ABI = [
    {
        "inputs": [{"name": "owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
]


def build_sign_message(discord_user_id: str, nonce: str) -> str:
    return (
        "Verify UnFairBears NFT holder\n"
        f"Discord User ID: {discord_user_id}\n"
        f"Nonce: {nonce}"
    )


def recover_signer(message: str, signature: str) -> str:
    encoded = encode_defunct(text=message)
    return Account.recover_message(encoded, signature=signature)


def get_balance(rpc_url: str, contract_address: str, wallet_address: str) -> int:
    web3 = Web3(Web3.HTTPProvider(rpc_url))
    if not web3.is_connected():
        raise RuntimeError(f"Could not connect to RPC at {rpc_url}")

    contract = web3.eth.contract(
        address=Web3.to_checksum_address(contract_address),
        abi=ERC721_ABI,
    )
    balance = contract.functions.balanceOf(
        Web3.to_checksum_address(wallet_address)
    ).call()
    return int(balance)


def _stacked_tier_roles(
    roles: tuple[RoleTier, ...], balance: int
) -> tuple[list[int], list[int]]:
    """Assign the matching tier plus every lower tier (roles stack)."""
    if balance <= 0 or not roles:
        return [], [tier.role_id for tier in roles]

    sorted_tiers = sorted(roles, key=lambda tier: tier.min_balance, reverse=True)
    qualifying_idx = None
    for idx, tier in enumerate(sorted_tiers):
        if tier.min_balance <= balance <= tier.max_balance:
            qualifying_idx = idx
            break

    if qualifying_idx is None:
        return [], [tier.role_id for tier in roles]

    stacked = sorted_tiers[qualifying_idx:]
    below = sorted_tiers[:qualifying_idx]
    return [tier.role_id for tier in stacked], [tier.role_id for tier in below]


def compute_role_changes(
    wallet_address: str, collections: tuple[Collection, ...]
) -> tuple[list[int], list[int], dict[str, int]]:
    to_add: list[int] = []
    to_remove: list[int] = []
    balances: dict[str, int] = {}

    for collection in collections:
        if not collection.enabled:
            continue

        assert collection.contract is not None
        balance = get_balance(collection.rpc_url, collection.contract, wallet_address)
        balances[collection.name] = balance

        add_ids, remove_ids = _stacked_tier_roles(collection.roles, balance)
        to_add.extend(add_ids)
        to_remove.extend(remove_ids)
        # #region agent log
        try:
            import json
            import time
            from pathlib import Path

            payload = {
                "sessionId": "cbd26f",
                "hypothesisId": "STACK",
                "location": "verify.py:compute_role_changes",
                "message": "stacked tier roles computed",
                "data": {
                    "collection": collection.name,
                    "balance": balance,
                    "to_add": add_ids,
                    "to_remove": remove_ids,
                },
                "timestamp": int(time.time() * 1000),
                "runId": "stack-roles",
            }
            Path(__file__).resolve().parent.parent.joinpath("debug-cbd26f.log").open(
                "a", encoding="utf-8"
            ).write(json.dumps(payload) + "\n")
        except Exception:
            pass
        # #endregion

    return to_add, to_remove, balances
