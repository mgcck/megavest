from __future__ import annotations

from datetime import datetime, timezone

from botocore.exceptions import ClientError

from shared.dynamo import get_orders_table
from shared.http import json_response, options_response
from shared.settings import load_settings
from shared.solana import SolanaRpcError, find_matching_payment


def _as_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _query_string(event: dict, key: str) -> str:
    return (event.get("queryStringParameters") or {}).get(key, "").strip()


def lambda_handler(event, _context):
    try:
        settings = load_settings()
    except ValueError as exc:
        return json_response(500, {"error": "Server configuration error", "details": str(exc)})

    method = (event.get("requestContext", {}).get("http", {}).get("method") or event.get("httpMethod", "")).upper()
    if method == "OPTIONS":
        return options_response(settings.cors_allow_origin)

    if method != "GET":
        return json_response(405, {"error": "Method not allowed"}, settings.cors_allow_origin)

    order_id = _query_string(event, "order_id")
    if not order_id:
        return json_response(400, {"error": "order_id is required"}, settings.cors_allow_origin)

    table = get_orders_table(settings.orders_table)
    response = table.get_item(Key={"order_id": order_id})
    item = response.get("Item")

    if not item:
        return json_response(404, {"error": "Order not found"}, settings.cors_allow_origin)

    status = str(item.get("status", ""))
    if status in {"PAID", "CLAIMED"}:
        return json_response(
            200,
            {
                "paid": True,
                "status": status,
                "tx_signature": item.get("tx_signature"),
                "claimed": status == "CLAIMED",
            },
            settings.cors_allow_origin,
        )

    expires_at_raw = str(item.get("expires_at", ""))
    try:
        expires_at = datetime.fromisoformat(expires_at_raw)
    except ValueError:
        expires_at = None

    if expires_at and datetime.now(timezone.utc) > expires_at:
        return json_response(
            200,
            {
                "paid": False,
                "status": "EXPIRED",
            },
            settings.cors_allow_origin,
        )

    try:
        tx_signature = find_matching_payment(
            rpc_url=settings.rpc_url,
            reference=str(item.get("reference", "")),
            destination_wallet=settings.merchant_wallet,
            token_mint=str(item.get("spl_token_mint", settings.spl_token_mint)),
            min_amount_base_units=_as_int(item.get("amount_base_units", item.get("amount_lamports"))),
        )
    except SolanaRpcError as exc:
        return json_response(
            502,
            {
                "error": "Could not verify payment right now",
                "details": str(exc),
            },
            settings.cors_allow_origin,
        )

    if not tx_signature:
        return json_response(
            200,
            {
                "paid": False,
                "status": "PENDING",
            },
            settings.cors_allow_origin,
        )

    paid_at = datetime.now(timezone.utc).isoformat()
    try:
        table.update_item(
            Key={"order_id": order_id},
            UpdateExpression="SET #status = :paid, tx_signature = :tx, paid_at = :paid_at, updated_at = :updated_at",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":paid": "PAID",
                ":tx": tx_signature,
                ":paid_at": paid_at,
                ":updated_at": paid_at,
                ":pending": "PENDING",
            },
            ConditionExpression="#status = :pending",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
            raise

    return json_response(
        200,
        {
            "paid": True,
            "status": "PAID",
            "tx_signature": tx_signature,
            "claimed": False,
        },
        settings.cors_allow_origin,
    )
