"""
Picklist upload: CSV invoice-table imports → picklist_import_rows; OCR → DeliveryOrders (legacy).
"""
import csv
import re
from decimal import Decimal, InvalidOperation
from datetime import datetime
from pathlib import Path

# --- CSV invoice-table format (distributor export) ---
# Headers: Invoice No, Inv Date, Customer, Customer Name, Beat, P-Mode, InvVal, RecAmt
PICKLIST_IMPORT_CSV_KEYS = (
    "invoice_no",
    "inv_date",
    "customer_code",
    "customer_name",
    "beat",
    "p_mode",
    "inv_val",
    "rec_amt",
)

PICKLIST_IMPORT_ALIASES = {
    "invoice_no": ("invoice no", "invoice no."),
    "inv_date": ("inv date", "invoice date"),
    "customer_code": ("customer", "customer code"),
    "customer_name": ("customer name",),
    "beat": ("beat",),
    "p_mode": ("p mode", "p-mode", "payment mode", "pmode"),
    "inv_val": ("invval", "inv val", "invoice value", "inv value"),
    "rec_amt": ("recamt", "rec amt", "received amount", "rec amount"),
}


def _normalize_header(h):
    if h is None:
        return ""
    return str(h).strip()


def _normalize_token(s):
    """Normalize labels for robust header matching (case/space/punctuation-insensitive)."""
    text = _normalize_header(s).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _find_import_column_indices(header_row):
    """Map canonical keys to column indices. Returns dict or None if incomplete."""
    normalized_headers = [_normalize_token(h) for h in header_row]
    indices = {}
    for key in PICKLIST_IMPORT_CSV_KEYS:
        aliases = PICKLIST_IMPORT_ALIASES.get(key, ())
        found = -1
        for alias in aliases:
            ac = _normalize_token(alias)
            for i, h in enumerate(normalized_headers):
                if h == ac:
                    found = i
                    break
            if found >= 0:
                break
        if found < 0:
            return None
        indices[key] = found
    # Disambiguate: "customer" must not match "customer name" column — already separate aliases
    return indices


def _score_import_header_row(header_row):
    """How many import columns are recognized (for auto-detecting header line)."""
    idx = _find_import_column_indices(header_row)
    if idx:
        return len(idx)
    return 0


def _parse_date(s):
    """Parse date string; return date or None."""
    if not s or not str(s).strip():
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_decimal(s):
    if s is None:
        return None
    t = str(s).strip()
    if not t:
        return None
    t = t.replace(",", "")
    try:
        return Decimal(t)
    except (InvalidOperation, ValueError):
        return None


def _should_skip_import_row(invoice_raw):
    """Skip summary / separator / header noise rows."""
    inv = _normalize_header(invoice_raw)
    if not inv:
        return True
    key = _normalize_token(inv)
    if not key:
        return True
    if key in ("invoice no", "inv date", "customer name", "grand total", "picklist", "page"):
        return True
    if "grandtotal" in key.replace(" ", "") or key.startswith("grand total"):
        return True
    if "salesman" in key:
        return True
    if re.fullmatch(r"[-_\s]+", inv):
        return True
    if re.match(r"^-{3,}$", inv.strip()):
        return True
    return False


def parse_picklist_csv(filepath):
    """
    Parse picklist CSV (invoice table export).

    Required header columns (labels matched case-insensitively, trimmed):
    Invoice No, Inv Date, Customer, Customer Name, Beat, P-Mode, InvVal, RecAmt

    Returns list of dicts:
      invoice_no, delivery_date, customer_code, customer_name, beat,
      amount, received_amount, payment_mode
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise ValueError("File not found")

    csv_data = None
    encodings = ["utf-8-sig", "utf-8", "latin-1", "cp1252", "iso-8859-1"]
    for encoding in encodings:
        try:
            with open(filepath, "r", encoding=encoding, newline="") as f:
                reader = csv.reader(f, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL)
                csv_data = list(reader)
            if csv_data:
                break
        except (UnicodeDecodeError, Exception):
            continue

    if not csv_data or len(csv_data) < 2:
        raise ValueError("CSV file is empty or has no data rows")

    best_header_idx = -1
    best_score = -1
    best_indices = None
    for row_idx, row in enumerate(csv_data):
        score = _score_import_header_row(row)
        if score > best_score:
            best_score = score
            best_header_idx = row_idx
            best_indices = _find_import_column_indices(row)

    if not best_indices or best_score < len(PICKLIST_IMPORT_CSV_KEYS):
        raise ValueError(
            "Missing required columns. Expected: Invoice No, Inv Date, Customer, Customer Name, "
            "Beat, P-Mode, InvVal, RecAmt"
        )

    idx = best_indices
    data_rows = csv_data[best_header_idx + 1 :]

    rows_out = []
    for row in data_rows:
        def cell(k):
            i = idx[k]
            return _normalize_header(row[i]) if i < len(row) else ""

        invoice_no = cell("invoice_no")
        if _should_skip_import_row(invoice_no):
            continue

        delivery_date = _parse_date(cell("inv_date"))
        if not delivery_date:
            if not any(_normalize_header(c) for c in row):
                continue
            rows_out.append({
                "invoice_no": invoice_no,
                "delivery_date": None,
                "customer_code": cell("customer_code") or None,
                "customer_name": cell("customer_name") or "",
                "beat": cell("beat") or "",
                "amount": _parse_decimal(cell("inv_val")),
                "received_amount": _parse_decimal(cell("rec_amt")),
                "payment_mode": cell("p_mode") or "",
            })
            continue

        rows_out.append({
            "invoice_no": invoice_no,
            "delivery_date": delivery_date,
            "customer_code": cell("customer_code") or None,
            "customer_name": cell("customer_name") or "",
            "beat": cell("beat") or "",
            "amount": _parse_decimal(cell("inv_val")),
            "received_amount": _parse_decimal(cell("rec_amt")),
            "payment_mode": (cell("p_mode") or "").strip(),
        })
    return rows_out


def parse_picklist_ocr_text(ocr_text):
    """
    Parse OCR-extracted text into delivery rows (best-effort).
    Looks for patterns like "Delivery Person: X", "Invoice No: Y", "Date: Z", "Address: ..."
    or table-like lines. Returns list of dicts for apply_picklist_rows (DeliveryOrder flow).
    """
    if not ocr_text or not str(ocr_text).strip():
        return []

    lines = [ln.strip() for ln in str(ocr_text).splitlines() if ln.strip()]
    rows = []
    current = {}

    label_patterns = {
        "invoice_no": re.compile(r"^(?:invoice\s*no\.?|bill\s*number|proxy\s*number)\s*[:\-]?\s*(.+)$", re.I),
        "delivery_person": re.compile(r"^(?:delivery\s*person|delivery\s*user)\s*[:\-]?\s*(.+)$", re.I),
        "delivery_date": re.compile(r"^(?:delivery\s*)?date\s*[:\-]?\s*(.+)$", re.I),
        "delivery_address": re.compile(r"^(?:delivery\s*)?address\s*[:\-]?\s*(.+)$", re.I),
        "salesman": re.compile(r"^salesman\s*(?:name)?\s*[:\-]?\s*(.+)$", re.I),
    }

    def flush_current():
        if current.get("invoice_no") or current.get("delivery_person") or current.get("delivery_address"):
            rows.append({
                "invoice_no": current.get("invoice_no", "").strip(),
                "delivery_person": current.get("delivery_person", "").strip(),
                "delivery_date": _parse_date(current.get("delivery_date", "")) if current.get("delivery_date") else None,
                "delivery_address": (current.get("delivery_address") or "").strip(),
                "salesman": (current.get("salesman") or "").strip() or None,
            })
        current.clear()

    for line in lines:
        matched = False
        for key, pat in label_patterns.items():
            m = pat.match(line)
            if m:
                current[key] = m.group(1).strip()
                matched = True
                break
        if not matched and current:
            if "address" in line.lower() or len(line) > 30:
                current["delivery_address"] = (current.get("delivery_address") or "") + " " + line
            else:
                flush_current()

    flush_current()
    return rows


def apply_picklist_csv_import_rows(tenant_id, rows):
    """
    Insert or update PicklistImportRow by (tenant_id, invoice_no).
    Returns dict: created, updated, skipped (list of (row_dict, reason)).
    """
    from models import PicklistImportRow
    from extensions import db

    created = 0
    updated = 0
    skipped = []

    for row in rows:
        invoice_no = (row.get("invoice_no") or "").strip()
        if not invoice_no:
            skipped.append((row, "Invoice No is empty"))
            continue
        delivery_date = row.get("delivery_date")
        if not delivery_date:
            skipped.append((row, "Delivery date (Inv Date) is missing or invalid"))
            continue

        existing = PicklistImportRow.query.filter_by(
            tenant_id=tenant_id,
            invoice_no=invoice_no,
        ).first()

        if existing:
            existing.delivery_date = delivery_date
            existing.customer_code = row.get("customer_code")
            existing.customer_name = row.get("customer_name") or None
            existing.beat = row.get("beat") or None
            existing.amount = row.get("amount")
            existing.received_amount = row.get("received_amount")
            existing.payment_mode = row.get("payment_mode") or None
            updated += 1
        else:
            rec = PicklistImportRow(
                tenant_id=tenant_id,
                invoice_no=invoice_no,
                delivery_date=delivery_date,
                customer_code=row.get("customer_code"),
                customer_name=row.get("customer_name") or None,
                beat=row.get("beat") or None,
                amount=row.get("amount"),
                received_amount=row.get("received_amount"),
                payment_mode=row.get("payment_mode") or None,
                status="pending",
            )
            db.session.add(rec)
            created += 1

    return {"created": created, "updated": updated, "skipped": skipped}


def apply_picklist_rows(tenant_id, rows):
    """
    Create or update DeliveryOrders from OCR-parsed rows (legacy).
    Uses models.DeliveryOrder, Bill, ProxyBill, User and extensions.db.
    Returns dict: created (int), updated (int), skipped (list of (row_dict, reason_string)).
    """
    from models import DeliveryOrder, Bill, ProxyBill, User
    from extensions import db

    def _normalize_lookup_key(value):
        text = (value or "").strip().lower()
        text = re.sub(r"[^a-z0-9/]+", "", text)
        return text

    created = 0
    updated = 0
    skipped = []

    bills = Bill.query.filter_by(tenant_id=tenant_id).all()
    proxy_bills = ProxyBill.query.filter_by(tenant_id=tenant_id).all()
    users = User.query.filter(
        User.tenant_id == tenant_id,
        User.role.in_(["DELIVERY", "SALESMAN"]),
        User.is_active == True,
    ).all()

    bill_lookup = {_normalize_lookup_key(b.bill_number): b for b in bills if b.bill_number}
    proxy_lookup = {_normalize_lookup_key(p.proxy_number): p for p in proxy_bills if p.proxy_number}
    user_lookup = {_normalize_lookup_key(u.username): u for u in users if u.username}
    default_delivery_user = next((u for u in users if u.role == "DELIVERY"), None)

    for row in rows:
        invoice_no = (row.get("invoice_no") or "").strip()
        delivery_person = (row.get("delivery_person") or "").strip()
        delivery_date = row.get("delivery_date")
        delivery_address = (row.get("delivery_address") or "").strip()
        salesman_name = (row.get("salesman") or "").strip() or None

        if not invoice_no:
            skipped.append((row, "Invoice No is empty"))
            continue
        if not delivery_person:
            skipped.append((row, "Delivery Person is empty"))
            continue
        if not delivery_date:
            skipped.append((row, "Delivery Date is missing or invalid"))
            continue
        if not delivery_address:
            skipped.append((row, "Delivery Address is empty"))
            continue

        normalized_invoice = _normalize_lookup_key(invoice_no)
        bill = bill_lookup.get(normalized_invoice)
        proxy_bill = None
        if not bill:
            proxy_bill = proxy_lookup.get(normalized_invoice)
        if not bill and not proxy_bill:
            skipped.append((row, f"No Bill or ProxyBill found for Invoice No '{invoice_no}'"))
            continue

        delivery_user = user_lookup.get(_normalize_lookup_key(delivery_person))
        if not delivery_user and _normalize_lookup_key(delivery_person) in {
            "defaultdeliveryrepresentative",
            "defaultdeliveryperson",
            "deliveryrepresentative",
            "deliveryperson",
        }:
            delivery_user = default_delivery_user
        if not delivery_user:
            skipped.append((row, f"No active user (DELIVERY/SALESMAN) found for '{delivery_person}'"))
            continue

        salesman_user = None
        if salesman_name:
            salesman_user = user_lookup.get(_normalize_lookup_key(salesman_name))

        bill_id = bill.id if bill else None
        proxy_bill_id = proxy_bill.id if proxy_bill else None

        if bill_id:
            existing = DeliveryOrder.query.filter_by(
                tenant_id=tenant_id,
                bill_id=bill_id,
                delivery_user_id=delivery_user.id,
                delivery_date=delivery_date,
            ).first()
        else:
            existing = DeliveryOrder.query.filter_by(
                tenant_id=tenant_id,
                proxy_bill_id=proxy_bill_id,
                delivery_user_id=delivery_user.id,
                delivery_date=delivery_date,
            ).first()

        if existing:
            existing.delivery_address = delivery_address
            if salesman_user is not None:
                existing.salesman_id = salesman_user.id
            else:
                existing.salesman_id = None
            updated += 1
        else:
            delivery = DeliveryOrder(
                tenant_id=tenant_id,
                bill_id=bill_id,
                proxy_bill_id=proxy_bill_id,
                delivery_user_id=delivery_user.id,
                delivery_address=delivery_address,
                delivery_date=delivery_date,
                status="PENDING",
                salesman_id=salesman_user.id if salesman_user else None,
            )
            db.session.add(delivery)
            created += 1

    return {"created": created, "updated": updated, "skipped": skipped}
