from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import Vendor, Tenant
from forms import VendorForm
from extensions import db
from audit import log_action
from sqlalchemy import or_
from auth_routes import permission_required

vendor_bp = Blueprint('vendor', __name__)


@vendor_bp.route('/')
@login_required
@permission_required('view_vendors')
def list():
    tenant = Tenant.query.filter_by(code='skanda').first()
    if not tenant:
        flash('Tenant not found.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    # Get filter parameters
    search = request.args.get('search', '').strip()
    type_filter = request.args.get('type', '')
    credit_limit_min = request.args.get('credit_limit_min', type=float)
    credit_limit_max = request.args.get('credit_limit_max', type=float)
    
    query = Vendor.query.filter_by(tenant_id=tenant.id)
    
    # Apply filters
    if search:
        query = query.filter(
            or_(
                Vendor.name.ilike(f'%{search}%'),
                Vendor.email.ilike(f'%{search}%'),
                Vendor.contact_phone.ilike(f'%{search}%')
            )
        )
    
    if type_filter:
        query = query.filter_by(type=type_filter)
    
    if credit_limit_min is not None:
        query = query.filter(Vendor.credit_limit >= credit_limit_min)
    
    if credit_limit_max is not None:
        query = query.filter(Vendor.credit_limit <= credit_limit_max)
    
    vendors = query.order_by(Vendor.name).all()
    
    # Prepare filter data for template
    filters = [
        {
            'name': 'search',
            'label': 'Search',
            'type': 'search',
            'placeholder': 'Search by name, email, or phone...',
            'value': search,
            'icon': 'bi-search',
            'col_size': 4
        },
        {
            'name': 'type',
            'label': 'Type',
            'type': 'select',
            'value': type_filter,
            'options': [
                {'value': 'SUPPLIER', 'label': 'Supplier'},
                {'value': 'CUSTOMER', 'label': 'Customer'},
                {'value': 'BOTH', 'label': 'Both'}
            ],
            'icon': 'bi-tag',
            'col_size': 2
        },
        {
            'name': 'credit_limit',
            'label': 'Credit Limit Range',
            'type': 'number-range',
            'value_min': credit_limit_min,
            'value_max': credit_limit_max,
            'icon': 'bi-currency-rupee',
            'col_size': 3
        }
    ]
    
    # Active filters for display
    active_filters = {}
    if search:
        active_filters['Search'] = search
    if type_filter:
        active_filters['Type'] = type_filter
    if credit_limit_min is not None or credit_limit_max is not None:
        active_filters['Credit Limit'] = f"₹{credit_limit_min or 0} - ₹{credit_limit_max or '∞'}"
    
    return render_template('vendors/list.html', vendors=vendors, type_filter=type_filter,
                         filters=filters, active_filters=active_filters)


@vendor_bp.route('/new', methods=['GET', 'POST'])
@login_required
@permission_required('create_vendor')
def create():
    tenant = Tenant.query.filter_by(code='skanda').first()
    if not tenant:
        flash('Tenant not found.', 'danger')
        return redirect(url_for('vendor.list'))
    
    form = VendorForm()
    if form.validate_on_submit():
        vendor = Vendor(
            tenant_id=tenant.id,
            name=form.name.data,
            type=form.type.data,
            contact_phone=form.contact_phone.data,
            email=form.email.data,
            address=form.address.data,
            gst_number=form.gst_number.data,
            credit_limit=form.credit_limit.data or 0.00
        )
        db.session.add(vendor)
        db.session.commit()
        log_action(current_user, 'CREATE_VENDOR', 'VENDOR', vendor.id)
        flash('Vendor created successfully.', 'success')
        return redirect(url_for('vendor.list'))
    
    return render_template('vendors/form.html', form=form, title='New Vendor')


@vendor_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required('edit_vendor')
def edit(id):
    vendor = Vendor.query.get_or_404(id)
    form = VendorForm(obj=vendor)
    
    if form.validate_on_submit():
        vendor.name = form.name.data
        vendor.type = form.type.data
        vendor.contact_phone = form.contact_phone.data
        vendor.email = form.email.data
        vendor.address = form.address.data
        vendor.gst_number = form.gst_number.data
        vendor.credit_limit = form.credit_limit.data or 0.00
        db.session.commit()
        log_action(current_user, 'UPDATE_VENDOR', 'VENDOR', vendor.id)
        flash('Vendor updated successfully.', 'success')
        return redirect(url_for('vendor.list'))
    
    return render_template('vendors/form.html', form=form, vendor=vendor, title='Edit Vendor')


@vendor_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@permission_required('delete_vendor')
def delete(id):
    from models import Bill, ProxyBill, CreditEntry
    
    vendor = Vendor.query.get_or_404(id)
    
    # Check if vendor has associated bills
    bill_count = Bill.query.filter_by(vendor_id=vendor.id).count()
    proxy_bill_count = ProxyBill.query.filter_by(vendor_id=vendor.id).count()
    credit_count = CreditEntry.query.filter_by(vendor_id=vendor.id).count()
    
    if bill_count > 0 or proxy_bill_count > 0 or credit_count > 0:
        error_msg = f'Cannot delete vendor "{vendor.name}" because it has '
        parts = []
        if bill_count > 0:
            parts.append(f'{bill_count} bill(s)')
        if proxy_bill_count > 0:
            parts.append(f'{proxy_bill_count} proxy bill(s)')
        if credit_count > 0:
            parts.append(f'{credit_count} credit entr{"y" if credit_count == 1 else "ies"}')
        error_msg += ', '.join(parts) + ' associated with it.'
        flash(error_msg, 'danger')
        return redirect(url_for('vendor.list'))
    
    # Safe to delete - no associated records
    db.session.delete(vendor)
    db.session.commit()
    log_action(current_user, 'DELETE_VENDOR', 'VENDOR', vendor.id)
    flash('Vendor deleted successfully.', 'success')
    return redirect(url_for('vendor.list'))

