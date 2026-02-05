"""
API routes - JSON-only endpoints for frontend consumption.
All business logic reused from existing route modules.
"""
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user, login_user, logout_user
from functools import wraps
from models import (
    User, Tenant, Vendor, Bill, BillItem, CreditEntry, ProxyBill, ProxyBillItem,
    DeliveryOrder, OCRJob, Permission, RolePermission
)
from extensions import db
from sqlalchemy import func
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from werkzeug.utils import secure_filename

from api_serializers import (
    vendor_to_dict, bill_to_dict, credit_to_dict, delivery_to_dict,
    proxy_bill_to_dict, user_to_dict, ocr_job_to_dict, serialize_model
)

api_bp = Blueprint('api', __name__, url_prefix='/api')


def api_permission_required(permission_code):
    """API version of permission_required - returns JSON on failure."""
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated(*args, **kwargs):
            if not current_user.has_permission(permission_code):
                return jsonify({'error': 'Permission denied'}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


def get_default_tenant():
    return Tenant.query.filter_by(code='skanda').first()


# --- Auth ---
@api_bp.route('/auth/login', methods=['POST'])
def auth_login():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password) or not user.is_active:
        return jsonify({'error': 'Invalid username or password'}), 401
    login_user(user)
    return jsonify({
        'success': True,
        'user': user_to_dict(user),
    })


@api_bp.route('/auth/logout', methods=['POST'])
@login_required
def auth_logout():
    logout_user()
    return jsonify({'success': True})


@api_bp.route('/auth/me')
@login_required
def auth_me():
    perms = []
    if current_user.role != 'ADMIN':
        for p in Permission.query.all():
            rp = RolePermission.query.filter_by(
                role=current_user.role, permission_id=p.id, granted=True
            ).first()
            if rp:
                perms.append(p.code)
    else:
        perms = [p.code for p in Permission.query.all()]
    return jsonify({
        'user': user_to_dict(current_user),
        'permissions': perms,
    })


# --- Dashboard ---
@api_bp.route('/dashboard')
@login_required
def dashboard():
    tenant = get_default_tenant()
    if not tenant:
        return jsonify({'error': 'Tenant not found'}), 404
    vendor_count = Vendor.query.filter_by(tenant_id=tenant.id).count()
    bill_count = Bill.query.filter_by(tenant_id=tenant.id).count()
    total_billed = db.session.query(func.sum(Bill.amount_total)).filter_by(
        tenant_id=tenant.id, status='CONFIRMED'
    ).scalar() or 0
    total_incoming = db.session.query(func.sum(CreditEntry.amount)).filter_by(
        tenant_id=tenant.id, direction='INCOMING'
    ).scalar() or 0
    total_outgoing = db.session.query(func.sum(CreditEntry.amount)).filter_by(
        tenant_id=tenant.id, direction='OUTGOING'
    ).scalar() or 0
    outstanding = float(total_billed) - float(total_incoming) + float(total_outgoing)
    return jsonify({
        'stats': {
            'vendor_count': vendor_count,
            'bill_count': bill_count,
            'outstanding': outstanding,
        },
    })


# --- Vendors ---
@api_bp.route('/vendors')
@login_required
@api_permission_required('view_vendors')
def vendors_list():
    tenant = get_default_tenant()
    if not tenant:
        return jsonify({'error': 'Tenant not found'}), 404
    search = request.args.get('search', '').strip()
    type_filter = request.args.get('type', '')
    query = Vendor.query.filter_by(tenant_id=tenant.id)
    if search:
        from sqlalchemy import or_
        query = query.filter(or_(
            Vendor.name.ilike(f'%{search}%'),
            Vendor.email.ilike(f'%{search}%'),
            Vendor.contact_phone.ilike(f'%{search}%'),
        ))
    if type_filter:
        query = query.filter_by(type=type_filter)
    vendors = query.order_by(Vendor.name).all()
    return jsonify({
        'vendors': [vendor_to_dict(v) for v in vendors],
        'filters': {'search': search, 'type': type_filter},
    })


@api_bp.route('/vendors/<int:id>')
@login_required
@api_permission_required('view_vendors')
def vendor_detail(id):
    v = Vendor.query.get_or_404(id)
    return jsonify(vendor_to_dict(v))


@api_bp.route('/vendors', methods=['POST'])
@login_required
@api_permission_required('create_vendor')
def vendor_create():
    tenant = get_default_tenant()
    if not tenant:
        return jsonify({'error': 'Tenant not found'}), 404
    data = request.get_json() or {}
    v = Vendor(
        tenant_id=tenant.id,
        name=data.get('name', '').strip(),
        type=data.get('type', 'CUSTOMER'),
        contact_phone=data.get('contact_phone') or None,
        email=data.get('email') or None,
        address=data.get('address') or None,
        gst_number=data.get('gst_number') or None,
        credit_limit=Decimal(str(data.get('credit_limit', 0) or 0)),
    )
    db.session.add(v)
    db.session.commit()
    from audit import log_action
    log_action(current_user, 'CREATE_VENDOR', 'VENDOR', v.id)
    return jsonify(vendor_to_dict(v)), 201


@api_bp.route('/vendors/<int:id>', methods=['PUT'])
@login_required
@api_permission_required('edit_vendor')
def vendor_update(id):
    v = Vendor.query.get_or_404(id)
    data = request.get_json() or {}
    v.name = data.get('name', v.name)
    v.type = data.get('type', v.type)
    v.contact_phone = data.get('contact_phone', v.contact_phone)
    v.email = data.get('email', v.email)
    v.address = data.get('address', v.address)
    v.gst_number = data.get('gst_number', v.gst_number)
    v.credit_limit = Decimal(str(data.get('credit_limit', v.credit_limit) or 0))
    db.session.commit()
    from audit import log_action
    log_action(current_user, 'UPDATE_VENDOR', 'VENDOR', v.id)
    return jsonify(vendor_to_dict(v))


@api_bp.route('/vendors/<int:id>', methods=['DELETE'])
@login_required
@api_permission_required('delete_vendor')
def vendor_delete(id):
    from models import Bill, ProxyBill, CreditEntry
    v = Vendor.query.get_or_404(id)
    if Bill.query.filter_by(vendor_id=v.id).count() > 0:
        return jsonify({'error': 'Cannot delete vendor with associated bills'}), 400
    if ProxyBill.query.filter_by(vendor_id=v.id).count() > 0:
        return jsonify({'error': 'Cannot delete vendor with associated proxy bills'}), 400
    if CreditEntry.query.filter_by(vendor_id=v.id).count() > 0:
        return jsonify({'error': 'Cannot delete vendor with associated credit entries'}), 400
    db.session.delete(v)
    db.session.commit()
    from audit import log_action
    log_action(current_user, 'DELETE_VENDOR', 'VENDOR', v.id)
    return jsonify({'success': True})


# --- Bills ---
@api_bp.route('/bills')
@login_required
@api_permission_required('view_bills')
def bills_list():
    tenant = get_default_tenant()
    if not tenant:
        return jsonify({'error': 'Tenant not found'}), 404
    query = Bill.query.filter_by(tenant_id=tenant.id)
    if current_user.role == 'ORGANISER':
        query = query.filter(Bill.is_authorized == True)
    search = request.args.get('search', '').strip()
    vendor_id = request.args.get('vendor_id', type=int)
    status = request.args.get('status', '')
    if search:
        query = query.filter(Bill.bill_number.ilike(f'%{search}%'))
    if vendor_id:
        query = query.filter(Bill.vendor_id == vendor_id)
    if status:
        query = query.filter(Bill.status == status)
    bills = query.order_by(Bill.created_at.desc()).all()
    bill_ids = [b.id for b in bills]
    paid_by_bill = {}
    if bills:
        paid_results = db.session.query(
            CreditEntry.bill_id,
            func.sum(CreditEntry.amount).label('total_paid')
        ).filter(
            CreditEntry.bill_id.in_(bill_ids),
            CreditEntry.direction == 'INCOMING'
        ).group_by(CreditEntry.bill_id).all()
        paid_by_bill = {r.bill_id: float(r.total_paid) for r in paid_results}
    payment_status_map = {}
    for b in bills:
        total_paid = paid_by_bill.get(b.id, 0)
        if total_paid >= float(b.amount_total):
            payment_status_map[b.id] = 'PAID'
        elif total_paid > 0:
            payment_status_map[b.id] = 'PARTIAL'
        else:
            payment_status_map[b.id] = 'UNPAID'
    vendors = Vendor.query.filter_by(tenant_id=tenant.id).order_by(Vendor.name).all()
    return jsonify({
        'bills': [bill_to_dict(b, payment_status_map.get(b.id)) for b in bills],
        'vendors': [vendor_to_dict(v) for v in vendors],
    })


@api_bp.route('/bills/<int:id>')
@login_required
@api_permission_required('view_bills')
def bill_detail(id):
    bill = Bill.query.get_or_404(id)
    tenant = get_default_tenant()
    credits = CreditEntry.query.filter_by(bill_id=bill.id, direction='INCOMING').all()
    proxy_bills = ProxyBill.query.filter_by(parent_bill_id=bill.id).all()
    total_paid = db.session.query(func.sum(CreditEntry.amount)).filter_by(
        tenant_id=tenant.id, bill_id=bill.id, direction='INCOMING'
    ).scalar() or Decimal('0.00')
    remaining = float(bill.amount_total) - float(total_paid)
    status = 'UNPAID'
    if total_paid >= bill.amount_total:
        status = 'FULLY_PAID'
    elif total_paid > 0:
        status = 'PARTIALLY_PAID'
    return jsonify({
        'bill': bill_to_dict(bill, status),
        'credits': [credit_to_dict(c) for c in credits],
        'proxy_bills': [proxy_bill_to_dict(pb) for pb in proxy_bills],
        'total_paid': float(total_paid),
        'remaining': remaining,
        'payment_status': status,
    })


@api_bp.route('/bills/new/ocr-upload', methods=['POST'])
@login_required
@api_permission_required('create_bill')
def bill_ocr_upload():
    """OCR upload endpoint - same logic as bill_routes.ocr_upload."""
    try:
        if 'ocr_image' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        file = request.files['ocr_image']
        if not file or not file.filename:
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        allowed = {'png', 'jpg', 'jpeg', 'pdf'}
        ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        if ext not in allowed:
            return jsonify({'success': False, 'error': 'Invalid file type'}), 400
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"ocr_{timestamp}_{filename}"
        upload_folder = Path(current_app.config['UPLOAD_FOLDER'])
        upload_folder.mkdir(parents=True, exist_ok=True)
        filepath = upload_folder / filename
        file.save(str(filepath))
        try:
            from ocr_utils import run_ocr
            from bill_routes import extract_bill_info, extract_bill_info_advanced
            ocr_result = run_ocr(str(filepath), return_detailed=True)
            if isinstance(ocr_result, str):
                ocr_text = ocr_result
                ocr_detailed = None
            else:
                ocr_text = ocr_result.get('text', '')
                ocr_detailed = ocr_result.get('detailed', [])
            if not ocr_text or not ocr_text.strip():
                return jsonify({
                    'success': False,
                    'error': 'No text could be extracted from the image.'
                }), 500
            try:
                suggestions = extract_bill_info_advanced(ocr_text, ocr_detailed)
            except Exception:
                suggestions = extract_bill_info(ocr_text)
            return jsonify({
                'success': True,
                'ocr_text': ocr_text,
                'image_path': f"uploads/bills/{filename}",
                'suggestions': suggestions,
            })
        except ImportError:
            return jsonify({
                'success': False,
                'error': 'OCR library not available on this server.'
            }), 500
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e),
            }), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/bills', methods=['POST'])
@login_required
@api_permission_required('create_bill')
def bill_create():
    tenant = get_default_tenant()
    if not tenant:
        return jsonify({'error': 'Tenant not found'}), 404
    data = request.get_json() or {}
    dd = data.get('delivery_date')
    bill = Bill(
        tenant_id=tenant.id,
        vendor_id=data['vendor_id'],
        bill_number=data.get('bill_number', '').strip(),
        bill_date=datetime.strptime(data.get('bill_date', ''), '%Y-%m-%d').date(),
        bill_type=data.get('bill_type', 'PURCHASE'),
        status='DRAFT',
        amount_subtotal=Decimal(str(data.get('amount_subtotal', 0) or 0)),
        amount_tax=Decimal(str(data.get('amount_tax', 0) or 0)),
        amount_total=Decimal(str(data.get('amount_total', 0) or 0)),
        delivery_date=datetime.strptime(dd, '%Y-%m-%d').date() if dd else None,
        billed_to_name=data.get('billed_to_name') or None,
        shipped_to_name=data.get('shipped_to_name') or None,
        delivery_recipient=data.get('delivery_recipient') or None,
        post=data.get('post') or None,
    )
    db.session.add(bill)
    db.session.flush()
    from audit import log_action
    log_action(current_user, 'CREATE_BILL', 'BILL', bill.id)
    if data.get('payment_type') in ['FULL', 'PARTIAL']:
        amt = bill.amount_total if data.get('payment_type') == 'FULL' else Decimal(str(data.get('partial_amount', 0) or 0))
        if amt > 0:
            credit = CreditEntry(
                tenant_id=tenant.id,
                bill_id=bill.id,
                vendor_id=bill.vendor_id,
                amount=amt,
                direction='INCOMING',
                payment_method=data.get('payment_method', 'CASH'),
                payment_date=bill.bill_date,
                reference_number=data.get('payment_reference'),
                notes=f'Payment for bill {bill.bill_number}',
            )
            db.session.add(credit)
            log_action(current_user, 'CREATE_CREDIT', 'CREDIT_ENTRY', credit.id)
    db.session.commit()
    return jsonify(bill_to_dict(bill)), 201


@api_bp.route('/bills/<int:id>/confirm', methods=['POST'])
@login_required
@api_permission_required('confirm_bill')
def bill_confirm(id):
    bill = Bill.query.get_or_404(id)
    if bill.status == 'DRAFT':
        bill.status = 'CONFIRMED'
        db.session.commit()
        from audit import log_action
        log_action(current_user, 'CONFIRM_BILL', 'BILL', bill.id)
    return jsonify(bill_to_dict(bill))


@api_bp.route('/bills/<int:id>/cancel', methods=['POST'])
@login_required
@api_permission_required('cancel_bill')
def bill_cancel(id):
    bill = Bill.query.get_or_404(id)
    if bill.status != 'CANCELLED':
        bill.status = 'CANCELLED'
        db.session.commit()
        from audit import log_action
        log_action(current_user, 'CANCEL_BILL', 'BILL', bill.id)
    return jsonify(bill_to_dict(bill))


@api_bp.route('/bills/<int:id>/mark-paid', methods=['POST'])
@login_required
@api_permission_required('create_credit')
def bill_mark_paid(id):
    bill = Bill.query.get_or_404(id)
    tenant = get_default_tenant()
    data = request.get_json() or {}
    payment_type = data.get('payment_type', 'FULL')
    payment_method = data.get('payment_method', 'CASH')
    payment_reference = data.get('payment_reference', '')
    payment_date_str = data.get('payment_date')
    partial_amount_str = str(data.get('partial_amount', 0) or 0)
    payment_date = bill.bill_date
    if payment_date_str:
        try:
            payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    if payment_type == 'FULL':
        payment_amount = bill.amount_total
    else:
        payment_amount = Decimal(partial_amount_str)
        if payment_amount <= 0:
            return jsonify({'error': 'Partial amount must be > 0'}), 400
        if payment_amount > bill.amount_total:
            return jsonify({'error': 'Partial amount exceeds total'}), 400
    total_paid = db.session.query(func.sum(CreditEntry.amount)).filter_by(
        tenant_id=tenant.id, bill_id=bill.id, direction='INCOMING'
    ).scalar() or Decimal('0.00')
    remaining = bill.amount_total - total_paid
    if payment_amount > remaining:
        return jsonify({'error': f'Payment exceeds remaining ₹{remaining}'}), 400
    credit = CreditEntry(
        tenant_id=tenant.id,
        bill_id=bill.id,
        vendor_id=bill.vendor_id,
        amount=payment_amount,
        direction='INCOMING',
        payment_method=payment_method,
        payment_date=payment_date,
        reference_number=payment_reference,
        notes=f'Payment for bill {bill.bill_number}',
    )
    db.session.add(credit)
    db.session.commit()
    from audit import log_action
    log_action(current_user, 'MARK_BILL_PAID', 'BILL', bill.id)
    log_action(current_user, 'CREATE_CREDIT', 'CREDIT_ENTRY', credit.id)
    return jsonify(credit_to_dict(credit))


# --- Credits ---
@api_bp.route('/credits')
@login_required
@api_permission_required('view_credits')
def credits_list():
    tenant = get_default_tenant()
    if not tenant:
        return jsonify({'error': 'Tenant not found'}), 404
    search = request.args.get('search', '').strip()
    vendor_id = request.args.get('vendor_id', type=int)
    direction = request.args.get('direction', '')
    query = CreditEntry.query.filter_by(tenant_id=tenant.id)
    if search:
        query = query.filter(CreditEntry.reference_number.ilike(f'%{search}%'))
    if vendor_id:
        query = query.filter(CreditEntry.vendor_id == vendor_id)
    if direction:
        query = query.filter(CreditEntry.direction == direction)
    credits = query.order_by(CreditEntry.payment_date.desc()).all()
    unpaid_bills = []
    bill_query = Bill.query.filter_by(tenant_id=tenant.id, status='CONFIRMED')
    if vendor_id:
        bill_query = bill_query.filter(Bill.vendor_id == vendor_id)
    for bill in bill_query.all():
        total_paid = db.session.query(func.sum(CreditEntry.amount)).filter_by(
            tenant_id=tenant.id, bill_id=bill.id, direction='INCOMING'
        ).scalar() or 0
        remaining = float(bill.amount_total) - float(total_paid)
        if remaining > 0:
            unpaid_bills.append({
                'bill': bill_to_dict(bill),
                'total': float(bill.amount_total),
                'paid': float(total_paid),
                'outstanding': remaining,
            })
    vendors = Vendor.query.filter_by(tenant_id=tenant.id).order_by(Vendor.name).all()
    return jsonify({
        'credits': [credit_to_dict(c) for c in credits],
        'unpaid_bills': unpaid_bills,
        'vendors': [vendor_to_dict(v) for v in vendors],
    })


@api_bp.route('/credits', methods=['POST'])
@login_required
@api_permission_required('create_credit')
def credit_create():
    tenant = get_default_tenant()
    if not tenant:
        return jsonify({'error': 'Tenant not found'}), 404
    data = request.get_json() or {}
    credit = CreditEntry(
        tenant_id=tenant.id,
        bill_id=data.get('bill_id') or None,
        proxy_bill_id=data.get('proxy_bill_id') or None,
        vendor_id=data['vendor_id'],
        amount=Decimal(str(data['amount'])),
        direction=data.get('direction', 'INCOMING'),
        payment_method=data.get('payment_method', 'CASH'),
        payment_date=datetime.strptime(data.get('payment_date', ''), '%Y-%m-%d').date(),
        reference_number=data.get('reference_number') or None,
        notes=data.get('notes') or None,
    )
    db.session.add(credit)
    db.session.commit()
    from audit import log_action
    log_action(current_user, 'CREATE_CREDIT', 'CREDIT_ENTRY', credit.id)
    return jsonify(credit_to_dict(credit)), 201


# --- Deliveries ---
@api_bp.route('/deliveries')
@login_required
@api_permission_required('view_deliveries')
def deliveries_list():
    tenant = get_default_tenant()
    if not tenant:
        return jsonify({'error': 'Tenant not found'}), 404
    from models import User
    from sqlalchemy import or_
    query = DeliveryOrder.query.filter_by(tenant_id=tenant.id)
    if current_user.role == 'DELIVERY':
        query = query.filter_by(delivery_user_id=current_user.id)
    status = request.args.get('status', '')
    if status:
        query = query.filter(DeliveryOrder.status == status)
    deliveries = query.order_by(DeliveryOrder.delivery_date.desc()).all()
    return jsonify({
        'deliveries': [delivery_to_dict(d) for d in deliveries],
    })


@api_bp.route('/deliveries/<int:id>')
@login_required
@api_permission_required('view_deliveries')
def delivery_detail(id):
    d = DeliveryOrder.query.get_or_404(id)
    return jsonify(delivery_to_dict(d))


@api_bp.route('/deliveries', methods=['POST'])
@login_required
@api_permission_required('create_delivery')
def delivery_create():
    tenant = get_default_tenant()
    if not tenant:
        return jsonify({'error': 'Tenant not found'}), 404
    data = request.get_json() or {}
    from models import User
    delivery = DeliveryOrder(
        tenant_id=tenant.id,
        bill_id=data.get('bill_id') or None,
        proxy_bill_id=data.get('proxy_bill_id') or None,
        delivery_user_id=data['delivery_user_id'],
        delivery_address=data.get('delivery_address', ''),
        delivery_date=datetime.strptime(data.get('delivery_date', ''), '%Y-%m-%d').date(),
        status='PENDING',
        remarks=data.get('remarks') or None,
    )
    db.session.add(delivery)
    db.session.commit()
    from audit import log_action
    log_action(current_user, 'CREATE_DELIVERY', 'DELIVERY_ORDER', delivery.id)
    return jsonify(delivery_to_dict(delivery)), 201


@api_bp.route('/deliveries/<int:id>/update-status', methods=['POST'])
@login_required
@api_permission_required('update_delivery')
def delivery_update_status(id):
    d = DeliveryOrder.query.get_or_404(id)
    data = request.get_json() or {}
    new_status = data.get('status')
    if new_status in ['PENDING', 'IN_TRANSIT', 'DELIVERED', 'CANCELLED']:
        d.status = new_status
        db.session.commit()
        from audit import log_action
        log_action(current_user, 'UPDATE_DELIVERY_STATUS', 'DELIVERY_ORDER', d.id)
    return jsonify(delivery_to_dict(d))


# --- Proxy Bills ---
@api_bp.route('/proxy-bills')
@login_required
@api_permission_required('view_bills')
def proxy_bills_list():
    tenant = get_default_tenant()
    if not tenant:
        return jsonify({'error': 'Tenant not found'}), 404
    proxy_bills = ProxyBill.query.filter_by(tenant_id=tenant.id).order_by(ProxyBill.created_at.desc()).all()
    return jsonify({
        'proxy_bills': [proxy_bill_to_dict(pb) for pb in proxy_bills],
    })


@api_bp.route('/proxy-bills/<int:id>')
@login_required
@api_permission_required('view_bills')
def proxy_bill_detail(id):
    pb = ProxyBill.query.get_or_404(id)
    credits = CreditEntry.query.filter_by(proxy_bill_id=pb.id).all()
    return jsonify({
        'proxy_bill': proxy_bill_to_dict(pb),
        'credits': [credit_to_dict(c) for c in credits],
    })


# --- OCR ---
@api_bp.route('/ocr/upload', methods=['POST'])
@login_required
@api_permission_required('create_bill')
def ocr_upload():
    tenant = get_default_tenant()
    if not tenant:
        return jsonify({'error': 'Tenant not found'}), 404
    bill_id = request.form.get('bill_id', type=int)
    if not bill_id:
        return jsonify({'error': 'bill_id required'}), 400
    bill = Bill.query.get_or_404(bill_id)
    if 'image' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['image']
    if not file or not file.filename:
        return jsonify({'error': 'No file selected'}), 400
    allowed = {'png', 'jpg', 'jpeg', 'pdf'}
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    if ext not in allowed:
        return jsonify({'error': 'Invalid file type'}), 400
    filename = secure_filename(file.filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{bill.id}_{timestamp}_{filename}"
    upload_folder = Path(current_app.config['UPLOAD_FOLDER'])
    upload_folder.mkdir(parents=True, exist_ok=True)
    filepath = upload_folder / filename
    file.save(str(filepath))
    relative_path = f"uploads/bills/{filename}"
    ocr_text = None
    try:
        from ocr_utils import run_ocr
        ocr_text = run_ocr(str(filepath))
        if ocr_text and (ocr_text.startswith("OCR error:") or ocr_text.startswith("Error:")):
            ocr_text = None
    except Exception:
        ocr_text = None
    job = OCRJob(
        tenant_id=tenant.id,
        bill_id=bill.id,
        image_path=relative_path,
        raw_text=ocr_text or "OCR processing failed or not available.",
    )
    db.session.add(job)
    bill.image_path = relative_path
    if ocr_text:
        bill.ocr_text = ocr_text
    db.session.commit()
    from audit import log_action
    log_action(current_user, 'UPLOAD_OCR', 'BILL', bill.id)
    return jsonify(ocr_job_to_dict(job)), 201


@api_bp.route('/ocr/<int:id>')
@login_required
@api_permission_required('view_bills')
def ocr_view(id):
    job = OCRJob.query.get_or_404(id)
    return jsonify(ocr_job_to_dict(job))


# --- Reports ---
@api_bp.route('/reports/outstanding')
@login_required
@api_permission_required('view_reports')
def report_outstanding():
    tenant = get_default_tenant()
    if not tenant:
        return jsonify({'error': 'Tenant not found'}), 404
    vendors = Vendor.query.filter_by(tenant_id=tenant.id).all()
    results = []
    for v in vendors:
        total_billed = db.session.query(func.sum(Bill.amount_total)).filter_by(
            tenant_id=tenant.id, vendor_id=v.id, status='CONFIRMED'
        ).scalar() or 0
        total_incoming = db.session.query(func.sum(CreditEntry.amount)).filter_by(
            tenant_id=tenant.id, vendor_id=v.id, direction='INCOMING'
        ).scalar() or 0
        total_outgoing = db.session.query(func.sum(CreditEntry.amount)).filter_by(
            tenant_id=tenant.id, vendor_id=v.id, direction='OUTGOING'
        ).scalar() or 0
        outstanding = float(total_billed) - float(total_incoming) + float(total_outgoing)
        if outstanding != 0 or total_billed > 0:
            results.append({
                'vendor': vendor_to_dict(v),
                'total_billed': float(total_billed),
                'total_incoming': float(total_incoming),
                'total_outgoing': float(total_outgoing),
                'outstanding': outstanding,
            })
    return jsonify({'results': results})


@api_bp.route('/reports/collection')
@login_required
@api_permission_required('view_reports')
def report_collection():
    tenant = get_default_tenant()
    if not tenant:
        return jsonify({'error': 'Tenant not found'}), 404
    start_str = request.args.get('start_date')
    end_str = request.args.get('end_date')
    if not start_str or not end_str:
        return jsonify({'error': 'start_date and end_date required'}), 400
    try:
        start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400
    total_incoming = db.session.query(func.sum(CreditEntry.amount)).filter(
        CreditEntry.tenant_id == tenant.id,
        CreditEntry.direction == 'INCOMING',
        CreditEntry.payment_date >= start_date,
        CreditEntry.payment_date <= end_date,
    ).scalar() or 0
    total_outgoing = db.session.query(func.sum(CreditEntry.amount)).filter(
        CreditEntry.tenant_id == tenant.id,
        CreditEntry.direction == 'OUTGOING',
        CreditEntry.payment_date >= start_date,
        CreditEntry.payment_date <= end_date,
    ).scalar() or 0
    net = float(total_incoming) - float(total_outgoing)
    return jsonify({
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'total_incoming': float(total_incoming),
        'total_outgoing': float(total_outgoing),
        'net': net,
    })


@api_bp.route('/reports/deliveries')
@login_required
@api_permission_required('view_reports')
def report_deliveries():
    tenant = get_default_tenant()
    if not tenant:
        return jsonify({'error': 'Tenant not found'}), 404
    from models import DeliveryOrder
    pending = DeliveryOrder.query.filter_by(tenant_id=tenant.id, status='PENDING').count()
    in_transit = DeliveryOrder.query.filter_by(tenant_id=tenant.id, status='IN_TRANSIT').count()
    delivered = DeliveryOrder.query.filter_by(tenant_id=tenant.id, status='DELIVERED').count()
    cancelled = DeliveryOrder.query.filter_by(tenant_id=tenant.id, status='CANCELLED').count()
    total = DeliveryOrder.query.filter_by(tenant_id=tenant.id).count()
    orders = DeliveryOrder.query.filter_by(tenant_id=tenant.id).order_by(DeliveryOrder.delivery_date.desc()).all()
    return jsonify({
        'stats': {'pending': pending, 'in_transit': in_transit, 'delivered': delivered, 'cancelled': cancelled, 'total': total},
        'delivery_orders': [delivery_to_dict(o) for o in orders],
    })


# --- Permissions ---
@api_bp.route('/permissions')
@login_required
@api_permission_required('manage_permissions')
def permissions_list():
    perms = Permission.query.order_by(Permission.category, Permission.name).all()
    roles = ['ADMIN', 'SALESMAN', 'DELIVERY', 'ORGANISER']
    role_permissions = {}
    for role in roles:
        role_permissions[role] = {}
        for p in perms:
            rp = RolePermission.query.filter_by(role=role, permission_id=p.id).first()
            role_permissions[role][p.code] = rp.granted if rp else False
    return jsonify({
        'permissions': [serialize_model(p) for p in perms],
        'roles': roles,
        'role_permissions': role_permissions,
    })


@api_bp.route('/permissions/update', methods=['POST'])
@login_required
@api_permission_required('manage_permissions')
def permissions_update():
    tenant = get_default_tenant()
    if not tenant:
        return jsonify({'error': 'Tenant not found'}), 404
    data = request.get_json() or {}
    perms = Permission.query.all()
    roles = ['ADMIN', 'SALESMAN', 'DELIVERY', 'ORGANISER']
    for role in roles:
        if role == 'ADMIN':
            continue
        for p in perms:
            key = f'{role}_{p.code}'
            is_granted = data.get(key, False)
            rp = RolePermission.query.filter_by(role=role, permission_id=p.id).first()
            if rp:
                rp.granted = is_granted
            else:
                rp = RolePermission(role=role, permission_id=p.id, granted=is_granted)
                db.session.add(rp)
    db.session.commit()
    from audit import log_action
    log_action(current_user, 'UPDATE_PERMISSIONS', 'PERMISSIONS', 0)
    return jsonify({'success': True})


# --- Form options (for dropdowns) ---
@api_bp.route('/options/vendors')
@login_required
def options_vendors():
    tenant = get_default_tenant()
    if not tenant:
        return jsonify({'error': 'Tenant not found'}), 404
    vendors = Vendor.query.filter_by(tenant_id=tenant.id).order_by(Vendor.name).all()
    return jsonify([{'id': v.id, 'name': v.name} for v in vendors])


@api_bp.route('/options/bills')
@login_required
def options_bills():
    tenant = get_default_tenant()
    if not tenant:
        return jsonify({'error': 'Tenant not found'}), 404
    bills = Bill.query.filter_by(tenant_id=tenant.id).all()
    return jsonify([{'id': b.id, 'label': f"{b.bill_number} - {b.vendor.name}"} for b in bills])


@api_bp.route('/options/proxy-bills')
@login_required
def options_proxy_bills():
    tenant = get_default_tenant()
    if not tenant:
        return jsonify({'error': 'Tenant not found'}), 404
    pbs = ProxyBill.query.filter_by(tenant_id=tenant.id).all()
    return jsonify([{'id': pb.id, 'label': f"{pb.proxy_number} - {pb.vendor.name}"} for pb in pbs])


@api_bp.route('/options/delivery-users')
@login_required
def options_delivery_users():
    from models import User
    tenant = get_default_tenant()
    if not tenant:
        return jsonify({'error': 'Tenant not found'}), 404
    users = User.query.filter_by(tenant_id=tenant.id, role='DELIVERY', is_active=True).all()
    return jsonify([{'id': u.id, 'name': u.username} for u in users])
