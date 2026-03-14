from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import lru_cache

DEFAULT_USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


@dataclass(frozen=True)
class Settings:
    orders_table: str
    merchant_wallet: str
    product_name: str
    product_link: str
    price_usdc: Decimal
    spl_token_mint: str
    token_decimals: int
    rpc_url: str
    order_ttl_minutes: int
    cors_allow_origin: str


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _decimal_env(name: str) -> Decimal:
    raw_value = _required_env(name)
    try:
        value = Decimal(raw_value)
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be a valid decimal number") from exc

    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


@lru_cache
def load_settings() -> Settings:
    try:
        order_ttl_minutes = int(os.getenv("ORDER_TTL_MINUTES", "30"))
    except ValueError as exc:
        raise ValueError("ORDER_TTL_MINUTES must be an integer") from exc

    try:
        token_decimals = int(os.getenv("TOKEN_DECIMALS", "6"))
    except ValueError as exc:
        raise ValueError("TOKEN_DECIMALS must be an integer") from exc

    if order_ttl_minutes <= 0:
        raise ValueError("ORDER_TTL_MINUTES must be greater than zero")
    if token_decimals < 0:
        raise ValueError("TOKEN_DECIMALS must be zero or greater")

    return Settings(
        orders_table=_required_env("ORDERS_TABLE"),
        merchant_wallet=_required_env("MERCHANT_WALLET"),
        product_name=os.getenv("PRODUCT_NAME", "My Game").strip() or "My Game",
        product_link=_required_env("PRODUCT_LINK"),
        price_usdc=_decimal_env("PRICE_USDC"),
        spl_token_mint=os.getenv("SPL_TOKEN_MINT", DEFAULT_USDC_MINT).strip() or DEFAULT_USDC_MINT,
        token_decimals=token_decimals,
        rpc_url=os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com").strip()
        or "https://api.mainnet-beta.solana.com",
        order_ttl_minutes=order_ttl_minutes,
        cors_allow_origin=os.getenv("CORS_ALLOW_ORIGIN", "*").strip() or "*",
    )
