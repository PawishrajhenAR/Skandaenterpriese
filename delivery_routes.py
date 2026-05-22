from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import DeliveryOrder, Bill, ProxyBill, User, Tenant, Vendor
from forms import DeliveryOrderForm
from extensions import db
from audit import log_action
from auth_routes import permission_required
from sqlalchemy import or_
from datetime import datetime

delivery_bp = Blueprint('delivery', __name__)


def get_default_tenant():
    return Tenant.query.filter_by(code='skanda').first()


@delivery_bp.route('/')
@login_required
@permission_required('view_deliveries')
def list():
    tenant = get_default_tenant()
    if not tenant:
        flash('Tenant not found.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    # Get filter parameters
    search = request.args.get('search', '').strip()
    status = request.args.get('status', '')
    delivery_user_id = request.args.get('delivery_user_id', type=int)
    vendor_id = request.args.get('vendor_id', type=int)
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    # Start with base query
    if current_user.role == 'DELIVERY':
        query = DeliveryOrder.query.filter_by(
            tenant_id=tenant.id, delivery_user_id=current_user.id
        )
    else:
        query = DeliveryOrder.query.filter_by(tenant_id=tenant.id)
    
    # Apply filters
    if search:
        query = query.filter(
            DeliveryOrder.delivery_address.ilike(f'%{search}%')
        )
    
    if status:
        query = query.filter(DeliveryOrder.status == status)
    
    if delivery_user_id:
        query = query.filter(DeliveryOrder.delivery_user_id == delivery_user_id)
    
    if vendor_id:
        # Filter by vendor through bill or proxy bill
        bill_ids = [b.id for b in Bill.query.filter_by(tenant_id=tenant.id, vendor_id=vendor_id).all()]
        proxy_bill_ids = [pb.id for pb in ProxyBill.query.filter_by(tenant_id=tenant.id, vendor_id=vendor_id).all()]
        query = query.filter(
            or_(
                DeliveryOrder.bill_id.in_(bill_ids),
                DeliveryOrder.proxy_bill_id.in_(proxy_bill_ids)
            )
        )
    
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
            query = query.filter(DeliveryOrder.delivery_date >= date_from_obj)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
            query = query.filter(DeliveryOrder.delivery_date <= date_to_obj)
        except ValueError:
            pass
    
    deliveries = query.order_by(DeliveryOrder.delivery_date.desc()).all()
    
    # Get data for filter dropdowns
    delivery_users = User.query.filter_by(tenant_id=tenant.id, role='DELIVERY', is_active=True).all()
    vendors = Vendor.query.filter_by(tenant_id=tenant.id).order_by(Vendor.name).all()
    
    # Prepare filter data for template
    filters = [
        {
            'name': 'search',
            'label': 'Search Address',
            'type': 'search',
            'placeholder': 'Search by address...',
            'value': search,
            'icon': 'bi-search',
            'col_size': 3
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
                {'value': 'CANCELLED', 'label': 'Cancelled'}
            ],
            'icon': 'bi-flag',
            'col_size': 2
        },
        {
            'name': 'delivery_user_id',
            'label': 'Delivery User',
            'type': 'select',
            'value': delivery_user_id,
            'options': [{'value': u.id, 'label': u.username} for u in delivery_users],
            'icon': 'bi-person',
            'col_size': 2
        },
        {
            'name': 'vendor_id',
            'label': 'Vendor',
            'type': 'select',
            'value': vendor_id,
            'options': [{'value': v.id, 'label': v.name} for v in vendors],
            'icon': 'bi-shop',
            'col_size': 2
        },
        {
            'name': 'delivery_date',
            'label': 'Date Range',
            'type': 'date-range',
            'value_from': date_from,
            'value_to': date_to,
            'icon': 'bi-calendar',
            'col_size': 3
        }
    ]
    
    # Active filters for display
    active_filters = {}
    if search:
        active_filters['Search'] = search
    if status:
        active_filters['Status'] = status
    if delivery_user_id:
        user = User.query.get(delivery_user_id)
        if user:
            active_filters['User'] = user.username
    if vendor_id:
        vendor = Vendor.query.get(vendor_id)
        if vendor:
            active_filters['Vendor'] = vendor.name
    if date_from or date_to:
        active_filters['Date'] = f"{date_from or 'Any'} to {date_to or 'Any'}"
    
    return render_template('deliveries/list.html', deliveries=deliveries, 
                         filters=filters, active_filters=active_filters)


@delivery_bp.route('/new', methods=['GET', 'POST'])
@login_required
@permission_required('create_delivery')
def create():
    tenant = get_default_tenant()
    if not tenant:
        flash('Tenant not found.', 'danger')
        return redirect(url_for('delivery.list'))
    
    form = DeliveryOrderForm()
    
    # Pre-fill from query params
    bill_id = request.args.get('bill_id', type=int)
    proxy_bill_id = request.args.get('proxy_bill_id', type=int)
    
    form.bill_id.choices = [('', 'None')] + [(b.id, f"{b.bill_number} - {b.vendor.name}") 
                                              for b in Bill.query.filter_by(tenant_id=tenant.id).all()]
    form.proxy_bill_id.choices = [('', 'None')] + [(pb.id, f"{pb.proxy_number} - {pb.vendor.name}") 
                                                    for pb in ProxyBill.query.filter_by(tenant_id=tenant.id).all()]
    form.delivery_user_id.choices = [(u.id, u.username) for u in User.query.filter_by(
        tenant_id=tenant.id, role='DELIVERY', is_active=True
    ).all()]
    
    if bill_id:
        form.bill_id.data = bill_id
    
    if proxy_bill_id:
        form.proxy_bill_id.data = proxy_bill_id
    
    if form.validate_on_submit():
        bill_id_val = form.bill_id.data if form.bill_id.data and form.bill_id.data != '' else None
        proxy_bill_id_val = form.proxy_bill_id.data if form.proxy_bill_id.data and form.proxy_bill_id.data != '' else None
        
        delivery = DeliveryOrder(
            tenant_id=tenant.id,
            bill_id=bill_id_val,
            proxy_bill_id=proxy_bill_id_val,
            delivery_user_id=form.delivery_user_id.data,
            delivery_address=form.delivery_address.data,
            delivery_date=form.delivery_date.data,
            status='PENDING',
            remarks=form.remarks.data
        )
        db.session.add(delivery)
        db.session.commit()
        log_action(current_user, 'CREATE_DELIVERY', 'DELIVERY_ORDER', delivery.id)
        flash('Delivery order created successfully.', 'success')
        return redirect(url_for('delivery.list'))
    
    return render_template('deliveries/form.html', form=form, title='New Delivery Order')


@delivery_bp.route('/<int:id>')
@login_required
@permission_required('view_deliveries')
def detail(id):
    tenant = get_default_tenant()
    delivery = DeliveryOrder.query.filter_by(tenant_id=tenant.id, id=id).first_or_404()
    if current_user.role == 'DELIVERY' and delivery.delivery_user_id != current_user.id:
        flash('Delivery order not found.', 'danger')
        return redirect(url_for('delivery.list'))
    return render_template('deliveries/detail.html', delivery=delivery)


@delivery_bp.route('/<int:id>/update-status', methods=['POST'])
@login_required
@permission_required('update_delivery')
def update_status(id):
    tenant = get_default_tenant()
    delivery = DeliveryOrder.query.filter_by(tenant_id=tenant.id, id=id).first_or_404()
    if current_user.role == 'DELIVERY' and delivery.delivery_user_id != current_user.id:
        flash('Delivery order not found.', 'danger')
        return redirect(url_for('delivery.list'))
    new_status = request.form.get('status')
    
    if new_status in ['PENDING', 'IN_TRANSIT', 'DELIVERED', 'CANCELLED']:
        delivery.status = new_status
        db.session.commit()
        log_action(current_user, 'UPDATE_DELIVERY_STATUS', 'DELIVERY_ORDER', delivery.id)
        flash('Delivery status updated.', 'success')
    
    return redirect(url_for('delivery.detail', id=delivery.id))

