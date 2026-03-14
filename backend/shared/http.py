from __future__ import annotations

import json
from typing import Any


def _cors_headers(origin: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "OPTIONS,GET,POST",
        "Access-Control-Allow-Headers": "Content-Type",
    }


def json_response(status_code: int, body: dict[str, Any], origin: str = "*") -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": _cors_headers(origin),
        "body": json.dumps(body),
    }


def options_response(origin: str = "*") -> dict[str, Any]:
    return {
        "statusCode": 204,
        "headers": _cors_headers(origin),
        "body": "",
    }
