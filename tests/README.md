# Testing Guide

## Running Tests

### Install Dependencies
```bash
.venv\Scripts\activate  # On Windows
pip install -r requirements.txt
```

### Run All Tests
```bash
pytest tests/ -v
```

### Run Specific Test File
```bash
pytest tests/test_main.py -v
```

### Run Specific Test Class
```bash
pytest tests/test_main.py::TestAuthentication -v
```

### Run Specific Test Method
```bash
pytest tests/test_main.py::TestAuthentication::test_login_success -v
```

### Run with Coverage
```bash
pytest tests/ --cov=. --cov-report=html
```

### Run Tests Matching Pattern
```bash
pytest tests/ -k "login" -v
```

## Test Structure

- `tests/conftest.py` - Test fixtures and configuration
- `tests/test_main.py` - Main test suite covering:
  - Authentication (login, logout, permissions)
  - Vendor management (CRUD operations)
  - Bill management (create, authorize, delete)
  - OCR functionality
  - Permission system
  - Reports
  - Error handling

## Test Coverage

The test suite covers:
1. ✅ Authentication flows
2. ✅ Vendor CRUD operations
3. ✅ Bill creation and authorization
4. ✅ OCR text extraction logic
5. ✅ Permission checks
6. ✅ Error handling (404, unauthorized access)
7. ✅ Database integrity (vendor deletion with bills)

## Adding New Tests

1. Create test methods in appropriate test class
2. Use fixtures from `conftest.py` (app, client, admin_user, etc.)
3. Follow naming convention: `test_<feature>_<scenario>`
4. Use descriptive docstrings

## Continuous Integration

Tests can be integrated into CI/CD pipelines:
```bash
pytest tests/ --cov=. --cov-report=xml
```

