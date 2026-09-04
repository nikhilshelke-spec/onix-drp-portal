import sys, json
sys.path.insert(0, r"C:\Users\nikhil.shelke\.gemini\antigravity\scratch\drp_portal")
from app import app
from drp_service import drp_service

client = app.test_client()
emps = drp_service.filter_employees()
print(f"Total employees in database: {len(emps)}")

for emp in emps[:100]:
    emp_id = emp["employee_id"]
    resp = client.get(f"/api/employee/{emp_id}")
    assert resp.status_code == 200, f"Failed on {emp_id}"
    raw = resp.data.decode("utf-8")
    assert "NaN" not in raw, f"Found NaN in {emp_id}"
    parsed = json.loads(raw)
    assert "employee" in parsed and "email" in parsed

print("SUCCESS: 100 Employees Tested - All JSON responses are 100% clean, valid, and free of NaN!")
