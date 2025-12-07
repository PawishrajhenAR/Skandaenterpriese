"""
Migration script to add OCR extracted fields to bills table
Run this once to update the database schema with new OCR fields:
- delivery_date
- billed_to_name
- shipped_to_name
- delivery_recipient (DR)
- post

Run: python migrate_db_ocr_fields.py
"""

from app import create_app
from extensions import db
from sqlalchemy import text

app = create_app('development')

with app.app_context():
    try:
        # Check if columns already exist
        result = db.session.execute(text("PRAGMA table_info(bills)"))
        columns = [row[1] for row in result]
        
        print("Checking for missing columns in bills table...")
        print(f"Existing columns: {', '.join(columns)}\n")
        
        # Add delivery_date column
        if 'delivery_date' not in columns:
            print("Adding delivery_date column...")
            db.session.execute(text("ALTER TABLE bills ADD COLUMN delivery_date DATE"))
            db.session.commit()
            print("✓ Added delivery_date column")
        else:
            print("✓ delivery_date column already exists")
        
        # Add billed_to_name column
        if 'billed_to_name' not in columns:
            print("Adding billed_to_name column...")
            db.session.execute(text("ALTER TABLE bills ADD COLUMN billed_to_name VARCHAR(200)"))
            db.session.commit()
            print("✓ Added billed_to_name column")
        else:
            print("✓ billed_to_name column already exists")
        
        # Add shipped_to_name column
        if 'shipped_to_name' not in columns:
            print("Adding shipped_to_name column...")
            db.session.execute(text("ALTER TABLE bills ADD COLUMN shipped_to_name VARCHAR(200)"))
            db.session.commit()
            print("✓ Added shipped_to_name column")
        else:
            print("✓ shipped_to_name column already exists")
        
        # Add delivery_recipient column (DR field)
        if 'delivery_recipient' not in columns:
            print("Adding delivery_recipient column...")
            db.session.execute(text("ALTER TABLE bills ADD COLUMN delivery_recipient VARCHAR(200)"))
            db.session.commit()
            print("✓ Added delivery_recipient column")
        else:
            print("✓ delivery_recipient column already exists")
        
        # Add post column
        if 'post' not in columns:
            print("Adding post column...")
            db.session.execute(text("ALTER TABLE bills ADD COLUMN post VARCHAR(100)"))
            db.session.commit()
            print("✓ Added post column")
        else:
            print("✓ post column already exists")
        
        print("\n" + "="*50)
        print("Migration completed successfully!")
        print("="*50)
        print("\nAll OCR extracted fields have been added to the bills table.")
        print("You can now use OCR functionality to extract and store:")
        print("  - Delivery Date")
        print("  - Billed To Name")
        print("  - Shipped To Name")
        print("  - Delivery Recipient (DR)")
        print("  - Post")
        
    except Exception as e:
        print(f"\n❌ Error during migration: {e}")
        db.session.rollback()
        raise

