from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3

from nft_collections import Collection

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

        for tier in collection.roles:
            if tier.min_balance <= balance <= tier.max_balance:
                to_add.append(tier.role_id)
            else:
                to_remove.append(tier.role_id)

    return to_add, to_remove, balances
