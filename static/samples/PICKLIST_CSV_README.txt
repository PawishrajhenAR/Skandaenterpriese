PICKLIST CSV UPLOAD (invoice table export)
==========================================

Required columns (header row; names matched case-insensitively):

  - Invoice No
  - Inv Date          (maps to delivery_date; use DD/MM/YYYY or YYYY-MM-DD)
  - Customer          (customer code)
  - Customer Name
  - Beat
  - P-Mode            (payment mode: Credit, Cash, etc.)
  - InvVal            (invoice amount; commas allowed)
  - RecAmt            (received amount; commas allowed)

Rows are stored in picklist_import_rows (status default: pending).
Re-uploading the same Invoice No updates the row (per tenant).

Ignored rows: empty invoice, Salesman summary, Grand Total, separator lines (---).

OCR upload still uses the older delivery-person + bill matching flow.
