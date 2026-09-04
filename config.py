import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DEFAULT_EXCEL_PATH = r"C:\Users\nikhil.shelke\Downloads\DRP Tier Project.xlsx"
LOCAL_EXCEL_PATH = os.path.join(DATA_DIR, "current_data.xlsx")

GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1BfjxlXT2oBXGD8wHLn8fM8fJlAdGJOQl_d9YEPxLsx0/edit?gid=0#gid=0"
DRP_PORTAL_URL = "https://delivery-readiness-portal.cloud.google/app/login"
CREDLY_URL = "https://www.credly.com/users/sign_in"
DRP_MAPPING_SHEET_URL = "https://docs.google.com/spreadsheets/d/18dCDJX27QVROXPPNghIC5F3VxzJ8cawXtOf3xgKtkAI/edit?gid=28087814#gid=28087814"
DRP_ATTRIBUTION_URL = DRP_MAPPING_SHEET_URL

TIER_DEFINITIONS = {
    "Tier 1": {"min": 49, "max": 999, "label": "Tier 1 (Mastery - 49+ pts)", "badge_color": "emerald", "target": "Goal Reached"},
    "Tier 2": {"min": 35, "max": 48.99, "label": "Tier 2 (35 – 49 pts)", "badge_color": "blue", "target": "Tier 1 (49+ pts)"},
    "Tier 3": {"min": 20, "max": 34.99, "label": "Tier 3 (20 – 34 pts)", "badge_color": "amber", "target": "Tier 2 (35 pts)"},
    "Tier 4": {"min": 0.01, "max": 19.99, "label": "Tier 4 (0 – 19 pts)", "badge_color": "purple", "target": "Tier 3 (20 pts)"},
    "DRP IDs with 0 Score": {"min": 0, "max": 0, "label": "DRP IDs with 0 Score", "badge_color": "rose", "target": "Tier 4 (1-19 pts)"},
    "DRP ID Not Created": {"min": 0, "max": 0, "label": "DRP ID Not Created", "badge_color": "rose", "target": "Create DRP ID & Tier 4"},
    "Exempted": {"min": 0, "max": 0, "label": "Exempted / Other", "badge_color": "gray", "target": "N/A"}
}

POINTS_CRITERIA = [
    {"activity": "Other Cloud Provider Experience (max 4)", "points": "1 Point Per Year"},
    {"activity": "Project Deployed (max 51)", "points": "5 Points Each"},
    {"activity": "Skill Badges / Labs (max 15)", "points": "5 Points Each"},
    {"activity": "Technical Training (max 15)", "points": "5 Points Each"},
    {"activity": "Technical Certification (max 15)", "points": "Primary Cert for Product - 10 | Other GCP Cert - 5"}
]

PRODUCT_SCORE_RULE = (
    "DRP scores are calculated using your highest score in a single product focus area; "
    "they are not cumulative across multiple products."
)

CREDLY_SYNC_RULE = (
    "If your current badges/certifications are not reflecting in DRP, ensure you have an active Credly profile "
    "and have added your ONIX email as a secondary email, as DRP does not sync data directly through Google Skills."
)
