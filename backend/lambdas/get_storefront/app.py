from __future__ import annotations

from decimal import Decimal

from shared.http import json_response, options_response
from shared.settings import load_settings


def _decimal_to_string(value: Decimal) -> str:
    normalized = value.normalize()
    as_text = format(normalized, "f")
    if "." in as_text:
        as_text = as_text.rstrip("0").rstrip(".")
    return as_text or "0"


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

    return json_response(
        200,
        {
            "productName": settings.product_name,
            "priceUsdc": _decimal_to_string(settings.price_usdc),
        },
        settings.cors_allow_origin,
    )
