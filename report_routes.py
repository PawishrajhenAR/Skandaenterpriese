from flask import Blueprint, render_template, redirect, url_for, flash, request, Response
from flask_login import login_required, current_user
from models import Vendor, Bill, CreditEntry, DeliveryOrder, Tenant, User, ProxyBill
from forms import ReportDateRangeForm
from extensions import db
from sqlalchemy import func, or_
from auth_routes import permission_required
from export_utils import (
    generate_outstanding_pdf, generate_outstanding_excel,
    generate_collection_pdf, generate_collection_excel,
    generate_deliveries_pdf, generate_deliveries_excel
)
from datetime import datetime

report_bp = Blueprint('report', __name__)


def get_default_tenant():
    return Tenant.query.filter_by(code='skanda').first()


def _parse_date_arg(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


def _delivery_report_data(tenant):
    search = request.args.get('search', '').strip()
    status = request.args.get('status', '').strip()
    delivery_user_id = request.args.get('delivery_user_id', type=int)
    vendor_id = request.args.get('vendor_id', type=int)
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    query = DeliveryOrder.query.filter_by(tenant_id=tenant.id)

    if search:
        like = f'%{search}%'
        bill_ids = [
            b.id for b in Bill.query.filter(
                Bill.tenant_id == tenant.id,
                Bill.bill_number.ilike(like)
            ).all()
        ]
        proxy_bill_ids = [
            pb.id for pb in ProxyBill.query.filter(
                ProxyBill.tenant_id == tenant.id,
                ProxyBill.proxy_number.ilike(like)
            ).all()
        ]
        query = query.filter(or_(
            DeliveryOrder.delivery_address.ilike(like),
            DeliveryOrder.bill_id.in_(bill_ids),
            DeliveryOrder.proxy_bill_id.in_(proxy_bill_ids),
        ))
    if status:
        query = query.filter(DeliveryOrder.status == status)
    if delivery_user_id:
        query = query.filter(DeliveryOrder.delivery_user_id == delivery_user_id)
    if vendor_id:
        bill_ids = [b.id for b in Bill.query.filter_by(tenant_id=tenant.id, vendor_id=vendor_id).all()]
        proxy_bill_ids = [pb.id for pb in ProxyBill.query.filter_by(tenant_id=tenant.id, vendor_id=vendor_id).all()]
        query = query.filter(or_(
            DeliveryOrder.bill_id.in_(bill_ids),
            DeliveryOrder.proxy_bill_id.in_(proxy_bill_ids),
        ))

    date_from_obj = _parse_date_arg(date_from)
    if date_from_obj:
        query = query.filter(DeliveryOrder.delivery_date >= date_from_obj)
    date_to_obj = _parse_date_arg(date_to)
    if date_to_obj:
        query = query.filter(DeliveryOrder.delivery_date <= date_to_obj)

    delivery_orders = query.order_by(DeliveryOrder.delivery_date.desc()).all()
    stats = {
        'pending': sum(1 for order in delivery_orders if order.status == 'PENDING'),
        'in_transit': sum(1 for order in delivery_orders if order.status == 'IN_TRANSIT'),
        'delivered': sum(1 for order in delivery_orders if order.status == 'DELIVERED'),
        'not_delivered': sum(1 for order in delivery_orders if order.status == 'NOT_DELIVERED'),
        'shop_closed': sum(1 for order in delivery_orders if order.status == 'SHOP_CLOSED'),
        'cancelled': sum(1 for order in delivery_orders if order.status == 'CANCELLED'),
        'total': len(delivery_orders),
    }

    delivery_users = User.query.filter_by(tenant_id=tenant.id, role='DELIVERY', is_active=True).order_by(User.username).all()
    vendors = Vendor.query.filter_by(tenant_id=tenant.id).order_by(Vendor.name).all()
    filters = [
        {
            'name': 'search',
            'label': 'Search',
            'type': 'search',
            'placeholder': 'Address or bill number...',
            'value': search,
            'icon': 'bi-search',
            'col_size': 3,
        },
        {
            'name': 'status',
            'label': 'Status',
            'type': 'select',
            'value': status,
            'options': [
                {'value': 'PENDING', 'label': 'Pending'},
                {'value': 'IN_TRANSIT', 'label': 'In Transit'},
                {'value': 'DELIVERED', 'label': 'Delivered'},
                {'value': 'NOT_DELIVERED', 'label': 'Not Delivered'},
                {'value': 'SHOP_CLOSED', 'label': 'Shop Closed'},
                {'value': 'CANCELLED', 'label': 'Cancelled'},
            ],
            'icon': 'bi-flag',
            'col_size': 2,
        },
        {
            'name': 'delivery_user_id',
            'label': 'Delivery User',
            'type': 'select',
            'value': delivery_user_id,
            'options': [{'value': u.id, 'label': u.username} for u in delivery_users],
            'icon': 'bi-person',
            'col_size': 2,
        },
        {
            'name': 'vendor_id',
            'label': 'Vendor',
            'type': 'select',
            'value': vendor_id,
            'options': [{'value': v.id, 'label': v.name} for v in vendors],
            'icon': 'bi-shop',
            'col_size': 2,
        },
        {
            'name': 'date',
            'label': 'Date Range',
            'type': 'date-range',
            'value_from': date_from,
            'value_to': date_to,
            'icon': 'bi-calendar',
            'col_size': 3,
        },
    ]

    active_filters = {}
    if search:
        active_filters['Search'] = search
    if status:
        active_filters['Status'] = status
    if delivery_user_id:
        user = User.query.get(delivery_user_id)
        if user:
            active_filters['Delivery User'] = user.username
    if vendor_id:
        vendor = Vendor.query.get(vendor_id)
        if vendor:
            active_filters['Vendor'] = vendor.name
    if date_from or date_to:
        active_filters['Date'] = f"{date_from or 'Any'} to {date_to or 'Any'}"

    return stats, delivery_orders, filters, active_filters


@report_bp.route('/outstanding')
@login_required
@permission_required('view_reports')
def outstanding():
    tenant = get_default_tenant()
    if not tenant:
        flash('Tenant not found.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    vendors = Vendor.query.filter_by(tenant_id=tenant.id).all()
    results = []
    
    for vendor in vendors:
        # Total billed (confirmed bills)
        total_billed = db.session.query(func.sum(Bill.amount_total)).filter_by(
            tenant_id=tenant.id, vendor_id=vendor.id, status='CONFIRMED'
        ).scalar() or 0
        
        # Total incoming payments (from credit entries)
        total_incoming = db.session.query(func.sum(CreditEntry.amount)).filter_by(
            tenant_id=tenant.id, vendor_id=vendor.id, direction='INCOMING'
        ).scalar() or 0
        
        # Total outgoing payments
        total_outgoing = db.session.query(func.sum(CreditEntry.amount)).filter_by(
            tenant_id=tenant.id, vendor_id=vendor.id, direction='OUTGOING'
        ).scalar() or 0
        
        # Outstanding = Total Billed - Total Incoming + Total Outgoing
        outstanding = float(total_billed) - float(total_incoming) + float(total_outgoing)
        
        if outstanding != 0 or total_billed > 0:
            results.append({
                'vendor': vendor,
                'total_billed': float(total_billed),
                'total_incoming': float(total_incoming),
                'total_outgoing': float(total_outgoing),
                'outstanding': outstanding
            })
    
    return render_template('reports/outstanding.html', results=results)


@report_bp.route('/collection', methods=['GET', 'POST'])
@login_required
@permission_required('view_reports')
def collection():
    tenant = get_default_tenant()
    if not tenant:
        flash('Tenant not found.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    form = ReportDateRangeForm()
    results = None
    
    if form.validate_on_submit():
        start_date = form.start_date.data
        end_date = form.end_date.data
        
        # Total incoming
        total_incoming = db.session.query(func.sum(CreditEntry.amount)).filter(
            CreditEntry.tenant_id == tenant.id,
            CreditEntry.direction == 'INCOMING',
            CreditEntry.payment_date >= start_date,
            CreditEntry.payment_date <= end_date
        ).scalar() or 0
        
        # Total outgoing
        total_outgoing = db.session.query(func.sum(CreditEntry.amount)).filter(
            CreditEntry.tenant_id == tenant.id,
            CreditEntry.direction == 'OUTGOING',
            CreditEntry.payment_date >= start_date,
            CreditEntry.payment_date <= end_date
        ).scalar() or 0
        
        net = float(total_incoming) - float(total_outgoing)
        
        results = {
            'start_date': start_date,
            'end_date': end_date,
            'total_incoming': float(total_incoming),
            'total_outgoing': float(total_outgoing),
            'net': net
        }
    
    return render_template('reports/collection.html', form=form, results=results)


@report_bp.route('/deliveries')
@login_required
@permission_required('view_reports')
def deliveries():
    tenant = get_default_tenant()
    if not tenant:
        flash('Tenant not found.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    stats, delivery_orders, filters, active_filters = _delivery_report_data(tenant)
    return render_template(
        'reports/deliveries.html',
        stats=stats,
        delivery_orders=delivery_orders,
        filters=filters,
        active_filters=active_filters,
    )


# Export routes for Outstanding Report
@report_bp.route('/outstanding/export/pdf')
@login_required
@permission_required('view_reports')
def outstanding_export_pdf():
    tenant = get_default_tenant()
    if not tenant:
        flash('Tenant not found.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    vendors = Vendor.query.filter_by(tenant_id=tenant.id).all()
    results = []
    
    for vendor in vendors:
        total_billed = db.session.query(func.sum(Bill.amount_total)).filter_by(
            tenant_id=tenant.id, vendor_id=vendor.id, status='CONFIRMED'
        ).scalar() or 0
        
        total_incoming = db.session.query(func.sum(CreditEntry.amount)).filter_by(
            tenant_id=tenant.id, vendor_id=vendor.id, direction='INCOMING'
        ).scalar() or 0
        
        total_outgoing = db.session.query(func.sum(CreditEntry.amount)).filter_by(
            tenant_id=tenant.id, vendor_id=vendor.id, direction='OUTGOING'
        ).scalar() or 0
        
        outstanding = float(total_billed) - float(total_incoming) + float(total_outgoing)
        
        if outstanding != 0 or total_billed > 0:
            results.append({
                'vendor': vendor,
                'total_billed': float(total_billed),
                'total_incoming': float(total_incoming),
                'total_outgoing': float(total_outgoing),
                'outstanding': outstanding
            })
    
    pdf_buffer = generate_outstanding_pdf(results)
    filename = f"outstanding_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    
    return Response(
        pdf_buffer.getvalue(),
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@report_bp.route('/outstanding/export/excel')
@login_required
@permission_required('view_reports')
def outstanding_export_excel():
    tenant = get_default_tenant()
    if not tenant:
        flash('Tenant not found.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    vendors = Vendor.query.filter_by(tenant_id=tenant.id).all()
    results = []
    
    for vendor in vendors:
        total_billed = db.session.query(func.sum(Bill.amount_total)).filter_by(
            tenant_id=tenant.id, vendor_id=vendor.id, status='CONFIRMED'
        ).scalar() or 0
        
        total_incoming = db.session.query(func.sum(CreditEntry.amount)).filter_by(
            tenant_id=tenant.id, vendor_id=vendor.id, direction='INCOMING'
        ).scalar() or 0
        
        total_outgoing = db.session.query(func.sum(CreditEntry.amount)).filter_by(
            tenant_id=tenant.id, vendor_id=vendor.id, direction='OUTGOING'
        ).scalar() or 0
        
        outstanding = float(total_billed) - float(total_incoming) + float(total_outgoing)
        
        if outstanding != 0 or total_billed > 0:
            results.append({
                'vendor': vendor,
                'total_billed': float(total_billed),
                'total_incoming': float(total_incoming),
                'total_outgoing': float(total_outgoing),
                'outstanding': outstanding
            })
    
    excel_buffer = generate_outstanding_excel(results)
    filename = f"outstanding_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    return Response(
        excel_buffer.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


# Export routes for Collection Report
@report_bp.route('/collection/export/pdf', methods=['GET', 'POST'])
@login_required
@permission_required('view_reports')
def collection_export_pdf():
    tenant = get_default_tenant()
    if not tenant:
        flash('Tenant not found.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    # Get date range from query parameters or form
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    if not start_date_str or not end_date_str:
        flash('Date range is required for export.', 'danger')
        return redirect(url_for('report.collection'))
    
    from datetime import datetime as dt
    try:
        start_date = dt.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = dt.strptime(end_date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format.', 'danger')
        return redirect(url_for('report.collection'))
    
    total_incoming = db.session.query(func.sum(CreditEntry.amount)).filter(
        CreditEntry.tenant_id == tenant.id,
        CreditEntry.direction == 'INCOMING',
        CreditEntry.payment_date >= start_date,
        CreditEntry.payment_date <= end_date
    ).scalar() or 0
    
    total_outgoing = db.session.query(func.sum(CreditEntry.amount)).filter(
        CreditEntry.tenant_id == tenant.id,
        CreditEntry.direction == 'OUTGOING',
        CreditEntry.payment_date >= start_date,
        CreditEntry.payment_date <= end_date
    ).scalar() or 0
    
    net = float(total_incoming) - float(total_outgoing)
    
    results = {
        'start_date': start_date,
        'end_date': end_date,
        'total_incoming': float(total_incoming),
        'total_outgoing': float(total_outgoing),
        'net': net
    }
    
    pdf_buffer = generate_collection_pdf(results)
    filename = f"collection_report_{start_date.strftime('%Y%m%d')}_to_{end_date.strftime('%Y%m%d')}.pdf"
    
    return Response(
        pdf_buffer.getvalue(),
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@report_bp.route('/collection/export/excel', methods=['GET', 'POST'])
@login_required
@permission_required('view_reports')
def collection_export_excel():
    tenant = get_default_tenant()
    if not tenant:
        flash('Tenant not found.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    # Get date range from query parameters
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    if not start_date_str or not end_date_str:
        flash('Date range is required for export.', 'danger')
        return redirect(url_for('report.collection'))
    
    from datetime import datetime as dt
    try:
        start_date = dt.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = dt.strptime(end_date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format.', 'danger')
        return redirect(url_for('report.collection'))
    
    total_incoming = db.session.query(func.sum(CreditEntry.amount)).filter(
        CreditEntry.tenant_id == tenant.id,
        CreditEntry.direction == 'INCOMING',
        CreditEntry.payment_date >= start_date,
        CreditEntry.payment_date <= end_date
    ).scalar() or 0
    
    total_outgoing = db.session.query(func.sum(CreditEntry.amount)).filter(
        CreditEntry.tenant_id == tenant.id,
        CreditEntry.direction == 'OUTGOING',
        CreditEntry.payment_date >= start_date,
        CreditEntry.payment_date <= end_date
    ).scalar() or 0
    
    net = float(total_incoming) - float(total_outgoing)
    
    results = {
        'start_date': start_date,
        'end_date': end_date,
        'total_incoming': float(total_incoming),
        'total_outgoing': float(total_outgoing),
        'net': net
    }
    
    excel_buffer = generate_collection_excel(results)
    filename = f"collection_report_{start_date.strftime('%Y%m%d')}_to_{end_date.strftime('%Y%m%d')}.xlsx"
    
    return Response(
        excel_buffer.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


# Export routes for Deliveries Report
@report_bp.route('/deliveries/export/pdf')
@login_required
@permission_required('view_reports')
def deliveries_export_pdf():
    tenant = get_default_tenant()
    if not tenant:
        flash('Tenant not found.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    stats, delivery_orders, _filters, _active_filters = _delivery_report_data(tenant)
    
    pdf_buffer = generate_deliveries_pdf(stats, delivery_orders)
    filename = f"deliveries_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    
    return Response(
        pdf_buffer.getvalue(),
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@report_bp.route('/deliveries/export/excel')
@login_required
@permission_required('view_reports')
def deliveries_export_excel():
    tenant = get_default_tenant()
    if not tenant:
        flash('Tenant not found.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    stats, delivery_orders, _filters, _active_filters = _delivery_report_data(tenant)
    
    excel_buffer = generate_deliveries_excel(stats, delivery_orders)
    filename = f"deliveries_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    return Response(
        excel_buffer.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

