from datetime import date

from extensions import db
from models import Bill, DeliveryOrder, ProxyBill, Tenant, User, Vendor
from picklist_upload_utils import apply_picklist_csv_import_rows


def _base_entities():
    tenant = Tenant.query.filter_by(code="skanda").first()
    vendor = Vendor(
        tenant_id=tenant.id,
        name="Sync Vendor",
        type="SUPPLIER",
    )
    db.session.add(vendor)
    db.session.flush()

    delivery_user = User.query.filter_by(tenant_id=tenant.id, role="DELIVERY").first()
    return tenant, vendor, delivery_user


def test_picklist_csv_sync_updates_bill_and_existing_delivery(app):
    with app.app_context():
        tenant, vendor, delivery_user = _base_entities()
        bill = Bill(
            tenant_id=tenant.id,
            vendor_id=vendor.id,
            bill_number="INV-1001",
            bill_date=date(2024, 1, 1),
            bill_type="NORMAL",
            status="CONFIRMED",
        )
        db.session.add(bill)
        db.session.flush()

        delivery = DeliveryOrder(
            tenant_id=tenant.id,
            bill_id=bill.id,
            delivery_user_id=delivery_user.id,
            delivery_address="Old address",
            delivery_date=date(2024, 1, 2),
            status="PENDING",
        )
        db.session.add(delivery)
        db.session.commit()

        rows = [
            {
                "invoice_no": "INV-1001",
                "delivery_date": date(2024, 2, 10),
                "customer_code": "C001",
                "customer_name": "Customer 1",
                "beat": "Beat A",
                "amount": None,
                "received_amount": None,
                "payment_mode": "CASH",
            }
        ]

        result = apply_picklist_csv_import_rows(tenant.id, rows)
        db.session.commit()
        db.session.refresh(bill)
        db.session.refresh(delivery)

        assert result["bills_updated"] == 1
        assert result["bills_created"] == 0
        assert result["deliveries_updated"] == 1
        assert result["no_existing_delivery"] == 0
        assert bill.delivery_date == date(2024, 2, 10)
        assert delivery.delivery_date == date(2024, 2, 10)


def test_picklist_csv_sync_updates_bill_and_creates_missing_delivery(app):
    with app.app_context():
        tenant, vendor, delivery_user = _base_entities()
        bill = Bill(
            tenant_id=tenant.id,
            vendor_id=vendor.id,
            bill_number="INV-2001",
            bill_date=date(2024, 1, 1),
            bill_type="NORMAL",
            status="CONFIRMED",
        )
        db.session.add(bill)
        db.session.commit()

        rows = [
            {
                "invoice_no": "INV-2001",
                "delivery_date": date(2024, 3, 15),
                "customer_code": "C002",
                "customer_name": "Customer 2",
                "beat": "Beat B",
                "amount": None,
                "received_amount": None,
                "payment_mode": "UPI",
            }
        ]

        result = apply_picklist_csv_import_rows(tenant.id, rows)
        db.session.commit()
        db.session.refresh(bill)

        assert result["bills_updated"] == 1
        assert result["bills_created"] == 0
        assert result["deliveries_created"] == 1
        assert result["deliveries_updated"] == 0
        assert result["no_existing_delivery"] == 0
        assert bill.delivery_date == date(2024, 3, 15)

        delivery = DeliveryOrder.query.filter_by(bill_id=bill.id).one()
        assert delivery.delivery_user_id == delivery_user.id
        assert delivery.delivery_date == date(2024, 3, 15)
        assert delivery.delivery_address == "Customer 2"


def test_picklist_csv_sync_creates_bill_when_invoice_is_new(app):
    with app.app_context():
        tenant = Tenant.query.filter_by(code="skanda").first()
        rows = [
            {
                "invoice_no": "INV-NEW-1",
                "delivery_date": date(2024, 4, 1),
                "customer_code": "C003",
                "customer_name": "Customer 3",
                "beat": "Beat C",
                "amount": 250,
                "received_amount": None,
                "payment_mode": "CARD",
            }
        ]

        result = apply_picklist_csv_import_rows(tenant.id, rows)
        db.session.commit()

        bill = Bill.query.filter_by(tenant_id=tenant.id, bill_number="INV-NEW-1").one()
        delivery = DeliveryOrder.query.filter_by(tenant_id=tenant.id, bill_id=bill.id).one()

        assert result["bills_created"] == 1
        assert result["no_matching_bill"] == 0
        assert result["deliveries_created"] == 1
        assert not result["skipped"]
        assert bill.bill_date == date(2024, 4, 1)
        assert bill.delivery_date == date(2024, 4, 1)
        assert bill.amount_total == 250
        assert bill.vendor.customer_code == "C003"
        assert bill.vendor.name == "Customer 3"
        assert delivery.delivery_date == date(2024, 4, 1)


def test_picklist_csv_sync_uses_delivery_user_column_when_multiple_delivery_users(app):
    with app.app_context():
        tenant, vendor, _delivery_user = _base_entities()
        second_delivery_user = User(
            tenant_id=tenant.id,
            username="delivery-two",
            role="DELIVERY",
            is_active=True,
        )
        second_delivery_user.set_password("delivery123")
        db.session.add(second_delivery_user)
        db.session.flush()

        bill = Bill(
            tenant_id=tenant.id,
            vendor_id=vendor.id,
            bill_number="INV-USER-1",
            bill_date=date(2024, 1, 1),
            bill_type="NORMAL",
            status="CONFIRMED",
        )
        db.session.add(bill)
        db.session.commit()

        rows = [
            {
                "invoice_no": "INV-USER-1",
                "delivery_date": date(2024, 6, 1),
                "customer_code": "C005",
                "customer_name": "Customer 5",
                "beat": "Beat E",
                "amount": None,
                "received_amount": None,
                "payment_mode": "CASH",
                "delivery_person": "delivery-two",
            }
        ]

        result = apply_picklist_csv_import_rows(tenant.id, rows)
        db.session.commit()

        assert result["deliveries_created"] == 1
        assert result["bills_created"] == 0
        assert result["no_delivery_user"] == 0
        delivery = DeliveryOrder.query.filter_by(bill_id=bill.id).one()
        assert delivery.delivery_user_id == second_delivery_user.id


def test_picklist_csv_sync_matches_proxy_and_updates_existing_delivery(app):
    with app.app_context():
        tenant, vendor, delivery_user = _base_entities()
        parent_bill = Bill(
            tenant_id=tenant.id,
            vendor_id=vendor.id,
            bill_number="INV-PARENT-1",
            bill_date=date(2024, 1, 1),
            bill_type="NORMAL",
            status="CONFIRMED",
        )
        db.session.add(parent_bill)
        db.session.flush()

        proxy_bill = ProxyBill(
            tenant_id=tenant.id,
            parent_bill_id=parent_bill.id,
            vendor_id=vendor.id,
            proxy_number="PX-7001",
            status="CONFIRMED",
        )
        db.session.add(proxy_bill)
        db.session.flush()

        delivery = DeliveryOrder(
            tenant_id=tenant.id,
            proxy_bill_id=proxy_bill.id,
            delivery_user_id=delivery_user.id,
            delivery_address="Proxy address",
            delivery_date=date(2024, 1, 10),
            status="PENDING",
        )
        db.session.add(delivery)
        db.session.commit()

        rows = [
            {
                "invoice_no": "PX-7001",
                "delivery_date": date(2024, 5, 5),
                "customer_code": "C004",
                "customer_name": "Customer 4",
                "beat": "Beat D",
                "amount": None,
                "received_amount": None,
                "payment_mode": "BANK",
            }
        ]

        result = apply_picklist_csv_import_rows(tenant.id, rows)
        db.session.commit()
        db.session.refresh(parent_bill)
        db.session.refresh(delivery)

        assert result["bills_updated"] == 1
        assert result["bills_created"] == 0
        assert result["deliveries_updated"] == 1
        assert result["deliveries_created"] == 0
        assert parent_bill.delivery_date == date(2024, 5, 5)
        assert delivery.delivery_date == date(2024, 5, 5)
