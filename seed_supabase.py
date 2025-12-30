"""
Direct seeding script for Supabase PostgreSQL
Doesn't require Flask to be installed
"""

import os
import psycopg2
from psycopg2.extras import execute_values
from werkzeug.security import generate_password_hash

DATABASE_URL = "postgresql://postgres:skandadb%40007@db.yqhwlczamvzmbziabwyv.supabase.co:5432/postgres"

# Define all permissions
PERMISSIONS = [
    # Bill permissions
    {'name': 'Create Bill', 'code': 'create_bill', 'description': 'Create new bills', 'category': 'BILL'},
    {'name': 'Edit Bill', 'code': 'edit_bill', 'description': 'Edit existing bills', 'category': 'BILL'},
    {'name': 'Delete Bill', 'code': 'delete_bill', 'description': 'Delete bills', 'category': 'BILL'},
    {'name': 'Confirm Bill', 'code': 'confirm_bill', 'description': 'Confirm bills', 'category': 'BILL'},
    {'name': 'Cancel Bill', 'code': 'cancel_bill', 'description': 'Cancel bills', 'category': 'BILL'},
    {'name': 'View Bills', 'code': 'view_bills', 'description': 'View bills list', 'category': 'BILL'},
    {'name': 'Authorize Bill', 'code': 'authorize_bill', 'description': 'Authorize bills for organiser view', 'category': 'BILL'},
    
    # Credit permissions
    {'name': 'Create Credit', 'code': 'create_credit', 'description': 'Create credit entries', 'category': 'CREDIT'},
    {'name': 'Edit Credit', 'code': 'edit_credit', 'description': 'Edit credit entries', 'category': 'CREDIT'},
    {'name': 'Delete Credit', 'code': 'delete_credit', 'description': 'Delete credit entries', 'category': 'CREDIT'},
    {'name': 'View Credits', 'code': 'view_credits', 'description': 'View credits list', 'category': 'CREDIT'},
    
    # Delivery permissions
    {'name': 'Create Delivery', 'code': 'create_delivery', 'description': 'Create delivery orders', 'category': 'DELIVERY'},
    {'name': 'Update Delivery', 'code': 'update_delivery', 'description': 'Update delivery status', 'category': 'DELIVERY'},
    {'name': 'View Deliveries', 'code': 'view_deliveries', 'description': 'View deliveries list', 'category': 'DELIVERY'},
    
    # Vendor permissions
    {'name': 'Create Vendor', 'code': 'create_vendor', 'description': 'Create vendors', 'category': 'VENDOR'},
    {'name': 'Edit Vendor', 'code': 'edit_vendor', 'description': 'Edit vendors', 'category': 'VENDOR'},
    {'name': 'Delete Vendor', 'code': 'delete_vendor', 'description': 'Delete vendors', 'category': 'VENDOR'},
    {'name': 'View Vendors', 'code': 'view_vendors', 'description': 'View vendors list', 'category': 'VENDOR'},
    
    # Report permissions
    {'name': 'View Reports', 'code': 'view_reports', 'description': 'View all reports', 'category': 'REPORT'},
    {'name': 'Export Reports', 'code': 'export_reports', 'description': 'Export reports', 'category': 'REPORT'},
    
    # Admin permissions
    {'name': 'Manage Permissions', 'code': 'manage_permissions', 'description': 'Manage user permissions', 'category': 'ADMIN'},
    {'name': 'Manage Users', 'code': 'manage_users', 'description': 'Manage users', 'category': 'ADMIN'},
]

# Default permissions for each role (excluding ADMIN who gets all)
DEFAULT_ROLE_PERMISSIONS = {
    'SALESMAN': [
        'view_bills', 'create_bill', 'edit_bill', 'confirm_bill',
        'view_credits', 'create_credit',
        'view_vendors'
    ],
    'DELIVERY': [
        'view_deliveries', 'create_delivery', 'update_delivery',
        'view_bills'
    ],
    'ORGANISER': [
        'view_bills',  # Only authorized bills
        'view_credits', 'view_deliveries',
        'view_vendors', 'view_reports'
    ]
}

def main():
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    cursor = conn.cursor()
    
    try:
        # Create tenant
        cursor.execute("SELECT id FROM tenants WHERE code = 'skanda'")
        tenant = cursor.fetchone()
        if not tenant:
            cursor.execute(
                "INSERT INTO tenants (name, code, is_active) VALUES (%s, %s, %s) RETURNING id",
                ('Skanda Enterprises', 'skanda', True)
            )
            tenant_id = cursor.fetchone()[0]
            print(f"✓ Created tenant: Skanda Enterprises (ID: {tenant_id})")
        else:
            tenant_id = tenant[0]
            print(f"✓ Tenant already exists: Skanda Enterprises (ID: {tenant_id})")
        
        # Create permissions
        permission_ids = {}
        for perm_data in PERMISSIONS:
            cursor.execute("SELECT id FROM permissions WHERE code = %s", (perm_data['code'],))
            perm = cursor.fetchone()
            if not perm:
                cursor.execute(
                    "INSERT INTO permissions (name, code, description, category) VALUES (%s, %s, %s, %s) RETURNING id",
                    (perm_data['name'], perm_data['code'], perm_data['description'], perm_data['category'])
                )
                perm_id = cursor.fetchone()[0]
                permission_ids[perm_data['code']] = perm_id
                print(f"  ✓ Created permission: {perm_data['code']}")
            else:
                permission_ids[perm_data['code']] = perm[0]
        
        # Create role permissions
        roles = ['ADMIN', 'SALESMAN', 'DELIVERY', 'ORGANISER']
        for role in roles:
            if role == 'ADMIN':
                # Admin gets all permissions
                for perm_data in PERMISSIONS:
                    perm_id = permission_ids[perm_data['code']]
                    cursor.execute(
                        "SELECT id FROM role_permissions WHERE role = %s AND permission_id = %s",
                        (role, perm_id)
                    )
                    if not cursor.fetchone():
                        cursor.execute(
                            "INSERT INTO role_permissions (role, permission_id, granted) VALUES (%s, %s, %s)",
                            (role, perm_id, True)
                        )
                print(f"  ✓ ADMIN: Granted all permissions")
            else:
                default_perms = DEFAULT_ROLE_PERMISSIONS.get(role, [])
                for perm_code in default_perms:
                    perm_id = permission_ids.get(perm_code)
                    if perm_id:
                        cursor.execute(
                            "SELECT id FROM role_permissions WHERE role = %s AND permission_id = %s",
                            (role, perm_id)
                        )
                        if not cursor.fetchone():
                            cursor.execute(
                                "INSERT INTO role_permissions (role, permission_id, granted) VALUES (%s, %s, %s)",
                                (role, perm_id, True)
                            )
                print(f"  ✓ {role}: Granted {len(default_perms)} default permissions")
        
        # Create users
        users_to_create = [
            {'username': 'admin', 'role': 'ADMIN', 'password': 'admin12233'},
            {'username': 'salesman', 'role': 'SALESMAN', 'password': 'salesman123'},
            {'username': 'delivery', 'role': 'DELIVERY', 'password': 'delivery123'},
            {'username': 'organiser', 'role': 'ORGANISER', 'password': 'organiser123'}
        ]
        
        for user_data in users_to_create:
            cursor.execute("SELECT id FROM users WHERE username = %s", (user_data['username'],))
            user = cursor.fetchone()
            if not user:
                password_hash = generate_password_hash(user_data['password'])
                cursor.execute(
                    "INSERT INTO users (tenant_id, username, password_hash, role, is_active) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                    (tenant_id, user_data['username'], password_hash, user_data['role'], True)
                )
                user_id = cursor.fetchone()[0]
                print(f"  ✓ Created {user_data['role']} user: {user_data['username']} / {user_data['password']} (ID: {user_id})")
            else:
                # Update password
                password_hash = generate_password_hash(user_data['password'])
                cursor.execute(
                    "UPDATE users SET password_hash = %s, role = %s, is_active = %s WHERE id = %s",
                    (password_hash, user_data['role'], True, user[0])
                )
                print(f"  ✓ Updated {user_data['role']} user: {user_data['username']} / {user_data['password']}")
        
        conn.commit()
        print("\n" + "="*50)
        print("Seed completed successfully!")
        print("="*50)
        print("You can now login with:")
        print("  Admin:     admin / admin12233")
        print("  Salesman:  salesman / salesman123")
        print("  Delivery:  delivery / delivery123")
        print("  Organiser: organiser / organiser123")
        
    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    main()

