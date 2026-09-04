import os
import sys

sys.path.insert(0, r'C:\Users\nikhil.shelke\.gemini\antigravity\scratch\drp_portal')
from app import app
from drp_service import drp_service
from email_service import email_service

client = app.test_client()

# 1. Test dashboard route
r1 = client.get('/')
print('1. Dashboard Status:', r1.status_code)
assert r1.status_code == 200, f'Dashboard failed: {r1.status_code}'

# 2. Test employees route
r2 = client.get('/employees')
print('2. Employees Status:', r2.status_code)
assert r2.status_code == 200, f'Employees failed: {r2.status_code}'

# 3. Test campaigns route
r3 = client.get('/campaigns?tier=Tier%204')
print('3. Campaigns Status (Tier 4):', r3.status_code)
assert r3.status_code == 200, f'Campaigns failed: {r3.status_code}'

# 4. Test campaigns route for Tier 0
r4 = client.get('/campaigns?tier=Tier%200')
print('4. Campaigns Status (Tier 0):', r4.status_code)
assert r4.status_code == 200, f'Campaigns failed: {r4.status_code}'

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

# 7. Test Campaign dispatch simulation
r7 = client.post('/api/dispatch_campaign', json={'tier': 'Tier 4', 'dry_run': True})
print('7. API Dispatch Campaign Status:', r7.status_code)
assert r7.status_code == 200, f'API dispatch failed: {r7.status_code}'

print('\nSUCCESS: All 7 Unit & Integration Tests Passed 100%!')
