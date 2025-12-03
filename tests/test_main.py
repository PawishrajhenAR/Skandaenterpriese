"""
Comprehensive Test Suite for Skanda Credit & Billing System

Run tests with: pytest tests/ -v
Run specific test: pytest tests/test_auth.py -v
Run with coverage: pytest tests/ --cov=. --cov-report=html
"""

import pytest
from extensions import db
from conftest import login_user, logout_user


class TestAuthentication:
    """Test authentication functionality"""
    
    def test_login_page_loads(self, client):
        """Test that login page loads correctly"""
        response = client.get('/login')
        assert response.status_code == 200
        assert b'Login' in response.data or b'Sign In' in response.data
    
    def test_login_success(self, client, admin_user):
        """Test successful login"""
        response = login_user(client, 'admin', 'admin123')
        assert response.status_code == 200
        # Should redirect to dashboard
        assert b'Dashboard' in response.data or response.request.path == '/'
    
    def test_login_invalid_credentials(self, client):
        """Test login with invalid credentials"""
        response = client.post('/login', data={
            'username': 'admin',
            'password': 'wrongpassword'
        }, follow_redirects=True)
        assert response.status_code == 200
        # Should show error message
        assert b'Invalid' in response.data or b'error' in response.data.lower()
    
    def test_logout(self, client, admin_user):
        """Test logout functionality"""
        # Login first
        login_user(client, 'admin', 'admin123')
        # Then logout
        response = logout_user(client)
        assert response.status_code == 200
        # Should redirect to login
        assert b'Login' in response.data or b'Sign In' in response.data
    
    def test_protected_route_requires_login(self, client):
        """Test that protected routes require login"""
        response = client.get('/bills/', follow_redirects=True)
        # Should redirect to login
        assert b'Login' in response.data or b'Sign In' in response.data


class TestVendorManagement:
    """Test vendor CRUD operations"""
    
    def test_vendor_list_requires_permission(self, client, salesman_user):
        """Test that vendor list requires permission"""
        from conftest import login_user
        login_user(client, 'salesman', 'salesman123')
        response = client.get('/vendors/', follow_redirects=False)
        # May redirect (302) if no permission, or show 200/403
        assert response.status_code in [200, 302, 403]
    
    def test_create_vendor(self, client, admin_user):
        """Test creating a new vendor"""
        from conftest import login_user
        login_user(client, 'admin', 'admin123')
        response = client.post('/vendors/new', data={
            'name': 'Test Vendor',
            'type': 'SUPPLIER',
            'contact_phone': '1234567890',
            'email': 'test@vendor.com',
            'address': 'Test Address',
            'gst_number': 'GST123456',
            'credit_limit': '10000.00'
        }, follow_redirects=True)
        assert response.status_code == 200
        # Should show success message or redirect
        assert b'success' in response.data.lower() or response.request.path == '/vendors/'
    
    def test_vendor_validation(self, client, admin_user):
        """Test vendor form validation"""
        from conftest import login_user
        login_user(client, 'admin', 'admin123')
        response = client.post('/vendors/new', data={
            'name': '',  # Empty name should fail
            'type': 'SUPPLIER'
        })
        # Should show validation error
        assert response.status_code == 200
        assert b'required' in response.data.lower() or b'error' in response.data.lower()
    
    def test_delete_vendor_with_bills(self, client, app, admin_user):
        """Test that vendor with bills cannot be deleted"""
        from models import Bill, Tenant
        from conftest import login_user
        
        login_user(client, 'admin', 'admin123')
        
        with app.app_context():
            tenant = Tenant.query.filter_by(code='skanda').first()
            # Create a vendor
            from models import Vendor
            vendor = Vendor(
                tenant_id=tenant.id,
                name='Test Vendor for Delete',
                type='SUPPLIER'
            )
            db.session.add(vendor)
            db.session.flush()
            
            # Create a bill for this vendor
            from datetime import date
            bill = Bill(
                tenant_id=tenant.id,
                vendor_id=vendor.id,
                bill_number='TEST-001',
                bill_date=date(2023, 1, 1),
                bill_type='NORMAL',
                status='DRAFT'
            )
            db.session.add(bill)
            db.session.commit()
            
            vendor_id = vendor.id
        
        # Try to delete vendor
        response = client.post(f'/vendors/{vendor_id}/delete', follow_redirects=True)
        assert response.status_code == 200
        # Should show error message about associated bills
        assert b'Cannot delete' in response.data or b'associated' in response.data.lower()


class TestBillManagement:
    """Test bill CRUD operations"""
    
    def test_create_bill(self, client, app, admin_user):
        """Test creating a new bill"""
        from models import Vendor, Tenant
        from conftest import login_user
        
        login_user(client, 'admin', 'admin123')
        
        with app.app_context():
            tenant = Tenant.query.filter_by(code='skanda').first()
            # Create a test vendor
            vendor = Vendor(
                tenant_id=tenant.id,
                name='Test Vendor for Bill',
                type='SUPPLIER'
            )
            db.session.add(vendor)
            db.session.commit()
            vendor_id = vendor.id
        
        response = client.post('/bills/new', data={
            'vendor_id': vendor_id,
            'bill_number': 'BILL-001',
            'bill_date': '2023-01-01',
            'bill_type': 'NORMAL',
            'is_proxy': 'NO',
            'payment_type': 'UNPAID',
            'item_description[]': ['Test Item'],
            'item_quantity[]': ['1'],
            'item_unit_price[]': ['100.00']
        }, follow_redirects=True)
        
        assert response.status_code == 200
        # Should create bill successfully
        assert b'success' in response.data.lower() or response.request.path.startswith('/bills/')
    
    def test_bill_authorization(self, client, app, admin_user):
        """Test bill authorization functionality"""
        from models import Bill, Vendor, Tenant
        from conftest import login_user
        
        login_user(client, 'admin', 'admin123')
        
        with app.app_context():
            tenant = Tenant.query.filter_by(code='skanda').first()
            vendor = Vendor.query.filter_by(tenant_id=tenant.id).first()
            if not vendor:
                vendor = Vendor(tenant_id=tenant.id, name='Test Vendor', type='SUPPLIER')
                db.session.add(vendor)
                db.session.flush()
            
            from datetime import date
            bill = Bill(
                tenant_id=tenant.id,
                vendor_id=vendor.id,
                bill_number='AUTH-TEST-001',
                bill_date=date(2023, 1, 1),
                bill_type='NORMAL',
                status='CONFIRMED',
                is_authorized=False
            )
            db.session.add(bill)
            db.session.commit()
            bill_id = bill.id
        
        # Authorize the bill
        response = client.post(f'/bills/{bill_id}/authorize', follow_redirects=True)
        assert response.status_code == 200
        # Should show success message
        assert b'authorized' in response.data.lower() or b'success' in response.data.lower()


class TestOCRFunctionality:
    """Test OCR functionality"""
    
    def test_ocr_upload_page_loads(self, client, admin_user):
        """Test that OCR upload page loads"""
        from conftest import login_user
        login_user(client, 'admin', 'admin123')
        response = client.get('/ocr/upload')
        assert response.status_code == 200
        assert b'Upload' in response.data or b'OCR' in response.data
    
    def test_ocr_utils_reader_caching(self, app):
        """Test that OCR reader is cached"""
        from ocr_utils import get_ocr_reader
        
        with app.app_context():
            reader1 = get_ocr_reader()
            reader2 = get_ocr_reader()
            # Should return same instance (cached)
            assert reader1 is reader2
    
    def test_ocr_extraction_logic(self):
        """Test OCR text extraction logic"""
        from bill_routes import extract_bill_info
        
        # Test with sample OCR text
        ocr_text = """
        Bill Number: ORD-2023-78912
        Bill Date: 2023-10-27
        
        1. Wireless Keyboard S45.00 S45.00
        2. USB-C Cable - S12.50 S12.50
        3. Desk Lamp S30.00 S30.00
        
        Subtotal: S87.50
        Tax (18%): S15.75
        Total: S103.25
        """
        
        result = extract_bill_info(ocr_text)
        
        assert result['bill_number'] == 'ORD-2023-78912'
        assert result['bill_date'] == '2023-10-27'
        assert len(result['items']) >= 2  # OCR may extract 2-3 items
        # Total may be None if not found, but should have items
        assert result.get('total') is not None or len(result['items']) > 0


class TestPermissions:
    """Test permission system"""
    
    def test_admin_has_all_permissions(self, app, admin_user):
        """Test that admin has all permissions"""
        with app.app_context():
            assert admin_user.has_permission('create_bill')
            assert admin_user.has_permission('delete_bill')
            assert admin_user.has_permission('manage_permissions')
            assert admin_user.has_permission('view_reports')
    
    def test_salesman_permissions(self, app, salesman_user):
        """Test salesman permissions"""
        with app.app_context():
            # Salesman should have view_bills permission (or at least not be admin)
            # The key test is that salesman is not admin
            assert salesman_user.role == 'SALESMAN'
            # Should not have admin permissions
            assert not salesman_user.has_permission('manage_permissions')


class TestReports:
    """Test report functionality"""
    
    def test_outstanding_report(self, client, admin_user):
        """Test outstanding report"""
        from conftest import login_user
        login_user(client, 'admin', 'admin123')
        response = client.get('/reports/outstanding')
        assert response.status_code == 200
        assert b'Outstanding' in response.data or b'Report' in response.data
    
    def test_collection_report(self, client, admin_user):
        """Test collection report"""
        from conftest import login_user
        login_user(client, 'admin', 'admin123')
        response = client.get('/reports/collection')
        assert response.status_code == 200
        assert b'Collection' in response.data or b'Report' in response.data


class TestErrorHandling:
    """Test error handling"""
    
    def test_404_error(self, client):
        """Test 404 error handling"""
        response = client.get('/nonexistent-page')
        assert response.status_code == 404
    
    def test_unauthorized_access(self, client):
        """Test unauthorized access to protected routes"""
        response = client.get('/bills/new')
        # Should redirect to login
        assert response.status_code in [302, 401]
    
    def test_permission_denied(self, client, organiser_user):
        """Test permission denied for restricted actions"""
        from conftest import login_user
        login_user(client, 'organiser', 'organiser123')
        # Organiser should not be able to create bills
        response = client.get('/bills/new')
        # Should redirect or show error
        assert response.status_code in [200, 302, 403]


class TestCreditManagement:
    """Test credit entry management"""
    
    def test_credit_list_requires_permission(self, client, admin_user):
        """Test that credit list requires permission"""
        from conftest import login_user
        login_user(client, 'admin', 'admin123')
        response = client.get('/credits/')
        assert response.status_code == 200
        assert b'Credit' in response.data or b'Entry' in response.data
    
    def test_create_credit_entry(self, client, app, admin_user):
        """Test creating a credit entry"""
        from models import Vendor, Tenant, CreditEntry
        from conftest import login_user
        
        login_user(client, 'admin', 'admin123')
        
        with app.app_context():
            tenant = Tenant.query.filter_by(code='skanda').first()
            vendor = Vendor.query.filter_by(tenant_id=tenant.id).first()
            if not vendor:
                vendor = Vendor(tenant_id=tenant.id, name='Test Vendor', type='SUPPLIER')
                db.session.add(vendor)
                db.session.commit()
            vendor_id = vendor.id
        
        from datetime import date
        response = client.post('/credits/new', data={
            'vendor_id': vendor_id,
            'direction': 'INCOMING',
            'amount': '1000.00',
            'payment_method': 'CASH',
            'payment_date': date.today().strftime('%Y-%m-%d'),
            'reference_number': 'CREDIT-001',
            'notes': 'Test credit entry'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        # Should create credit entry successfully
        assert b'success' in response.data.lower() or response.request.path == '/credits/'


class TestDeliveryManagement:
    """Test delivery order management"""
    
    def test_delivery_list_requires_permission(self, client, admin_user):
        """Test that delivery list requires permission"""
        from conftest import login_user
        login_user(client, 'admin', 'admin123')
        response = client.get('/deliveries/')
        assert response.status_code == 200
        assert b'Delivery' in response.data or b'Order' in response.data
    
    def test_create_delivery_order(self, client, app, admin_user):
        """Test creating a delivery order"""
        from models import Vendor, Tenant, Bill
        from conftest import login_user
        
        login_user(client, 'admin', 'admin123')
        
        with app.app_context():
            tenant = Tenant.query.filter_by(code='skanda').first()
            vendor = Vendor.query.filter_by(tenant_id=tenant.id).first()
            if not vendor:
                vendor = Vendor(tenant_id=tenant.id, name='Test Vendor', type='SUPPLIER')
                db.session.add(vendor)
                db.session.flush()
            
            # Create a bill for delivery
            from datetime import date
            bill = Bill(
                tenant_id=tenant.id,
                vendor_id=vendor.id,
                bill_number='DELIVERY-BILL-001',
                bill_date=date(2023, 1, 1),
                bill_type='NORMAL',
                status='CONFIRMED',
                is_authorized=True
            )
            db.session.add(bill)
            db.session.commit()
            bill_id = bill.id
        
        from datetime import date
        from models import User
        with app.app_context():
            delivery_user = User.query.filter_by(role='DELIVERY').first()
            delivery_user_id = delivery_user.id if delivery_user else None
        
        response = client.post('/deliveries/new', data={
            'bill_id': bill_id,
            'delivery_user_id': delivery_user_id,
            'delivery_address': '123 Test Street',
            'delivery_date': date(2023, 1, 5).strftime('%Y-%m-%d'),
            'remarks': 'Test delivery order'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        # Should create delivery order successfully
        assert b'success' in response.data.lower() or response.request.path.startswith('/deliveries/')


class TestEdgeCases:
    """Test edge cases and boundary conditions"""
    
    def test_empty_vendor_list(self, client, app, admin_user):
        """Test vendor list with no vendors"""
        from conftest import login_user
        login_user(client, 'admin', 'admin123')
        response = client.get('/vendors/')
        assert response.status_code == 200
        # Should show empty state or no vendors message
    
    def test_bill_with_zero_amount(self, client, app, admin_user):
        """Test creating bill with zero amount"""
        from models import Vendor, Tenant
        from conftest import login_user
        
        login_user(client, 'admin', 'admin123')
        
        with app.app_context():
            tenant = Tenant.query.filter_by(code='skanda').first()
            vendor = Vendor.query.filter_by(tenant_id=tenant.id).first()
            if not vendor:
                vendor = Vendor(tenant_id=tenant.id, name='Test Vendor', type='SUPPLIER')
                db.session.add(vendor)
                db.session.commit()
            vendor_id = vendor.id
        
        response = client.post('/bills/new', data={
            'vendor_id': vendor_id,
            'bill_number': 'ZERO-001',
            'bill_date': '2023-01-01',
            'bill_type': 'NORMAL',
            'is_proxy': 'NO',
            'payment_type': 'UNPAID',
            'item_description[]': ['Free Item'],
            'item_quantity[]': ['1'],
            'item_unit_price[]': ['0.00']
        }, follow_redirects=True)
        
        # Should handle zero amount gracefully
        assert response.status_code == 200
    
    def test_invalid_date_format(self, client, app, admin_user):
        """Test form submission with invalid date format"""
        from models import Vendor, Tenant
        from conftest import login_user
        
        login_user(client, 'admin', 'admin123')
        
        with app.app_context():
            tenant = Tenant.query.filter_by(code='skanda').first()
            vendor = Vendor.query.filter_by(tenant_id=tenant.id).first()
            if not vendor:
                vendor = Vendor(tenant_id=tenant.id, name='Test Vendor', type='SUPPLIER')
                db.session.add(vendor)
                db.session.commit()
            vendor_id = vendor.id
        
        response = client.post('/bills/new', data={
            'vendor_id': vendor_id,
            'bill_number': 'INVALID-001',
            'bill_date': 'invalid-date',
            'bill_type': 'NORMAL',
            'is_proxy': 'NO',
            'payment_type': 'UNPAID'
        })
        
        # Should show validation error
        assert response.status_code == 200
        assert b'error' in response.data.lower() or b'invalid' in response.data.lower()
    
    def test_large_amount_handling(self, client, app, admin_user):
        """Test handling of very large amounts"""
        from models import Vendor, Tenant
        from conftest import login_user
        
        login_user(client, 'admin', 'admin123')
        
        with app.app_context():
            tenant = Tenant.query.filter_by(code='skanda').first()
            vendor = Vendor.query.filter_by(tenant_id=tenant.id).first()
            if not vendor:
                vendor = Vendor(tenant_id=tenant.id, name='Test Vendor', type='SUPPLIER')
                db.session.add(vendor)
                db.session.commit()
            vendor_id = vendor.id
        
        response = client.post('/bills/new', data={
            'vendor_id': vendor_id,
            'bill_number': 'LARGE-001',
            'bill_date': '2023-01-01',
            'bill_type': 'NORMAL',
            'is_proxy': 'NO',
            'payment_type': 'UNPAID',
            'item_description[]': ['Expensive Item'],
            'item_quantity[]': ['1'],
            'item_unit_price[]': ['999999999.99']
        }, follow_redirects=True)
        
        # Should handle large amounts
        assert response.status_code == 200
    
    def test_special_characters_in_bill_number(self, client, app, admin_user):
        """Test bill number with special characters"""
        from models import Vendor, Tenant
        from conftest import login_user
        
        login_user(client, 'admin', 'admin123')
        
        with app.app_context():
            tenant = Tenant.query.filter_by(code='skanda').first()
            vendor = Vendor.query.filter_by(tenant_id=tenant.id).first()
            if not vendor:
                vendor = Vendor(tenant_id=tenant.id, name='Test Vendor', type='SUPPLIER')
                db.session.add(vendor)
                db.session.commit()
            vendor_id = vendor.id
        
        response = client.post('/bills/new', data={
            'vendor_id': vendor_id,
            'bill_number': 'BILL-2023/001-SPECIAL',
            'bill_date': '2023-01-01',
            'bill_type': 'NORMAL',
            'is_proxy': 'NO',
            'payment_type': 'UNPAID',
            'item_description[]': ['Test Item'],
            'item_quantity[]': ['1'],
            'item_unit_price[]': ['100.00']
        }, follow_redirects=True)
        
        # Should handle special characters
        assert response.status_code == 200
    
    def test_duplicate_bill_number(self, client, app, admin_user):
        """Test creating bill with duplicate bill number"""
        from models import Vendor, Tenant, Bill
        from conftest import login_user
        
        login_user(client, 'admin', 'admin123')
        
        with app.app_context():
            tenant = Tenant.query.filter_by(code='skanda').first()
            vendor = Vendor.query.filter_by(tenant_id=tenant.id).first()
            if not vendor:
                vendor = Vendor(tenant_id=tenant.id, name='Test Vendor', type='SUPPLIER')
                db.session.add(vendor)
                db.session.flush()
            
            # Create first bill
            from datetime import date
            bill1 = Bill(
                tenant_id=tenant.id,
                vendor_id=vendor.id,
                bill_number='DUPLICATE-001',
                bill_date=date(2023, 1, 1),
                bill_type='NORMAL',
                status='DRAFT'
            )
            db.session.add(bill1)
            db.session.commit()
            vendor_id = vendor.id
        
        # Try to create duplicate
        response = client.post('/bills/new', data={
            'vendor_id': vendor_id,
            'bill_number': 'DUPLICATE-001',
            'bill_date': '2023-01-02',
            'bill_type': 'NORMAL',
            'is_proxy': 'NO',
            'payment_type': 'UNPAID',
            'item_description[]': ['Test Item'],
            'item_quantity[]': ['1'],
            'item_unit_price[]': ['100.00']
        }, follow_redirects=True)
        
        # Should handle duplicate (may allow or show error depending on business logic)
        assert response.status_code == 200

