import os
import json
import time
import uuid
import secrets
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file, Response, session, flash
import pandas as pd
from config import GOOGLE_SHEET_URL, DRP_PORTAL_URL, CREDLY_URL, DRP_MAPPING_SHEET_URL, DRP_ATTRIBUTION_URL, TIER_DEFINITIONS
from drp_service import drp_service
from email_service import email_service
from access_manager import (
    add_leader, remove_leader, get_all_leaders, validate_leader_token,
    add_editor, remove_editor, get_all_editors, validate_editor_token,
    validate_employee_token, get_employee_token, is_allowed_employee_domain,
    OWNER_EMAIL
)

app = Flask(__name__)
app.secret_key = "onix-drp-command-center-2026-secure"
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.jinja_env.auto_reload = True
app.jinja_env.globals.update(zip=zip, min=min, max=max)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
OTP_STORE_FILE = os.path.join(DATA_DIR, "otp_store.json")

def _load_otp_store():
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(OTP_STORE_FILE):
        try:
            with open(OTP_STORE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_otp_store(store):
    try:
        with open(OTP_STORE_FILE, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2)
    except Exception:
        pass

@app.before_request
def setup_role():
    if 'role' not in session:
        session['role'] = 'owner'

@app.context_processor
def inject_global_vars():
    role = session.get('role', 'owner')
    verified_email = session.get('verified_email', '')
    return {
        'google_sheet_url': GOOGLE_SHEET_URL,
        'drp_portal_url': DRP_PORTAL_URL,
        'credly_url': CREDLY_URL,
        'drp_mapping_sheet_url': DRP_MAPPING_SHEET_URL,
        'drp_attribution_url': DRP_ATTRIBUTION_URL,
        'tier_definitions': TIER_DEFINITIONS,
        'current_role': role,
        'is_editor': role in ['owner', 'editor'],
        'owner_email': OWNER_EMAIL,
        'verified_email': verified_email,
        'user_email': session.get('user_email', OWNER_EMAIL if role == 'owner' else verified_email),
        'last_sync_source': drp_service.last_sync_source
    }

def _get_shareable_base_url():
    public_url = os.environ.get('PUBLIC_PORTAL_URL', '') or os.environ.get('RENDER_EXTERNAL_URL', '')
    if public_url:
        return public_url.rstrip('/')
    
    if hasattr(request, 'headers') and request:
        proto = request.headers.get('X-Forwarded-Proto', request.scheme)
        host = request.headers.get('X-Forwarded-Host', request.host)
        if host and 'localhost' not in host and '127.0.0.1' not in host:
            return f"{proto}://{host}".rstrip('/')
            
    import socket
    local_ip = '127.0.0.1'
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass
    port = int(os.environ.get('PORT', 4000))
    if local_ip and local_ip != '127.0.0.1' and not local_ip.startswith('10.'):
        return f"http://{local_ip}:{port}"
    return request.host_url.rstrip('/')

@app.route('/set_role')
def set_role():
    role = request.args.get('role', 'owner')
    if role in ['owner', 'editor', 'leader', 'user']:
        session['role'] = role
    next_url = request.args.get('next', url_for('dashboard'))
    if session['role'] == 'user' and (next_url == '/' or 'campaigns' in next_url or 'sync' in next_url):
        next_url = url_for('employees')
    return redirect(next_url)

@app.route('/set_owner')
def set_owner():
    session['role'] = 'owner'
    session['user_email'] = OWNER_EMAIL
    next_url = request.args.get('next', url_for('dashboard'))
    return redirect(next_url)

@app.route('/')
def dashboard():
    if session.get('role') == 'user':
        return redirect(url_for('employees'))
    kpis = drp_service.get_kpis()
    charts = drp_service.get_chart_data()
    return render_template('dashboard.html', kpis=kpis, charts=charts, page='dashboard')

# ─── EMPLOYEE HUB & VERIFICATION ─────────────────────────────────────────────

@app.route('/employees')
def employees():
    role = session.get('role', 'owner')
    verified_email = session.get('verified_email', '')

    # Determine scope based on identity
    scope = drp_service.get_user_scope(verified_email, role)
    is_authenticated = (role in ['owner', 'editor', 'leader']) or bool(verified_email)

    filters = drp_service.get_filter_options(base_df=scope['allowed_df'])
    tier_filter = request.args.get('tier', 'All')
    manager_filter = request.args.get('manager', 'All')
    cluster_filter = request.args.get('cluster', 'All')
    product_filter = request.args.get('product', 'All')
    search_query = request.args.get('search', '')

    employee_list = drp_service.filter_employees(
        tier=tier_filter,
        manager=manager_filter,
        cluster=cluster_filter,
        product=product_filter,
        search=search_query,
        base_df=scope['allowed_df']
    )

    return render_template(
        'employees.html',
        employees=employee_list,
        filters=filters,
        selected_tier=tier_filter,
        selected_manager=manager_filter,
        selected_cluster=cluster_filter,
        selected_product=product_filter,
        search_query=search_query,
        is_authenticated=is_authenticated,
        scope=scope,
        page='employees'
    )

@app.route('/api/auth/send_otp', methods=['POST'])
def api_send_otp():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()

    if not email or '@' not in email:
        return jsonify({'success': False, 'error': 'Please enter a valid email address.'}), 400

    # Generate 6-digit OTP and secure magic token
    otp = str(secrets.randbelow(900000) + 100000)
    token = secrets.token_urlsafe(16)
    expires = time.time() + (15 * 60) # 15 minutes

    store = _load_otp_store()
    store[email] = {
        'otp': otp,
        'token': token,
        'expires': expires
    }
    # Index by token as well for magic link lookup
    store[f"token_{token}"] = {
        'email': email,
        'expires': expires
    }
    base = _get_shareable_base_url()
    magic_link = f"{base}/magic_login/{token}"

    ok, msg = email_service.send_otp_email(email, otp, magic_link)
    if ok:
        return jsonify({'success': True, 'message': f'Verification code dispatched to {email}. Please check your email inbox.'})
    else:
        # Never leak OTP on screen. Return explicit error if delivery fails.
        return jsonify({
            'success': False,
            'error': f'Email dispatch failed: {msg}. Please ensure email service or Google Webhook is active.'
        }), 500

@app.route('/api/auth/verify_otp', methods=['POST'])
def api_verify_otp():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    otp = data.get('otp', '').strip()

    store = _load_otp_store()
    rec = store.get(email)
    if not rec:
        return jsonify({'success': False, 'error': 'No pending verification found. Please request a new code.'}), 400

    if time.time() > rec.get('expires', 0):
        return jsonify({'success': False, 'error': 'Code has expired. Please request a new one.'}), 400

    if rec.get('otp') != otp:
        return jsonify({'success': False, 'error': 'Invalid 6-digit code. Please check and re-enter.'}), 400

    session['verified_email'] = email
    session['role'] = 'user'
    return jsonify({'success': True, 'redirect': url_for('employees')})

@app.route('/magic_login/<token>')
def magic_login(token):
    store = _load_otp_store()
    rec = store.get(f"token_{token}")
    if not rec or time.time() > rec.get('expires', 0):
        return render_template('access_denied.html', reason="This login link is invalid or has expired. Please request a new code on the Employee Hub."), 403

    session['verified_email'] = rec['email']
    session['role'] = 'user'
    return redirect(url_for('employees'))

@app.route('/logout_employee')
def logout_employee():
    session.pop('verified_email', None)
    return redirect(url_for('employees'))

# ─── CAMPAIGNS & TEMPLATE EDITING ────────────────────────────────────────────

@app.route('/campaigns')
def campaigns():
    if session.get('role') not in ['owner', 'editor']:
        return redirect(url_for('dashboard' if session.get('role') == 'leader' else 'employees'))
        
    target_tier = request.args.get('tier', 'Tier 4')
    filtered_emps = drp_service.filter_employees(tier=target_tier)
    sample_emp = filtered_emps[0] if len(filtered_emps) > 0 else None
    
    current_template = email_service.get_template(target_tier)
    sample_email = None
    all_gmail_urls = []
    if sample_emp:
        sample_email = email_service.generate_email_content(sample_emp, current_template)
    
    for emp in filtered_emps:
        email_data = email_service.generate_email_content(emp, current_template)
        if email_data.get('gmail_url'):
            all_gmail_urls.append(email_data['gmail_url'])

    campaign_history = email_service.get_campaign_history()

    return render_template(
        'campaigns.html',
        target_tier=target_tier,
        employee_count=len(filtered_emps),
        sample_emp=sample_emp,
        sample_email=sample_email,
        current_template=current_template,
        all_gmail_urls=all_gmail_urls,
        campaign_history=campaign_history,
        page='campaigns'
    )

@app.route('/api/save_email_template', methods=['POST'])
def api_save_email_template():
    if session.get('role') not in ['owner', 'editor']:
        return jsonify({'error': 'Permission denied'}), 403
    data = request.get_json() or {}
    tier = data.get('tier', 'Tier 4')
    subject = data.get('subject', '')
    body = data.get('body', '')

    email_service.save_template(tier, subject, body)
    return jsonify({'success': True, 'message': f'Template for {tier} saved successfully!'})

@app.route('/api/start_campaign_job', methods=['POST'])
def api_start_campaign_job():
    if session.get('role') not in ['owner', 'editor']:
        return jsonify({'error': 'Permission denied'}), 403
    data = request.get_json() or {}
    tier = data.get('tier', 'Tier 4')
    recipients = drp_service.filter_employees(tier=tier)

    if not recipients:
        return jsonify({'success': False, 'error': f'No recipients in {tier}.'}), 400

    job_id = email_service.start_campaign_job(tier, recipients)
    return jsonify({'success': True, 'job_id': job_id, 'total': len(recipients)})

@app.route('/api/campaign_job_status/<job_id>')
def api_campaign_job_status(job_id):
    job = email_service.get_job_status(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(job)

@app.route('/api/resend_failed_emails', methods=['POST'])
def api_resend_failed_emails():
    if session.get('role') not in ['owner', 'editor']:
        return jsonify({'error': 'Permission denied'}), 403
    data = request.get_json() or {}
    job_id = data.get('job_id')
    job = email_service.get_job_status(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404

    failed_list = job.get('failed_list', [])
    if not failed_list:
        return jsonify({'success': False, 'error': 'No failed recipients to retry.'}), 400

    failed_emails = [f['email'] for f in failed_list]
    retry_employees = [e for e in drp_service.filter_employees() if e.get('email') in failed_emails]

    new_job_id = email_service.start_campaign_job(f"{job.get('tier')} (Retry)", retry_employees)
    return jsonify({'success': True, 'job_id': new_job_id, 'total': len(retry_employees)})

# ─── DATA SYNC & SETTINGS ───────────────────────────────────────────────────

@app.route('/sync')
def sync_page():
    if session.get('role') not in ['owner', 'editor']:
        return redirect(url_for('employees'))
    kpis = drp_service.get_kpis()
    return render_template('settings_sync.html', kpis=kpis, page='sync')

@app.route('/api/employee/<emp_id>')
def api_employee_detail(emp_id):
    emp = drp_service.get_employee(emp_id)
    if not emp:
        return jsonify({'error': 'Employee not found'}), 404
    email_preview = email_service.generate_email_content(emp)
    return jsonify({'employee': emp, 'email': email_preview})

@app.route('/api/refresh_data', methods=['POST'])
def api_refresh_data():
    success, msg = drp_service.sync_from_google_sheet()
    if not success:
        load_ok, _ = drp_service.load_data()
        count = len(drp_service.df) if drp_service.df is not None else 0
        sync_msg = f"{msg} (Currently using local dataset with {count} records)"
        return redirect(url_for('sync_page', sync_msg=sync_msg, sync_ok=0))
    return redirect(url_for('sync_page', sync_msg=msg, sync_ok=1))

@app.route('/api/upload_excel', methods=['POST'])
def api_upload_excel():
    if session.get('role') not in ['owner', 'editor']:
        return redirect(url_for('employees'))
        
    if 'file' not in request.files:
        return redirect(url_for('sync_page'))
    file = request.files['file']
    if file.filename == '':
        return redirect(url_for('sync_page'))
    
    save_path = os.path.join(drp_service.df_path if hasattr(drp_service, 'df_path') else 'data', 'current_data.xlsx')
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    file.save(save_path)
    
    success, msg = drp_service.load_data(save_path)
    drp_service.last_sync_source = "Uploaded Excel"
    return redirect(url_for('dashboard'))

@app.route('/export_csv')
def export_csv():
    tier = request.args.get('tier', 'All')
    manager = request.args.get('manager', 'All')
    emps = drp_service.filter_employees(tier=tier, manager=manager)
    df_exp = pd.DataFrame(emps)
    csv_data = df_exp.to_csv(index=False)
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=Onix_DRP_Report.csv"}
    )

# ─── ACCESS / JOIN ROUTES ────────────────────────────────────────────────────

@app.route('/join/editor/<token>')
def join_editor(token):
    editor_email = validate_editor_token(token)
    if editor_email:
        session['role'] = 'editor'
        session['user_email'] = editor_email
        session['access_type'] = 'editor_link'
        return redirect(url_for('campaigns'))
    return render_template('access_denied.html', reason="This editor access link is invalid or has been revoked."), 403

@app.route('/join/leader/<token>')
def join_leader(token):
    leader_email = validate_leader_token(token)
    if leader_email:
        session['role'] = 'leader'
        session['user_email'] = leader_email
        session['access_type'] = 'leader_link'
        return redirect(url_for('dashboard'))
    return render_template('access_denied.html', reason="This leader access link is invalid, expired, or not authorized."), 403

@app.route('/join/employee/<token>')
def join_employee(token):
    if validate_employee_token(token):
        session['role'] = 'user'
        session['access_type'] = 'employee_link'
        return redirect(url_for('employees'))
    return render_template('access_denied.html', reason="Invalid or expired access link."), 403

@app.route('/api/access/add_editor', methods=['POST'])
def api_add_editor():
    if session.get('role') not in ['owner', 'editor']:
        return jsonify({'error': 'Permission denied'}), 403
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    if not email or '@' not in email:
        return jsonify({'error': 'Invalid email address'}), 400
    token = add_editor(email)
    base = _get_shareable_base_url()
    link = f"{base}/join/editor/{token}"
    return jsonify({'success': True, 'email': email, 'token': token, 'link': link})

@app.route('/api/access/remove_editor', methods=['POST'])
def api_remove_editor():
    if session.get('role') not in ['owner', 'editor']:
        return jsonify({'error': 'Permission denied'}), 403
    data = request.get_json() or {}
    email = data.get('email', '').strip()
    remove_editor(email)
    return jsonify({'success': True})

@app.route('/api/access/editors')
def api_get_editors():
    editors = get_all_editors()
    base = _get_shareable_base_url()
    for e in editors:
        e['link'] = f"{base}/join/editor/{e['token']}"
    return jsonify({'editors': editors})

@app.route('/api/access/add_leader', methods=['POST'])
def api_add_leader():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    if not email or '@' not in email:
        return jsonify({'error': 'Invalid email address'}), 400
    token = add_leader(email)
    base = _get_shareable_base_url()
    link = f"{base}/join/leader/{token}"
    return jsonify({'success': True, 'email': email, 'token': token, 'link': link})

@app.route('/api/access/remove_leader', methods=['POST'])
def api_remove_leader():
    data = request.get_json() or {}
    email = data.get('email', '').strip()
    remove_leader(email)
    return jsonify({'success': True})

@app.route('/api/access/leaders')
def api_get_leaders():
    leaders = get_all_leaders()
    base = _get_shareable_base_url()
    for l in leaders:
        l['link'] = f"{base}/join/leader/{l['token']}"
    return jsonify({'leaders': leaders})

@app.route('/api/access/employee_link')
def api_employee_link():
    token = get_employee_token()
    base = _get_shareable_base_url()
    link = f"{base}/join/employee/{token}"
    return jsonify({'link': link, 'token': token})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 4000))
    print(f"Starting Delivery Readiness Portal Executive Dashboard on 0.0.0.0:{port} ...")
    app.run(host='0.0.0.0', port=port, debug=False)
