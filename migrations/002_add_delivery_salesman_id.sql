-- Add optional salesman to delivery_orders for picklist upload
ALTER TABLE delivery_orders ADD COLUMN IF NOT EXISTS salesman_id INTEGER REFERENCES users(id) ON DELETE SET NULL;
