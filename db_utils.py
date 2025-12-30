"""
Database utility functions for transaction management and error handling.
"""

from functools import wraps
from flask import flash
from extensions import db
import logging

logger = logging.getLogger(__name__)


def with_transaction(func):
    """
    Decorator to wrap database operations with proper transaction handling.
    Automatically commits on success and rolls back on error.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
            db.session.commit()
            return result
        except Exception as e:
            db.session.rollback()
            logger.error(f"Database transaction failed in {func.__name__}: {str(e)}", exc_info=True)
            flash(f'An error occurred: {str(e)}', 'danger')
            raise
    return wrapper


def safe_commit(flash_message=None, flash_category='success'):
    """
    Safely commit database transaction with error handling.
    
    Args:
        flash_message: Optional success message to flash
        flash_category: Category for flash message (default: 'success')
    
    Returns:
        True if commit successful, False otherwise
    """
    try:
        db.session.commit()
        if flash_message:
            flash(flash_message, flash_category)
        return True
    except Exception as e:
        db.session.rollback()
        logger.error(f"Database commit failed: {str(e)}", exc_info=True)
        flash(f'Database error: {str(e)}', 'danger')
        return False

