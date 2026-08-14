import os
from dataclasses import dataclass


MAX_BALANCE = 10**9


@dataclass(frozen=True)
class RoleTier:
    min_balance: int
    max_balance: int
    role_id: int
    name: str


@dataclass(frozen=True)
class Collection:
    name: str
    contract: str | None
    chain_id: int
    rpc_url: str
    enabled: bool
    roles: tuple[RoleTier, ...]


def _optional_int(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    return int(value)


def _optional_address(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def _load_tiers(prefix: str, tier_defs: list[tuple[int, int, str, str]]) -> tuple[RoleTier, ...]:
    tiers: list[RoleTier] = []
    for min_bal, max_bal, env_key, label in tier_defs:
        role_id = _optional_int(f"{prefix}_{env_key}")
        if role_id is None:
            continue
        tiers.append(
            RoleTier(
                min_balance=min_bal,
                max_balance=max_bal,
                role_id=role_id,
                name=label,
            )
        )
    return tuple(tiers)


def load_collections() -> tuple[Collection, ...]:
    pg_contract = _optional_address("PG_CONTRACT_ADDRESS") or _optional_address(
        "CONTRACT_ADDRESS"
    )
    pg_rpc = os.getenv(
        "PG_RPC_URL",
        os.getenv("ROBINHOOD_RPC_URL", "https://rpc.mainnet.chain.robinhood.com"),
    ).strip()
    pg_chain_id = int(os.getenv("PG_CHAIN_ID", os.getenv("CHAIN_ID", "4663")))

    pg_tier_defs = [
        (25, MAX_BALANCE, "ROLE_FLOWER", "Flower [25+]"),
        (15, 24, "ROLE_FLOWERING", "Flowering [15-24]"),
        (6, 14, "ROLE_VEG", "Veg [6-14]"),
        (1, 5, "ROLE_SPROUT", "sprout [1-5]"),
        (1, MAX_BALANCE, "ROLE_HOLDER", "PG Holder"),
    ]
    pg_roles = _load_tiers("PG", pg_tier_defs)
    if not pg_roles:
        holder_id = _optional_int("HOLDER_ROLE_ID") or _optional_int("PG_ROLE_HOLDER")
        if holder_id is not None:
            pg_roles = (
                RoleTier(1, MAX_BALANCE, holder_id, "PG Holder"),
            )

    pg = Collection(
        name="PG",
        contract=pg_contract,
        chain_id=pg_chain_id,
        rpc_url=pg_rpc,
        enabled=bool(pg_contract and pg_roles),
        roles=pg_roles,
    )

    ub_contract = _optional_address("UB_CONTRACT_ADDRESS")
    ub_enabled = os.getenv("UB_ENABLED", "").strip().lower() in {"1", "true", "yes"}
    ub_rpc = os.getenv("UB_RPC_URL", pg_rpc).strip()
    ub_chain_id = int(os.getenv("UB_CHAIN_ID", "4663"))

    ub_tier_defs = [
        (25, MAX_BALANCE, "ROLE_GRIZZLY", "Grizzly [25+]"),
        (15, 24, "ROLE_BEARS", "Bears [15-24]"),
        (6, 14, "ROLE_CUB", "Cub [6-14]"),
        (1, 5, "ROLE_BABY_BEAR", "Baby Bear [1-5]"),
        (1, MAX_BALANCE, "ROLE_HOLDER", "UB Holder"),
    ]
    ub_roles = _load_tiers("UB", ub_tier_defs)

    ub = Collection(
        name="UB",
        contract=ub_contract,
        chain_id=ub_chain_id,
        rpc_url=ub_rpc,
        enabled=bool(ub_enabled and ub_contract and ub_roles),
        roles=ub_roles,
    )

    return (pg, ub)


def all_managed_role_ids(collections: tuple[Collection, ...]) -> set[int]:
    ids: set[int] = set()
    for collection in collections:
        for tier in collection.roles:
            ids.add(tier.role_id)
    return ids
