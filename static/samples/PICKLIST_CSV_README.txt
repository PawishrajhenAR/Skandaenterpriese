PICKLIST UPLOAD - SAMPLE CSV
============================

Required columns (exact or similar names):
  - Invoice No   (or Bill Number, Proxy Number) - must match an existing bill/proxy number in the app
  - Delivery Person (or Delivery_User) - must match a user with role DELIVERY or SALESMAN (e.g. "delivery", "salesman")
  - Delivery Date (e.g. 2025-03-15 or 15/03/2025)
  - Delivery Address

Optional:
  - Salesman (username of salesman for this delivery)

To test with the sample CSV (picklist_upload_sample.csv):
  1. Ensure you have run seed.py (creates users: admin, delivery, salesman, organiser).
  2. Create at least one bill in the app (Bills -> New Bill) with Bill Number "BILL-001" (and optionally BILL-002, BILL-003).
  3. Go to Picklists -> Upload Picklist, choose the sample CSV, and upload.

Rows are skipped if:
  - Invoice No does not match any Bill or Proxy Bill.
  - Delivery Person is not an active user with role DELIVERY or SALESMAN.
