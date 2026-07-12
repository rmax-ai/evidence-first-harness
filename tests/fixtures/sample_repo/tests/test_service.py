"""Tests for the payment service.

These tests exercise idempotency, authorization, and ledger recording.
The impact analyzer should identify these as affected when service.py changes.
"""

import pytest

from payments.service import AuthorizationError, Ledger, PaymentService


class TestPaymentService:
    def test_process_payment_success(self) -> None:
        ledger = Ledger()
        svc = PaymentService(ledger)
        payment = svc.process_payment(amount=100, currency="USD", idempotency_key="key-1", authorized=True)
        assert payment.status == "completed"
        assert payment.amount == 100
        assert len(ledger.get_entries()) == 1

    def test_idempotency_prevents_duplicate(self) -> None:
        ledger = Ledger()
        svc = PaymentService(ledger)
        first = svc.process_payment(amount=100, currency="USD", idempotency_key="dup-key", authorized=True)
        second = svc.process_payment(amount=100, currency="USD", idempotency_key="dup-key", authorized=True)
        assert first.status == "completed"
        assert second.status == "duplicate"
        assert len(ledger.get_entries()) == 1

    def test_unauthorized_payment_raises(self) -> None:
        ledger = Ledger()
        svc = PaymentService(ledger)
        with pytest.raises(AuthorizationError, match="Unauthorized"):
            svc.process_payment(amount=100, currency="USD", idempotency_key="key-2", authorized=False)

    def test_negative_amount_raises(self) -> None:
        ledger = Ledger()
        svc = PaymentService(ledger)
        with pytest.raises(ValueError, match="positive"):
            svc.process_payment(amount=-50, currency="USD", idempotency_key="key-3", authorized=True)

    def test_validate_currency(self) -> None:
        assert PaymentService.validate_currency("USD") is True
        assert PaymentService.validate_currency("XYZ") is False


class TestLedger:
    def test_record_and_retrieve(self) -> None:
        from payments.service import Payment

        ledger = Ledger()
        payment = Payment(id="pay-1", amount=50, currency="EUR", status="completed")
        ledger.record(payment)
        assert len(ledger.get_entries()) == 1
        assert ledger.get_entry("pay-1") is not None
        assert ledger.get_entry("nonexistent") is None
