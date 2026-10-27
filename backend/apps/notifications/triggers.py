"""Auto-triggers. Failures never break callers."""
import logging

logger = logging.getLogger(__name__)


def _money(value):
    """Format Decimal/None for notification context."""
    if value is None:
        return ''
    from decimal import Decimal
    if isinstance(value, Decimal):
        return '{:,.2f}'.format(value)
    return value


def on_payment_received(payment):
    try:
        from .services import send_from_template
        client = payment.client
        org = payment.organization
        ctx = {
            'amount': _money(payment.amount),
            'loan_number': payment.loan.loan_number if payment.loan else '',
            'payment_number': payment.payment_number,
            'balance_due': _money(payment.loan.balance_due) if payment.loan else '0.00',
            'date': payment.received_at.strftime('%d %b %Y') if payment.received_at else '',
        }
        send_from_template(org=org, client=client, template_key='payment_received',
                           context=ctx, sent_by=payment.received_by)
        if client.email:
            send_from_template(org=org, client=client, template_key='payment_received_email',
                               context=ctx, channels=['EMAIL'], sent_by=payment.received_by)
    except Exception as e:
        logger.warning('payment_received notification failed: %s', e)


def on_loan_disbursed(loan, user=None):
    try:
        from .services import send_from_template
        first_due = ''
        if loan.installments.exists():
            fi = loan.installments.order_by('due_date').first()
            first_due = fi.due_date.strftime('%d %b %Y')
        ctx = {
            'amount': _money(loan.disbursed_amount or loan.amount),
            'loan_number': loan.loan_number,
            'maturity_date': loan.maturity_date.strftime('%d %b %Y') if loan.maturity_date else '',
            'first_due_date': first_due,
        }
        send_from_template(org=loan.organization, client=loan.client,
                           template_key='loan_disbursed', context=ctx, sent_by=user)
        if loan.client.email:
            send_from_template(org=loan.organization, client=loan.client,
                               template_key='loan_disbursed_email', context=ctx,
                               channels=['EMAIL'], sent_by=user)
    except Exception as e:
        logger.warning('loan_disbursed notification failed: %s', e)


def on_kyc_approved(client, user=None):
    try:
        from .services import send_from_template
        send_from_template(org=client.organization, client=client,
                           template_key='kyc_approved', context={}, sent_by=user)
        if client.email:
            send_from_template(org=client.organization, client=client,
                               template_key='kyc_approved_email', context={},
                               channels=['EMAIL'], sent_by=user)
    except Exception as e:
        logger.warning('kyc_approved notification failed: %s', e)


def on_application_approved(application, user=None):
    try:
        from .services import send_from_template
        ctx = {
            'amount': _money(application.requested_amount),
            'application_number': application.application_number,
        }
        send_from_template(org=application.organization, client=application.client,
                           template_key='application_approved', context=ctx, sent_by=user)
        if application.client.email:
            send_from_template(org=application.organization, client=application.client,
                               template_key='application_approved_email', context=ctx,
                               channels=['EMAIL'], sent_by=user)
    except Exception as e:
        logger.warning('application_approved notification failed: %s', e)


def send_due_reminders(org, days_ahead=3, user=None):
    from datetime import timedelta
    from django.utils import timezone
    from apps.loans.models import LoanInstallment
    from .services import send_from_template

    target = timezone.now().date() + timedelta(days=days_ahead)
    qs = LoanInstallment.objects.filter(
        is_paid=False, due_date=target,
        loan__organization=org, loan__is_fully_repaid=False,
    ).select_related('loan', 'loan__client')

    sent = 0
    for inst in qs:
        client = inst.loan.client
        ctx = {
            'amount': _money(inst.total_due - inst.paid_amount),
            'due_date': inst.due_date.strftime('%d %b %Y'),
            'loan_number': inst.loan.loan_number,
            'installment_no': inst.installment_no,
        }
        key = 'due_reminder_%dd' % days_ahead
        sent += len(send_from_template(org, client, key, context=ctx, sent_by=user))
        if client.email:
            sent += len(send_from_template(org, client, 'due_reminder_email',
                                           context=ctx, channels=['EMAIL'], sent_by=user))
    return sent