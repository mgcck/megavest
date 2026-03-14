from __future__ import annotations

import secrets
from datetime import datetime, timezone

from botocore.exceptions import ClientError

from shared.dynamo import get_orders_table
from shared.http import json_response, options_response
from shared.settings import load_settings


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
    claim_token = _query_string(event, "claim_token")

    if not order_id or not claim_token:
        return json_response(
            400,
            {"error": "order_id and claim_token are required"},
            settings.cors_allow_origin,
        )

    table = get_orders_table(settings.orders_table)
    response = table.get_item(Key={"order_id": order_id})
    item = response.get("Item")

    if not item:
        return json_response(404, {"error": "Order not found"}, settings.cors_allow_origin)

    stored_token = str(item.get("claim_token", ""))
    if not secrets.compare_digest(stored_token, claim_token):
        return json_response(403, {"error": "Invalid claim token"}, settings.cors_allow_origin)

    status = str(item.get("status", ""))
    if status not in {"PAID", "CLAIMED"}:
        return json_response(402, {"error": "Payment not confirmed yet"}, settings.cors_allow_origin)

    now_iso = datetime.now(timezone.utc).isoformat()

    if status != "CLAIMED":
        try:
            table.update_item(
                Key={"order_id": order_id},
                UpdateExpression="SET #status = :claimed, claimed_at = :claimed_at, updated_at = :updated_at",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":claimed": "CLAIMED",
                    ":paid": "PAID",
                    ":claimed_at": now_iso,
                    ":updated_at": now_iso,
                },
                ConditionExpression="#status = :paid",
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise

    return json_response(
        200,
        {
            "order_id": order_id,
            "download_url": item.get("product_link") or settings.product_link,
            "status": "CLAIMED",
        },
        settings.cors_allow_origin,
    )
