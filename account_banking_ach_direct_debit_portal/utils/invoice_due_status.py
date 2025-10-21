from datetime import date


def get_invoice_due_status(invoices):
    """Return dict {invoice_id: status_text}."""
    if not invoices:
        return {}
    today = date.today()
    out = {}
    for inv in invoices:
        due = inv.invoice_date_due
        if not due:
            out[inv.id] = "No due date"
            continue
        days = (due - today).days
        if days < 0:
            out[inv.id] = f"Due {abs(days)} days ago"
        elif days == 0:
            out[inv.id] = "Due today"
        else:
            out[inv.id] = f"Due in {days} days"
    return out
