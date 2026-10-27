"""
Event hooks — when other modules fire, send the appropriate notification.

Kept lightweight: wraps sends in try/except so a notification failure
NEVER breaks a financial transaction.
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='loans.Loan')
def on_loan_status_change(sender, instance, created, **kwargs):
    """When a loan transitions to ACTIVE, send the disbursement SMS."""
    if created:
        return

    # Check if we already notified for this loan (idempotency)
    from .models import NotificationLog
    already_sent = NotificationLog.objects.filter(
        source_type='Loan',
        source_id=instance.id,
        template_code='LOAN_DISBURSED',
    ).exists()

    if already_sent:
        return

    if instance.status in ('ACTIVE', 'DISBURSED') and instance.disbursed_amount > 0:
        try:
            from .services import NotificationService
            NotificationService.on_loan_disbursed(instance)
        except Exception:
            logger.exception("Failed to send disbursement notification")


@receiver(post_save, sender='payments.Payment')
def on_payment_created(sender, instance, created, **kwargs):
    """When a payment is recorded, send the receipt SMS."""
    if not created:
        return
    try:
        from .services import NotificationService
        NotificationService.on_payment_received(instance)
    except Exception:
        logger.exception("Failed to send payment notification")