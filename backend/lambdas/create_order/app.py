from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from shared.dynamo import get_orders_table
from shared.http import json_response, options_response
from shared.settings import load_settings
from shared.solana import amount_to_base_units, build_payment_uri, generate_reference


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def lambda_handler(event, _context):
    try:
        settings = load_settings()
    except ValueError as exc:
        return json_response(500, {"error": "Server configuration error", "details": str(exc)})

    method = (event.get("requestContext", {}).get("http", {}).get("method") or event.get("httpMethod", "")).upper()
    if method == "OPTIONS":
        return options_response(settings.cors_allow_origin)

    if method != "POST":
        return json_response(405, {"error": "Method not allowed"}, settings.cors_allow_origin)

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.order_ttl_minutes)

    order_id = str(uuid.uuid4())
    claim_token = secrets.token_urlsafe(24)
    reference = generate_reference()
    amount_base_units = amount_to_base_units(settings.price_usdc, settings.token_decimals)
    if amount_base_units <= 0:
        return json_response(
            500,
            {
                "error": "Server configuration error",
                "details": "PRICE_USDC is too small for TOKEN_DECIMALS",
            },
            settings.cors_allow_origin,
        )

    payment_uri = build_payment_uri(
        recipient_wallet=settings.merchant_wallet,
        amount=settings.price_usdc,
        spl_token_mint=settings.spl_token_mint,
        reference=reference,
        label=settings.product_name,
        message=f"Order {order_id}",
        memo=order_id,
    )

    table = get_orders_table(settings.orders_table)
    table.put_item(
        Item={
            "order_id": order_id,
            "status": "PENDING",
            "claim_token": claim_token,
            "reference": reference,
            "price_usdc": str(settings.price_usdc),
            "amount_base_units": amount_base_units,
            "spl_token_mint": settings.spl_token_mint,
            "product_name": settings.product_name,
            "product_link": settings.product_link,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "ttl_epoch": int(expires_at.timestamp()),
            "updated_at": _utc_now_iso(),
        },
        ConditionExpression="attribute_not_exists(order_id)",
    )

    return json_response(
        200,
        {
            "order_id": order_id,
            "claim_token": claim_token,
            "payment_uri": payment_uri,
            "reference": reference,
            "product_name": settings.product_name,
            "amount_usdc": str(settings.price_usdc),
            "expires_at": expires_at.isoformat(),
        },
        settings.cors_allow_origin,
    )
