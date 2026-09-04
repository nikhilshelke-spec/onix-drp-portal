import os
import json
import time
import uuid
import smtplib
import threading
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import quote
from config import DRP_PORTAL_URL, CREDLY_URL, DRP_MAPPING_SHEET_URL, POINTS_CRITERIA, PRODUCT_SCORE_RULE, CREDLY_SYNC_RULE

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SMTP_FILE = os.path.join(DATA_DIR, "smtp_settings.json")
TEMPLATES_FILE = os.path.join(DATA_DIR, "email_templates.json")
JOBS_FILE = os.path.join(DATA_DIR, "campaign_jobs.json")
HISTORY_FILE = os.path.join(DATA_DIR, "campaign_history.json")

DEFAULT_TEMPLATES = {
    "DRP ID Not Created": {
        "subject": "Action Required: Urgent DRP Profile Setup & Registration",
        "body": """Our records indicate your Google Delivery Readiness Portal (DRP) account is pending registration. Creating your DRP account is mandatory to track your Google Cloud technical competency and partner tier.

We are launching a company-wide drive to help every technical engineer get registered and advance towards Tier 1 (49+ points) in our Google DRP framework. Upgrading your tier showcases your technical mastery and directly impacts our Google Premier Partner metrics.

Please complete your DRP profile registration immediately to ensure your competency contributions and project credentials are fully recognized."""
    },
    "DRP IDs with 0 Score": {
        "subject": "Action Required: Push Your DRP Score to Reach Tier 1!",
        "body": """We noticed your DRP score is currently at 0.0 points in your mapped focus area: {product}. We are launching a focused drive to help you activate your points and advance towards Tier 1 (49+ points).

Your Current Standing:
- Standing: Score 0.0 pts | Product Focus: {product}
- Target: Tier 4 (1-19 pts) (Activate your score with 1 badge or cert)

Complete a quick Skill Badge (5 pts) or Google Cloud Certification (10 pts) on Credly and link it to DRP to activate your score this week!"""
    },
    "Tier 4": {
        "subject": "Action Required: Push Your DRP Score to Reach Tier 1!",
        "body": """We are launching a focused drive to help everyone reach Tier 1 (49+ points) in our Google DRP framework. Upgrading your tier showcases your technical mastery and directly impacts our team's core competency metrics.

Your Current Status:
- Current Tier: Tier 4 | Current Score: {score} pts | Focus: {product}
- Next Milestone Target: {target_tier} (You need only {gap} more points to upgrade!)

Every badge, skill lab, and project deployment counts. Review the DRP Attribution sheet and pick your next milestone."""
    },
    "Tier 3": {
        "subject": "Action Required: Push Your DRP Score to Reach Tier 1!",
        "body": """Great momentum! You are currently in Tier 3 with {score} points in your mapped product: {product}. 

Your Current Status:
- Current Tier: Tier 3 | Current Score: {score} pts | Focus: {product}
- Next Milestone Target: {target_tier} (You need only {gap} more points to upgrade!)

You are within striking distance of Tier 2. Complete your product-specific certifications and project contributions to upgrade this quarter."""
    },
    "Tier 2": {
        "subject": "Action Required: Push Your DRP Score to Reach Tier 1!",
        "body": """Outstanding progress! You are currently in Tier 2 with {score} points in your mapped product: {product}. 

Your Current Status:
- Current Tier: Tier 2 | Current Score: {score} pts | Focus: {product}
- Next Milestone Target: Tier 1 (49+ pts) (You need only {gap} more points to reach Tier 1 Mastery!)

You are in the final sprint to Tier 1 Mastery. Drive your projects and advanced Google certifications to cross the finish line."""
    },
    "Tier 1": {
        "subject": "Congratulations: Tier 1 Mastery Recognition & Mentor Leadership",
        "body": """Congratulations on achieving Tier 1 Mastery ({score} points) with your focus area in {product}! You represent the highest level of Google Cloud technical competency across Onix.

Your technical expertise sets a stellar benchmark for our team. As a Tier 1 leader, we invite you to guide and mentor team members in Tiers 2, 3, and 4 to help accelerate their journey towards Tier 1."""
    }
}

class EmailService:
    def __init__(self):
        self.sent_history = []
        self.smtp_config = self._load_smtp_config()
        self.templates = self._load_templates()
        self.jobs = self._load_jobs()
        self.history = self._load_history()

    def _load_smtp_config(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(SMTP_FILE):
            try:
                with open(SMTP_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            'host': os.environ.get('SMTP_HOST', 'smtp.gmail.com'),
            'port': int(os.environ.get('SMTP_PORT', 587)),
            'user': os.environ.get('SMTP_USER', 'nikhil.shelke@onixnet.com'),
            'password': os.environ.get('SMTP_PASSWORD', ''),
            'sender_name': 'Nikhil Shelke'
        }

    def save_smtp_config(self, host, port, user, password, sender_name):
        self.smtp_config = {
            'host': host.strip() if host else 'smtp.gmail.com',
            'port': int(port) if port else 587,
            'user': user.strip() if user else '',
            'password': password.strip() if password else '',
            'sender_name': sender_name.strip() if sender_name else 'Nikhil Shelke'
        }
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(SMTP_FILE, "w", encoding="utf-8") as f:
            json.dump(self.smtp_config, f, indent=2)
        return True

    def _load_templates(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(TEMPLATES_FILE):
            try:
                with open(TEMPLATES_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    templates = DEFAULT_TEMPLATES.copy()
                    templates.update(loaded)
                    return templates
            except Exception:
                pass
        return DEFAULT_TEMPLATES.copy()

    def get_template(self, tier):
        self.templates = self._load_templates()
        tpl = self.templates.get(tier, DEFAULT_TEMPLATES.get(tier, {
            "subject": "Action Required: Push Your DRP Score to Reach Tier 1!",
            "body": "We are launching a focused drive to help everyone reach Tier 1 (49+ points) in our Google DRP framework."
        }))
        # Ensure single body field compatibility
        if 'body' not in tpl and 'intro_text' in tpl:
            tpl['body'] = (tpl.get('intro_text', '') + "\n\n" + tpl.get('custom_body', '')).strip()
        return tpl

    def save_template(self, tier, subject, body):
        self.templates = self._load_templates()
        self.templates[tier] = {
            "subject": subject.strip(),
            "body": body.strip()
        }
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(TEMPLATES_FILE, "w", encoding="utf-8") as f:
            json.dump(self.templates, f, indent=2)
        return True

    def _load_jobs(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(JOBS_FILE):
            try:
                with open(JOBS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_jobs(self):
        try:
            with open(JOBS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.jobs, f, indent=2)
        except Exception:
            pass

    def _load_history(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_history(self):
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.history, f, indent=2)
        except Exception:
            pass

    def record_campaign_history(self, tier, sent_count, failed_count, total, sent_by="Nikhil Shelke"):
        self.history = self._load_history()
        entry = {
            "id": str(uuid.uuid4())[:8],
            "date": datetime.now().strftime("%d %b %Y, %I:%M %p"),
            "timestamp": time.time(),
            "tier": tier,
            "sent_count": sent_count,
            "failed_count": failed_count,
            "total": total,
            "sent_by": sent_by,
            "status": "Delivered" if failed_count == 0 else f"{sent_count}/{total} Delivered"
        }
        self.history.insert(0, entry)
        self._save_history()
        return entry

    def get_campaign_history(self):
        self.history = self._load_history()
        return self.history

    def interpolate_text(self, text, employee_data):
        name = employee_data.get('name', 'Colleague')
        tier = employee_data.get('normalized_tier', 'Tier 4')
        score = float(employee_data.get('score', 0.0))
        product = employee_data.get('product', 'Google Cloud')
        if product in ['Not Specified', 'nan', '']:
            product = 'Primary Google Cloud Product'
        gap = float(employee_data.get('gap_points', 0.0))
        target_tier = employee_data.get('target_tier', 'Tier 1')
        drp_id = employee_data.get('drp_id', 'None')
        manager = employee_data.get('manager', 'Manager')

        replacements = {
            "{name}": name,
            "{score}": f"{score:.1f}",
            "{gap}": f"{gap:.1f}",
            "{product}": product,
            "{tier}": tier,
            "{target_tier}": target_tier,
            "{drp_id}": drp_id,
            "{manager}": manager
        }
        out = text
        for k, v in replacements.items():
            out = out.replace(k, str(v))
        return out

    def generate_email_content(self, employee_data, custom_template=None):
        name = employee_data.get('name', 'Team Member')
        tier = employee_data.get('normalized_tier', 'Tier 4')
        score = float(employee_data.get('score', 0.0))
        product = employee_data.get('product', 'Google Cloud')
        if product in ['Not Specified', 'nan', '']:
            product = 'Primary Google Cloud Product'
        manager = employee_data.get('manager', '')
        gap = float(employee_data.get('gap_points', 0.0))
        to_email = employee_data.get('email', '')

        tpl = custom_template or self.get_template(tier)
        subject = self.interpolate_text(tpl.get('subject', 'Action Required: Push Your DRP Score to Reach Tier 1!'), employee_data)
        raw_body = tpl.get('body', '')
        if not raw_body and 'intro_text' in tpl:
            raw_body = (tpl.get('intro_text', '') + "\n\n" + tpl.get('custom_body', '')).strip()

        body_text_interpolated = self.interpolate_text(raw_body, employee_data)
        
        # Convert plain paragraphs to clean HTML paragraphs
        body_paragraphs = body_text_interpolated.split('\n\n')
        body_html_formatted = "".join([f'<p style="font-size: 14px; line-height: 1.6; color: #374151; margin: 0 0 14px 0;">{p.replace(chr(10), "<br>")}</p>' for p in body_paragraphs if p.strip()])

        table_rows = ''
        for p in POINTS_CRITERIA:
            table_rows += f"""
            <tr style="border-bottom: 1px solid #E5E7EB;">
                <td style="padding: 10px 14px; font-size: 13px; color: #1F2937;">{p['activity']}</td>
                <td style="padding: 10px 14px; font-size: 13px; color: #1F2937; font-weight: 600;">{p['points']}</td>
            </tr>
            """

        html_body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #F9FAFB; margin: 0; padding: 24px; }}
        .container {{ max-width: 640px; margin: 0 auto; background: #FFFFFF; border-radius: 8px; border: 1px solid #E5E7EB; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }}
        .header {{ background-color: #30496D; color: white; padding: 24px; text-align: left; }}
        .content {{ padding: 24px 28px; }}
        .table-box {{ width: 100%; border-collapse: collapse; margin: 16px 0; background: #FAFAFA; border: 1px solid #E5E7EB; border-radius: 6px; }}
        .rule-card {{ background-color: #FFF0F0; border: 2px solid #f35959; border-left: 6px solid #f35959; padding: 16px 18px; border-radius: 8px; margin: 20px 0; font-size: 13px; color: #1F2937; line-height: 1.6; }}
        .footer {{ background: #F3F4F6; padding: 16px 28px; font-size: 12px; color: #6B7280; text-align: center; border-top: 1px solid #E5E7EB; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div style="font-size: 12px; text-transform: uppercase; letter-spacing: 1px; opacity: 0.9; margin-bottom: 4px; font-weight: 600;">L&D Enablement</div>
            <h2 style="margin: 0; font-size: 20px; font-weight: 700;">Google DRP Tier Acceleration Drive</h2>
        </div>
        <div class="content">
            <p style="font-size: 15px; color: #111827; margin: 0 0 16px 0;">Hi <strong>{name}</strong>,</p>
            
            {body_html_formatted}

            <div style="margin: 20px 0;">
                <h4 style="margin: 0 0 8px 0; font-size: 14px; text-transform: uppercase; color: #4B5563; letter-spacing: 0.5px;">Current Tier Breakdown</h4>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 13px; background: #F9FAFB; padding: 12px; border-radius: 6px; border: 1px solid #E5E7EB;">
                    <div>• <strong style="color: #059669;">Tier 1:</strong> 49+ points</div>
                    <div>• <strong style="color: #30496D;">Tier 2:</strong> 35 – 49 points</div>
                    <div>• <strong style="color: #D97706;">Tier 3:</strong> 20 – 34 points</div>
                    <div>• <strong style="color: #7C3AED;">Tier 4:</strong> 0 – 19 points</div>
                </div>
            </div>

            <h4 style="margin: 20px 0 8px 0; font-size: 14px; text-transform: uppercase; color: #4B5563; letter-spacing: 0.5px;">How to Earn Points</h4>
            <p style="font-size: 13px; color: #6B7280; margin: 0 0 10px 0;">You can build your overall score through the following activities:</p>
            <table class="table-box">
                <thead>
                    <tr style="background: #F3F4F6; text-align: left; border-bottom: 2px solid #E5E7EB;">
                        <th style="padding: 10px 14px; font-size: 13px; color: #374151;">Activity</th>
                        <th style="padding: 10px 14px; font-size: 13px; color: #374151;">Points</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>

            <div class="rule-card">
                <strong style="color: #f35959; font-size: 13.5px; display: block; margin-bottom: 8px; letter-spacing: 0.3px;">CRITICAL NOTE ON PRODUCT SCORE ACCUMULATION:</strong>
                <ul style="margin: 0; padding-left: 18px;">
                    <li style="margin-bottom: 6px;">{PRODUCT_SCORE_RULE}</li>
                    <li style="margin-bottom: 6px;">{CREDLY_SYNC_RULE.replace('Credly', f'<a href="{CREDLY_URL}" style="color: #30496D; text-decoration: underline; font-weight: 600;" target="_blank">Credly</a>')}</li>
                    <li>Those in Product Engineering/sales may skip the project component and instead complete the learning modules to earn points and maintain an active profile.</li>
                </ul>
            </div>

            <h4 style="margin: 20px 0 8px 0; font-size: 14px; text-transform: uppercase; color: #4B5563; letter-spacing: 0.5px;">Next Steps</h4>
            <ol style="font-size: 13px; color: #374151; line-height: 1.7; margin: 0; padding-left: 20px;">
                <li>Check your current primary product mapping in your <a href="{DRP_PORTAL_URL}" style="color: #30496D; font-weight: 600;" target="_blank">DRP Profile</a> (Mapped: <strong>{product}</strong>).</li>
                <li>Review the <a href="{DRP_MAPPING_SHEET_URL}" style="color: #30496D; font-weight: 600;" target="_blank">DRP Attribution Mapping Sheet</a> for your product pathways.</li>
                <li>Complete your labs, trainings, or certifications to upgrade your tier.</li>
            </ol>

            <div style="margin-top: 24px; padding: 14px 18px; background: #F8FAFC; border-radius: 6px; border: 1px solid #E2E8F0; font-size: 13px; color: #334155; line-height: 1.6;">
                <strong>Let's get everyone across the finish line to Tier 1!</strong> Reach out to L&D team if you have any questions regarding your mapped product or score calculations.
                <div style="margin-top: 8px; font-size: 12px; color: #475569;">
                    <strong>Contact:</strong> <a href="mailto:learninganddevelopment@onixnet.com" style="color: #30496D; font-weight: 600; text-decoration: underline;">learninganddevelopment@onixnet.com</a> (L&D Team)
                </div>
            </div>
        </div>
        <div class="footer">
            <p style="margin: 0; font-weight: 600; color: #64748B;">This communication is auto-generated by L&D team.</p>
        </div>
    </div>
</body>
</html>"""

        text_body = f"""Hi {name},

{body_text_interpolated}

Next Steps:
1. DRP Profile: {DRP_PORTAL_URL}
2. DRP Attribution: {DRP_MAPPING_SHEET_URL}
3. Credly Verification: {CREDLY_URL}

Contact: learninganddevelopment@onixnet.com (L&D Team)
This communication is auto-generated by L&D team.
"""

        gmail_url = f"https://mail.google.com/mail/?view=cm&fs=1&to={quote(to_email)}&su={quote(subject)}&body={quote(text_body)}"
        mailto_url = f"mailto:{quote(to_email)}?subject={quote(subject)}&body={quote(text_body)}"

        return {
            'to': to_email,
            'name': name,
            'manager': manager,
            'subject': subject,
            'body_html': html_body,
            'body_text': text_body,
            'raw_body': raw_body,
            'gmail_url': gmail_url,
            'mailto_url': mailto_url
        }

    def send_email_live(self, to_email, subject, html_content, text_content='', cc_email=''):
        self.smtp_config = self._load_smtp_config()
        
        # 1. First priority: Check if Google Apps Script Webhook is configured (Works 100% on Render/Cloud HTTPS)
        webhook_url = os.environ.get('GOOGLE_MAIL_WEBHOOK', '') or self.smtp_config.get('webhook_url', '')
        if webhook_url:
            try:
                import requests
                payload = {
                    'to': to_email,
                    'subject': subject,
                    'html': html_content,
                    'text': text_content,
                    'cc': cc_email if (cc_email and '@' in cc_email) else ''
                }
                resp = requests.post(webhook_url, json=payload, timeout=15, allow_redirects=True)
                if resp.status_code in [200, 302]:
                    return True, f"Dispatched via Google Cloud Webhook to {to_email}"
                else:
                    return False, f"Webhook error HTTP {resp.status_code}: {resp.text[:150]}"
            except Exception as we:
                return False, f"Webhook dispatch exception: {str(we)}"

        user = (self.smtp_config.get('user') or '').strip()
        pwd = (self.smtp_config.get('password') or '').replace(' ', '').strip()
        host = self.smtp_config.get('host', 'smtp.gmail.com')
        port = int(self.smtp_config.get('port', 587))
        sender_name = self.smtp_config.get('sender_name', 'Nikhil Shelke')

        if not user or not pwd:
            return False, "SMTP Credentials (User/App Password) not configured yet."
        
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{sender_name} <{user}>"
            msg['To'] = to_email
            
            valid_cc = cc_email.strip() if (cc_email and '@' in cc_email) else ''
            if valid_cc:
                msg['Cc'] = valid_cc
                
            if text_content:
                msg.attach(MIMEText(text_content, 'plain'))
            if html_content:
                msg.attach(MIMEText(html_content, 'html'))
            
            recipients = [to_email]
            if valid_cc:
                recipients.append(valid_cc)

            # Try Port 465 (SSL) first, then fallback to Port 587 (TLS)
            server_connected = False
            last_err = None
            try:
                with smtplib.SMTP_SSL(host, 465, timeout=10) as server:
                    server.login(user, pwd)
                    server.sendmail(user, recipients, msg.as_string())
                    server_connected = True
            except Exception as e1:
                last_err = e1
                try:
                    with smtplib.SMTP(host, port if port != 465 else 587, timeout=10) as server:
                        server.starttls()
                        server.login(user, pwd)
                        server.sendmail(user, recipients, msg.as_string())
                        server_connected = True
                except Exception as e2:
                    last_err = e2
            
            if server_connected:
                return True, f"Dispatched successfully to {to_email}"
            return False, f"SMTP Dispatch Error: {str(last_err)}"
        except Exception as e:
            return False, f"SMTP Dispatch Error: {str(e)}"

    def send_otp_email(self, to_email, otp_code, magic_link):
        subject = f"Your Onix Employee Hub Verification Code: {otp_code}"
        html_content = f"""<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #F8FAFC; padding: 24px; margin: 0;">
    <div style="max-width: 500px; margin: 0 auto; background: #FFFFFF; border-radius: 12px; border: 1px solid #E2E8F0; padding: 32px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
        <div style="background: #30496D; padding: 12px 16px; border-radius: 8px; display: inline-block; color: white; font-weight: 800; font-size: 14px; margin-bottom: 20px;">
            ONIX L&D ENABLEMENT
        </div>
        <h2 style="margin: 0 0 12px 0; font-size: 20px; color: #0F172A;">Employee Hub Access Verification</h2>
        <p style="color: #475569; font-size: 14px; line-height: 1.5; margin: 0 0 20px 0;">
            Use the verification code below to securely log in and access your personal DRP Scorecard and team dashboard on the <strong>Onix Employee Hub</strong>:
        </p>
        
        <div style="text-align: center; margin: 24px 0;">
            <div style="display: inline-block; background: #EEF2FF; border: 2px dashed #30496D; border-radius: 10px; padding: 14px 28px; font-size: 32px; font-weight: 800; letter-spacing: 6px; color: #30496D;">
                {otp_code}
            </div>
            <p style="font-size: 12px; color: #64748B; margin-top: 8px;">Code expires in 15 minutes.</p>
        </div>

        <div style="text-align: center; margin: 24px 0 16px 0;">
            <a href="{magic_link}" style="background-color: #30496D; color: #FFFFFF; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-size: 14px; font-weight: 700; display: inline-block;">
                Direct Access Link &rarr;
            </a>
        </div>

        <hr style="border: none; border-top: 1px solid #E2E8F0; margin: 24px 0;">
        <p style="font-size: 11px; color: #94A3B8; margin: 0; text-align: center;">
            Created & Managed by L&D Enablement Team.
        </p>
    </div>
</body>
</html>"""
        text_content = f"Your Onix Employee Hub verification code is: {otp_code}\n\nOr access directly with this link: {magic_link}\n\nCode expires in 15 minutes.\nCreated & Managed by L&D Enablement Team."
        return self.send_email_live(to_email, subject, html_content, text_content)

    def start_campaign_job(self, tier, employees, custom_template=None, cc_manager=True):
        job_id = str(uuid.uuid4())[:8]
        self.jobs[job_id] = {
            'id': job_id,
            'tier': tier,
            'total': len(employees),
            'processed': 0,
            'success_count': 0,
            'failed_count': 0,
            'status': 'running',
            'start_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'sent_list': [],
            'failed_list': [],
            'error_message': ''
        }
        self._save_jobs()

        def _run_worker():
            self.smtp_config = self._load_smtp_config()
            user = (self.smtp_config.get('user') or '').strip()
            pwd = (self.smtp_config.get('password') or '').replace(' ', '').strip()
            host = self.smtp_config.get('host', 'smtp.gmail.com')
            port = int(self.smtp_config.get('port', 587))
            sender_name = self.smtp_config.get('sender_name', 'Nikhil Shelke')

            if not user or not pwd:
                self.jobs[job_id]['status'] = 'failed'
                self.jobs[job_id]['error_message'] = 'SMTP credentials not configured.'
                self._save_jobs()
                return

            server = None
            try:
                server = smtplib.SMTP(host, port, timeout=30)
                server.starttls()
                server.login(user, pwd)

                for idx, emp in enumerate(employees):
                    to_email = emp.get('email', '').strip()
                    name = emp.get('name', 'Colleague')
                    if not to_email or '@' not in to_email:
                        self.jobs[job_id]['processed'] += 1
                        self.jobs[job_id]['failed_count'] += 1
                        self.jobs[job_id]['failed_list'].append({'name': name, 'email': to_email or '(missing)', 'reason': 'Invalid or missing email address'})
                        self._save_jobs()
                        continue

                    # Reconnect periodically
                    if idx > 0 and idx % 25 == 0:
                        try:
                            server.quit()
                        except Exception:
                            pass
                        time.sleep(1)
                        server = smtplib.SMTP(host, port, timeout=30)
                        server.starttls()
                        server.login(user, pwd)

                    try:
                        content = self.generate_email_content(emp, custom_template)
                        msg = MIMEMultipart('alternative')
                        msg['Subject'] = content['subject']
                        msg['From'] = f"{sender_name} <{user}>"
                        msg['To'] = to_email

                        cc_email = emp.get('manager_email', '') if cc_manager else ''
                        if cc_email and '@' in cc_email:
                            msg['Cc'] = cc_email
                            recipients = [to_email, cc_email]
                        else:
                            recipients = [to_email]

                        msg.attach(MIMEText(content['body_text'], 'plain'))
                        msg.attach(MIMEText(content['body_html'], 'html'))

                        server.sendmail(user, recipients, msg.as_string())
                        self.jobs[job_id]['success_count'] += 1
                        self.jobs[job_id]['sent_list'].append({'name': name, 'email': to_email})
                    except Exception as ex:
                        self.jobs[job_id]['failed_count'] += 1
                        self.jobs[job_id]['failed_list'].append({'name': name, 'email': to_email, 'reason': str(ex)})

                    self.jobs[job_id]['processed'] += 1
                    if idx % 5 == 0:
                        self._save_jobs()
                    time.sleep(0.15)

                self.jobs[job_id]['status'] = 'completed'
                # Record to persistent history log
                self.record_campaign_history(
                    tier=tier,
                    sent_count=self.jobs[job_id]['success_count'],
                    failed_count=self.jobs[job_id]['failed_count'],
                    total=self.jobs[job_id]['total'],
                    sent_by=sender_name
                )
            except Exception as outer_ex:
                self.jobs[job_id]['status'] = 'failed'
                self.jobs[job_id]['error_message'] = str(outer_ex)
            finally:
                if server:
                    try:
                        server.quit()
                    except Exception:
                        pass
                self._save_jobs()

        t = threading.Thread(target=_run_worker, daemon=True)
        t.start()
        return job_id

    def get_job_status(self, job_id):
        return self.jobs.get(job_id, None)

email_service = EmailService()
