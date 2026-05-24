from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import ProxyBill, ProxyBillItem, Bill, Vendor, Tenant, CreditEntry
from forms import ProxyBillForm
from extensions import db
from audit import log_action
from auth_routes import permission_required
from decimal import Decimal
from sqlalchemy import func

proxy_bp = Blueprint('proxy', __name__)


def get_default_tenant():
    return Tenant.query.filter_by(code='skanda').first()


def get_or_create_customer_vendor(tenant_id, vendor_id=None, manual_name=None):
    if vendor_id:
        return Vendor.query.filter_by(tenant_id=tenant_id, id=vendor_id).first()
    name = (manual_name or '').strip()
    if not name:
        return None
    existing = Vendor.query.filter(
        Vendor.tenant_id == tenant_id,
        func.lower(Vendor.name) == name.lower()
    ).first()
    if existing:
        return existing
    vendor = Vendor(tenant_id=tenant_id, name=name, type='CUSTOMER')
    db.session.add(vendor)
    db.session.flush()
    return vendor


@proxy_bp.route('/')
@login_required
@permission_required('view_bills')
def list():
    tenant = get_default_tenant()
    if not tenant:
        flash('Tenant not found.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    proxy_bills = ProxyBill.query.filter_by(tenant_id=tenant.id).order_by(ProxyBill.created_at.desc()).all()
    return render_template('proxy_bills/list.html', proxy_bills=proxy_bills)


@proxy_bp.route('/new', methods=['GET', 'POST'])
@login_required
@permission_required('create_bill')
def create():
    tenant = get_default_tenant()
    if not tenant:
        flash('Tenant not found.', 'danger')
        return redirect(url_for('proxy.list'))
    
    form = ProxyBillForm()
    form.parent_bill_id.choices = [(b.id, f"{b.bill_number} - {b.vendor.name}") 
                                   for b in Bill.query.filter_by(tenant_id=tenant.id, status='CONFIRMED').all()]
    form.vendor_id.choices = [('', 'Select existing vendor')] + [
        (v.id, v.name) for v in Vendor.query.filter_by(tenant_id=tenant.id).order_by(Vendor.name).all()
    ]
    
    # Pre-fill from query params
    parent_bill_id = request.args.get('parent_bill_id', type=int)
    if parent_bill_id:
        form.parent_bill_id.data = parent_bill_id
    
    if form.validate_on_submit():
        vendor = get_or_create_customer_vendor(
            tenant.id,
            form.vendor_id.data,
            form.manual_vendor_name.data,
        )
        if not vendor:
            flash('Choose an existing vendor or enter a new vendor name.', 'danger')
            return render_template('proxy_bills/form.html', form=form, title='New Proxy Bill')

        # Get items from request
        descriptions = request.form.getlist('item_description[]')
        quantities = request.form.getlist('item_quantity[]')
        unit_prices = request.form.getlist('item_unit_price[]')
        
        # Calculate total
        total = Decimal('0.00')
        items = []
        
        for i in range(len(descriptions)):
            if descriptions[i].strip():
                qty = Decimal(quantities[i] or '0')
                price = Decimal(unit_prices[i] or '0')
                amount = qty * price
                total += amount
                items.append({
                    'description': descriptions[i],
                    'quantity': qty,
                    'unit_price': price,
                    'amount': amount
                })
        
        proxy_bill = ProxyBill(
            tenant_id=tenant.id,
            parent_bill_id=form.parent_bill_id.data,
            vendor_id=vendor.id,
            proxy_number=form.proxy_number.data,
            status='DRAFT',
            amount_total=total
        )
        db.session.add(proxy_bill)
        db.session.flush()
        
        # Add items
        for item_data in items:
            item = ProxyBillItem(
                proxy_bill_id=proxy_bill.id,
                description=item_data['description'],
                quantity=item_data['quantity'],
                unit_price=item_data['unit_price'],
                amount=item_data['amount']
            )
            db.session.add(item)
        
        db.session.commit()
        log_action(current_user, 'CREATE_PROXY_BILL', 'PROXY_BILL', proxy_bill.id)
        flash('Proxy bill created successfully.', 'success')
        return redirect(url_for('proxy.detail', id=proxy_bill.id))
    
    return render_template('proxy_bills/form.html', form=form, title='New Proxy Bill')


@proxy_bp.route('/<int:id>')
@login_required
@permission_required('view_bills')
def detail(id):
    proxy_bill = ProxyBill.query.get_or_404(id)
    credits = CreditEntry.query.filter_by(proxy_bill_id=proxy_bill.id).all()
    return render_template('proxy_bills/detail.html', proxy_bill=proxy_bill, credits=credits)


@proxy_bp.route('/<int:id>/confirm', methods=['POST'])
@login_required
@permission_required('confirm_bill')
def confirm(id):
    proxy_bill = ProxyBill.query.get_or_404(id)
    if proxy_bill.status == 'DRAFT':
        proxy_bill.status = 'CONFIRMED'
        db.session.commit()
        log_action(current_user, 'CONFIRM_PROXY_BILL', 'PROXY_BILL', proxy_bill.id)
        flash('Proxy bill confirmed.', 'success')
    return redirect(url_for('proxy.detail', id=proxy_bill.id))


@proxy_bp.route('/<int:id>/cancel', methods=['POST'])
@login_required
@permission_required('cancel_bill')
def cancel(id):
    proxy_bill = ProxyBill.query.get_or_404(id)
    if proxy_bill.status != 'CANCELLED':
        proxy_bill.status = 'CANCELLED'
        db.session.commit()
        log_action(current_user, 'CANCEL_PROXY_BILL', 'PROXY_BILL', proxy_bill.id)
        flash('Proxy bill cancelled.', 'success')
    return redirect(url_for('proxy.detail', id=proxy_bill.id))

