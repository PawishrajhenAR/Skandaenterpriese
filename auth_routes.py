from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from functools import wraps
from models import User, Tenant, Permission, RolePermission
from forms import LoginForm
from extensions import db

auth_bp = Blueprint('auth', __name__)


def role_required(*roles):
    """Decorator to require specific roles"""
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if current_user.role not in roles:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('main.dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def permission_required(permission_code):
    """Decorator to require specific permission"""
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if not current_user.has_permission(permission_code):
                flash('You do not have permission to perform this action.', 'danger')
                return redirect(url_for('main.dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def check_permission(user, permission_code):
    """Helper function to check if user has permission"""
    return user.has_permission(permission_code)


def has_role_permission(role, permission_code):
    """Helper function to check if role has permission"""
    if role == 'ADMIN':
        return True
    
    permission = Permission.query.filter_by(code=permission_code).first()
    if not permission:
        return False
    
    role_perm = RolePermission.query.filter_by(
        role=role,
        permission_id=permission.id,
        granted=True
    ).first()
    
    return role_perm is not None


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data) and user.is_active:
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('main.dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
    
    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))

