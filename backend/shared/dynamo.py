from __future__ import annotations

from functools import lru_cache

import boto3


@lru_cache
def get_orders_table(table_name: str):
    dynamodb = boto3.resource("dynamodb")
    return dynamodb.Table(table_name)
