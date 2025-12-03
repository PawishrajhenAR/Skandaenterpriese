from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import OCRJob, Bill, Tenant
from forms import OCRUploadForm
from extensions import db
from audit import log_action
from ocr_utils import run_ocr
from auth_routes import permission_required
import os
from pathlib import Path

ocr_bp = Blueprint('ocr', __name__)


def get_default_tenant():
    return Tenant.query.filter_by(code='skanda').first()


def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@ocr_bp.route('/upload', methods=['GET', 'POST'])
@login_required
@permission_required('create_bill')
def upload():
    tenant = get_default_tenant()
    if not tenant:
        flash('Tenant not found.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    form = OCRUploadForm()
    form.bill_id.choices = [(b.id, f"{b.bill_number} - {b.vendor.name}") 
                            for b in Bill.query.filter_by(tenant_id=tenant.id).all()]
    
    # Pre-fill from query params
    bill_id = request.args.get('bill_id', type=int)
    if bill_id:
        form.bill_id.data = bill_id
    
    if form.validate_on_submit():
        bill = Bill.query.get(form.bill_id.data)
        if not bill:
            flash('Bill not found.', 'danger')
            return redirect(url_for('ocr.upload'))
        
        file = form.image.data
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Create unique filename
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{bill.id}_{timestamp}_{filename}"
            
            upload_folder = Path(current_app.config['UPLOAD_FOLDER'])
            upload_folder.mkdir(parents=True, exist_ok=True)
            filepath = upload_folder / filename
            file.save(str(filepath))
            
            # Run OCR with error handling
            relative_path = f"uploads/bills/{filename}"
            try:
                ocr_text = run_ocr(str(filepath))
                
                # Check if OCR returned an error message
                if ocr_text.startswith("OCR error:") or ocr_text.startswith("Error:"):
                    flash(f'OCR processing failed: {ocr_text}', 'danger')
                    # Still save the file but without OCR text
                    ocr_text = None
            except Exception as e:
                flash(f'OCR processing error: {str(e)}', 'danger')
                ocr_text = None
            
            # Create OCR job (even if OCR failed, we still save the image)
            ocr_job = OCRJob(
                tenant_id=tenant.id,
                bill_id=bill.id,
                image_path=relative_path,
                raw_text=ocr_text or "OCR processing failed or not available."
            )
            db.session.add(ocr_job)
            
            # Update bill
            bill.image_path = relative_path
            if ocr_text:
                bill.ocr_text = ocr_text
            
            db.session.commit()
            log_action(current_user, 'UPLOAD_OCR', 'BILL', bill.id)
            
            if ocr_text and not ocr_text.startswith("OCR error:") and not ocr_text.startswith("Error:"):
                flash('OCR image uploaded and processed successfully.', 'success')
            else:
                flash('Image uploaded but OCR processing failed. You can view the image manually.', 'warning')
            
            return redirect(url_for('ocr.view', id=ocr_job.id))
        else:
            flash('Invalid file type.', 'danger')
    
    return render_template('ocr/upload.html', form=form)


@ocr_bp.route('/<int:id>')
@login_required
@permission_required('view_bills')
def view(id):
    ocr_job = OCRJob.query.get_or_404(id)
    return render_template('ocr/view.html', ocr_job=ocr_job)

