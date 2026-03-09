"""
Picklist upload: parse CSV or OCR text and apply rows to create/update DeliveryOrders.
"""
import csv
import re
from io import StringIO
from datetime import datetime
from pathlib import Path

# Column header aliases: canonical name -> accepted names
PICKLIST_CSV_COLUMNS = {
    "invoice_no": [
        "Invoice No",
        "Invoice No.",
        "Bill Number",
        "Proxy Number",
        "invoice_no",
        "invoice no",
    ],
    "delivery_person": [
        "Delivery Person",
        "DeliveryPerson",
        "Delivery_User",
        "Delivery User",
        "delivery_person",
        "delivery person",
    ],
    "delivery_date": [
        "Delivery Date",
        "delivery_date",
        "delivery date",
        "Date",
    ],
    "delivery_address": [
        "Delivery Address",
        "Address",
        "delivery_address",
        "delivery address",
    ],
    "salesman": [
        "Salesman",
        "Salesman Name",
        "salesman",
        "salesman name",
    ],
}


def _normalize_header(h):
    if h is None:
        return ""
    return str(h).strip()


def _find_column_index(headers, canonical_key):
    names = PICKLIST_CSV_COLUMNS.get(canonical_key, [])
    normalized_headers = [_normalize_header(h) for h in headers]
    for alias in names:
        alias_clean = alias.strip().lower()
        for i, h in enumerate(normalized_headers):
            if h.lower() == alias_clean:
                return i
    return -1


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


def parse_picklist_csv(filepath):
    """
    Parse a picklist CSV file. Returns list of dicts with keys:
    invoice_no, delivery_person, delivery_date, delivery_address, salesman (optional).
    Raises ValueError if required columns are missing or file cannot be read.
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

    headers = csv_data[0]
    data_rows = csv_data[1:]
    idx_inv = _find_column_index(headers, "invoice_no")
    idx_person = _find_column_index(headers, "delivery_person")
    idx_date = _find_column_index(headers, "delivery_date")
    idx_address = _find_column_index(headers, "delivery_address")
    idx_salesman = _find_column_index(headers, "salesman")

    missing = []
    if idx_inv < 0:
        missing.append("Invoice No")
    if idx_person < 0:
        missing.append("Delivery Person")
    if idx_date < 0:
        missing.append("Delivery Date")
    if idx_address < 0:
        missing.append("Delivery Address")
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(missing))

    rows = []
    for row in data_rows:
        if len(row) <= max(idx_inv, idx_person, idx_date, idx_address):
            continue
        invoice_no = _normalize_header(row[idx_inv]) if idx_inv < len(row) else ""
        delivery_person = _normalize_header(row[idx_person]) if idx_person < len(row) else ""
        delivery_date_raw = _normalize_header(row[idx_date]) if idx_date < len(row) else ""
        delivery_address = _normalize_header(row[idx_address]) if idx_address < len(row) else ""
        salesman = _normalize_header(row[idx_salesman]) if idx_salesman >= 0 and idx_salesman < len(row) else None
        if not invoice_no and not delivery_person and not delivery_address:
            continue
        delivery_date = _parse_date(delivery_date_raw)
        rows.append({
            "invoice_no": invoice_no,
            "delivery_person": delivery_person,
            "delivery_date": delivery_date,
            "delivery_address": delivery_address or "",
            "salesman": salesman if salesman else None,
        })
    return rows


def parse_picklist_ocr_text(ocr_text):
    """
    Parse OCR-extracted text into delivery rows (best-effort).
    Looks for patterns like "Delivery Person: X", "Invoice No: Y", "Date: Z", "Address: ..."
    or table-like lines. Returns list of dicts same shape as parse_picklist_csv.
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


def apply_picklist_rows(tenant_id, rows):
    """
    Create or update DeliveryOrders from parsed rows.
    Uses models.DeliveryOrder, Bill, ProxyBill, User and extensions.db (imported inside to avoid circular import).
    Returns dict: created (int), updated (int), skipped (list of (row_dict, reason_string)).
    """
    from models import DeliveryOrder, Bill, ProxyBill, User
    from extensions import db
    from sqlalchemy import and_

    created = 0
    updated = 0
    skipped = []

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

        bill = Bill.query.filter_by(tenant_id=tenant_id, bill_number=invoice_no).first()
        proxy_bill = None
        if not bill:
            proxy_bill = ProxyBill.query.filter_by(tenant_id=tenant_id, proxy_number=invoice_no).first()
        if not bill and not proxy_bill:
            skipped.append((row, f"No Bill or ProxyBill found for Invoice No '{invoice_no}'"))
            continue

        delivery_user = User.query.filter(
            User.tenant_id == tenant_id,
            User.username == delivery_person,
            User.role.in_(["DELIVERY", "SALESMAN"]),
            User.is_active == True,
        ).first()
        if not delivery_user:
            skipped.append((row, f"No active user (DELIVERY/SALESMAN) found for '{delivery_person}'"))
            continue

        salesman_user = None
        if salesman_name:
            salesman_user = User.query.filter(
                User.tenant_id == tenant_id,
                User.username == salesman_name,
                User.role.in_(["DELIVERY", "SALESMAN"]),
                User.is_active == True,
            ).first()

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
