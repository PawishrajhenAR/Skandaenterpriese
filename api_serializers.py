"""Serializers for API JSON responses. Converts SQLAlchemy models to dicts."""
from datetime import date, datetime
from decimal import Decimal


def serialize_model(obj, exclude=None):
    """Convert SQLAlchemy model to dict, handling relationships and special types."""
    if obj is None:
        return None
    exclude = exclude or []
    result = {}
    for col in obj.__table__.columns:
        if col.name in exclude:
            continue
        val = getattr(obj, col.name)
        if isinstance(val, (date, datetime)):
            result[col.name] = val.isoformat() if val else None
        elif isinstance(val, Decimal):
            result[col.name] = float(val) if val is not None else None
        else:
            result[col.name] = val
    return result


def vendor_to_dict(v):
    if not v:
        return None
    return serialize_model(v)


def bill_to_dict(b, payment_status=None):
    if not b:
        return None
    d = serialize_model(b)
    d['vendor'] = vendor_to_dict(b.vendor) if b.vendor else None
    if payment_status:
        d['payment_status'] = payment_status
    return d


def credit_to_dict(c):
    if not c:
        return None
    d = serialize_model(c)
    d['vendor'] = vendor_to_dict(c.vendor) if c.vendor else None
    return d


def delivery_to_dict(delivery):
    if not delivery:
        return None
    d = serialize_model(delivery)
    d['bill'] = bill_to_dict(delivery.bill) if delivery.bill else None
    d['proxy_bill'] = proxy_bill_to_dict(delivery.proxy_bill) if delivery.proxy_bill else None
    return d


def proxy_bill_to_dict(pb):
    if not pb:
        return None
    d = serialize_model(pb)
    d['vendor'] = vendor_to_dict(pb.vendor) if pb.vendor else None
    d['items'] = [serialize_model(i) for i in (pb.items or [])]
    return d


def user_to_dict(u):
    if not u:
        return None
    return {
        'id': u.id,
        'username': u.username,
        'role': u.role,
        'tenant_id': u.tenant_id,
    }


def ocr_job_to_dict(job):
    if not job:
        return None
    d = serialize_model(job)
    d['bill'] = bill_to_dict(job.bill) if job.bill else None
    return d
