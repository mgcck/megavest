from __future__ import annotations

import json
import urllib.error
import urllib.request
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from urllib.parse import urlencode

import base58
from nacl.signing import SigningKey

class SolanaRpcError(RuntimeError):
    pass


def _rpc_call(rpc_url: str, method: str, params: list[Any]) -> Any:
    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        rpc_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise SolanaRpcError(f"Could not reach Solana RPC endpoint: {exc}") from exc

    data = json.loads(body)
    if data.get("error"):
        raise SolanaRpcError(f"Solana RPC error: {data['error']}")

    return data.get("result")


def generate_reference() -> str:
    signing_key = SigningKey.generate()
    public_key_bytes = bytes(signing_key.verify_key)
    return base58.b58encode(public_key_bytes).decode("ascii")


def amount_to_base_units(amount: Decimal, decimals: int) -> int:
    multiplier = Decimal(10) ** decimals
    base_units = (amount * multiplier).to_integral_value(rounding=ROUND_HALF_UP)
    return int(base_units)


def _format_decimal_amount(amount: Decimal) -> str:
    as_text = format(amount.normalize(), "f")
    if "." in as_text:
        as_text = as_text.rstrip("0").rstrip(".")
    return as_text


def build_payment_uri(
    recipient_wallet: str,
    amount: Decimal,
    spl_token_mint: str,
    reference: str,
    label: str,
    message: str,
    memo: str,
) -> str:
    query = urlencode(
        {
            "amount": _format_decimal_amount(amount),
            "spl-token": spl_token_mint,
            "reference": reference,
            "label": label,
            "message": message,
            "memo": memo,
        }
    )
    return f"solana:{recipient_wallet}?{query}"


def _iter_instructions(tx: dict[str, Any]) -> list[dict[str, Any]]:
    instructions: list[dict[str, Any]] = []

    top_level = tx.get("transaction", {}).get("message", {}).get("instructions", [])
    if isinstance(top_level, list):
        instructions.extend(item for item in top_level if isinstance(item, dict))

    inner_groups = tx.get("meta", {}).get("innerInstructions", [])
    if isinstance(inner_groups, list):
        for group in inner_groups:
            if not isinstance(group, dict):
                continue
            group_instructions = group.get("instructions", [])
            if not isinstance(group_instructions, list):
                continue
            instructions.extend(item for item in group_instructions if isinstance(item, dict))

    return instructions


def _merchant_token_accounts(rpc_url: str, owner_wallet: str, token_mint: str) -> set[str]:
    result = _rpc_call(
        rpc_url,
        "getTokenAccountsByOwner",
        [
            owner_wallet,
            {"mint": token_mint},
            {"encoding": "jsonParsed", "commitment": "confirmed"},
        ],
    )

    if not isinstance(result, dict):
        return set()

    value = result.get("value")
    if not isinstance(value, list):
        return set()

    token_accounts: set[str] = set()
    for account in value:
        if not isinstance(account, dict):
            continue
        pubkey = account.get("pubkey")
        if isinstance(pubkey, str) and pubkey:
            token_accounts.add(pubkey)

    return token_accounts


def _extract_transfer_amount_base_units(instruction_type: str, info: dict[str, Any]) -> int | None:
    if instruction_type == "transferChecked":
        token_amount = info.get("tokenAmount")
        if not isinstance(token_amount, dict):
            return None
        raw_amount = token_amount.get("amount")
    else:
        raw_amount = info.get("amount")

    try:
        return int(raw_amount)
    except (TypeError, ValueError):
        return None


def _matches_token_transfer(
    instruction: dict[str, Any],
    destination_token_accounts: set[str],
    token_mint: str,
    min_amount_base_units: int,
) -> bool:
    if instruction.get("program") not in {"spl-token", "spl-token-2022"}:
        return False

    parsed = instruction.get("parsed")
    if not isinstance(parsed, dict):
        return False

    instruction_type = parsed.get("type")
    if instruction_type not in {"transfer", "transferChecked"}:
        return False

    info = parsed.get("info")
    if not isinstance(info, dict):
        return False

    destination_token_account = info.get("destination")
    if destination_token_account not in destination_token_accounts:
        return False

    if instruction_type == "transferChecked" and info.get("mint") != token_mint:
        return False

    amount = _extract_transfer_amount_base_units(instruction_type, info)
    if amount is None:
        return False

    return amount >= min_amount_base_units


def find_matching_payment(
    rpc_url: str,
    reference: str,
    destination_wallet: str,
    token_mint: str,
    min_amount_base_units: int,
) -> str | None:
    destination_token_accounts = _merchant_token_accounts(rpc_url, destination_wallet, token_mint)
    if not destination_token_accounts:
        return None

    signatures = _rpc_call(
        rpc_url,
        "getSignaturesForAddress",
        [reference, {"limit": 25, "commitment": "confirmed"}],
    )

    if not isinstance(signatures, list):
        return None

    for entry in signatures:
        if not isinstance(entry, dict):
            continue

        signature = entry.get("signature")
        if not isinstance(signature, str):
            continue

        tx = _rpc_call(
            rpc_url,
            "getTransaction",
            [
                signature,
                {
                    "encoding": "jsonParsed",
                    "maxSupportedTransactionVersion": 0,
                    "commitment": "confirmed",
                },
            ],
        )

        if not isinstance(tx, dict):
            continue

        meta = tx.get("meta")
        if isinstance(meta, dict) and meta.get("err") is not None:
            continue

        for instruction in _iter_instructions(tx):
            if _matches_token_transfer(
                instruction=instruction,
                destination_token_accounts=destination_token_accounts,
                token_mint=token_mint,
                min_amount_base_units=min_amount_base_units,
            ):
                return signature

    return None
