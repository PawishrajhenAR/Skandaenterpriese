"""
Seed dummy data for testing: ~2000 bills, vendors, proxy bills, credits, delivery orders.
Run after seed.py. Uses existing tenant and users.
"""
import random
from datetime import datetime, timedelta
from decimal import Decimal

from app import create_app
from extensions import db
from models import (
    Tenant,
    User,
    Vendor,
    Bill,
    BillItem,
    ProxyBill,
    ProxyBillItem,
    CreditEntry,
    DeliveryOrder,
)

app = create_app("development")

# Config
NUM_VENDORS = 80
NUM_BILLS = 2000
NUM_PROXY_BILLS = 500
NUM_CREDIT_ENTRIES = 3000
NUM_DELIVERY_ORDERS = 800
BATCH_SIZE = 200

ITEM_DESCRIPTIONS = [
    "Rice 25kg bag", "Wheat flour 10kg", "Sugar 5kg", "Cooking oil 1L",
    "Toor dal 1kg", "Chana dal 1kg", "Tea 500g", "Soap bar 100g",
    "Detergent 500g", "Biscuits 200g", "Salt 1kg", "Spices mix 200g",
    "Pulses 1kg", "Atta 5kg", "Basmati rice 5kg", "Groundnut oil 500ml",
    "Jaggery 1kg", "Honey 500g", "Jam 200g", "Noodles 400g",
    "Pasta 500g", "Cereal 300g", "Milk powder 500g", "Ghee 500g",
    "Mustard oil 1L", "Lentils 1kg", "Dry fruits 200g", "Snacks 150g",
]

PAYMENT_METHODS = ["CASH", "UPI", "BANK", "CHEQUE", "CARD"]
DELIVERY_STATUSES = ["PENDING", "IN_TRANSIT", "DELIVERED", "CANCELLED"]
ADDRESSES = [
    "123 Main St, City A", "456 Park Ave, City B", "789 Market Rd, City C",
    "101 Sector 5, City D", "202 Industrial Area, City E", "303 Block B, City F",
]


def random_date(days_back=365):
    start = datetime.now().date() - timedelta(days=days_back)
    return start + timedelta(days=random.randint(0, days_back))


def with_app_context():
    with app.app_context():
        tenant = Tenant.query.filter_by(code="skanda").first()
        if not tenant:
            print("Run seed.py first to create tenant and users.")
            return

        users = User.query.filter_by(tenant_id=tenant.id, is_active=True).all()
        delivery_users = [u for u in users if u.role == "DELIVERY"]
        if not delivery_users:
            # Create 2 delivery users for dummy data
            for i in range(1, 3):
                u = User(
                    tenant_id=tenant.id,
                    username=f"delivery{i}",
                    role="DELIVERY",
                    is_active=True,
                )
                u.set_password("delivery123")
                db.session.add(u)
            db.session.flush()
            delivery_users = User.query.filter_by(tenant_id=tenant.id, role="DELIVERY").all()
        print(f"Using {len(delivery_users)} delivery user(s) for delivery orders.")

        # 1. Vendors
        existing_vendors = Vendor.query.filter_by(tenant_id=tenant.id).count()
        if existing_vendors >= NUM_VENDORS:
            print(f"Vendors already exist ({existing_vendors}). Skipping vendor creation.")
            vendors = Vendor.query.filter_by(tenant_id=tenant.id).all()
        else:
            vendors = list(Vendor.query.filter_by(tenant_id=tenant.id).all())
            to_create = NUM_VENDORS - len(vendors)
            for i in range(to_create):
                v = Vendor(
                    tenant_id=tenant.id,
                    name=f"Vendor {len(vendors) + i + 1}",
                    type=random.choice(["SUPPLIER", "CUSTOMER", "BOTH"]),
                    customer_code=f"CUST{len(vendors) + i + 1:05d}",
                    address=random.choice(ADDRESSES),
                    status="ACTIVE",
                )
                db.session.add(v)
                vendors.append(v)
            db.session.flush()
            vendors = Vendor.query.filter_by(tenant_id=tenant.id).all()
            print(f"Created/using {len(vendors)} vendors.")

        # 2. Bills + BillItems
        existing_bills = Bill.query.filter_by(tenant_id=tenant.id).count()
        if existing_bills >= NUM_BILLS:
            print(f"Bills already exist ({existing_bills}). Skipping bill creation.")
        else:
            to_create = NUM_BILLS - existing_bills
            vendor_ids = [v.id for v in vendors]
            for batch_start in range(0, to_create, BATCH_SIZE):
                batch_end = min(batch_start + BATCH_SIZE, to_create)
                for i in range(batch_start, batch_end):
                    bill_num = existing_bills + i + 1
                    bill = Bill(
                        tenant_id=tenant.id,
                        vendor_id=random.choice(vendor_ids),
                        bill_number=f"BILL-{bill_num:05d}",
                        bill_date=random_date(),
                        bill_type=random.choice(["NORMAL", "NORMAL", "HANDBILL"]),
                        status=random.choice(["CONFIRMED", "CONFIRMED", "CONFIRMED", "DRAFT", "CANCELLED"]),
                    )
                    db.session.add(bill)
                    db.session.flush()
                    subtotal = Decimal("0")
                    num_items = random.randint(1, 5)
                    for _ in range(num_items):
                        qty = Decimal(str(round(random.uniform(1, 50), 2)))
                        up = Decimal(str(round(random.uniform(20, 500), 2)))
                        amt = round(qty * up, 2)
                        subtotal += amt
                        db.session.add(
                            BillItem(
                                bill_id=bill.id,
                                description=random.choice(ITEM_DESCRIPTIONS),
                                quantity=qty,
                                unit_price=up,
                                amount=amt,
                            )
                        )
                    bill.amount_subtotal = subtotal
                    bill.amount_tax = round(subtotal * Decimal("0.05"), 2)
                    bill.amount_total = bill.amount_subtotal + bill.amount_tax
                db.session.commit()
                print(f"  Bills: {existing_bills + batch_end}/{NUM_BILLS}")
            print(f"Created {to_create} bills (total {NUM_BILLS}).")

        # 3. Proxy bills (from CONFIRMED bills that don't have one yet)
        bills_for_proxy = (
            Bill.query.filter_by(tenant_id=tenant.id, status="CONFIRMED")
            .order_by(Bill.id)
            .all()
        )
        existing_proxy = ProxyBill.query.filter_by(tenant_id=tenant.id).count()
        to_proxy = min(NUM_PROXY_BILLS - existing_proxy, len(bills_for_proxy))
        if to_proxy > 0:
            # Pick random parent bills (avoid same bill twice)
            random.shuffle(bills_for_proxy)
            for i, parent in enumerate(bills_for_proxy[:to_proxy]):
                # Use a different vendor (customer) for proxy
                other_vendors = [v for v in vendors if v.id != parent.vendor_id]
                if not other_vendors:
                    continue
                proxy_vendor = random.choice(other_vendors)
                pb = ProxyBill(
                    tenant_id=tenant.id,
                    parent_bill_id=parent.id,
                    vendor_id=proxy_vendor.id,
                    proxy_number=f"PB-{existing_proxy + i + 1:05d}",
                    status=random.choice(["CONFIRMED", "CONFIRMED", "DRAFT"]),
                    amount_total=Decimal("0"),
                )
                db.session.add(pb)
                db.session.flush()
                # Copy 1-3 items from parent
                parent_items = list(parent.items)
                if not parent_items:
                    continue
                n_copy = min(random.randint(1, 3), len(parent_items))
                for it in random.sample(parent_items, n_copy):
                    db.session.add(
                        ProxyBillItem(
                            proxy_bill_id=pb.id,
                            description=it.description,
                            quantity=it.quantity,
                            unit_price=it.unit_price,
                            amount=it.amount,
                        )
                    )
                    pb.amount_total += it.amount
                db.session.commit()
                if (i + 1) % 100 == 0:
                    print(f"  Proxy bills: {i + 1}/{to_proxy}")
            print(f"Created {to_proxy} proxy bills.")
        else:
            print(f"Proxy bills already sufficient ({existing_proxy}).")

        # 4. Credit entries (INCOMING for bills and proxy bills)
        all_bills = Bill.query.filter_by(tenant_id=tenant.id).filter(Bill.status.in_(["CONFIRMED", "DRAFT"])).all()
        all_proxy = ProxyBill.query.filter_by(tenant_id=tenant.id).filter(ProxyBill.status.in_(["CONFIRMED", "DRAFT"])).all()
        existing_credits = CreditEntry.query.filter_by(tenant_id=tenant.id).count()
        to_credits = max(0, NUM_CREDIT_ENTRIES - existing_credits)
        if to_credits > 0:
            entries_added = 0
            for _ in range(to_credits):
                if random.random() < 0.6 and all_bills:
                    b = random.choice(all_bills)
                    vendor_id = b.vendor_id
                    amt = round(Decimal(str(random.uniform(100, min(float(b.amount_total or 0), 50000)))), 2)
                    if amt <= 0:
                        continue
                    db.session.add(
                        CreditEntry(
                            tenant_id=tenant.id,
                            bill_id=b.id,
                            proxy_bill_id=None,
                            vendor_id=vendor_id,
                            amount=amt,
                            direction="INCOMING",
                            payment_method=random.choice(PAYMENT_METHODS),
                            payment_date=random_date(),
                        )
                    )
                    entries_added += 1
                elif all_proxy:
                    pb = random.choice(all_proxy)
                    vendor_id = pb.vendor_id
                    amt = round(Decimal(str(random.uniform(50, min(float(pb.amount_total or 0), 20000)))), 2)
                    if amt <= 0:
                        continue
                    db.session.add(
                        CreditEntry(
                            tenant_id=tenant.id,
                            bill_id=None,
                            proxy_bill_id=pb.id,
                            vendor_id=vendor_id,
                            amount=amt,
                            direction="INCOMING",
                            payment_method=random.choice(PAYMENT_METHODS),
                            payment_date=random_date(),
                        )
                    )
                    entries_added += 1
                if entries_added % 500 == 0 and entries_added > 0:
                    db.session.commit()
                    print(f"  Credits: {entries_added}")
            db.session.commit()
            print(f"Created {entries_added} credit entries.")
        else:
            print(f"Credit entries already sufficient ({existing_credits}).")

        # 5. Delivery orders (so Picklists have data)
        delivery_user_ids = [u.id for u in delivery_users]
        bill_list = Bill.query.filter_by(tenant_id=tenant.id).filter(Bill.status.in_(["CONFIRMED"])).all()
        proxy_list = ProxyBill.query.filter_by(tenant_id=tenant.id).filter(ProxyBill.status.in_(["CONFIRMED"])).all()
        existing_deliveries = DeliveryOrder.query.filter_by(tenant_id=tenant.id).count()
        to_deliveries = max(0, NUM_DELIVERY_ORDERS - existing_deliveries)
        if to_deliveries > 0:
            added = 0
            for _ in range(to_deliveries):
                if random.random() < 0.5 and bill_list:
                    b = random.choice(bill_list)
                    db.session.add(
                        DeliveryOrder(
                            tenant_id=tenant.id,
                            bill_id=b.id,
                            proxy_bill_id=None,
                            delivery_user_id=random.choice(delivery_user_ids),
                            delivery_address=random.choice(ADDRESSES) + f", Pincode {random.randint(100000, 999999)}",
                            delivery_date=random_date(),
                            status=random.choice(DELIVERY_STATUSES),
                        )
                    )
                    added += 1
                elif proxy_list:
                    pb = random.choice(proxy_list)
                    db.session.add(
                        DeliveryOrder(
                            tenant_id=tenant.id,
                            bill_id=None,
                            proxy_bill_id=pb.id,
                            delivery_user_id=random.choice(delivery_user_ids),
                            delivery_address=random.choice(ADDRESSES) + f", Pincode {random.randint(100000, 999999)}",
                            delivery_date=random_date(),
                            status=random.choice(DELIVERY_STATUSES),
                        )
                    )
                    added += 1
                if added % 200 == 0 and added > 0:
                    db.session.commit()
                    print(f"  Deliveries: {added}")
            db.session.commit()
            print(f"Created {added} delivery orders (Picklists).")
        else:
            print(f"Delivery orders already sufficient ({existing_deliveries}).")

        print("\n" + "="*50)
        print("Dummy data seed completed.")
        print("="*50)
        print(f"  Vendors:      {Vendor.query.filter_by(tenant_id=tenant.id).count()}")
        print(f"  Bills:        {Bill.query.filter_by(tenant_id=tenant.id).count()}")
        print(f"  Proxy bills:  {ProxyBill.query.filter_by(tenant_id=tenant.id).count()}")
        print(f"  Credits:      {CreditEntry.query.filter_by(tenant_id=tenant.id).count()}")
        print(f"  Deliveries:   {DeliveryOrder.query.filter_by(tenant_id=tenant.id).count()}")
        print("  You can now test Bills, Credits, Deliveries, Picklists, and Reports.")


if __name__ == "__main__":
    with_app_context()
