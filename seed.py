"""
Seed script to initialize the database with default tenant, admin user, and permissions.
Run this script once to set up the initial data.
"""

from app import create_app
from extensions import db
from models import Tenant, User, Permission, RolePermission

app = create_app('development')

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

with app.app_context():
    # Create all tables
    db.create_all()
    
    # Check if tenant already exists
    tenant = Tenant.query.filter_by(code='skanda').first()
    if not tenant:
        tenant = Tenant(
            name='Skanda Enterprises',
            code='skanda',
            is_active=True
        )
        db.session.add(tenant)
        db.session.flush()
        print(f"Created tenant: {tenant.name} (code: {tenant.code})")
    else:
        print(f"Tenant already exists: {tenant.name}")
    
    # Create permissions
    print("\nCreating permissions...")
    for perm_data in PERMISSIONS:
        perm = Permission.query.filter_by(code=perm_data['code']).first()
        if not perm:
            perm = Permission(
                name=perm_data['name'],
                code=perm_data['code'],
                description=perm_data['description'],
                category=perm_data['category']
            )
            db.session.add(perm)
            print(f"  Created permission: {perm_data['code']}")
        else:
            print(f"  Permission already exists: {perm_data['code']}")
    
    db.session.flush()
    
    # Create role permissions
    print("\nSetting up role permissions...")
    roles = ['ADMIN', 'SALESMAN', 'DELIVERY', 'ORGANISER']
    
    for role in roles:
        if role == 'ADMIN':
            # Admin gets all permissions
            for perm_data in PERMISSIONS:
                perm = Permission.query.filter_by(code=perm_data['code']).first()
                role_perm = RolePermission.query.filter_by(
                    role=role,
                    permission_id=perm.id
                ).first()
                if not role_perm:
                    role_perm = RolePermission(
                        role=role,
                        permission_id=perm.id,
                        granted=True
                    )
                    db.session.add(role_perm)
            print(f"  ADMIN: Granted all permissions")
        else:
            # Other roles get default permissions
            default_perms = DEFAULT_ROLE_PERMISSIONS.get(role, [])
            for perm_code in default_perms:
                perm = Permission.query.filter_by(code=perm_code).first()
                if perm:
                    role_perm = RolePermission.query.filter_by(
                        role=role,
                        permission_id=perm.id
                    ).first()
                    if not role_perm:
                        role_perm = RolePermission(
                            role=role,
                            permission_id=perm.id,
                            granted=True
                        )
                        db.session.add(role_perm)
            print(f"  {role}: Granted {len(default_perms)} default permissions")
    
    # Create users for each role
    print("\nCreating users...")
    
    users_to_create = [
        {'username': 'admin', 'role': 'ADMIN', 'password': 'admin12233'},
        {'username': 'salesman', 'role': 'SALESMAN', 'password': 'salesman123'},
        {'username': 'delivery', 'role': 'DELIVERY', 'password': 'delivery123'},
        {'username': 'organiser', 'role': 'ORGANISER', 'password': 'organiser123'}
    ]
    
    for user_data in users_to_create:
        user = User.query.filter_by(username=user_data['username']).first()
        if not user:
            user = User(
                tenant_id=tenant.id,
                username=user_data['username'],
                role=user_data['role'],
                is_active=True
            )
            user.set_password(user_data['password'])
            db.session.add(user)
            print(f"  Created {user_data['role']} user: {user_data['username']} / {user_data['password']}")
        else:
            # Update existing user password and role if needed
            user.set_password(user_data['password'])
            user.role = user_data['role']
            user.is_active = True
            print(f"  Updated {user_data['role']} user: {user_data['username']} / {user_data['password']}")
    
    db.session.commit()
    print("\n" + "="*50)
    print("Seed completed successfully!")
    print("="*50)
    print("You can now login with:")
    print("  Admin:     admin / admin12233")
    print("  Salesman:  salesman / salesman123")
    print("  Delivery:  delivery / delivery123")
    print("  Organiser: organiser / organiser123")
    print("\nPermissions have been set up for all roles.")

