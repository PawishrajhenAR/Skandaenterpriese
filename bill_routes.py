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
@permission_required('create_bill')
def ocr_upload():
    """Handle OCR image upload and return extracted text with advanced processing"""
    try:
        # Check if file is provided
        if 'ocr_image' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['ocr_image']
        if not file or not file.filename:
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        # Check file extension
        allowed_extensions = {'png', 'jpg', 'jpeg', 'pdf'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        if file_ext not in allowed_extensions:
            return jsonify({'success': False, 'error': 'Invalid file type. Please upload JPG, PNG, or PDF.'}), 400
        
        # Save file
        try:
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"ocr_{timestamp}_{filename}"
            
            upload_folder = Path(current_app.config['UPLOAD_FOLDER'])
            upload_folder.mkdir(parents=True, exist_ok=True)
            filepath = upload_folder / filename
            file.save(str(filepath))
        except Exception as save_error:
            return jsonify({
                'success': False,
                'error': f'Failed to save file: {str(save_error)}'
            }), 500
        
        # Run advanced OCR with detailed results
        try:
            # Check if OCR utils is available
            try:
                ocr_result = run_ocr(str(filepath), return_detailed=True)
            except NameError:
                return jsonify({
                    'success': False,
                    'error': 'OCR module not properly imported. Please check server logs.'
                }), 500
            
            # Check if OCR returned an error message (string)
            if isinstance(ocr_result, str):
                if (ocr_result.startswith("OCR error:") or 
                    ocr_result.startswith("Error:") or 
                    "not installed" in ocr_result.lower() or
                    "failed" in ocr_result.lower()):
                    return jsonify({
                        'success': False,
                        'error': ocr_result
                    }), 500
                # Fallback: treat as simple text extraction
                ocr_text = ocr_result
                ocr_detailed = None
            elif isinstance(ocr_result, dict):
                # Use detailed results
                ocr_text = ocr_result.get('text', '')
                ocr_detailed = ocr_result.get('detailed', [])
                
                # Validate that we got some text
                if not ocr_text or not ocr_text.strip():
                    return jsonify({
                        'success': False,
                        'error': 'No text could be extracted from the image. Please ensure the image is clear and contains readable text.'
                    }), 500
            else:
                # Unexpected return type
                current_app.logger.warning(f"Unexpected OCR result type: {type(ocr_result)}")
                return jsonify({
                    'success': False,
                    'error': 'Unexpected OCR result format. Please try again.'
                }), 500
            
            # Extract information using advanced extraction with bounding box context
            try:
                suggestions = extract_bill_info_advanced(ocr_text, ocr_detailed)
                # Log extraction results for debugging
                current_app.logger.info(f"OCR Extraction Results: {suggestions}")
            except Exception as extract_error:
                current_app.logger.error(f"Advanced extraction failed: {str(extract_error)}")
                # If advanced extraction fails, try basic extraction
                try:
                    suggestions = extract_bill_info(ocr_text)
                    current_app.logger.info(f"Basic extraction results: {suggestions}")
                except Exception as basic_error:
                    current_app.logger.error(f"Basic extraction also failed: {str(basic_error)}")
                    suggestions = {
                        'bill_number': None,
                        'bill_date': None,
                        'delivery_date': None,
                        'subtotal': None,
                        'tax': None,
                        'total': None,
                        'total_net': None,
                        'vendor_name': None,
                        'billed_to_name': None,
                        'shipped_to_name': None,
                        'delivery_recipient': None,
                        'post': None
                    }
            
            return jsonify({
                'success': True,
                'ocr_text': ocr_text,
                'image_path': f"uploads/bills/{filename}",
                'suggestions': suggestions
            })
            
        except ImportError as import_error:
            return jsonify({
                'success': False,
                'error': f'OCR library not available: {str(import_error)}'
            }), 500
        except Exception as ocr_error:
            import traceback
            error_trace = traceback.format_exc()
            current_app.logger.error(f"OCR processing error: {error_trace}")
            return jsonify({
                'success': False,
                'error': f'OCR processing failed: {str(ocr_error)}'
            }), 500
            
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        current_app.logger.error(f"OCR upload error: {error_trace}")
        return jsonify({
            'success': False,
            'error': f'Upload failed: {str(e)}'
        }), 500


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
        # Get amounts directly from form
        subtotal = Decimal(request.form.get('amount_subtotal', '0.00') or '0.00')
        tax = Decimal(request.form.get('amount_tax', '0.00') or '0.00')
        total = Decimal(request.form.get('amount_total', '0.00') or '0.00')
        
        bill = Bill(
            tenant_id=tenant.id,
            vendor_id=form.vendor_id.data,
            bill_number=form.bill_number.data,
            bill_date=form.bill_date.data,
            bill_type=form.bill_type.data,
            status='DRAFT',
            amount_subtotal=subtotal,
            amount_tax=tax,
            amount_total=total,
            delivery_date=form.delivery_date.data if form.delivery_date.data else None,
            billed_to_name=form.billed_to_name.data if form.billed_to_name.data else None,
            shipped_to_name=form.shipped_to_name.data if form.shipped_to_name.data else None,
            delivery_recipient=form.delivery_recipient.data if form.delivery_recipient.data else None,
            post=form.post.data if form.post.data else None
        )
        try:
            db.session.add(bill)
            db.session.flush()  # Get bill.id before commit
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
                    db.session.flush()
                    log_action(current_user, 'CREATE_CREDIT', 'CREDIT_ENTRY', credit.id)
            
            db.session.commit()
            
            # Show success messages
            if form.payment_type.data in ['FULL', 'PARTIAL']:
                payment_amount = bill.amount_total if form.payment_type.data == 'FULL' else (form.partial_amount.data or Decimal('0.00'))
                if payment_amount > 0:
                    if form.payment_type.data == 'FULL':
                        flash('Bill created and fully paid. Credit entry created.', 'success')
                    else:
                        flash(f'Bill created with partial payment of ₹{payment_amount}. Credit entry created.', 'success')
                else:
                    flash('Bill created successfully.', 'success')
            else:
                flash('Bill created successfully (unpaid).', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating bill: {str(e)}', 'danger')
            return render_template('bills/form.html', form=form, title='New Bill')
        
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
        'delivery_date': None,
        'subtotal': None,
        'tax': None,
        'total': None,
        'total_net': None,
        'vendor_name': None,
        'billed_to_name': None,
        'shipped_to_name': None,
        'delivery_recipient': None,
        'post': None
    }
    
    if not ocr_text or not ocr_text.strip():
        return suggestions
    
    # Clean and split text into lines
    lines = [line.strip() for line in ocr_text.split('\n') if line.strip()]
    full_text = ' '.join(lines).lower()
    
    # Extract Invoice Number - Focus on "Invoice" instead of "Bill"
    # Look for patterns like "1/25-26/014013" or "Invoice No: 1/25-26/014013"
    invoice_patterns = [
        r'invoice\s+no[.:\s]+([A-Z0-9\-/]+)',  # "Invoice No. 1/25-26/014014"
        r'(?:invoice|inv)[\s]*(?:number|no|#)[\s#:]*([A-Z0-9\-/]+)',  # "Invoice Number: 1/25-26/014013"
        r'(?:invoice|inv)[\s#:]+([A-Z0-9\-/]+)',  # "Invoice: 1/25-26/014013"
        r'inv[.\s]*no[.:\s]+([A-Z0-9\-/]+)',  # "Inv No. 1/25-26/014013"
        r'doc[.\s]*no[.:\s]+([A-Z0-9\-/]+)',  # "Doc No: MM/25-26/014013"
        r'#\s*([A-Z0-9\-/]+)',  # "#1/25-26/014013"
        r'no[.:\s]+([A-Z0-9\-/]+)',  # "No. 1/25-26/014013"
        r'([A-Z0-9]{1,}[/-]\d{2,}[/-]\d{2,}[/-]\d{3,})',  # Pattern like 1/25-26/014013
        r'([A-Z]{2,}[-/]\d{4}[-/]\d{3,})',  # Pattern like ORD-2023-78912
        r'([A-Z]{2,}\d{4,})',  # Pattern like ABC1234
        r'(\d{4,}[-/][A-Z0-9]+)',  # Pattern like 2023-ORD789
    ]
    
    # Check both individual lines and combined text
    full_text_lower = full_text.lower()
    for pattern in invoice_patterns:
        match = re.search(pattern, full_text_lower, re.IGNORECASE)
        if match:
            invoice_num = match.group(1).strip()
            # Clean up - remove common suffixes
            invoice_num = re.sub(r'\s*(?:gst|phone|email|address|pincode|pin|state|city|page|date|invoice).*$', '', invoice_num, flags=re.IGNORECASE)
            invoice_num = invoice_num.strip()
            # Validate it looks like an invoice number
            if (len(invoice_num) >= 3 and len(invoice_num) < 100 and
                invoice_num.lower() != 'number' and
                invoice_num.lower() != 'no' and
                '/' in invoice_num):  # Invoice numbers usually have slashes
                suggestions['bill_number'] = invoice_num  # Store as bill_number in DB
                break
    
    # Also check line by line if not found
    if not suggestions['bill_number']:
        for line in lines[:30]:
            # Skip lines that are form labels
            if any(keyword in line.lower() for keyword in ['bill type', 'payment', 'create proxy', 'items', 'subtotal', 'tax']):
                continue
                
            for pattern in invoice_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    invoice_num = match.group(1).strip()
                    invoice_num = re.sub(r'\s*(?:gst|phone|email|address|pincode|pin|state|city|page|date).*$', '', invoice_num, flags=re.IGNORECASE)
                    invoice_num = invoice_num.strip()
                    if (len(invoice_num) >= 3 and len(invoice_num) < 100 and
                        invoice_num.lower() != 'number' and
                        invoice_num.lower() != 'no'):
                        suggestions['bill_number'] = invoice_num
                        break
            if suggestions['bill_number']:
                break
    
    # Extract Date - More comprehensive date patterns
    # Handle DD/MM/YYYY format (common in Indian invoices)
    date_patterns = [
        (r'invoice\s+date[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', ['%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%m-%y']),  # "Invoice Date: 04/12/2025"
        (r'(?:bill|invoice)[\s]*(?:date|dated)[\s:]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', ['%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%m-%y']),
        (r'\d{1,2}[/-]\d{1,2}[/-]\d{4}', ['%d/%m/%Y', '%d-%m-%Y']),  # DD/MM/YYYY format
        (r'\d{4}[/-]\d{1,2}[/-]\d{1,2}', ['%Y-%m-%d', '%Y/%m/%d']),  # YYYY-MM-DD format
        (r'\d{1,2}[/-]\d{1,2}[/-]\d{2}', ['%d/%m/%y', '%d-%m-%y']),  # DD/MM/YY format
        (r'\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4}', ['%d %b %Y', '%d %B %Y', '%d %b %y']),
    ]
    
    # Check full text first for "Invoice Date:" pattern
    for pattern, formats in date_patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            date_str = match.group(1) if len(match.groups()) > 0 else match.group(0)
            date_str = date_str.strip()
            for fmt in formats:
                try:
                    parsed_date = datetime.strptime(date_str, fmt)
                    if 2000 <= parsed_date.year <= 2100:
                        suggestions['bill_date'] = parsed_date.strftime('%Y-%m-%d')
                        break
                except:
                    continue
            if suggestions['bill_date']:
                break
    
    # Also check line by line if not found
    if not suggestions['bill_date']:
        for line in lines[:30]:
            if any(keyword in line.lower() for keyword in ['bill type', 'payment', 'create proxy', 'items']):
                continue
                
            for pattern, formats in date_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    date_str = match.group(1) if len(match.groups()) > 0 else match.group(0)
                    date_str = date_str.strip()
                    for fmt in formats:
                        try:
                            parsed_date = datetime.strptime(date_str, fmt)
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
            r'(?:net\s+amt\s+payable|net\s+amount\s+payable|amount\s+payable)[:\s]*[₹$S]?\s*(\d+(?:[.,]\d{2})?)',  # "NNet Amt Payable 815.00"
            r'(?:grand\s*)?total[:\s]*[₹$S]?\s*(\d+(?:[.,]\d{2})?)',
            r'total[:\s]*[₹$S]?\s*(\d+(?:[.,]\d{2})?)',
            r'total\s*amount[:\s]*[₹$S]?\s*(\d+(?:[.,]\d{2})?)',
        ],
        'total_net': [
            r'(?:nnet\s+amt\s+payable|net\s+amt\s+payable|net\s+amount\s+payable)[:\s]*[₹$S]?\s*(\d+(?:[.,]\d{2})?)',  # "NNet Amt Payable 815.00"
            r'net\s+amt[:\s]*[₹$S]?\s*(\d+(?:[.,]\d{2})?)',  # "Net Amt: 815.00"
            r'(?:net|net\s+amount)[:\s]*[₹$S]?\s*(\d+(?:[.,]\d{2})?)',
            r'total\s+net[:\s]*[₹$S]?\s*(\d+(?:[.,]\d{2})?)',
        ],
        'subtotal': [
            r'(?:taxable\s+value|taxable\s+amt)[:\s]*[₹$S]?\s*(\d+(?:[.,]\d{2})?)',  # "Taxable Value" from invoice
            r'sub\s*total[:\s]*[₹$S]?\s*(\d+(?:[.,]\d{2})?)',
            r'total\s*before\s*tax[:\s]*[₹$S]?\s*(\d+(?:[.,]\d{2})?)',
        ],
        'tax': [
            r'total\s+tax\s+amt[:\s]*[₹$S]?\s*(\d+(?:[.,]\d{2})?)',  # "Total Tax Amt: 38.80"
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
    
    # Extract Delivery Date - Look for delivery date patterns
    delivery_date_patterns = [
        (r'(?:delivery|delivered|ship|shipped)[\s]*(?:date|on|dt)[\s:]*(\d{4}[/-]\d{1,2}[/-]\d{1,2})', ['%Y-%m-%d', '%Y/%m/%d']),
        (r'(?:delivery|delivered|ship|shipped)[\s]*(?:date|on|dt)[\s:]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', ['%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%m-%y', '%m/%d/%Y', '%m-%d-%Y']),
        (r'(?:delivery|delivered|ship|shipped)[\s]*(?:date|on|dt)[\s:]*(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4})', ['%d %b %Y', '%d %B %Y', '%d %b %y']),
    ]
    
    for line in lines[:30]:
        line_lower = line.lower()
        if any(keyword in line_lower for keyword in ['bill type', 'payment', 'create proxy', 'items']):
            continue
        
        for pattern, formats in delivery_date_patterns:
            match = re.search(pattern, line_lower, re.IGNORECASE)
            if match:
                date_str = match.group(1).strip()
                for fmt in formats:
                    try:
                        parsed_date = datetime.strptime(date_str, fmt)
                        if 2000 <= parsed_date.year <= 2100:
                            suggestions['delivery_date'] = parsed_date.strftime('%Y-%m-%d')
                            break
                    except:
                        continue
                if suggestions['delivery_date']:
                    break
        if suggestions['delivery_date']:
            break
    
    # Extract Total Net Amount - Look for "NNet Amt Payable" or "Net Amt Payable" patterns
    net_amount_patterns = [
        r'(?:nnet\s+amt\s+payable|net\s+amt\s+payable|net\s+amount\s+payable)[:\s]*[₹$S]?\s*(\d+(?:[.,]\d{2})?)',  # "NNet Amt Payable 815.00"
        r'net\s+amt[:\s]*[₹$S]?\s*(\d+(?:[.,]\d{2})?)',  # "Net Amt: 815.00"
        r'(?:net|net\s+amount|amount\s+net)[\s:]*[₹$S]?\s*(\d+(?:[.,]\d{2})?)',
        r'total\s+net[:\s]*[₹$S]?\s*(\d+(?:[.,]\d{2})?)',
        r'net\s+total[:\s]*[₹$S]?\s*(\d+(?:[.,]\d{2})?)',
    ]
    
    # Check full text first for "NNet Amt Payable" pattern
    for pattern in net_amount_patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            amount_str = match.group(1).replace(',', '')
            try:
                amount_float = float(amount_str)
                if amount_float > 0:
                    suggestions['total_net'] = amount_str
                    break
            except:
                pass
    
    # Also check line by line from bottom up (totals are usually at bottom)
    if not suggestions['total_net']:
        for line in reversed(lines):
            line_lower = line.lower().strip()
            if not line_lower or any(keyword in line_lower for keyword in ['bill type', 'payment', 'create proxy']):
                continue
            
            for pattern in net_amount_patterns:
                match = re.search(pattern, line_lower, re.IGNORECASE)
                if match:
                    amount_str = match.group(1).replace(',', '')
                    try:
                        amount_float = float(amount_str)
                        if amount_float > 0:
                            suggestions['total_net'] = amount_str
                            break
                    except:
                        pass
            if suggestions['total_net']:
                break
    
    # Extract Billed To Name - Look for "billed to", "bill to", "customer", etc.
    billed_to_patterns = [
        r'(?:billed\s+to|bill\s+to|customer|cust\.|buyer|purchaser)[\s:]+(.+?)(?:\n|$)',
        r'(?:billed\s+to|bill\s+to|customer|cust\.)[\s:]+(.+?)(?:\n|delivery|ship|address|gst|phone|email|$)',
    ]
    
    for i, line in enumerate(lines[:40]):
        line_lower = line.lower()
        if any(keyword in line_lower for keyword in ['bill type', 'payment', 'create proxy', 'items', 'total', 'subtotal']):
            continue
        
        for pattern in billed_to_patterns:
            match = re.search(pattern, line_lower, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                # Clean up the name - remove common suffixes
                name = re.sub(r'\s*(?:gst|phone|email|address|pincode|pin|state|city).*$', '', name, flags=re.IGNORECASE)
                name = name.strip()
                if len(name) > 2 and len(name) < 200:
                    suggestions['billed_to_name'] = name
                    break
        
        # Also check next line if current line has the label
        if 'billed to' in line_lower or 'bill to' in line_lower or 'customer' in line_lower:
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if len(next_line) > 2 and len(next_line) < 200:
                    # Check if it's not a date, number, or address pattern
                    if not re.match(r'^[\d\s\-/:]+$', next_line) and not re.search(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', next_line):
                        suggestions['billed_to_name'] = next_line
                        break
        
        if suggestions['billed_to_name']:
            break
    
    # Extract Shipped To Name - Look for "shipped to", "ship to", "delivery to", etc.
    shipped_to_patterns = [
        r'shipped\s+to[:\s]+(.+?)(?:\n|cust\s+code|address|gst|phone|email|$)',
        r'(?:shipped\s+to|ship\s+to|delivery\s+to|deliver\s+to|consignee|recipient)[\s:]+(.+?)(?:\n|$)',
    ]
    
    # Check full text first
    for pattern in shipped_to_patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            name = re.sub(r'\s*(?:cust\s*code|address|gst|phone|email|pincode|pin|state|city).*$', '', name, flags=re.IGNORECASE)
            name = name.strip()
            if len(name) > 2 and len(name) < 200 and not re.match(r'^[\d\s\-/:]+$', name):
                suggestions['shipped_to_name'] = name
                break
    
    # Also check line by line
    if not suggestions['shipped_to_name']:
        for i, line in enumerate(lines[:40]):
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in ['bill type', 'payment', 'create proxy', 'items', 'total', 'subtotal']):
                continue
            
            for pattern in shipped_to_patterns:
                match = re.search(pattern, line_lower, re.IGNORECASE)
                if match:
                    name = match.group(1).strip()
                    name = re.sub(r'\s*(?:gst|phone|email|address|pincode|pin|state|city).*$', '', name, flags=re.IGNORECASE)
                    name = name.strip()
                    if len(name) > 2 and len(name) < 200:
                        suggestions['shipped_to_name'] = name
                        break
            
            # Check next line if current line has the label
            if any(keyword in line_lower for keyword in ['shipped to', 'ship to', 'delivery to', 'deliver to', 'consignee']):
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if (len(next_line) > 2 and len(next_line) < 200 and
                        not re.match(r'^[\d\s\-/:]+$', next_line) and
                        not re.search(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', next_line) and
                        'cust code' not in next_line.lower()):
                        suggestions['shipped_to_name'] = next_line
                        break
            
            if suggestions['shipped_to_name']:
                break
    
    # Extract DR (Delivery Recipient) - Look for "DR", "Delivery Recipient", etc.
    # Handle various formats: DR:, D.R., D R, dr:, etc.
    dr_patterns = [
        r'(?:^|\s)(?:d\.?\s*r\.?|dr)[:\s]+([A-Za-z][A-Za-z\s]{1,50})(?:\n|$|contact|phone|mobile|dr)',
        r'(?:d\.?\s*r\.?|dr)[:\s]+([A-Za-z][A-Za-z\s]{1,50})(?:\s|$|contact|phone)',
        r'(?:d\.?\s*r\.?|dr)[:\s]+([A-Za-z\s]{2,50})(?:\n|$|contact|phone|mobile|dr)',
        r'delivery\s+recipient[:\s]+([A-Za-z\s]{2,50})(?:\n|$|contact|phone|mobile)',
        r'delivery\s+rec[:\s]+([A-Za-z\s]{2,50})(?:\n|$|contact|phone|mobile)',
        r'(?:d\.?\s*r\.?|dr)\s+contact[:\s]+([A-Za-z\s]{2,50})(?:\n|$|phone|mobile)',
        r'recipient[:\s]+([A-Za-z\s]{2,50})(?:\n|$|contact|phone|mobile)',  # Just "Recipient:"
    ]
    
    # Check full text first - look for "DR" followed by name
    for pattern in dr_patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            dr_name = match.group(1).strip()
            # Remove "DR" if it's still in the name
            dr_name = re.sub(r'^(?:dr|dr\s*:)\s*', '', dr_name, flags=re.IGNORECASE).strip()
            dr_name = re.sub(r'\s*(?:contact|phone|mobile|email|address|dr\s+contact).*$', '', dr_name, flags=re.IGNORECASE)
            dr_name = dr_name.strip()
            if len(dr_name) > 2 and len(dr_name) < 200:
                suggestions['delivery_recipient'] = dr_name
                break
    
    # Also check line by line - look for "DR" on one line and name on next
    if not suggestions['delivery_recipient']:
        for i, line in enumerate(lines[:50]):
            line_lower = line.lower().strip()
            if any(keyword in line_lower for keyword in ['bill type', 'payment', 'create proxy', 'items', 'total', 'subtotal']):
                continue
            
            # Check if line contains just "DR" or "DR:" (handle D.R., D R, etc.)
            if re.match(r'^(?:d\.?\s*r\.?|dr)\s*:?\s*$', line, re.IGNORECASE):
                # Next line should be the name
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if (len(next_line) > 2 and len(next_line) < 200 and
                        not re.match(r'^[\d\s\-/:]+$', next_line) and
                        not re.search(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', next_line) and
                        re.search(r'[A-Za-z]', next_line) and
                        'contact' not in next_line.lower()):
                        suggestions['delivery_recipient'] = next_line
                        break
            
            # Check if line contains "DR:" followed by name on same line (handle D.R., D R, etc.)
            dr_same_line = re.search(r'(?:^|\s)(?:d\.?\s*r\.?|dr)[:\s]+([A-Za-z][A-Za-z\s]{1,50})(?:\s|$|contact|phone)', line, re.IGNORECASE)
            if dr_same_line:
                dr_name = dr_same_line.group(1).strip()
                dr_name = re.sub(r'\s*(?:contact|phone|mobile|email).*$', '', dr_name, flags=re.IGNORECASE).strip()
                if len(dr_name) > 2 and len(dr_name) < 200:
                    suggestions['delivery_recipient'] = dr_name
                    break
            
            # Also check for "DR Contact:" pattern (handle D.R., D R, etc.)
            dr_contact = re.search(r'(?:d\.?\s*r\.?|dr)\s+contact[:\s]+([A-Za-z\s]{2,50})(?:\s|$|phone|mobile)', line, re.IGNORECASE)
            if dr_contact:
                dr_name = dr_contact.group(1).strip()
                dr_name = re.sub(r'\s*(?:phone|mobile|email).*$', '', dr_name, flags=re.IGNORECASE).strip()
                if len(dr_name) > 2 and len(dr_name) < 200:
                    suggestions['delivery_recipient'] = dr_name
                    break
            
            # Also check with patterns - more flexible matching
            for pattern in dr_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    dr_name = match.group(1).strip()
                    dr_name = re.sub(r'^(?:(?:d\.?\s*r\.?|dr)\s*:?)\s*', '', dr_name, flags=re.IGNORECASE).strip()
                    dr_name = re.sub(r'\s*(?:contact|phone|mobile|email|address).*$', '', dr_name, flags=re.IGNORECASE)
                    dr_name = dr_name.strip()
                    # More flexible validation - allow any text that looks like a name
                    if len(dr_name) > 2 and len(dr_name) < 200 and re.search(r'[A-Za-z]{2,}', dr_name):
                        suggestions['delivery_recipient'] = dr_name
                        break
            
            # Check if current line has a name and previous line has "DR" (reverse pattern)
            if not suggestions['delivery_recipient'] and i > 0:
                prev_line = lines[i - 1].strip() if i > 0 else ''
                if re.search(r'^(?:d\.?\s*r\.?|dr)\s*:?\s*$', prev_line, re.IGNORECASE):
                    # Previous line was "DR:", current line might be the name
                    if (len(line.strip()) > 2 and len(line.strip()) < 200 and
                        not re.match(r'^[\d\s\-/:]+$', line.strip()) and
                        re.search(r'[A-Za-z]{2,}', line.strip()) and
                        'contact' not in line.lower()):
                        suggestions['delivery_recipient'] = line.strip()
                        break
            
            if suggestions['delivery_recipient']:
                break
    
    # Extract Post - Look for "post", "post office", "postal", etc.
    post_patterns = [
        r'(?:post|post\s+office|postal)[\s:]+([A-Za-z\s]{2,50})(?:\n|$|,|pincode|pin)',
        r'post[:\s]+([A-Za-z\s]{2,50})(?:\n|$|,|pincode|pin|state|district)',
        r'post\s+office[:\s]+([A-Za-z\s]{2,50})(?:\n|$|,|pincode|pin)',
    ]
    
    for i, line in enumerate(lines[:50]):
        line_lower = line.lower()
        if any(keyword in line_lower for keyword in ['bill type', 'payment', 'create proxy', 'items', 'total', 'subtotal']):
            continue
        
        for pattern in post_patterns:
            match = re.search(pattern, line_lower, re.IGNORECASE)
            if match:
                post = match.group(1).strip()
                # Clean up - remove common suffixes
                post = re.sub(r'\s*(?:pincode|pin|state|district|city|taluk).*$', '', post, flags=re.IGNORECASE)
                post = post.strip()
                if len(post) > 2 and len(post) < 100:
                    suggestions['post'] = post
                    break
        
        # Also check next line if current line has "post"
        if 'post' in line_lower and ('office' in line_lower or 'postal' in line_lower):
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if len(next_line) > 2 and len(next_line) < 100:
                    # Check if it looks like a post name (mostly letters, not numbers/dates)
                    if re.match(r'^[A-Za-z\s]+$', next_line):
                        suggestions['post'] = next_line
                        break
        
        if suggestions['post']:
            break
    
    return suggestions


def extract_bill_info_advanced(ocr_text, ocr_detailed=None):
    """
    Advanced bill information extraction with context awareness and bounding box analysis.
    Uses detailed OCR results with bounding boxes for better field detection.
    """
    import re
    from datetime import datetime
    from difflib import SequenceMatcher
    
    def similarity(a, b):
        """Calculate similarity ratio between two strings"""
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()
    
    def find_text_near_label(label_patterns, ocr_detailed, max_distance=200):
        """Find text near a label using bounding box positions"""
        if not ocr_detailed:
            return None
        
        for item in ocr_detailed:
            text = item['text'].lower()
            for pattern in label_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    # Found label, look for value nearby
                    label_y = item['center_y']
                    label_x = item['center_x']
                    
                    # Find closest text block to the right or below
                    best_match = None
                    min_distance = float('inf')
                    
                    for candidate in ocr_detailed:
                        if candidate == item:
                            continue
                        
                        # Calculate distance
                        dist_x = abs(candidate['left'] - item['left'])
                        dist_y = abs(candidate['top'] - item['top'])
                        distance = (dist_x ** 2 + dist_y ** 2) ** 0.5
                        
                        # Prefer items to the right or slightly below
                        if (candidate['left'] > label_x or 
                            (candidate['top'] > label_y and dist_x < 100)):
                            if distance < min_distance and distance < max_distance:
                                min_distance = distance
                                best_match = candidate['text']
                    
                    if best_match:
                        return best_match.strip()
        return None
    
    def clean_text(text):
        """Clean and normalize extracted text"""
        if not text:
            return None
        # Remove extra whitespace
        text = ' '.join(text.split())
        # Remove common OCR artifacts
        text = re.sub(r'[^\w\s\-/.,:()₹$]', '', text)
        return text.strip() if text.strip() else None
    
    def extract_amount_from_text(text):
        """Extract numeric amount from text, handling various formats"""
        if not text:
            return None
        
        # Remove currency symbols and extract numbers
        amount_patterns = [
            r'(\d{1,3}(?:[.,]\d{2,3})*(?:[.,]\d{2})?)',  # Standard number format
            r'[₹$]?\s*(\d+(?:[.,]\d{2})?)',  # With currency symbol
        ]
        
        for pattern in amount_patterns:
            matches = re.findall(pattern, text.replace(',', ''))
            if matches:
                try:
                    # Get the largest number (likely the amount)
                    amounts = [float(m.replace(',', '')) for m in matches]
                    return str(max(amounts))
                except:
                    continue
        return None
    
    # Initialize suggestions
    suggestions = {
        'bill_number': None,  # Will store invoice number
        'bill_date': None,
        'delivery_date': None,
        'subtotal': None,
        'tax': None,
        'total': None,
        'total_net': None,
        'vendor_name': None,
        'billed_to_name': None,
        'shipped_to_name': None,
        'delivery_recipient': None,  # DR field
        'post': None
    }
    
    if not ocr_text or not ocr_text.strip():
        return suggestions
    
    # Clean and split text into lines
    lines = [line.strip() for line in ocr_text.split('\n') if line.strip()]
    full_text = ' '.join(lines).lower()
    
    # Use bounding box information if available for better extraction
    if ocr_detailed:
        # Sort by position (top to bottom, left to right)
        sorted_items = sorted(ocr_detailed, key=lambda x: (x['top'], x['left']))
        
        # Extract Invoice Number using bounding box context (look for "Invoice" not "Bill")
        invoice_number_patterns = [
            r'(?:invoice|inv)[\s]*(?:number|no|#)[\s#:]',
            r'(?:invoice|inv)[\s#:]',
            r'doc[.\s]*(?:number|no|#)[\s#:]',  # Doc No pattern
        ]
        invoice_num = find_text_near_label(invoice_number_patterns, sorted_items, max_distance=150)
        if invoice_num:
            # Clean and validate invoice number
            invoice_num = clean_text(invoice_num)
            if invoice_num and len(invoice_num) >= 3:
                suggestions['bill_number'] = invoice_num  # Store as bill_number in DB
        
        # Extract DR (Delivery Recipient) using context
        dr_patterns = [
            r'^(?:d\.?\s*r\.?|dr)[:\s]',  # Match "DR:" or "D.R.:" at start
            r'(?:^|\s)(?:d\.?\s*r\.?|dr)[:\s]',  # Match "DR:" with optional space
            r'(?:d\.?\s*r\.?|dr)\s+contact[:\s]',  # Match "DR Contact:" or "D.R. Contact:"
            r'delivery\s+recipient[:\s]',
            r'delivery\s+rec[:\s]',
        ]
        dr_name = find_text_near_label(dr_patterns, sorted_items, max_distance=200)
        if dr_name:
            dr_name = clean_text(dr_name)
            # Remove "DR" if it's still in the name (handle D.R., D R, etc.)
            dr_name = re.sub(r'^(?:d\.?\s*r\.?|dr)\s*:?\s*', '', dr_name, flags=re.IGNORECASE).strip()
            # Remove "DR Contact" if present
            dr_name = re.sub(r'^(?:(?:d\.?\s*r\.?|dr)\s+contact|(?:d\.?\s*r\.?|dr)\s*contact\s*:)\s*', '', dr_name, flags=re.IGNORECASE).strip()
            # Remove contact info if present
            dr_name = re.sub(r'\s*(?:contact|phone|mobile|email|dr\s+contact).*$', '', dr_name, flags=re.IGNORECASE).strip()
            if dr_name and len(dr_name) > 2:
                suggestions['delivery_recipient'] = dr_name
        
        # Extract Billed To using context
        billed_to_patterns = [
            r'(?:billed\s+to|bill\s+to|customer|cust\.)',
        ]
        billed_to = find_text_near_label(billed_to_patterns, sorted_items, max_distance=200)
        if billed_to:
            billed_to = clean_text(billed_to)
            if billed_to and len(billed_to) > 2:
                suggestions['billed_to_name'] = billed_to
        
        # Extract Shipped To using context
        shipped_to_patterns = [
            r'(?:shipped\s+to|ship\s+to|delivery\s+to|deliver\s+to|consignee)',
        ]
        shipped_to = find_text_near_label(shipped_to_patterns, sorted_items, max_distance=200)
        if shipped_to:
            shipped_to = clean_text(shipped_to)
            if shipped_to and len(shipped_to) > 2:
                suggestions['shipped_to_name'] = shipped_to
        
        # Extract Post using context
        post_patterns = [
            r'(?:post|post\s+office|postal)',
        ]
        post = find_text_near_label(post_patterns, sorted_items, max_distance=150)
        if post:
            post = clean_text(post)
            if post and len(post) > 2:
                suggestions['post'] = post
        
        # Extract amounts using context (look for labels in bottom section)
        # Sort by Y position (bottom items are usually totals)
        bottom_items = sorted(sorted_items, key=lambda x: x['top'], reverse=True)[:30]
        
        for item in bottom_items:
            text_lower = item['text'].lower()
            
            # Total Net Amount - prioritize "net amt payable" or "net amount payable"
            if not suggestions['total_net']:
                # Check for "NNet Amt Payable" or "Net Amt Payable" patterns
                if re.search(r'(?:nnet|net)\s+amt\s+payable', text_lower):
                    amount = extract_amount_from_text(item['text'])
                    if amount:
                        suggestions['total_net'] = amount
                        continue  # Found it, move on
                elif any(keyword in text_lower for keyword in ['net amt payable', 'net amount payable', 'nnet amt payable']):
                    amount = extract_amount_from_text(item['text'])
                    if amount:
                        suggestions['total_net'] = amount
                        continue  # Found it, move on
            
            # Total Amount
            if not suggestions['total']:
                if any(keyword in text_lower for keyword in ['total', 'grand total', 'amount payable']):
                    if 'net' not in text_lower and 'amt payable' not in text_lower:  # Avoid net total
                        amount = extract_amount_from_text(item['text'])
                        if amount:
                            suggestions['total'] = amount
            
            # Subtotal
            if not suggestions['subtotal']:
                if any(keyword in text_lower for keyword in ['subtotal', 'sub total', 'total before', 'taxable value']):
                    amount = extract_amount_from_text(item['text'])
                    if amount:
                        suggestions['subtotal'] = amount
            
            # Tax
            if not suggestions['tax']:
                if any(keyword in text_lower for keyword in ['total tax amt', 'tax amt', 'tax amount', 'gst', 'vat']):
                    amount = extract_amount_from_text(item['text'])
                    if amount:
                        suggestions['tax'] = amount
    
    # Fallback to original extraction method for fields not found via bounding boxes
    # This ensures we still extract data even if bounding box method fails
    try:
        fallback_suggestions = extract_bill_info(ocr_text)
        
        # Merge results, preferring bounding box results but using fallback if needed
        for key in suggestions:
            if not suggestions[key] and fallback_suggestions.get(key):
                suggestions[key] = fallback_suggestions[key]
    except Exception as e:
        # If fallback also fails, just use what we have
        import logging
        logging.warning(f"Fallback extraction failed: {str(e)}")
    
    # Enhanced validation and cleaning with intelligent understanding
    if suggestions['bill_number']:
        suggestions['bill_number'] = clean_text(suggestions['bill_number'])
        # Remove common OCR errors in bill numbers
        suggestions['bill_number'] = re.sub(r'[O0]', '0', suggestions['bill_number'])  # Fix O/0 confusion
        suggestions['bill_number'] = re.sub(r'[Il1]', '1', suggestions['bill_number'])  # Fix I/l/1 confusion
    
    # Enhanced date extraction with better validation
    if not suggestions['bill_date']:
        # Try to find date near "date" or "dated" labels
        date_patterns = [
            (r'(?:bill|invoice)[\s]*(?:date|dated)[\s:]*(\d{4}[/-]\d{1,2}[/-]\d{1,2})', ['%Y-%m-%d', '%Y/%m/%d']),
            (r'(?:date|dated)[\s:]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', ['%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%m-%y', '%m/%d/%Y', '%m-%d-%Y']),
        ]
        
        for line in lines[:30]:
            for pattern, formats in date_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    date_str = match.group(1).strip()
                    for fmt in formats:
                        try:
                            parsed_date = datetime.strptime(date_str, fmt)
                            if 2000 <= parsed_date.year <= 2100:
                                suggestions['bill_date'] = parsed_date.strftime('%Y-%m-%d')
                                break
                        except:
                            continue
                    if suggestions['bill_date']:
                        break
            if suggestions['bill_date']:
                break
    
    if suggestions['billed_to_name']:
        suggestions['billed_to_name'] = clean_text(suggestions['billed_to_name'])
        # Remove common suffixes and clean up
        suggestions['billed_to_name'] = re.sub(r'\s*(?:pvt|ltd|limited|inc|corporation|corp|company).*$', '', 
                                               suggestions['billed_to_name'], flags=re.IGNORECASE).strip()
        # Remove address-like patterns
        suggestions['billed_to_name'] = re.sub(r'\d+.*$', '', suggestions['billed_to_name']).strip()
        # Capitalize properly
        if suggestions['billed_to_name']:
            suggestions['billed_to_name'] = ' '.join(word.capitalize() for word in suggestions['billed_to_name'].split())
    
    if suggestions['shipped_to_name']:
        suggestions['shipped_to_name'] = clean_text(suggestions['shipped_to_name'])
        suggestions['shipped_to_name'] = re.sub(r'\s*(?:pvt|ltd|limited|inc|corporation|corp|company).*$', '', 
                                                suggestions['shipped_to_name'], flags=re.IGNORECASE).strip()
        suggestions['shipped_to_name'] = re.sub(r'\d+.*$', '', suggestions['shipped_to_name']).strip()
        if suggestions['shipped_to_name']:
            suggestions['shipped_to_name'] = ' '.join(word.capitalize() for word in suggestions['shipped_to_name'].split())
    
    if suggestions['delivery_recipient']:
        suggestions['delivery_recipient'] = clean_text(suggestions['delivery_recipient'])
        # Remove contact info, phone numbers, etc.
        suggestions['delivery_recipient'] = re.sub(r'\s*(?:contact|phone|mobile|email|address).*$', '', 
                                                   suggestions['delivery_recipient'], flags=re.IGNORECASE).strip()
        # Capitalize properly
        if suggestions['delivery_recipient']:
            suggestions['delivery_recipient'] = ' '.join(word.capitalize() for word in suggestions['delivery_recipient'].split())
    
    if suggestions['post']:
        suggestions['post'] = clean_text(suggestions['post'])
        # Capitalize post name properly
        suggestions['post'] = suggestions['post'].title()
        # Remove numbers and common suffixes
        suggestions['post'] = re.sub(r'\d+', '', suggestions['post']).strip()
        suggestions['post'] = re.sub(r'\s*(?:office|ofc).*$', '', suggestions['post'], flags=re.IGNORECASE).strip()
    
    # Validate and clean amounts
    for amount_field in ['subtotal', 'tax', 'total', 'total_net']:
        if suggestions[amount_field]:
            try:
                # Ensure it's a valid number
                amount_val = float(suggestions[amount_field].replace(',', ''))
                if amount_val < 0:
                    suggestions[amount_field] = None
                else:
                    suggestions[amount_field] = str(amount_val)
            except:
                suggestions[amount_field] = None
    
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

