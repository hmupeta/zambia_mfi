# apps/accounting/importers.py
import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation
from apps.accounting.models import BankAccount, BankStatement, BankStatementLine

def import_statement(bank_account: BankAccount, file_obj, period_from, period_to, user) -> dict:
    content = file_obj.read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(content))
    
    # 1. Create the parent BankStatement
    statement = BankStatement.objects.create(
        organization=bank_account.organization,
        bank_account=bank_account,
        period_from=period_from,
        period_to=period_to,
        opening_balance=Decimal('0'), # Update from CSV if available
        closing_balance=Decimal('0'), # Update from CSV if available
        source='CSV',
        statement_file=file_obj,
        created_by=user,
        status='IN_PROGRESS'
    )

    # 2. Parse lines (Simplified - assumes standard columns)
    lines = []
    for row in reader:
        try:
            stmt_date = datetime.strptime(row['Date'], '%Y-%m-%d').date()
            # Bank convention: debit = out, credit = in
            debit = Decimal(row.get('Debit', '0').replace(',', ''))
            credit = Decimal(row.get('Credit', '0').replace(',', ''))
            
            lines.append(BankStatementLine(
                statement=statement,
                transaction_date=stmt_date,
                description=row.get('Description', '')[:255],
                reference=row.get('Reference', '')[:100],
                debit=debit,
                credit=credit,
                match_status='UNMATCHED'
            ))
        except (ValueError, KeyError, InvalidOperation):
            continue

    BankStatementLine.objects.bulk_create(lines)
    return {'statement_id': statement.id, 'imported': len(lines)}