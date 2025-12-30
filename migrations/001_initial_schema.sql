-- Supabase PostgreSQL Migration Script
-- Initial Schema for Skanda Credit & Billing System
-- This script creates all tables with proper PostgreSQL data types and constraints

-- Enable UUID extension (if needed in future)
-- CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Table: tenants
CREATE TABLE IF NOT EXISTS tenants (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    code VARCHAR(50) UNIQUE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: users
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    username VARCHAR(80) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('ADMIN', 'SALESMAN', 'DELIVERY', 'ORGANISER')),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: vendors
CREATE TABLE IF NOT EXISTS vendors (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    type VARCHAR(20) NOT NULL CHECK (type IN ('SUPPLIER', 'CUSTOMER', 'BOTH')),
    contact_phone VARCHAR(20),
    email VARCHAR(100),
    address TEXT,
    gst_number VARCHAR(50),
    credit_limit NUMERIC(12, 2) DEFAULT 0.00,
    -- Additional fields for Excel import
    customer_code VARCHAR(100),
    billing_address TEXT,
    shipping_address TEXT,
    pincode VARCHAR(20),
    city VARCHAR(100),
    country VARCHAR(100),
    state VARCHAR(100),
    status VARCHAR(20), -- ACTIVE/INACTIVE
    block_status VARCHAR(10), -- YES/NO
    contact_person VARCHAR(200),
    alternate_name VARCHAR(200),
    alternate_mobile VARCHAR(20),
    whatsapp_no VARCHAR(20),
    pan VARCHAR(50),
    additional_data TEXT, -- JSON string for other fields
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: bills
CREATE TABLE IF NOT EXISTS bills (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    vendor_id INTEGER NOT NULL REFERENCES vendors(id) ON DELETE RESTRICT,
    bill_number VARCHAR(100) NOT NULL,
    bill_date DATE NOT NULL,
    bill_type VARCHAR(20) NOT NULL CHECK (bill_type IN ('NORMAL', 'HANDBILL')),
    status VARCHAR(20) DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    amount_subtotal NUMERIC(12, 2) DEFAULT 0.00,
    amount_tax NUMERIC(12, 2) DEFAULT 0.00,
    amount_total NUMERIC(12, 2) DEFAULT 0.00,
    ocr_text TEXT,
    image_path VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Authorization fields
    is_authorized BOOLEAN DEFAULT FALSE,
    authorized_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    authorized_at TIMESTAMP,
    -- OCR extracted fields
    delivery_date DATE,
    billed_to_name VARCHAR(200),
    shipped_to_name VARCHAR(200),
    delivery_recipient VARCHAR(200), -- DR field
    post VARCHAR(100)
);

-- Table: bill_items
CREATE TABLE IF NOT EXISTS bill_items (
    id SERIAL PRIMARY KEY,
    bill_id INTEGER NOT NULL REFERENCES bills(id) ON DELETE CASCADE,
    description VARCHAR(500) NOT NULL,
    quantity NUMERIC(10, 2) NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,
    amount NUMERIC(12, 2) NOT NULL
);

-- Table: proxy_bills
CREATE TABLE IF NOT EXISTS proxy_bills (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    parent_bill_id INTEGER NOT NULL REFERENCES bills(id) ON DELETE RESTRICT,
    vendor_id INTEGER NOT NULL REFERENCES vendors(id) ON DELETE RESTRICT,
    proxy_number VARCHAR(100) NOT NULL,
    status VARCHAR(20) DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    amount_total NUMERIC(12, 2) DEFAULT 0.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: proxy_bill_items
CREATE TABLE IF NOT EXISTS proxy_bill_items (
    id SERIAL PRIMARY KEY,
    proxy_bill_id INTEGER NOT NULL REFERENCES proxy_bills(id) ON DELETE CASCADE,
    description VARCHAR(500) NOT NULL,
    quantity NUMERIC(10, 2) NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,
    amount NUMERIC(12, 2) NOT NULL
);

-- Table: credit_entries
CREATE TABLE IF NOT EXISTS credit_entries (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    bill_id INTEGER REFERENCES bills(id) ON DELETE SET NULL,
    proxy_bill_id INTEGER REFERENCES proxy_bills(id) ON DELETE SET NULL,
    vendor_id INTEGER NOT NULL REFERENCES vendors(id) ON DELETE RESTRICT,
    amount NUMERIC(12, 2) NOT NULL,
    direction VARCHAR(20) NOT NULL CHECK (direction IN ('INCOMING', 'OUTGOING')),
    payment_method VARCHAR(20) NOT NULL CHECK (payment_method IN ('CASH', 'UPI', 'BANK', 'CHEQUE', 'CARD')),
    payment_date DATE NOT NULL,
    reference_number VARCHAR(100),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: delivery_orders
CREATE TABLE IF NOT EXISTS delivery_orders (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    bill_id INTEGER REFERENCES bills(id) ON DELETE SET NULL,
    proxy_bill_id INTEGER REFERENCES proxy_bills(id) ON DELETE SET NULL,
    delivery_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    delivery_address TEXT NOT NULL,
    delivery_date DATE NOT NULL,
    status VARCHAR(20) DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'IN_TRANSIT', 'DELIVERED', 'CANCELLED')),
    remarks TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: ocr_jobs
CREATE TABLE IF NOT EXISTS ocr_jobs (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    bill_id INTEGER NOT NULL REFERENCES bills(id) ON DELETE CASCADE,
    image_path VARCHAR(500) NOT NULL,
    raw_text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: audit_logs
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id INTEGER NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: permissions
CREATE TABLE IF NOT EXISTS permissions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(50) UNIQUE NOT NULL,
    description VARCHAR(255),
    category VARCHAR(50) NOT NULL CHECK (category IN ('BILL', 'CREDIT', 'DELIVERY', 'VENDOR', 'REPORT', 'ADMIN')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: role_permissions
CREATE TABLE IF NOT EXISTS role_permissions (
    id SERIAL PRIMARY KEY,
    role VARCHAR(20) NOT NULL CHECK (role IN ('ADMIN', 'SALESMAN', 'DELIVERY', 'ORGANISER')),
    permission_id INTEGER NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    granted BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(role, permission_id)
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_users_tenant_id ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_vendors_tenant_id ON vendors(tenant_id);
CREATE INDEX IF NOT EXISTS idx_bills_tenant_id ON bills(tenant_id);
CREATE INDEX IF NOT EXISTS idx_bills_vendor_id ON bills(vendor_id);
CREATE INDEX IF NOT EXISTS idx_bills_status ON bills(status);
CREATE INDEX IF NOT EXISTS idx_bills_bill_date ON bills(bill_date);
CREATE INDEX IF NOT EXISTS idx_bill_items_bill_id ON bill_items(bill_id);
CREATE INDEX IF NOT EXISTS idx_proxy_bills_tenant_id ON proxy_bills(tenant_id);
CREATE INDEX IF NOT EXISTS idx_proxy_bills_parent_bill_id ON proxy_bills(parent_bill_id);
CREATE INDEX IF NOT EXISTS idx_proxy_bills_vendor_id ON proxy_bills(vendor_id);
CREATE INDEX IF NOT EXISTS idx_proxy_bill_items_proxy_bill_id ON proxy_bill_items(proxy_bill_id);
CREATE INDEX IF NOT EXISTS idx_credit_entries_tenant_id ON credit_entries(tenant_id);
CREATE INDEX IF NOT EXISTS idx_credit_entries_vendor_id ON credit_entries(vendor_id);
CREATE INDEX IF NOT EXISTS idx_credit_entries_payment_date ON credit_entries(payment_date);
CREATE INDEX IF NOT EXISTS idx_delivery_orders_tenant_id ON delivery_orders(tenant_id);
CREATE INDEX IF NOT EXISTS idx_delivery_orders_delivery_user_id ON delivery_orders(delivery_user_id);
CREATE INDEX IF NOT EXISTS idx_delivery_orders_status ON delivery_orders(status);
CREATE INDEX IF NOT EXISTS idx_ocr_jobs_tenant_id ON ocr_jobs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_ocr_jobs_bill_id ON ocr_jobs(bill_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_tenant_id ON audit_logs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_role_permissions_role ON role_permissions(role);
CREATE INDEX IF NOT EXISTS idx_role_permissions_permission_id ON role_permissions(permission_id);

-- Add comments for documentation
COMMENT ON TABLE tenants IS 'Multi-tenant support table';
COMMENT ON TABLE users IS 'User accounts with role-based access';
COMMENT ON TABLE vendors IS 'Suppliers and customers';
COMMENT ON TABLE bills IS 'Main billing entity';
COMMENT ON TABLE bill_items IS 'Line items for bills';
COMMENT ON TABLE proxy_bills IS 'Split bills for end customers';
COMMENT ON TABLE proxy_bill_items IS 'Line items for proxy bills';
COMMENT ON TABLE credit_entries IS 'Payment tracking (incoming/outgoing)';
COMMENT ON TABLE delivery_orders IS 'Delivery order management';
COMMENT ON TABLE ocr_jobs IS 'OCR processing jobs';
COMMENT ON TABLE audit_logs IS 'Action audit trail';
COMMENT ON TABLE permissions IS 'Permission definitions';
COMMENT ON TABLE role_permissions IS 'Role-permission mappings';

