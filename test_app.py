import os
import sys

sys.path.insert(0, r'C:\Users\nikhil.shelke\.gemini\antigravity\scratch\drp_portal')
from app import app
from drp_service import drp_service, DATA_DIR
from email_service import email_service

client = app.test_client()

# 1. Test dashboard route & Table A / Table B presence
r1 = client.get('/')
print('1. Dashboard Status:', r1.status_code)
assert r1.status_code == 200, f'Dashboard failed: {r1.status_code}'
assert b'Table A: DRP profiles with 8 Google-priority products' in r1.data, 'Table A title missing from Dashboard!'
assert b'Table B : DRP profiles with other products' in r1.data, 'Table B title missing from Dashboard!'
assert b'Top Product Focus Areas' not in r1.data, 'Old Top Product Focus Areas still present!'
print('   -> Table A and Table B verified in HTML output!')

# 2. Verify Table A & Table B data structure
tables = drp_service.get_product_tables()
assert len(tables['table_a']['rows']) == 8, f"Expected 8 priority products, got {len(tables['table_a']['rows'])}"
assert len(tables['table_b']['rows']) == 6, f"Expected 6 other products, got {len(tables['table_b']['rows'])}"
assert tables['table_a']['grand_total']['total'] > 0
assert tables['table_b']['grand_total']['total'] > 0
print('2. Product tables verified: Table A has 8 rows, Table B has 6 rows, Grand Totals computed.')

# 3. Test employees route
r2 = client.get('/employees')
print('3. Employees Status:', r2.status_code)
assert r2.status_code == 200, f'Employees failed: {r2.status_code}'

# 4. Test campaigns route
r3 = client.get('/campaigns?tier=Tier%204')
print('4. Campaigns Status (Tier 4):', r3.status_code)
assert r3.status_code == 200, f'Campaigns failed: {r3.status_code}'

# 5. Test sync page
r5 = client.get('/sync')
print('5. Sync Page Status:', r5.status_code)
assert r5.status_code == 200, f'Sync failed: {r5.status_code}'

# 6. Test API employee detail
emp = drp_service.filter_employees()[0]
emp_id = emp['employee_id']
r6 = client.get(f'/api/employee/{emp_id}')
print(f'6. API Employee Detail ({emp_id}) Status:', r6.status_code)
assert r6.status_code == 200, f'API employee failed: {r6.status_code}'

# 7. Test Campaign Job start
r7 = client.post('/api/start_campaign_job', json={'tier': 'Tier 1'})
print('7. API Start Campaign Job Status:', r7.status_code)
assert r7.status_code == 200, f'Start campaign failed: {r7.status_code}'

# 8. Test Draft Protection Flow
print('8. Testing Draft Protection...')
test_xlsx = os.path.join(DATA_DIR, 'current_data.xlsx')
with open(test_xlsx, 'rb') as f:
    backup_bytes = f.read()

ok, meta = drp_service.save_as_draft(test_xlsx, 'test_sample.xlsx')
assert ok, 'save_as_draft failed'
assert drp_service.get_draft_metadata() is not None, 'draft metadata missing'

# Attempt upload while draft exists without force
import io
upload_res = client.post('/api/upload_excel', data={'file': (io.BytesIO(backup_bytes), 'another_file.xlsx')}, follow_redirects=True)
assert b'already attached and active' in upload_res.data or b'currently attached' in upload_res.data, 'Upload was not blocked by draft lock!'
print('   -> Draft lock successfully prevented unauthorized overwrite!')

# Test Delete Draft
del_res = client.post('/api/delete_data', follow_redirects=True)
assert del_res.status_code == 200
print('   -> Delete Draft executed successfully.')

# Restore the real current dataset so portal is fully loaded and ready
with open(test_xlsx, 'wb') as f:
    f.write(backup_bytes)
drp_service.save_as_draft(test_xlsx, 'DRP Tier Project.xlsx')
print('   -> Production draft re-attached and locked!')

print('\nSUCCESS: All 8 Comprehensive Integration & Verification Tests Passed 100%!')
