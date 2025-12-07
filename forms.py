from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, SelectField, DateField, DecimalField, TextAreaField, IntegerField
from wtforms.validators import DataRequired, Email, Optional, NumberRange
from datetime import date


def coerce_int_or_none(value):
    """Coerce value to int or None if empty string"""
    if value == '' or value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])


class VendorForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    type = SelectField('Type', choices=[
        ('SUPPLIER', 'Supplier'),
        ('CUSTOMER', 'Customer'),
        ('BOTH', 'Both')
    ], validators=[DataRequired()])
    contact_phone = StringField('Contact Phone', validators=[Optional()])
    email = StringField('Email', validators=[Optional(), Email()])
    address = TextAreaField('Address', validators=[Optional()])
    gst_number = StringField('GST Number', validators=[Optional()])
    credit_limit = DecimalField('Credit Limit', places=2, validators=[Optional(), NumberRange(min=0)])


class BillForm(FlaskForm):
    vendor_id = SelectField('Vendor', coerce=int, validators=[DataRequired()])
    bill_number = StringField('Bill Number', validators=[DataRequired()])
    bill_date = DateField('Bill Date', default=date.today, validators=[DataRequired()])
    bill_type = SelectField('Bill Type', choices=[
        ('NORMAL', 'Normal'),
        ('HANDBILL', 'Handbill')
    ], validators=[DataRequired()])
    delivery_date = DateField('Delivery Date', validators=[Optional()])
    billed_to_name = StringField('Billed To Name', validators=[Optional()])
    shipped_to_name = StringField('Shipped To Name', validators=[Optional()])
    delivery_recipient = StringField('Delivery Recipient (DR)', validators=[Optional()])
    post = StringField('Post', validators=[Optional()])
    is_proxy = SelectField('Create Proxy Bills?', choices=[
        ('NO', 'No'),
        ('YES', 'Yes')
    ], default='NO', validators=[Optional()])
    number_of_splits = IntegerField('Number of Proxy Splits', validators=[Optional()], default=0)
    payment_type = SelectField('Payment Status', choices=[
        ('NONE', 'Unpaid'),
        ('FULL', 'Fully Paid'),
        ('PARTIAL', 'Partially Paid')
    ], default='NONE', validators=[Optional()])
    partial_amount = DecimalField('Partial Payment Amount', places=2, validators=[Optional()])
    payment_method = SelectField('Payment Method', choices=[
        ('CASH', 'Cash'),
        ('UPI', 'UPI'),
        ('BANK', 'Bank Transfer'),
        ('CHEQUE', 'Cheque'),
        ('CARD', 'Card')
    ], validators=[Optional()])
    payment_reference = StringField('Payment Reference', validators=[Optional()])


class ProxyBillForm(FlaskForm):
    parent_bill_id = SelectField('Parent Bill', coerce=int, validators=[DataRequired()])
    vendor_id = SelectField('Vendor (End Customer)', coerce=int, validators=[DataRequired()])
    proxy_number = StringField('Proxy Bill Number', validators=[DataRequired()])


class CreditEntryForm(FlaskForm):
    bill_id = SelectField('Bill', coerce=coerce_int_or_none, validators=[Optional()])
    proxy_bill_id = SelectField('Proxy Bill', coerce=coerce_int_or_none, validators=[Optional()])
    vendor_id = SelectField('Vendor', coerce=int, validators=[DataRequired()])
    amount = DecimalField('Amount', places=2, validators=[DataRequired(), NumberRange(min=0.01)])
    direction = SelectField('Direction', choices=[
        ('INCOMING', 'Incoming'),
        ('OUTGOING', 'Outgoing')
    ], validators=[DataRequired()])
    payment_method = SelectField('Payment Method', choices=[
        ('CASH', 'Cash'),
        ('UPI', 'UPI'),
        ('BANK', 'Bank Transfer'),
        ('CHEQUE', 'Cheque'),
        ('CARD', 'Card')
    ], validators=[DataRequired()])
    payment_date = DateField('Payment Date', default=date.today, validators=[DataRequired()])
    reference_number = StringField('Reference Number', validators=[Optional()])
    notes = TextAreaField('Notes', validators=[Optional()])


class DeliveryOrderForm(FlaskForm):
    bill_id = SelectField('Bill', coerce=coerce_int_or_none, validators=[Optional()])
    proxy_bill_id = SelectField('Proxy Bill', coerce=coerce_int_or_none, validators=[Optional()])
    delivery_user_id = SelectField('Delivery User', coerce=int, validators=[DataRequired()])
    delivery_address = TextAreaField('Delivery Address', validators=[DataRequired()])
    delivery_date = DateField('Delivery Date', default=date.today, validators=[DataRequired()])
    remarks = TextAreaField('Remarks', validators=[Optional()])


class OCRUploadForm(FlaskForm):
    bill_id = SelectField('Bill', coerce=int, validators=[DataRequired()])
    image = FileField('Bill Image', validators=[
        DataRequired(),
        FileAllowed(['jpg', 'jpeg', 'png', 'pdf'], 'Images and PDFs only!')
    ])


class ReportDateRangeForm(FlaskForm):
    start_date = DateField('Start Date', validators=[DataRequired()])
    end_date = DateField('End Date', validators=[DataRequired()])

