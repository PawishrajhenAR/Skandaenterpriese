from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db


class Tenant(db.Model):
    __tablename__ = 'tenants'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    code = db.Column(db.String(50), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    
    users = db.relationship('User', backref='tenant', lazy=True)
    vendors = db.relationship('Vendor', backref='tenant', lazy=True)
    bills = db.relationship('Bill', backref='tenant', lazy=True)
    proxy_bills = db.relationship('ProxyBill', backref='tenant', lazy=True)
    credit_entries = db.relationship('CreditEntry', backref='tenant', lazy=True)
    delivery_orders = db.relationship('DeliveryOrder', backref='tenant', lazy=True)
    ocr_jobs = db.relationship('OCRJob', backref='tenant', lazy=True)
    audit_logs = db.relationship('AuditLog', backref='tenant', lazy=True)


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # ADMIN, SALESMAN, DELIVERY, ORGANISER
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    delivery_orders = db.relationship('DeliveryOrder', backref='delivery_user', lazy=True)
    audit_logs = db.relationship('AuditLog', backref='user', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def has_permission(self, permission_code):
        """Check if user has a specific permission"""
        # Admin always has all permissions
        if self.role == 'ADMIN':
            return True
        
        # Check role-based permissions
        permission = Permission.query.filter_by(code=permission_code).first()
        if not permission:
            return False
        
        role_perm = RolePermission.query.filter_by(
            role=self.role,
            permission_id=permission.id,
            granted=True
        ).first()
        
        return role_perm is not None


class Vendor(db.Model):
    __tablename__ = 'vendors'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # SUPPLIER, CUSTOMER, BOTH
    contact_phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    address = db.Column(db.Text)
    gst_number = db.Column(db.String(50))
    credit_limit = db.Column(db.Numeric(12, 2), default=0.00)
    
    bills = db.relationship('Bill', backref='vendor', lazy=True)
    proxy_bills = db.relationship('ProxyBill', backref='vendor', lazy=True)
    credit_entries = db.relationship('CreditEntry', backref='vendor', lazy=True)


class Bill(db.Model):
    __tablename__ = 'bills'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendors.id'), nullable=False)
    bill_number = db.Column(db.String(100), nullable=False)
    bill_date = db.Column(db.Date, nullable=False)
    bill_type = db.Column(db.String(20), nullable=False)  # NORMAL, HANDBILL
    status = db.Column(db.String(20), default='DRAFT')  # DRAFT, CONFIRMED, CANCELLED
    amount_subtotal = db.Column(db.Numeric(12, 2), default=0.00)
    amount_tax = db.Column(db.Numeric(12, 2), default=0.00)
    amount_total = db.Column(db.Numeric(12, 2), default=0.00)
    ocr_text = db.Column(db.Text)
    image_path = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Authorization fields
    is_authorized = db.Column(db.Boolean, default=False)  # Admin authorization required
    authorized_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    authorized_at = db.Column(db.DateTime, nullable=True)
    # OCR extracted fields
    delivery_date = db.Column(db.Date, nullable=True)
    billed_to_name = db.Column(db.String(200), nullable=True)
    shipped_to_name = db.Column(db.String(200), nullable=True)
    delivery_recipient = db.Column(db.String(200), nullable=True)  # DR field
    post = db.Column(db.String(100), nullable=True)
    
    items = db.relationship('BillItem', backref='bill', lazy=True, cascade='all, delete-orphan')
    proxy_bills = db.relationship('ProxyBill', backref='parent_bill', lazy=True)
    credit_entries = db.relationship('CreditEntry', backref='bill', lazy=True)
    delivery_orders = db.relationship('DeliveryOrder', backref='bill', lazy=True)
    ocr_jobs = db.relationship('OCRJob', backref='bill', lazy=True)
    authorizer = db.relationship('User', foreign_keys=[authorized_by], backref='authorized_bills')


class BillItem(db.Model):
    __tablename__ = 'bill_items'
    
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bills.id'), nullable=False)
    description = db.Column(db.String(500), nullable=False)
    quantity = db.Column(db.Numeric(10, 2), nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)


class ProxyBill(db.Model):
    __tablename__ = 'proxy_bills'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    parent_bill_id = db.Column(db.Integer, db.ForeignKey('bills.id'), nullable=False)
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendors.id'), nullable=False)
    proxy_number = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='DRAFT')  # DRAFT, CONFIRMED, CANCELLED
    amount_total = db.Column(db.Numeric(12, 2), default=0.00)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    items = db.relationship('ProxyBillItem', backref='proxy_bill', lazy=True, cascade='all, delete-orphan')
    credit_entries = db.relationship('CreditEntry', backref='proxy_bill', lazy=True)
    delivery_orders = db.relationship('DeliveryOrder', backref='proxy_bill', lazy=True)


class ProxyBillItem(db.Model):
    __tablename__ = 'proxy_bill_items'
    
    id = db.Column(db.Integer, primary_key=True)
    proxy_bill_id = db.Column(db.Integer, db.ForeignKey('proxy_bills.id'), nullable=False)
    description = db.Column(db.String(500), nullable=False)
    quantity = db.Column(db.Numeric(10, 2), nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)


class CreditEntry(db.Model):
    __tablename__ = 'credit_entries'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    bill_id = db.Column(db.Integer, db.ForeignKey('bills.id'), nullable=True)
    proxy_bill_id = db.Column(db.Integer, db.ForeignKey('proxy_bills.id'), nullable=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendors.id'), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    direction = db.Column(db.String(20), nullable=False)  # INCOMING, OUTGOING
    payment_method = db.Column(db.String(20), nullable=False)  # CASH, UPI, BANK, CHEQUE, CARD
    payment_date = db.Column(db.Date, nullable=False)
    reference_number = db.Column(db.String(100))
    notes = db.Column(db.Text)


class DeliveryOrder(db.Model):
    __tablename__ = 'delivery_orders'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    bill_id = db.Column(db.Integer, db.ForeignKey('bills.id'), nullable=True)
    proxy_bill_id = db.Column(db.Integer, db.ForeignKey('proxy_bills.id'), nullable=True)
    delivery_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    delivery_address = db.Column(db.Text, nullable=False)
    delivery_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='PENDING')  # PENDING, IN_TRANSIT, DELIVERED, CANCELLED
    remarks = db.Column(db.Text)


class OCRJob(db.Model):
    __tablename__ = 'ocr_jobs'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    bill_id = db.Column(db.Integer, db.ForeignKey('bills.id'), nullable=False)
    image_path = db.Column(db.String(500), nullable=False)
    raw_text = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(50), nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class Permission(db.Model):
    __tablename__ = 'permissions'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(255))
    category = db.Column(db.String(50), nullable=False)  # BILL, CREDIT, DELIVERY, VENDOR, REPORT, ADMIN
    
    role_permissions = db.relationship('RolePermission', backref='permission', lazy=True)


class RolePermission(db.Model):
    __tablename__ = 'role_permissions'
    
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(20), nullable=False)  # ADMIN, SALESMAN, DELIVERY, ORGANISER
    permission_id = db.Column(db.Integer, db.ForeignKey('permissions.id'), nullable=False)
    granted = db.Column(db.Boolean, default=True)

