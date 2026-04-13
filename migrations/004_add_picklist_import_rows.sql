-- Picklist CSV import rows (invoice-style exports from distributor reports)
CREATE TABLE IF NOT EXISTS public.picklist_import_rows (
  id SERIAL PRIMARY KEY,
  tenant_id INTEGER NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  invoice_no VARCHAR(200) NOT NULL,
  delivery_date DATE,
  customer_code VARCHAR(100),
  customer_name VARCHAR(500),
  beat VARCHAR(300),
  amount NUMERIC(12, 2),
  received_amount NUMERIC(12, 2),
  payment_mode VARCHAR(50),
  status VARCHAR(30) NOT NULL DEFAULT 'pending',
  created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_picklist_import_tenant_invoice UNIQUE (tenant_id, invoice_no)
);

CREATE INDEX IF NOT EXISTS idx_picklist_import_tenant_date ON public.picklist_import_rows (tenant_id, delivery_date DESC);
