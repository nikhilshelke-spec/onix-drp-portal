import os
import io
import urllib.request
import pandas as pd
import numpy as np
from config import DEFAULT_EXCEL_PATH, LOCAL_EXCEL_PATH, GOOGLE_SHEET_URL, TIER_DEFINITIONS

class DRPService:
    def __init__(self):
        self.df = None
        self.last_sync_source = "Local Cache"
        # On startup: first try Google Sheet, then fall back to local Excel
        success, msg = self.sync_from_google_sheet()
        if not success:
            self.load_data()

    def sync_from_google_sheet(self):
        # Extract Sheet ID from URL
        sheet_url = GOOGLE_SHEET_URL
        csv_export_url = "https://docs.google.com/spreadsheets/d/1BfjxlXT2oBXGD8wHLn8fM8fJlAdGJOQl_d9YEPxLsx0/export?format=csv&gid=0"
        try:
            req = urllib.request.Request(csv_export_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            with urllib.request.urlopen(req, timeout=8) as resp:
                csv_bytes = resp.read()
                df = pd.read_csv(io.BytesIO(csv_bytes))
                self.df = self._clean_and_normalize(df)
                os.makedirs(os.path.dirname(LOCAL_EXCEL_PATH), exist_ok=True)
                self.df.to_excel(LOCAL_EXCEL_PATH, index=False)
                self.last_sync_source = "Live Google Sheet"
                return True, f"Successfully synced live {len(self.df)} employees from Google Sheet!"
        except Exception as e:
            err_msg = str(e)
            if '401' in err_msg or 'Unauthorized' in err_msg:
                err_msg = "Google Sheet permission is Restricted. Click the 'Share' button in Google Sheet (top right) and set General access to 'Anyone with the link can view' for automatic live cloud sync."
            return False, f"{err_msg}"

    def load_data(self, file_path=None):
        target_path = file_path
        if not target_path or not os.path.exists(target_path):
            if os.path.exists(LOCAL_EXCEL_PATH):
                target_path = LOCAL_EXCEL_PATH
            elif os.path.exists(DEFAULT_EXCEL_PATH):
                target_path = DEFAULT_EXCEL_PATH

        if target_path and os.path.exists(target_path):
            try:
                if target_path.endswith('.csv'):
                    df = pd.read_csv(target_path)
                else:
                    df = pd.read_excel(target_path)
                self.df = self._clean_and_normalize(df)
                return True, f"Successfully loaded {len(self.df)} records"
            except Exception as e:
                return False, f"Error loading data: {str(e)}"
        return False, "No data file found."

    def _clean_and_normalize(self, df):
        df.columns = [str(c).strip() for c in df.columns]
        
        std_cols = {
            'Employee Id': 'employee_id',
            'Name': 'name',
            'Official Email Id': 'email',
            'Status': 'status',
            'Function': 'function',
            'Direct Manager Name': 'manager',
            'Cluster/Portfolio': 'cluster',
            'DRP ID': 'drp_id',
            'DRP Score': 'score',
            'Tier': 'tier',
            'DRP ID Status': 'drp_status',
            'Product': 'product'
        }
        
        rename_map = {}
        for col in df.columns:
            for std_key, std_val in std_cols.items():
                if col.lower() == std_key.lower():
                    rename_map[col] = std_val
                    break
        df = df.rename(columns=rename_map)
        
        df = df[[c for c in df.columns if not c.startswith('Unnamed:')]]

        if 'employee_id' not in df.columns:
            df['employee_id'] = [f'EMP{i+1:04d}' for i in range(len(df))]
        if 'name' not in df.columns:
            df['name'] = 'Unknown'
        if 'email' not in df.columns:
            df['email'] = ''
        if 'manager' not in df.columns:
            df['manager'] = 'Unassigned'
        if 'cluster' not in df.columns:
            df['cluster'] = 'General'
        if 'score' not in df.columns:
            df['score'] = 0.0
        if 'tier' not in df.columns:
            df['tier'] = 'Tier 4'
        if 'drp_status' not in df.columns:
            df['drp_status'] = 'Active'
        if 'product' not in df.columns:
            df['product'] = 'General Google Cloud'

        df['score'] = pd.to_numeric(df['score'], errors='coerce').fillna(0.0)
        df['manager'] = df['manager'].fillna('Unassigned').astype(str).str.strip()
        df['cluster'] = df['cluster'].fillna('General').astype(str).str.strip()
        df['product'] = df['product'].fillna('Not Specified').astype(str).str.strip()
        df['email'] = df['email'].fillna('').astype(str).str.strip()
        df['name'] = df['name'].fillna('Colleague').astype(str).str.strip()
        df['drp_id'] = df['drp_id'].fillna('None').astype(str).str.strip()
        df['drp_status'] = df['drp_status'].fillna('Active').astype(str).str.strip()

        def normalize_tier_row(row):
            tier_raw = str(row.get('tier', '')).strip()
            status_raw = str(row.get('drp_status', '')).strip().lower()
            score = float(row.get('score', 0))

            if 'exempted' in tier_raw.lower() or 'exempted' in status_raw:
                return 'Exempted'
            if 'admin' in tier_raw.lower():
                return 'Admin'
            if 'not created' in status_raw or tier_raw in ['nan', '', 'None', 'Tier 0', '0']:
                return 'DRP ID Not Created'
            
            if 'tier 1' in tier_raw.lower() or score >= 49:
                return 'Tier 1'
            elif 'tier 2' in tier_raw.lower() or (35 <= score < 49):
                return 'Tier 2'
            elif 'tier 3' in tier_raw.lower() or (20 <= score < 35):
                return 'Tier 3'
            elif 'tier 4' in tier_raw.lower() or (0 <= score < 20):
                return 'Tier 4'
            
            return 'Tier 4'

        df['normalized_tier'] = df.apply(normalize_tier_row, axis=1)

        def calculate_gap(row):
            ntier = row['normalized_tier']
            score = float(row['score'])
            if ntier == 'Tier 1':
                return 0.0, 'Goal Achieved', 'Mastery (49+ pts)'
            elif ntier == 'Tier 2':
                gap = max(0.0, 49.0 - score)
                return gap, 'Tier 1 (49 pts)', f'Need {gap:.1f} more pts'
            elif ntier == 'Tier 3':
                gap = max(0.0, 35.0 - score)
                return gap, 'Tier 2 (35 pts)', f'Need {gap:.1f} more pts'
            elif ntier == 'Tier 4':
                gap = max(0.0, 20.0 - score)
                return gap, 'Tier 3 (20 pts)', f'Need {gap:.1f} more pts'
            elif ntier == 'DRP ID Not Created':
                return 20.0, 'Create DRP Account & Tier 3', 'Register DRP ID'
            else:
                return 0.0, 'N/A', 'Exempted'

        gaps = df.apply(calculate_gap, axis=1)
        df['gap_points'] = [g[0] for g in gaps]
        df['target_tier'] = [g[1] for g in gaps]
        df['action_summary'] = [g[2] for g in gaps]

        df = df.fillna('')
        return df

    def get_kpis(self):
        if self.df is None or len(self.df) == 0:
            return {}
        
        total = len(self.df)
        counts = self.df['normalized_tier'].value_counts().to_dict()
        
        t1 = counts.get('Tier 1', 0)
        t2 = counts.get('Tier 2', 0)
        t3 = counts.get('Tier 3', 0)
        t4 = int(((self.df['normalized_tier'] == 'Tier 4') & (self.df['score'] > 0)).sum())
        zero_score = int((self.df['score'] == 0).sum())
        t0 = int(((self.df['drp_status'].str.lower().str.contains('not created')) | (self.df['drp_id'].isin(['None', '', 'nan']))).sum())
        exempted = counts.get('Exempted', 0) + counts.get('Admin', 0)
        
        active_tech = total - exempted
        t1_pct = round((t1 / max(1, active_tech)) * 100, 1)
        t2_pct = round((t2 / max(1, active_tech)) * 100, 1)
        t3_pct = round((t3 / max(1, active_tech)) * 100, 1)
        t4_pct = round((t4 / max(1, active_tech)) * 100, 1)
        zero_score_pct = round((zero_score / max(1, active_tech)) * 100, 1)
        
        drp_created = total - t0
        drp_created_pct = round((drp_created / max(1, total)) * 100, 1)
        drp_not_created_pct = round((t0 / max(1, total)) * 100, 1)

        active_scores = self.df[self.df['normalized_tier'].isin(['Tier 1', 'Tier 2', 'Tier 3', 'Tier 4'])]['score']
        avg_score = round(float(active_scores.mean()), 1) if len(active_scores) > 0 else 0.0

        return {
            'total_headcount': total,
            'active_tech_headcount': active_tech,
            'tier1_count': t1,
            'tier1_pct': t1_pct,
            'tier2_count': t2,
            'tier2_pct': t2_pct,
            'tier3_count': t3,
            'tier3_pct': t3_pct,
            'tier4_count': t4,
            'tier4_pct': t4_pct,
            'zero_score_count': zero_score,
            'zero_score_pct': zero_score_pct,
            'drp_not_created_count': t0,
            'drp_not_created_pct': drp_not_created_pct,
            'drp_created_count': drp_created,
            'drp_created_pct': drp_created_pct,
            'exempted_count': exempted,
            'avg_score': avg_score
        }

    def get_chart_data(self):
        if self.df is None:
            return {}

        clusters = [c for c in self.df['cluster'].value_counts().index.tolist() if c and c != 'General']
        if not clusters:
            clusters = self.df['cluster'].value_counts().index.tolist()
        clusters = clusters[:10]

        cluster_tier_breakdown = []
        for c in clusters:
            cdf = self.df[self.df['cluster'] == c]
            cluster_tier_breakdown.append({
                'cluster': c,
                'total': len(cdf),
                't1': int((cdf['normalized_tier'] == 'Tier 1').sum()),
                't2': int((cdf['normalized_tier'] == 'Tier 2').sum()),
                't3': int((cdf['normalized_tier'] == 'Tier 3').sum()),
                't4': int(((cdf['normalized_tier'] == 'Tier 4') & (cdf['score'] > 0)).sum()),
                'zero_score': int((cdf['score'] == 0).sum()),
                't0': int(((cdf['drp_status'].str.lower().str.contains('not created')) | (cdf['drp_id'].isin(['None', '', 'nan']))).sum())
            })

        prod_counts = self.df[self.df['product'] != 'Not Specified']['product'].value_counts().head(7)
        product_items = [{'name': k, 'count': int(v)} for k, v in prod_counts.items() if k]

        mgr_data = []
        for (mgr, clus), group in self.df.groupby(['manager', 'cluster']):
            if mgr and mgr != 'Unassigned':
                mgr_data.append({
                    'manager': mgr,
                    'cluster': clus,
                    'total': len(group),
                    't1': int((group['normalized_tier'] == 'Tier 1').sum()),
                    't2': int((group['normalized_tier'] == 'Tier 2').sum()),
                    't3': int((group['normalized_tier'] == 'Tier 3').sum()),
                    't4': int(((group['normalized_tier'] == 'Tier 4') & (group['score'] > 0)).sum()),
                    'zero_score': int((group['score'] == 0).sum()),
                    't0': int(((group['drp_status'].str.lower().str.contains('not created')) | (group['drp_id'].isin(['None', '', 'nan']))).sum())
                })

        mgr_data = sorted(mgr_data, key=lambda x: (x['t1'], x['t2'], x['total']), reverse=True)

        return {
            'cluster_dist': cluster_tier_breakdown,
            'product_items': product_items,
            'manager_leaderboard': mgr_data,
            'all_clusters': sorted(list(set(self.df['cluster'].dropna().tolist())))
        }

    def get_user_scope(self, verified_email, role='user'):
        """
        Determines the accessible employee scope for a user based on their verified email.
        - Owner/Editor/Leader: full access across all employees.
        - Regular verified user: their own record + direct reports where they are manager.
        """
        if self.df is None or len(self.df) == 0:
            return {'my_record': None, 'direct_reports': [], 'is_manager': False, 'allowed_df': None, 'is_admin': False}

        if role in ['owner', 'editor', 'leader']:
            return {'my_record': None, 'direct_reports': [], 'is_manager': True, 'allowed_df': self.df.copy(), 'is_admin': True}

        if not verified_email:
            return {'my_record': None, 'direct_reports': [], 'is_manager': False, 'allowed_df': self.df.iloc[0:0].copy(), 'is_admin': False}

        v_email = verified_email.strip().lower()
        prefix = v_email.split('@')[0].lower()

        # Find personal record
        my_df = self.df[(self.df['email'].str.lower() == v_email) | (self.df['email'].str.lower().str.startswith(prefix))]
        my_record = my_df.iloc[0].to_dict() if len(my_df) > 0 else None

        # Find direct reports where manager is this user
        manager_names = [prefix]
        if my_record and my_record.get('name'):
            manager_names.append(str(my_record['name']).strip().lower())

        reports_mask = (
            self.df['manager'].str.lower().str.contains(prefix, na=False) |
            self.df['manager'].str.lower().isin(manager_names)
        )
        reports_df = self.df[reports_mask].copy()

        # Exclude self from direct reports if present
        if my_record:
            reports_df = reports_df[reports_df['employee_id'] != my_record.get('employee_id', '')]

        # Combined allowed dataset
        frames = []
        if my_record:
            frames.append(my_df)
        if len(reports_df) > 0:
            frames.append(reports_df)

        allowed_df = pd.concat(frames).drop_duplicates(subset=['employee_id']).fillna('') if frames else self.df.iloc[0:0].copy()

        return {
            'my_record': my_record,
            'direct_reports': reports_df.fillna('').to_dict(orient='records'),
            'is_manager': len(reports_df) > 0,
            'allowed_df': allowed_df,
            'is_admin': False
        }

    def filter_employees(self, tier=None, manager=None, cluster=None, product=None, search=None, base_df=None):
        target_df = base_df if base_df is not None else self.df
        if target_df is None:
            return []
        
        filtered = target_df.copy()
        if tier and tier != 'All':
            if tier == 'DRP IDs with 0 Score':
                filtered = filtered[filtered['score'] == 0]
            else:
                filtered = filtered[filtered['normalized_tier'] == tier]
        if manager and manager != 'All':
            filtered = filtered[filtered['manager'] == manager]
        if cluster and cluster != 'All':
            filtered = filtered[filtered['cluster'] == cluster]
        if product and product != 'All':
            filtered = filtered[filtered['product'] == product]
        if search:
            s = search.lower().strip()
            filtered = filtered[
                filtered['name'].str.lower().str.contains(s, na=False) |
                filtered['email'].str.lower().str.contains(s, na=False) |
                filtered['employee_id'].str.lower().str.contains(s, na=False) |
                filtered['drp_id'].str.lower().str.contains(s, na=False)
            ]
        filtered = filtered.fillna('')
        return filtered.to_dict(orient='records')

    def get_filter_options(self, base_df=None):
        target_df = base_df if base_df is not None else self.df
        if target_df is None or len(target_df) == 0:
            return {'managers': [], 'clusters': [], 'products': [], 'tiers': []}
        return {
            'managers': sorted([m for m in target_df['manager'].dropna().unique().tolist() if m and m != 'Unassigned']),
            'clusters': sorted([c for c in target_df['cluster'].dropna().unique().tolist() if c]),
            'products': sorted([p for p in target_df['product'].dropna().unique().tolist() if p and p != 'Not Specified']),
            'tiers': ['Tier 1', 'Tier 2', 'Tier 3', 'Tier 4', 'DRP IDs with 0 Score', 'DRP ID Not Created', 'Exempted']
        }

    def get_employee(self, emp_id):
        if self.df is None:
            return None
        match = self.df[self.df['employee_id'] == str(emp_id)]
        if len(match) > 0:
            rec = match.iloc[0].to_dict()
            clean_rec = {}
            for k, v in rec.items():
                if pd.isna(v) or v is None or str(v) == 'nan':
                    clean_rec[k] = ''
                else:
                    clean_rec[k] = v
            return clean_rec
        return None

drp_service = DRPService()
