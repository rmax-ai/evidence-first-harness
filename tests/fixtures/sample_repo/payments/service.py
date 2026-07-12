"""Sample payment service for impact analysis testing.

Minimal but realistic: REST API, idempotency, auth, ledger.
Used by test_impact_analyzer.py to verify AST parsing, dependency graph, and test selection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import uuid4


class AuthorizationError(Exception):
    """Raised when a caller lacks required permissions."""


@dataclass(frozen=True)
class Payment:
    id: str
    amount: int
    currency: str
    status: str


class PaymentService:
    """Core payment processing with idempotency key support."""

    def __init__(self, ledger: "Ledger") -> None:
        self._ledger = ledger
        self._processed: set[str] = set()

    def process_payment(
        self,
        amount: int,
        currency: str,
        idempotency_key: str,
        authorized: bool = False,
    ) -> Payment:
        if not authorized:
            raise AuthorizationError("Unauthorized payment")

        if idempotency_key in self._processed:
            return Payment(id=idempotency_key, amount=amount, currency=currency, status="duplicate")

        if amount <= 0:
            raise ValueError("Amount must be positive")

        payment = Payment(
            id=str(uuid4()),
            amount=amount,
            currency=currency,
            status="completed",
        )
        self._processed.add(idempotency_key)
        self._ledger.record(payment)
        return payment

    @staticmethod
    def validate_currency(currency: str) -> bool:
        return currency in {"USD", "EUR", "GBP"}


class Ledger:
    """Append-only ledger for audit trail."""

    def __init__(self) -> None:
        self._entries: list[Payment] = []

    def record(self, payment: Payment) -> None:
        self._entries.append(payment)

    def get_entries(self) -> list[Payment]:
        return list(self._entries)

    def get_entry(self, payment_id: str) -> Optional[Payment]:
        for entry in self._entries:
            if entry.id == payment_id:
                return entry
        return None
