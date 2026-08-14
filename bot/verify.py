from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3

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
        "Verify Pixel Gardens holder\n"
        f"Discord User ID: {discord_user_id}\n"
        f"Nonce: {nonce}"
    )


def recover_signer(message: str, signature: str) -> str:
    encoded = encode_defunct(text=message)
    return Account.recover_message(encoded, signature=signature)


def check_nft_holder(rpc_url: str, contract_address: str, wallet_address: str) -> bool:
    web3 = Web3(Web3.HTTPProvider(rpc_url))
    if not web3.is_connected():
        raise RuntimeError("Could not connect to Robinhood Chain RPC")

    contract = web3.eth.contract(
        address=Web3.to_checksum_address(contract_address),
        abi=ERC721_ABI,
    )
    balance = contract.functions.balanceOf(
        Web3.to_checksum_address(wallet_address)
    ).call()
    return balance > 0
