"""Loads the Olist CSVs once and exposes deterministic lookup helpers.

All numeric/ID retrieval used by the policy engine goes through this module so
that agents never have to (and never get to) invent facts.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

DATE_COLUMNS_ORDERS = [
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
]


@dataclass
class OrderRecord:
    order_id: str
    customer_id: str
    order_status: str
    order_purchase_timestamp: Optional[pd.Timestamp]
    order_approved_at: Optional[pd.Timestamp]
    order_delivered_carrier_date: Optional[pd.Timestamp]
    order_delivered_customer_date: Optional[pd.Timestamp]
    order_estimated_delivery_date: Optional[pd.Timestamp]


@dataclass
class ItemRecord:
    order_id: str
    order_item_id: int
    product_id: str
    seller_id: str
    shipping_limit_date: Optional[pd.Timestamp]
    price: float
    freight_value: float


@dataclass
class PaymentRecord:
    order_id: str
    payment_sequential: int
    payment_type: str
    payment_installments: int
    payment_value: float


@dataclass
class SellerRecord:
    seller_id: str
    seller_zip_code_prefix: str
    seller_city: str
    seller_state: str


@dataclass
class OrderFacts:
    """Everything the agents need for one claimed_order_id, pre-joined."""

    order: Optional[OrderRecord]
    items: list = field(default_factory=list)
    payments: list = field(default_factory=list)
    sellers: dict = field(default_factory=dict)  # seller_id -> SellerRecord


class DataStore:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self._orders = self._load_orders()
        self._items = self._load_items()
        self._payments = self._load_payments()
        self._sellers = self._load_sellers()

    def _read(self, name: str, **kwargs) -> pd.DataFrame:
        return pd.read_csv(self.data_dir / name, dtype=str, keep_default_na=False, **kwargs)

    def _load_orders(self) -> pd.DataFrame:
        df = self._read("olist_orders_dataset.csv")
        for col in DATE_COLUMNS_ORDERS:
            df[col] = pd.to_datetime(df[col], errors="coerce")
        return df.set_index("order_id", drop=False)

    def _load_items(self) -> pd.DataFrame:
        df = self._read("olist_order_items_dataset.csv")
        df["order_item_id"] = df["order_item_id"].astype(int)
        df["price"] = df["price"].astype(float)
        df["freight_value"] = df["freight_value"].astype(float)
        df["shipping_limit_date"] = pd.to_datetime(df["shipping_limit_date"], errors="coerce")
        return df

    def _load_payments(self) -> pd.DataFrame:
        df = self._read("olist_order_payments_dataset.csv")
        df["payment_sequential"] = df["payment_sequential"].astype(int)
        df["payment_installments"] = df["payment_installments"].astype(int)
        df["payment_value"] = df["payment_value"].astype(float)
        return df

    def _load_sellers(self) -> pd.DataFrame:
        df = self._read("olist_sellers_dataset.csv")
        return df.set_index("seller_id", drop=False)

    def get_order_facts(self, order_id: str) -> OrderFacts:
        order = None
        if order_id in self._orders.index:
            row = self._orders.loc[order_id]
            order = OrderRecord(
                order_id=row["order_id"],
                customer_id=row["customer_id"],
                order_status=row["order_status"],
                order_purchase_timestamp=_none_if_nat(row["order_purchase_timestamp"]),
                order_approved_at=_none_if_nat(row["order_approved_at"]),
                order_delivered_carrier_date=_none_if_nat(row["order_delivered_carrier_date"]),
                order_delivered_customer_date=_none_if_nat(row["order_delivered_customer_date"]),
                order_estimated_delivery_date=_none_if_nat(row["order_estimated_delivery_date"]),
            )

        item_rows = self._items[self._items["order_id"] == order_id].sort_values("order_item_id")
        items = [
            ItemRecord(
                order_id=r["order_id"],
                order_item_id=int(r["order_item_id"]),
                product_id=r["product_id"],
                seller_id=r["seller_id"],
                shipping_limit_date=_none_if_nat(r["shipping_limit_date"]),
                price=float(r["price"]),
                freight_value=float(r["freight_value"]),
            )
            for _, r in item_rows.iterrows()
        ]

        payment_rows = self._payments[self._payments["order_id"] == order_id].sort_values(
            "payment_sequential"
        )
        payments = [
            PaymentRecord(
                order_id=r["order_id"],
                payment_sequential=int(r["payment_sequential"]),
                payment_type=r["payment_type"],
                payment_installments=int(r["payment_installments"]),
                payment_value=float(r["payment_value"]),
            )
            for _, r in payment_rows.iterrows()
        ]

        sellers = {}
        for item in items:
            if item.seller_id in sellers:
                continue
            sellers[item.seller_id] = self.get_seller(item.seller_id)

        return OrderFacts(order=order, items=items, payments=payments, sellers=sellers)

    def get_seller(self, seller_id: str) -> Optional[SellerRecord]:
        if seller_id not in self._sellers.index:
            return None
        row = self._sellers.loc[seller_id]
        return SellerRecord(
            seller_id=row["seller_id"],
            seller_zip_code_prefix=row["seller_zip_code_prefix"],
            seller_city=row["seller_city"],
            seller_state=row["seller_state"],
        )


def _none_if_nat(value):
    if pd.isna(value):
        return None
    return value
