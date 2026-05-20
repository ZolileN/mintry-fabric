# Dashboard-Driven Budget Allocation & Controls - Quick Start Guide

## Manual Testing & Verification

This guide walks you through testing the Dashboard-Driven Budget Allocation & Controls feature end-to-end.

## Prerequisites

- Python 3.12+
- Mintry-fabric installed (`pip install -e .`)
- Access to a browser
- Terminal access

## Step 1: Prepare Test Environment

```bash
cd /home/zolile/Documents/mintry-fabric
source .venv/bin/activate

# Create a test database
mkdir -p test_data
export TEST_DB="test_data/dashboard_test.db"
```

## Step 2: Start the Dashboard

Create a test script `test_dashboard.py`:

```python
#!/usr/bin/env python3
import sys
from pathlib import Path

# Ensure mintry is importable
sys.path.insert(0, str(Path(__file__).parent / "src"))

from mintry.core.dashboard import start_dashboard
from mintry.core.wallet import MintryWallet

if __name__ == "__main__":
    db_path = "test_data/dashboard_test.db"
    
    # Initialize wallet to ensure DB exists
    wallet = MintryWallet(db_path=db_path)
    print(f"Wallet initialized at {db_path}")
    
    # Start dashboard on localhost:8000
    start_dashboard(db_path=db_path, host="127.0.0.1", port=8000)
```

Run it:
```bash
python3 test_dashboard.py
```

You should see:
```
Wallet initialized at test_data/dashboard_test.db
✨ Mintry Observability Dashboard running at http://127.0.0.1:8000
```

## Step 3: Open Dashboard in Browser

1. Open http://127.0.0.1:8000 in your browser
2. You should see the MINTRY.FABRIC dashboard with:
   - **Section 01**: Executive fiscal indicators (KPIs)
   - **Section 02**: Real-time telemetry (chart & top consumers)
   - **Section 03**: System ledger & administration
   - **Section 04**: Security audit logs

## Step 4: Test Mandate Allocation

### Test Case 1: Create New Mandate

1. Scroll to **Section 03** → Right panel "Allocate / Update Mandate"
2. Fill the form:
   - **Mandate ID**: `test_job_001`
   - **Budget Limit (USD)**: `50.00`
   - **Expiry Date**: (leave empty for no expiry, or select future date)
3. Click **"Apply Mandate"** button
4. You should see:
   - Green success message: "Mandate allocated successfully"
   - Form clears
   - **Left panel "Mandates Ledger"** updates with new row:
     - ID: `test_job_001`
     - Status: `active` (green badge)
     - Budget: `$50.0000`
     - Spent: `$0.0000`
     - Actions: `Revoke` and `Top-up` buttons

### Test Case 2: Update Existing Mandate (Top-up)

1. In the ledger table, find `test_job_001`
2. Click **"Top-up"** button
3. Form pre-fills with:
   - Mandate ID: `test_job_001`
   - Budget: `50.00`
4. Change budget to `100.00`
5. Click **"Apply Mandate"**
6. Success message appears
7. Ledger updates: Budget now shows `$100.0000`
8. Audit feed shows: `TOP_UP test_job_001: Updated budget ceiling to $100.0000 (was $50.0000), status set to 'active'`

### Test Case 3: Revoke Mandate (Kill-Switch)

1. Find `test_job_001` in the ledger
2. Click **"Revoke"** button
3. Confirm in dialog: "Are you sure you want to revoke budget for mandate: test_job_001?"
4. Click OK
5. You should see:
   - Green success message: "Mandate test_job_001 revoked"
   - Status badge changes to: `exhausted` (amber badge)
   - Audit feed shows: `EXHAUST test_job_001: Mandate marked as exhausted`

### Test Case 4: Verify KPI Updates

After allocations, check the **Section 01 - Executive Fiscal Indicators**:

- **Allocated Budget**: Should increase as you allocate
- **Cumulative Spend**: Should remain 0 if you haven't called APIs
- **Remaining Headroom**: Should be Allocated - Spend
- **Active Mandates**: Should show count of "active" status mandates

## Step 5: Test SDK Integration

Create another test script `test_sdk_integration.py`:

```python
#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from mintry.core.wallet import MintryWallet
from mintry.core.engine import PolicyEngine

if __name__ == "__main__":
    db_path = "test_data/dashboard_test.db"
    
    # Initialize wallet and engine
    wallet = MintryWallet(db_path=db_path)
    engine = PolicyEngine(wallet)
    
    # Test 1: Use pre-allocated mandate from dashboard
    print("Test 1: Using pre-allocated mandate 'test_job_001'")
    try:
        with engine.shield("test_job_001") as mandate:
            print(f"  ✓ Shield acquired: {mandate}")
            print(f"    - Mandate ID: {mandate.id}")
            print(f"    - Max USD: ${mandate.max_usd}")
            
            # Check authorization
            is_authorized = engine.authorize(mandate.id, None, deduct=False)
            print(f"    - Pre-flight authorization: {is_authorized}")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    
    # Test 2: Check revoked mandate
    print("\nTest 2: Checking revoked mandate")
    auth_result = engine.authorize("test_job_001", None, deduct=False)
    print(f"  Authorization result for revoked mandate: {auth_result}")
    if not auth_result:
        print("  ✓ Correctly blocked (mandate is exhausted)")
    
    # Test 3: Create temporary mandate with explicit budget
    print("\nTest 3: Using temporary mandate with explicit budget")
    try:
        with engine.shield("temp_task", max_usd=25.0) as mandate:
            print(f"  ✓ Temporary mandate created: {mandate.id}")
            print(f"    - Max USD: ${mandate.max_usd}")
            
            # After exiting, it should be exhausted
        
        # Try to use after exit
        auth = engine.authorize(mandate.id, None, deduct=False)
        print(f"    - Post-exit authorization: {auth} (should be False)")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    
    print("\n✓ SDK integration tests complete")
```

Run it:
```bash
python3 test_sdk_integration.py
```

Expected output:
```
Test 1: Using pre-allocated mandate 'test_job_001'
  ✓ Shield acquired: Mandate(id='test_job_001', task='test_job_001', max_usd=100.0)
    - Mandate ID: test_job_001
    - Max USD: $100.0
    - Pre-flight authorization: True

Test 2: Checking revoked mandate
  Authorization result for revoked mandate: False
  ✓ Correctly blocked (mandate is exhausted)

Test 3: Using temporary mandate with explicit budget
  ✓ Temporary mandate created: mt_xxxxxxxxxxxx
    - Max USD: $25.0
    - Post-exit authorization: False (should be False)

✓ SDK integration tests complete
```

## Step 6: Verify Dashboard Reflects Changes

Go back to the browser at http://127.0.0.1:8000:

1. Refresh the page (browser auto-refreshes every 3 seconds anyway)
2. Check **Section 04 - Live Audit Feed**:
   - You should see entries for:
     - `CREATE` for test_job_001 (initial)
     - `TOP_UP` for test_job_001 (top-up action)
     - `EXHAUST` for test_job_001 (revoke action)

3. Check **Section 03 - Mandates Ledger**:
   - `test_job_001` should show status: `exhausted`
   - Other temporary mandates may also appear

## Step 7: Verify Database State

You can also inspect the SQLite database directly:

```bash
# Install sqlite3 if not already available
python3 << 'EOF'
import sqlite3
from pathlib import Path

db_path = Path("test_data/dashboard_test.db")
conn = sqlite3.connect(str(db_path))

print("\n=== MANDATES TABLE ===")
mandates = conn.execute("SELECT id, max_usd, spent_usd, status FROM mandates").fetchall()
for row in mandates:
    print(f"  {row[0]:30} | Budget: ${row[1]:8.4f} | Spent: ${row[2]:8.4f} | Status: {row[3]}")

print("\n=== AUDIT LOG (Last 10) ===")
logs = conn.execute(
    "SELECT timestamp, mandate_id, action, amount FROM mandate_audit_log ORDER BY id DESC LIMIT 10"
).fetchall()
for row in logs:
    print(f"  {row[0]} | {row[1]:20} | {row[2]:8} | ${row[3]:.4f}")

conn.close()
EOF
```

## Step 8: Test Error Handling

Try these edge cases:

### Missing Budget Value
1. Fill Mandate ID: `edge_test_1`
2. Leave Budget empty
3. Click "Apply Mandate"
4. You should see error: "Missing 'id' or 'budget_usd'"

### Invalid Date Format
1. Mandate ID: `edge_test_2`
2. Budget: `10.00`
3. Expiry Date: Type `invalid-date` (not ISO8601)
4. Click "Apply Mandate"
5. You should see error: "Invalid date format for 'expires_at'. Use ISO8601."

### Revoke Non-Existent Mandate
1. In JS console, run:
```javascript
fetch('/api/mandates/revoke', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: 'nonexistent_mandate' })
}).then(r => r.json()).then(console.log)
```
2. Server handles gracefully (no error for non-existent mandate)

## Step 9: Run Automated Tests

```bash
# Run all tests
python3 -m pytest tests/test_observability.py -v

# Run specific test
python3 -m pytest tests/test_observability.py::test_dashboard_budget_allocation_flow -v

# Run with detailed output
python3 -m pytest tests/test_observability.py -vv --tb=long
```

## Troubleshooting

### "Address already in use" when starting dashboard
```bash
# Kill existing process on port 8000
lsof -ti:8000 | xargs kill -9

# Or use different port
start_dashboard(db_path=db_path, port=8001)
```

### Database locked errors
```bash
# Ensure no other processes have the database open
rm -f test_data/dashboard_test.db*  # Deletes .db, .db-wal, .db-shm files

# Restart dashboard
```

### Import errors
```bash
# Reinstall package in editable mode
pip install -e .

# Verify installation
python3 -c "from mintry.core.dashboard import start_dashboard; print('OK')"
```

## Summary

You have now verified:
- ✅ Dashboard loads and displays correctly
- ✅ Can allocate budget via UI form
- ✅ Can update (top-up) budget
- ✅ Can revoke (kill-switch) budget
- ✅ UI refreshes in real-time
- ✅ SDK engine recognizes pre-allocated budgets
- ✅ SDK engine blocks exhausted mandates
- ✅ Audit trail logs all actions
- ✅ Database state is consistent

The feature is **ready for production use**!
