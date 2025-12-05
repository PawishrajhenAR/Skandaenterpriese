from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from models import Bill, BillItem, Vendor, Tenant, CreditEntry, ProxyBill, ProxyBillItem
from forms import BillForm
from extensions import db
from audit import log_action
from ocr_utils import run_ocr
from werkzeug.utils import secure_filename
from decimal import Decimal
from pathlib import Path
from datetime import datetime
from sqlalchemy import func
from auth_routes import permission_required

bill_bp = Blueprint('bill', __name__)


def get_default_tenant():
    return Tenant.query.filter_by(code='skanda').first()


@bill_bp.route('/')
@login_required
@permission_required('view_bills')
def list():
    tenant = get_default_tenant()
    if not tenant:
        flash('Tenant not found.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    # Start with base query
    query = Bill.query.filter_by(tenant_id=tenant.id)
    
    # ORGANISER can only see authorized bills
    if current_user.role == 'ORGANISER':
        query = query.filter(Bill.is_authorized == True)
    
    # Get filter parameters
    show_unauthorized = request.args.get('show_unauthorized', 'false') == 'true'
    search = request.args.get('search', '').strip()
    vendor_id = request.args.get('vendor_id', type=int)
    status = request.args.get('status', '')
    payment_status = request.args.get('payment_status', '')
    bill_type = request.args.get('bill_type', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    amount_min = request.args.get('amount_min', type=float)
    amount_max = request.args.get('amount_max', type=float)
    
    # Apply filters
    if search:
        query = query.filter(
            Bill.bill_number.ilike(f'%{search}%')
        )
    
    if vendor_id:
        query = query.filter(Bill.vendor_id == vendor_id)
    
    if status:
        query = query.filter(Bill.status == status)
    
    if payment_status:
        if payment_status == 'UNPAID':
            query = query.filter(Bill.payment_status == 'UNPAID')
        elif payment_status == 'PARTIAL':
            query = query.filter(Bill.payment_status == 'PARTIAL')
        elif payment_status == 'PAID':
            query = query.filter(Bill.payment_status == 'PAID')
    
    if bill_type:
        query = query.filter(Bill.bill_type == bill_type)
    
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
            query = query.filter(Bill.bill_date >= date_from_obj)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
            query = query.filter(Bill.bill_date <= date_to_obj)
        except ValueError:
            pass
    
    if amount_min is not None:
        query = query.filter(Bill.amount_total >= amount_min)
    
    if amount_max is not None:
        query = query.filter(Bill.amount_total <= amount_max)
    
    # Admin can filter unauthorized bills
    if current_user.role == 'ADMIN' and show_unauthorized:
        query = query.filter(Bill.is_authorized == False)
    
    # Get sort parameter
    sort_by = request.args.get('sort', 'created_at')
    sort_order = request.args.get('order', 'desc')
    
    if sort_by == 'bill_date':
        if sort_order == 'asc':
            query = query.order_by(Bill.bill_date.asc())
        else:
            query = query.order_by(Bill.bill_date.desc())
    elif sort_by == 'amount_total':
        if sort_order == 'asc':
            query = query.order_by(Bill.amount_total.asc())
        else:
            query = query.order_by(Bill.amount_total.desc())
    else:
        if sort_order == 'asc':
            query = query.order_by(Bill.created_at.asc())
        else:
            query = query.order_by(Bill.created_at.desc())
    
    bills = query.all()
    
    # Get vendors for filter dropdown
    vendors = Vendor.query.filter_by(tenant_id=tenant.id).order_by(Vendor.name).all()
    
    # Prepare filter data for template
    filters = [
        {
            'name': 'search',
            'label': 'Search',
            'type': 'search',
            'placeholder': 'Search by bill number...',
            'value': search,
            'icon': 'bi-search',
            'col_size': 3
        },
        {
            'name': 'vendor_id',
            'label': 'Vendor',
            'type': 'select',
            'value': vendor_id,
            'options': [{'value': v.id, 'label': v.name} for v in vendors],
            'icon': 'bi-person',
            'col_size': 2
        },
        {
            'name': 'status',
            'label': 'Status',
            'type': 'select',
            'value': status,
            'options': [
                {'value': 'DRAFT', 'label': 'Draft'},
                {'value': 'CONFIRMED', 'label': 'Confirmed'},
                {'value': 'CANCELLED', 'label': 'Cancelled'}
            ],
            'icon': 'bi-flag',
            'col_size': 2
        },
        {
            'name': 'payment_status',
            'label': 'Payment Status',
            'type': 'select',
            'value': payment_status,
            'options': [
                {'value': 'UNPAID', 'label': 'Unpaid'},
                {'value': 'PARTIAL', 'label': 'Partial'},
                {'value': 'PAID', 'label': 'Paid'}
            ],
            'icon': 'bi-cash-coin',
            'col_size': 2
        },
        {
            'name': 'bill_type',
            'label': 'Bill Type',
            'type': 'select',
            'value': bill_type,
            'options': [
                {'value': 'PURCHASE', 'label': 'Purchase'},
                {'value': 'SALE', 'label': 'Sale'}
            ],
            'icon': 'bi-receipt',
            'col_size': 2
        },
        {
            'name': 'bill_date',
            'label': 'Date Range',
            'type': 'date-range',
            'value_from': date_from,
            'value_to': date_to,
            'icon': 'bi-calendar',
            'col_size': 3
        },
        {
            'name': 'amount',
            'label': 'Amount Range',
            'type': 'number-range',
            'value_min': amount_min,
            'value_max': amount_max,
            'icon': 'bi-currency-rupee',
            'col_size': 3
        }
    ]
    
    # Add unauthorized filter for admin
    if current_user.role == 'ADMIN':
        filters.append({
            'name': 'show_unauthorized',
            'label': 'Show Unauthorized Only',
            'type': 'select',
            'value': 'true' if show_unauthorized else 'false',
            'options': [
                {'value': 'false', 'label': 'All Bills'},
                {'value': 'true', 'label': 'Unauthorized Only'}
            ],
            'icon': 'bi-shield-exclamation',
            'col_size': 2
        })
    
    # Active filters for display
    active_filters = {}
    if search:
        active_filters['Search'] = search
    if vendor_id:
        vendor = Vendor.query.get(vendor_id)
        if vendor:
            active_filters['Vendor'] = vendor.name
    if status:
        active_filters['Status'] = status
    if payment_status:
        active_filters['Payment'] = payment_status
    if bill_type:
        active_filters['Type'] = bill_type
    if date_from or date_to:
        active_filters['Date'] = f"{date_from or 'Any'} to {date_to or 'Any'}"
    if amount_min is not None or amount_max is not None:
        active_filters['Amount'] = f"₹{amount_min or 0} - ₹{amount_max or '∞'}"
    if show_unauthorized:
        active_filters['Filter'] = 'Unauthorized Only'
    
    return render_template('bills/list.html', bills=bills, vendors=vendors, filters=filters, active_filters=active_filters)


@bill_bp.route('/new/ocr-upload', methods=['POST'])
@login_required
def ocr_upload():
    """Handle OCR image upload and return extracted text"""
    if 'ocr_image' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['ocr_image']
    if not file or not file.filename:
        return jsonify({'success': False, 'error': 'No file selected'}), 400
    
    # Check file extension
    allowed_extensions = {'png', 'jpg', 'jpeg', 'pdf'}
    if '.' not in file.filename or file.filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
        return jsonify({'success': False, 'error': 'Invalid file type. Please upload JPG, PNG, or PDF.'}), 400
    
    try:
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"ocr_{timestamp}_{filename}"
        
        upload_folder = Path(current_app.config['UPLOAD_FOLDER'])
        upload_folder.mkdir(parents=True, exist_ok=True)
        filepath = upload_folder / filename
        file.save(str(filepath))
        
        # Run OCR with error handling
        try:
            ocr_text = run_ocr(str(filepath))
            
            # Check if OCR returned an error message
            if ocr_text.startswith("OCR error:") or ocr_text.startswith("Error:") or "not installed" in ocr_text.lower():
                return jsonify({
                    'success': False,
                    'error': ocr_text
                }), 500
            
            # Try to extract basic info from OCR text
            suggestions = extract_bill_info(ocr_text)
            
            return jsonify({
                'success': True,
                'ocr_text': ocr_text,
                'image_path': f"uploads/bills/{filename}",
                'suggestions': suggestions
            })
        except Exception as ocr_error:
            return jsonify({
                'success': False,
                'error': f'OCR processing failed: {str(ocr_error)}'
            }), 500
            
    except Exception as e:
        return jsonify({'success': False, 'error': f'Upload failed: {str(e)}'}), 500


@bill_bp.route('/new', methods=['GET', 'POST'])
@login_required
@permission_required('create_bill')
def create():
    tenant = get_default_tenant()
    if not tenant:
        flash('Tenant not found.', 'danger')
        return redirect(url_for('bill.list'))
    
    form = BillForm()
    form.vendor_id.choices = [(v.id, v.name) for v in Vendor.query.filter_by(tenant_id=tenant.id).order_by(Vendor.name).all()]
    
    if form.validate_on_submit():
        # Get items from request
        items_data = request.form.getlist('items')
        descriptions = request.form.getlist('item_description[]')
        quantities = request.form.getlist('item_quantity[]')
        unit_prices = request.form.getlist('item_unit_price[]')
        
        # Calculate amounts
        subtotal = Decimal('0.00')
        items = []
        
        for i in range(len(descriptions)):
            if descriptions[i].strip():
                qty = Decimal(quantities[i] or '0')
                price = Decimal(unit_prices[i] or '0')
                amount = qty * price
                subtotal += amount
                items.append({
                    'description': descriptions[i],
                    'quantity': qty,
                    'unit_price': price,
                    'amount': amount
                })
        
        # Calculate tax (assuming 18% GST)
        tax = subtotal * Decimal('0.18')
        total = subtotal + tax
        
        bill = Bill(
            tenant_id=tenant.id,
            vendor_id=form.vendor_id.data,
            bill_number=form.bill_number.data,
            bill_date=form.bill_date.data,
            bill_type=form.bill_type.data,
            status='DRAFT',
            amount_subtotal=subtotal,
            amount_tax=tax,
            amount_total=total
        )
        db.session.add(bill)
        db.session.flush()
        
        # Add items
        for item_data in items:
            item = BillItem(
                bill_id=bill.id,
                description=item_data['description'],
                quantity=item_data['quantity'],
                unit_price=item_data['unit_price'],
                amount=item_data['amount']
            )
            db.session.add(item)
        
        db.session.commit()
        log_action(current_user, 'CREATE_BILL', 'BILL', bill.id)
        
        # Handle payment - create credit entry if paid or partially paid
        if form.payment_type.data in ['FULL', 'PARTIAL']:
            payment_amount = bill.amount_total if form.payment_type.data == 'FULL' else (form.partial_amount.data or Decimal('0.00'))
            
            if payment_amount > 0:
                credit = CreditEntry(
                    tenant_id=tenant.id,
                    bill_id=bill.id,
                    vendor_id=bill.vendor_id,
                    amount=payment_amount,
                    direction='INCOMING',
                    payment_method=form.payment_method.data or 'CASH',
                    payment_date=bill.bill_date,
                    reference_number=form.payment_reference.data,
                    notes=f'Payment for bill {bill.bill_number}'
                )
                db.session.add(credit)
                db.session.commit()
                log_action(current_user, 'CREATE_CREDIT', 'CREDIT_ENTRY', credit.id)
                
                if form.payment_type.data == 'FULL':
                    flash('Bill created and fully paid. Credit entry created.', 'success')
                else:
                    flash(f'Bill created with partial payment of ₹{payment_amount}. Credit entry created.', 'success')
            else:
                flash('Bill created successfully.', 'success')
        else:
            flash('Bill created successfully (unpaid).', 'success')
        
        # Handle proxy bill creation if requested
        if form.is_proxy.data == 'YES' and form.number_of_splits.data and form.number_of_splits.data > 0:
            return redirect(url_for('bill.create_proxy_splits', id=bill.id, splits=form.number_of_splits.data))
        
        return redirect(url_for('bill.detail', id=bill.id))
    
    return render_template('bills/form.html', form=form, title='New Bill')


def extract_bill_info(ocr_text):
    """Extract bill information from OCR text with improved accuracy"""
    import re
    from datetime import datetime
    
    suggestions = {
        'bill_number': None,
        'bill_date': None,
        'items': [],
        'subtotal': None,
        'tax': None,
        'total': None,
        'vendor_name': None
    }
    
    if not ocr_text or not ocr_text.strip():
        return suggestions
    
    # Clean and split text into lines
    lines = [line.strip() for line in ocr_text.split('\n') if line.strip()]
    full_text = ' '.join(lines).lower()
    
    # Extract Bill/Invoice Number - More comprehensive patterns
    # Look for patterns like "ORD-2023-78912" or "Bill Number: ORD-2023-78912"
    bill_patterns = [
        r'(?:bill|invoice|inv)[\s]*(?:number|no)[\s#:]*([A-Z0-9\-/]+)',  # "Bill Number: ORD-2023-78912"
        r'(?:bill|invoice|inv)[\s#:]+([A-Z0-9\-/]+)',  # "Bill: ORD-2023-78912"
        r'#\s*([A-Z0-9\-/]+)',  # "#ORD-2023-78912"
        r'no[.:\s]+([A-Z0-9\-/]+)',  # "No. ORD-2023-78912"
        r'([A-Z]{2,}[-/]\d{4}[-/]\d{3,})',  # Pattern like ORD-2023-78912
        r'([A-Z]{2,}\d{4,})',  # Pattern like ABC1234
        r'(\d{4,}[-/][A-Z0-9]+)',  # Pattern like 2023-ORD789
    ]
    
    for line in lines[:20]:  # Check first 20 lines
        # Skip lines that are form labels
        if any(keyword in line.lower() for keyword in ['bill type', 'payment', 'create proxy', 'items', 'subtotal', 'tax']):
            continue
            
        for pattern in bill_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                bill_num = match.group(1).strip()
                # Validate it looks like a bill number (has alphanumeric and is not just "Number")
                if (len(bill_num) >= 5 and 
                    re.search(r'[A-Z]', bill_num) and 
                    re.search(r'[0-9]', bill_num) and
                    bill_num.lower() != 'number'):
                    suggestions['bill_number'] = bill_num
                    break
        if suggestions['bill_number']:
            break
    
    # Extract Date - More comprehensive date patterns
    # Prioritize YYYY-MM-DD format first (most common in bills)
    date_patterns = [
        (r'\d{4}[/-]\d{1,2}[/-]\d{1,2}', ['%Y-%m-%d', '%Y/%m/%d']),  # 2023-10-27 or 2023/10/27
        (r'(?:bill|invoice)[\s]*(?:date|dated)[\s:]*(\d{4}[/-]\d{1,2}[/-]\d{1,2})', ['%Y-%m-%d', '%Y/%m/%d']),  # "Bill Date: 2023-10-27"
        (r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', ['%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%m-%y', '%m/%d/%Y', '%m-%d-%Y']),
        (r'\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4}', ['%d %b %Y', '%d %B %Y', '%d %b %y']),
        (r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{2,4}', ['%b %d, %Y', '%B %d, %Y', '%b %d %Y']),
    ]
    
    for line in lines[:25]:  # Check first 25 lines
        # Skip lines that are form labels
        if any(keyword in line.lower() for keyword in ['bill type', 'payment', 'create proxy', 'items']):
            continue
            
        for pattern, formats in date_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                date_str = match.group(1) if len(match.groups()) > 0 else match.group(0)
                date_str = date_str.strip()
                # Try to parse with different formats
                for fmt in formats:
                    try:
                        parsed_date = datetime.strptime(date_str, fmt)
                        # Validate year is reasonable (not in future, not too old)
                        if 2000 <= parsed_date.year <= 2100:
                            suggestions['bill_date'] = parsed_date.strftime('%Y-%m-%d')
                            break
                    except:
                        continue
                if suggestions['bill_date']:
                    break
        if suggestions['bill_date']:
            break
    
    # Extract Amounts - Improved pattern matching
    # Look for amounts with currency symbols (₹, $, S, etc.) and labels
    # Handle "S" as currency symbol (might be "$" in OCR)
    amount_patterns = {
        'total': [
            r'(?:grand\s*)?total[:\s]*[₹$S]?\s*(\d+(?:[.,]\d{2})?)',
            r'total[:\s]*[₹$S]?\s*(\d+(?:[.,]\d{2})?)',
            r'total\s*amount[:\s]*[₹$S]?\s*(\d+(?:[.,]\d{2})?)',
            r'amount\s*payable[:\s]*[₹$S]?\s*(\d+(?:[.,]\d{2})?)',
        ],
        'subtotal': [
            r'sub\s*total[:\s]*[₹$S]?\s*(\d+(?:[.,]\d{2})?)',
            r'total\s*before\s*tax[:\s]*[₹$S]?\s*(\d+(?:[.,]\d{2})?)',
        ],
        'tax': [
            r'(?:gst|tax|vat)[\s(]*\d+%[):\s]*[₹$S]?\s*(\d+(?:[.,]\d{2})?)',  # "Tax (18%): S15.75"
            r'(?:gst|tax|vat)[:\s]*[₹$S]?\s*(\d+(?:[.,]\d{2})?)',
            r'tax\s*amount[:\s]*[₹$S]?\s*(\d+(?:[.,]\d{2})?)',
        ]
    }
    
    # Search from bottom up for totals (usually at end of bill)
    for line in reversed(lines):
        line_clean = line.strip()
        line_lower = line_clean.lower()
        
        # Skip empty lines or form labels
        if not line_clean or any(keyword in line_lower for keyword in ['bill type', 'payment', 'create proxy']):
            continue
            
        for amount_type, patterns in amount_patterns.items():
            if not suggestions.get(amount_type):
                for pattern in patterns:
                    match = re.search(pattern, line_lower, re.IGNORECASE)
        if match:
                        amount_str = match.group(1)
                        # Clean amount: remove commas, keep decimal point
                        amount = amount_str.replace(',', '')
                        # Validate it's a reasonable amount
                        try:
                            amount_float = float(amount)
                            if amount_float > 0:
                                suggestions[amount_type] = amount
                                break
                        except:
                            pass
    
    # Extract Items - More robust item extraction
    # Look for table-like structures with items
    item_started = False
    item_headers_found = False
    
    for i, line in enumerate(lines):
        line_lower = line.lower()
        
        # Detect item table header
        if any(keyword in line_lower for keyword in ['description', 'item', 'particular', 'product']):
            if any(keyword in line_lower for keyword in ['qty', 'quantity', 'rate', 'price', 'amount']):
                item_headers_found = True
                item_started = True
                continue
        
        # Skip if we haven't found item section yet
        if not item_started and i < len(lines) * 0.3:  # Items usually in middle section
            continue
        
        # Stop if we hit totals section
        if any(keyword in line_lower for keyword in ['total', 'subtotal', 'grand total', 'amount payable']):
            if item_started:
                break
        
        # Extract item data - Handle formats like:
        # "1 Wireless Keyboard S45.00 S45.00"
        # "2. USB-C Cable - S12.50 S12.50"
        # "3. Desk Lamp S30.00 S30.00"
        
        # Skip if line starts with common non-item keywords
        if any(line_lower.startswith(keyword) for keyword in ['subtotal', 'tax', 'total', 'items', 'description']):
            continue
        
        # Try to match item pattern: number + description + numbers (with optional currency)
        # Pattern: optional number/dot, description text, then 1-3 price amounts
        item_match = re.match(r'^\d+[.\s]*(.+?)(?:\s+[₹$S-]?\s*\d+(?:[.,]\d{2})?)+\s*$', line, re.IGNORECASE)
        if not item_match:
            # Try splitting on spaces/tabs
            parts = re.split(r'\s{2,}|\t', line)
            if len(parts) < 2:
                parts = line.split()
        else:
            parts = line.split()
        
        # Extract numbers with currency symbols (₹, $, S)
        numbers = []
        text_parts = []
        seen_dash = False
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # Skip item numbers (1, 2., etc.)
            if re.match(r'^\d+\.?$', part):
                continue
            
            # Check if it's a dash (for missing quantity)
            if part == '-':
                seen_dash = True
                numbers.append('1')  # Default quantity to 1
                continue
            
            # Check if it's a number with currency symbol
            num_match = re.search(r'[₹$S]?\s*(\d+(?:[.,]\d{2})?)', part)
            if num_match:
                num = num_match.group(1).replace(',', '')
                try:
                    float(num)
                    numbers.append(num)
                except:
                    text_parts.append(part)
            else:
                text_parts.append(part)
        
        # If we have description and at least 1 number (price), it's likely an item
        if len(text_parts) > 0 and len(numbers) >= 1:
            description = ' '.join(text_parts).strip()
            
            # Remove leading numbers/dots from description
            description = re.sub(r'^\d+[.\s]+', '', description)
            
            # Filter out common non-item lines
            if (len(description) > 2 and 
                not any(keyword in description.lower() for keyword in 
                    ['total', 'subtotal', 'tax', 'gst', 'discount', 'bill', 'invoice', 'date', 'page', 'items'])):
                
                # Determine quantity and price
                # If we have 2+ numbers: first might be qty, second is price
                # If we have 1 number: it's likely the price, qty defaults to 1
                if len(numbers) >= 2:
                    # First number might be quantity if it's small (< 1000), otherwise it's a price
                    first_num = float(numbers[0])
                    if first_num < 1000 and first_num > 0:
                        qty = str(first_num)
                        price = numbers[1]
                    else:
                        qty = '1'
                        price = numbers[0]
                elif len(numbers) == 1:
                    qty = '1'
                    price = numbers[0]
                else:
                    continue
                
                # Validate numbers are reasonable
                try:
                    qty_float = float(qty)
                    price_float = float(price)
                    if qty_float > 0 and price_float > 0:
                        suggestions['items'].append({
                            'description': description,
                            'quantity': str(qty_float),
                            'unit_price': str(price_float)
                        })
                except:
                    pass
        
        # Limit items
        if len(suggestions['items']) >= 50:
            break
    
    # Extract Vendor Name - Usually at the top, but skip form labels
    if lines:
        # First few non-empty lines are often vendor info
        skip_keywords = ['bill', 'invoice', 'date', 'page', 'gst', 'number', 'normal', 'handbill', 
                        'yes', 'no', 'payment', 'status', 'items', 'subtotal', 'tax', 'total',
                        'create proxy', 'fully paid', 'unpaid', 'partially paid']
        
        for line in lines[:10]:
            line_clean = line.strip()
            line_lower = line_clean.lower()
            
            # Skip if it looks like a number, date, form label, or common header
            if (len(line_clean) > 3 and len(line_clean) < 100 and 
                not re.match(r'^[\d\s\-/:]+$', line_clean) and
                not any(keyword in line_lower for keyword in skip_keywords) and
                not re.match(r'^[A-Z0-9\-/]+$', line_clean) and  # Skip bill numbers
                not re.search(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', line_clean)):  # Skip dates
                suggestions['vendor_name'] = line_clean
            break
    
    return suggestions


@bill_bp.route('/<int:id>/create-proxy-splits/<int:splits>', methods=['GET', 'POST'])
@login_required
@permission_required('create_bill')
def create_proxy_splits(id, splits):
    """Create multiple proxy bills from a parent bill"""
    bill = Bill.query.get_or_404(id)
    tenant = get_default_tenant()
    
    if request.method == 'POST':
        # Get all proxy bill data from form
        for i in range(splits):
            proxy_number = request.form.get(f'proxy_number_{i}')
            vendor_id = request.form.get(f'vendor_id_{i}', type=int)
            
            if proxy_number and vendor_id:
                # Get items for this proxy
                descriptions = request.form.getlist(f'item_description_{i}[]')
                quantities = request.form.getlist(f'item_quantity_{i}[]')
                unit_prices = request.form.getlist(f'item_unit_price_{i}[]')
                
                total = Decimal('0.00')
                items = []
                
                for j in range(len(descriptions)):
                    if descriptions[j].strip():
                        qty = Decimal(quantities[j] or '0')
                        price = Decimal(unit_prices[j] or '0')
                        amount = qty * price
                        total += amount
                        items.append({
                            'description': descriptions[j],
                            'quantity': qty,
                            'unit_price': price,
                            'amount': amount
                        })
                
                proxy_bill = ProxyBill(
                    tenant_id=tenant.id,
                    parent_bill_id=bill.id,
                    vendor_id=vendor_id,
                    proxy_number=proxy_number,
                    status='DRAFT',
                    amount_total=total
                )
                db.session.add(proxy_bill)
                db.session.flush()
                
                for item_data in items:
                    item = ProxyBillItem(
                        proxy_bill_id=proxy_bill.id,
                        description=item_data['description'],
                        quantity=item_data['quantity'],
                        unit_price=item_data['unit_price'],
                        amount=item_data['amount']
                    )
                    db.session.add(item)
        
        db.session.commit()
        log_action(current_user, 'CREATE_PROXY_SPLITS', 'BILL', bill.id)
        flash(f'Created {splits} proxy bill(s) successfully.', 'success')
        return redirect(url_for('bill.detail', id=bill.id))
    
    vendors = Vendor.query.filter_by(tenant_id=tenant.id).order_by(Vendor.name).all()
    return render_template('bills/create_proxy_splits.html', bill=bill, splits=splits, vendors=vendors)


@bill_bp.route('/<int:id>')
@login_required
@permission_required('view_bills')
def detail(id):
    bill = Bill.query.get_or_404(id)
    tenant = get_default_tenant()
    credits = CreditEntry.query.filter_by(bill_id=bill.id, direction='INCOMING').all()
    proxy_bills = ProxyBill.query.filter_by(parent_bill_id=bill.id).all()
    
    # Calculate payment status
    total_paid = db.session.query(func.sum(CreditEntry.amount)).filter_by(
        tenant_id=tenant.id,
        bill_id=bill.id,
        direction='INCOMING'
    ).scalar() or Decimal('0.00')
    
    remaining = bill.amount_total - total_paid
    
    payment_status = 'UNPAID'
    if total_paid >= bill.amount_total:
        payment_status = 'FULLY_PAID'
    elif total_paid > 0:
        payment_status = 'PARTIALLY_PAID'
    
    return render_template('bills/detail.html', 
                         bill=bill, 
                         credits=credits, 
                         proxy_bills=proxy_bills,
                         total_paid=total_paid,
                         remaining=remaining,
                         payment_status=payment_status)


@bill_bp.route('/<int:id>/confirm', methods=['POST'])
@login_required
@permission_required('confirm_bill')
def confirm(id):
    bill = Bill.query.get_or_404(id)
    if bill.status == 'DRAFT':
        bill.status = 'CONFIRMED'
        db.session.commit()
        log_action(current_user, 'CONFIRM_BILL', 'BILL', bill.id)
        flash('Bill confirmed.', 'success')
    return redirect(url_for('bill.detail', id=bill.id))


@bill_bp.route('/<int:id>/authorize', methods=['POST'])
@login_required
@permission_required('authorize_bill')
def authorize(id):
    """Authorize a bill so organiser can see it"""
    bill = Bill.query.get_or_404(id)
    tenant = get_default_tenant()
    
    if bill.tenant_id != tenant.id:
        flash('Bill not found.', 'danger')
        return redirect(url_for('bill.list'))
    
    if bill.is_authorized:
        flash('Bill is already authorized.', 'warning')
        return redirect(url_for('bill.detail', id=id))
    
    bill.is_authorized = True
    bill.authorized_by = current_user.id
    bill.authorized_at = datetime.utcnow()
    db.session.commit()
    log_action(current_user, 'AUTHORIZE_BILL', 'BILL', bill.id)
    flash('Bill authorized successfully. Organiser can now view this bill.', 'success')
    return redirect(url_for('bill.detail', id=id))


@bill_bp.route('/<int:id>/unauthorize', methods=['POST'])
@login_required
@permission_required('authorize_bill')
def unauthorize(id):
    """Unauthorize a bill so organiser cannot see it"""
    bill = Bill.query.get_or_404(id)
    tenant = get_default_tenant()
    
    if bill.tenant_id != tenant.id:
        flash('Bill not found.', 'danger')
        return redirect(url_for('bill.list'))
    
    if not bill.is_authorized:
        flash('Bill is not authorized.', 'warning')
        return redirect(url_for('bill.detail', id=id))
    
    bill.is_authorized = False
    bill.authorized_by = None
    bill.authorized_at = None
    db.session.commit()
    log_action(current_user, 'UNAUTHORIZE_BILL', 'BILL', bill.id)
    flash('Bill unauthorized successfully. Organiser can no longer view this bill.', 'success')
    return redirect(url_for('bill.detail', id=id))


@bill_bp.route('/<int:id>/cancel', methods=['POST'])
@login_required
@permission_required('cancel_bill')
def cancel(id):
    bill = Bill.query.get_or_404(id)
    if bill.status != 'CANCELLED':
        bill.status = 'CANCELLED'
        db.session.commit()
        log_action(current_user, 'CANCEL_BILL', 'BILL', bill.id)
        flash('Bill cancelled.', 'success')
    return redirect(url_for('bill.detail', id=bill.id))


@bill_bp.route('/<int:id>/mark-paid', methods=['POST'])
@login_required
@permission_required('create_credit')
def mark_paid(id):
    """Mark a bill as paid (full or partial) and create credit entry"""
    bill = Bill.query.get_or_404(id)
    tenant = get_default_tenant()
    
    # Get payment details from form
    payment_type = request.form.get('payment_type', 'FULL')
    payment_method = request.form.get('payment_method', 'CASH')
    payment_reference = request.form.get('payment_reference', '')
    payment_date_str = request.form.get('payment_date')
    partial_amount_str = request.form.get('partial_amount', '0')
    
    from datetime import datetime
    if payment_date_str:
        try:
            payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d').date()
        except:
            payment_date = bill.bill_date
    else:
        payment_date = bill.bill_date
    
    # Calculate payment amount
    if payment_type == 'FULL':
        payment_amount = bill.amount_total
    else:
        try:
            payment_amount = Decimal(partial_amount_str)
            if payment_amount <= 0:
                flash('Partial payment amount must be greater than 0.', 'danger')
                return redirect(url_for('bill.detail', id=bill.id))
            if payment_amount > bill.amount_total:
                flash('Partial payment amount cannot exceed bill total.', 'danger')
                return redirect(url_for('bill.detail', id=bill.id))
        except:
            flash('Invalid partial payment amount.', 'danger')
            return redirect(url_for('bill.detail', id=bill.id))
    
    # Check total paid so far
    total_paid = db.session.query(func.sum(CreditEntry.amount)).filter_by(
        tenant_id=tenant.id,
        bill_id=bill.id,
        direction='INCOMING'
    ).scalar() or Decimal('0.00')
    
    remaining = bill.amount_total - total_paid
    
    if payment_amount > remaining:
        flash(f'Payment amount exceeds remaining balance of ₹{remaining}.', 'danger')
        return redirect(url_for('bill.detail', id=bill.id))
    
    # Create credit entry
    credit = CreditEntry(
        tenant_id=tenant.id,
        bill_id=bill.id,
        vendor_id=bill.vendor_id,
        amount=payment_amount,
        direction='INCOMING',
        payment_method=payment_method,
        payment_date=payment_date,
        reference_number=payment_reference,
        notes=f'Payment for bill {bill.bill_number}'
    )
    db.session.add(credit)
    db.session.commit()
    log_action(current_user, 'MARK_BILL_PAID', 'BILL', bill.id)
    log_action(current_user, 'CREATE_CREDIT', 'CREDIT_ENTRY', credit.id)
    
    if payment_type == 'FULL':
        flash('Bill marked as fully paid. Credit entry created.', 'success')
    else:
        flash(f'Partial payment of ₹{payment_amount} recorded. Credit entry created.', 'success')
    
    return redirect(url_for('bill.detail', id=bill.id))

