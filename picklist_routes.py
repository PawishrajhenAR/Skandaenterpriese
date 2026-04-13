"""
Picklist routes: list and detail views built from DeliveryOrder + Bill/ProxyBill.
One Picklist = one DeliveryOrder (delivery person + date + linked bill/proxy bill).
"""
from decimal import Decimal
from pathlib import Path
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort, Response, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from sqlalchemy import func, desc
from datetime import datetime

from export_utils import generate_picklist_pdf
from picklist_upload_utils import (
    parse_picklist_csv,
    parse_picklist_ocr_text,
    apply_picklist_rows,
    apply_picklist_csv_import_rows,
)

from models import (
    DeliveryOrder,
    Bill,
    BillItem,
    ProxyBill,
    ProxyBillItem,
    Vendor,
    Tenant,
    CreditEntry,
    PicklistImportRow,
)
from extensions import db
from auth_routes import permission_required
from audit import log_action

picklist_bp = Blueprint("picklist", __name__)


def get_default_tenant():
    return Tenant.query.filter_by(code="skanda").first()


def build_picklist_payload(delivery):
    """
    Build picklist payload from a DeliveryOrder.
    Returns dict: picklist_number, delivery_person, delivery_date, items, grand_total,
                  invoice_rows, salesman_summary.
    """
    if delivery.bill_id:
        bill_or_proxy = delivery.bill
        is_proxy = False
    elif delivery.proxy_bill_id:
        bill_or_proxy = delivery.proxy_bill
        is_proxy = True
    else:
        return None

    if not bill_or_proxy:
        return None

    vendor = bill_or_proxy.vendor

    # Items: from BillItem or ProxyBillItem
    if is_proxy:
        line_items = bill_or_proxy.items
        inv_no = bill_or_proxy.proxy_number
        inv_date = bill_or_proxy.created_at.date() if bill_or_proxy.created_at else None
        bill_id_for_credit = None
        proxy_bill_id_for_credit = bill_or_proxy.id
    else:
        line_items = bill_or_proxy.items
        inv_no = bill_or_proxy.bill_number
        inv_date = bill_or_proxy.bill_date
        bill_id_for_credit = bill_or_proxy.id
        proxy_bill_id_for_credit = None

    items = []
    for it in line_items:
        items.append({
            "cat": "",
            "item_name": it.description,
            "mrp": float(it.unit_price) if it.unit_price else 0,
            "value": float(it.amount) if it.amount else 0,
            "b_uom": "",
            "cfc": "",
            "pac": "",
            "fr_qty": float(it.quantity) if it.quantity else 0,
        })

    grand_total = float(bill_or_proxy.amount_total) if bill_or_proxy.amount_total else 0

    # RecAmt: sum INCOMING credits for this bill/proxy
    rec_amt_q = db.session.query(func.coalesce(func.sum(CreditEntry.amount), 0)).filter(
        CreditEntry.direction == "INCOMING"
    )
    if bill_id_for_credit is not None:
        rec_amt_q = rec_amt_q.filter(CreditEntry.bill_id == bill_id_for_credit)
    else:
        rec_amt_q = rec_amt_q.filter(CreditEntry.proxy_bill_id == proxy_bill_id_for_credit)
    rec_amt = float(rec_amt_q.scalar() or 0)

    invoice_rows = [
        {
            "invoice_no": inv_no,
            "inv_date": inv_date.strftime("%Y-%m-%d") if inv_date else "",
            "customer_code": vendor.customer_code or "",
            "customer_name": vendor.name or "",
            "beat": "",
            "p_mode": "",
            "inv_val": grand_total,
            "rec_amt": rec_amt,
        }
    ]

    salesman_name = "—"
    if getattr(delivery, "salesman_id", None) and delivery.salesman:
        salesman_name = delivery.salesman.username
    salesman_summary = {
        "salesman_name": salesman_name,
        "invoice_count": 1,
        "net_amount": grand_total,
        "received_amount": rec_amt,
    }

    return {
        "picklist_number": f"PL-{delivery.id}",
        "delivery_person": delivery.delivery_user.username if delivery.delivery_user else "",
        "delivery_date": delivery.delivery_date.strftime("%Y-%m-%d") if delivery.delivery_date else "",
        "items": items,
        "grand_total": grand_total,
        "invoice_rows": invoice_rows,
        "salesman_summary": salesman_summary,
        "delivery_id": delivery.id,
    }


@picklist_bp.route("/")
@login_required
@permission_required("view_deliveries")
def list():
    tenant = get_default_tenant()
    if not tenant:
        flash("Tenant not found.", "danger")
        return redirect(url_for("main.dashboard"))

    import_rows = (
        PicklistImportRow.query.filter_by(tenant_id=tenant.id)
        .order_by(desc(PicklistImportRow.delivery_date).nulls_last(), PicklistImportRow.id.desc())
        .all()
    )

    # Delivery orders linked to bills (e.g. OCR / legacy flow)
    if current_user.role == "DELIVERY":
        query = DeliveryOrder.query.filter_by(
            tenant_id=tenant.id,
            delivery_user_id=current_user.id,
        )
    else:
        query = DeliveryOrder.query.filter_by(tenant_id=tenant.id)

    query = query.filter(
        (DeliveryOrder.bill_id.isnot(None)) | (DeliveryOrder.proxy_bill_id.isnot(None))
    )
    deliveries = query.order_by(DeliveryOrder.delivery_date.desc()).all()

    return render_template(
        "picklists/list.html",
        import_rows=import_rows,
        deliveries=deliveries,
    )


def _allowed_picklist_file(filename, allowed_extensions):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions


@picklist_bp.route("/upload", methods=["GET", "POST"])
@login_required
@permission_required("create_delivery")
def upload():
    tenant = get_default_tenant()
    if not tenant:
        flash("Tenant not found.", "danger")
        return redirect(url_for("main.dashboard"))

    if request.method == "GET":
        ocr_available = True
        try:
            from ocr_utils import run_ocr
        except Exception:
            ocr_available = False
        return render_template(
            "picklists/upload.html",
            ocr_available=ocr_available,
            upload_result=None,
        )

    upload_type = request.form.get("upload_type", "csv").strip().lower()
    if "file" not in request.files:
        flash("No file selected.", "danger")
        return redirect(url_for("picklist.upload"))

    file = request.files["file"]
    if not file or not file.filename:
        flash("No file selected.", "danger")
        return redirect(url_for("picklist.upload"))

    upload_folder = Path(current_app.config["UPLOAD_FOLDER"])
    upload_folder.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = secure_filename(file.filename) or "upload"
    filepath = upload_folder / f"picklist_{timestamp}_{safe_name}"

    if upload_type == "csv":
        if not _allowed_picklist_file(file.filename, {"csv"}):
            flash("Please upload a CSV file (.csv).", "danger")
            return redirect(url_for("picklist.upload"))
        try:
            file.save(str(filepath))
            rows = parse_picklist_csv(filepath)
        except ValueError as e:
            flash(str(e), "danger")
            return redirect(url_for("picklist.upload"))
        except Exception as e:
            current_app.logger.exception("Picklist CSV parse error")
            flash(f"Failed to parse CSV: {e}", "danger")
            return redirect(url_for("picklist.upload"))
    else:
        if not _allowed_picklist_file(file.filename, {"png", "jpg", "jpeg", "pdf"}):
            flash("Please upload an image (PNG, JPG, JPEG) or PDF.", "danger")
            return redirect(url_for("picklist.upload"))
        try:
            from ocr_utils import run_ocr
        except Exception:
            flash("OCR is not available in this environment. Please use CSV upload.", "danger")
            return redirect(url_for("picklist.upload"))
        file.save(str(filepath))
        ocr_text = run_ocr(str(filepath))
        if isinstance(ocr_text, str) and (
            ocr_text.startswith("OCR error:") or ocr_text.startswith("Error:") or "not installed" in ocr_text.lower()
        ):
            flash(f"OCR failed: {ocr_text}", "danger")
            return redirect(url_for("picklist.upload"))
        rows = parse_picklist_ocr_text(ocr_text)
        if not rows:
            flash("Could not extract any delivery rows from the image. Try CSV upload or check image.", "warning")
            return redirect(url_for("picklist.upload"))

    try:
        if upload_type == "csv":
            result = apply_picklist_csv_import_rows(tenant.id, rows)
        else:
            result = apply_picklist_rows(tenant.id, rows)
        db.session.commit()
        log_action(current_user, "UPLOAD_PICKLIST", "PICKLIST", 0)
        created = result["created"]
        updated = result["updated"]
        skipped_list = result["skipped"]
        msg = f"Picklist upload complete: {created} created, {updated} updated, {len(skipped_list)} skipped."
        flash(msg, "success")
        if upload_type != "csv" and skipped_list and created == 0 and updated == 0:
            missing_bill_skips = sum(
                1
                for _row, reason in skipped_list
                if reason.startswith("No Bill or ProxyBill found for Invoice No")
            )
            if missing_bill_skips == len(skipped_list):
                flash(
                    "No matching bills/proxy bills found for uploaded invoices. "
                    "Import or create bills first, then upload picklist again.",
                    "warning",
                )
        if skipped_list and len(skipped_list) <= 20:
            for _row, reason in skipped_list[:10]:
                flash(f"Skipped: {reason}", "info")
            if len(skipped_list) > 10:
                flash(f"... and {len(skipped_list) - 10} more skipped.", "info")
        elif len(skipped_list) > 20:
            flash(f"First skip reason: {skipped_list[0][1]}", "info")
        return render_template(
            "picklists/upload.html",
            ocr_available=True,
            upload_result=result,
        )
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Picklist apply error")
        flash(f"Failed to apply picklist: {e}", "danger")
        return redirect(url_for("picklist.upload"))


@picklist_bp.route("/import/<int:id>")
@login_required
@permission_required("view_deliveries")
def import_detail(id):
    tenant = get_default_tenant()
    if not tenant:
        flash("Tenant not found.", "danger")
        return redirect(url_for("main.dashboard"))

    row = PicklistImportRow.query.filter_by(tenant_id=tenant.id, id=id).first()
    if not row:
        abort(404)
    return render_template("picklists/import_detail.html", row=row)


@picklist_bp.route("/<int:id>")
@login_required
@permission_required("view_deliveries")
def detail(id):
    tenant = get_default_tenant()
    if not tenant:
        flash("Tenant not found.", "danger")
        return redirect(url_for("main.dashboard"))

    delivery = DeliveryOrder.query.filter_by(tenant_id=tenant.id, id=id).first()
    if not delivery:
        abort(404)

    payload = build_picklist_payload(delivery)
    if not payload:
        flash("This delivery has no linked bill or proxy bill.", "warning")
        return redirect(url_for("picklist.list"))

    return render_template("picklists/detail.html", **payload)


@picklist_bp.route("/<int:id>/json")
@login_required
@permission_required("view_deliveries")
def detail_json(id):
    tenant = get_default_tenant()
    if not tenant:
        return jsonify({"error": "Tenant not found"}), 500

    delivery = DeliveryOrder.query.filter_by(tenant_id=tenant.id, id=id).first()
    if not delivery:
        return jsonify({"error": "Not found"}), 404

    payload = build_picklist_payload(delivery)
    if not payload:
        return jsonify({"error": "No linked bill or proxy bill"}), 404

    # Serialize for JSON (dates and decimals already as strings/float)
    return jsonify(payload)


@picklist_bp.route("/<int:id>/pdf")
@login_required
@permission_required("view_deliveries")
def detail_pdf(id):
    tenant = get_default_tenant()
    if not tenant:
        return jsonify({"error": "Tenant not found"}), 500

    delivery = DeliveryOrder.query.filter_by(tenant_id=tenant.id, id=id).first()
    if not delivery:
        abort(404)

    payload = build_picklist_payload(delivery)
    if not payload:
        abort(404)

    pdf_buffer = generate_picklist_pdf(payload)
    filename = f"picklist_{payload['picklist_number']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(
        pdf_buffer.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
