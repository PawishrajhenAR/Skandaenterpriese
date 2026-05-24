-- Add optional proxy name on bills for cases where billing and receiving parties differ.
ALTER TABLE bills ADD COLUMN IF NOT EXISTS proxy_name VARCHAR(200);
