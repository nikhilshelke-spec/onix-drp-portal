import os
import io
import re
import json
import urllib.request
import pandas as pd
import numpy as np
from config import LOCAL_EXCEL_PATH, GOOGLE_SHEET_URL, TIER_DEFINITIONS

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SHEET_CONFIG_FILE = os.path.join(DATA_DIR, "spreadsheet_config.json")
DRAFT_METADATA_FILE = os.path.join(DATA_DIR, "draft_metadata.json")

class DRPService:
    def __init__(self):
        self.df = None
        self.last_sync_source = "Uploaded Excel"
        self.file_mtime = 0
        self.current_loaded_path = None
        self.load_data()

    def get_draft_status(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(DRAFT_METADATA_FILE):
            try:
                with open(DRAFT_METADATA_FILE, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                    if meta.get('is_draft'):
                        default_path = os.path.join(DATA_DIR, "default_data.xlsx")
                        if os.path.exists(default_path) or any(os.path.exists(os.path.join(DATA_DIR, f"current_data{ext}")) for ext in ['.xlsx', '.xls', '.csv']):
                            meta['exists'] = True
                            return meta
            except Exception:
                pass
        return {'is_draft': False, 'exists': False}

    def get_data_as_of(self):
        try:
            self.ensure_loaded()
            meta = self.get_draft_status()
            raw_val = None
            if meta.get('is_draft') and meta.get('uploaded_at'):
                raw_val = meta.get('uploaded_at')
            elif self.current_loaded_path and os.path.exists(self.current_loaded_path):
                try:
                    mtime = os.path.getmtime(self.current_loaded_path)
                    import datetime
                    dt = datetime.datetime.fromtimestamp(mtime)
                    raw_val = dt.strftime("%d %b %Y")
                except Exception:
                    pass

            if raw_val:
                return str(raw_val).split(',')[0].strip()
        except Exception:
            pass
        import datetime
        return datetime.datetime.now().strftime("%d %b %Y")

    def save_as_draft(self, file_path, original_filename):
        os.makedirs(DATA_DIR, exist_ok=True)
        now_ts = int(pd.Timestamp.now().timestamp())
        meta = {
            'is_draft': True,
            'filename': original_filename,
            'uploaded_at': pd.Timestamp.now().strftime("%d %b %Y"),
            'records': len(self.df) if self.df is not None else 0,
            'updated_at': now_ts
        }
        try:
            with open(DRAFT_METADATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(meta, f, indent=2)
        except Exception:
            pass

        # Always sync uploaded file over default_data.xlsx as well
        default_path = os.path.join(DATA_DIR, "default_data.xlsx")
        try:
            if file_path != default_path and os.path.exists(file_path):
                import shutil
                shutil.copyfile(file_path, default_path)
        except Exception:
            pass

        self.last_sync_source = f"Draft Excel ({original_filename})"

    def delete_data(self):
        self.df = None
        self.file_mtime = 0
        self.current_loaded_path = None
        self.last_sync_source = "None"
        
        # Delete default_data.xlsx and all active excel/csv/metadata files
        if os.path.exists(DATA_DIR):
            for fname in os.listdir(DATA_DIR):
                fpath = os.path.join(DATA_DIR, fname)
                if os.path.isfile(fpath) and fname not in ['access_control.json', 'email_templates.json', 'smtp_settings.json', 'campaign_history.json', 'campaign_jobs.json', 'otp_store.json']:
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass
        return True

    def _find_best_candidate(self):
        default_path = os.path.join(DATA_DIR, "default_data.xlsx")
        if os.path.exists(default_path):
            for ext in ['.xlsx', '.xls', '.csv']:
                legacy_file = os.path.join(DATA_DIR, f"current_data{ext}")
                if os.path.exists(legacy_file):
                    try:
                        os.remove(legacy_file)
                    except Exception:
                        pass
            return default_path

        current_cands = [
            os.path.join(DATA_DIR, "current_data.xlsx"),
            os.path.join(DATA_DIR, "current_data.xls"),
            os.path.join(DATA_DIR, "current_data.csv"),
            LOCAL_EXCEL_PATH
        ]
        for cand in current_cands:
            if os.path.exists(cand):
                return cand
        return None

    def sync_from_github_raw(self):
        try:
            raw_meta_url = "https://raw.githubusercontent.com/nikhilshelke-spec/onix-drp-portal/main/data/draft_metadata.json"
            raw_excel_url = "https://raw.githubusercontent.com/nikhilshelke-spec/onix-drp-portal/main/data/default_data.xlsx"
            
            req = urllib.request.Request(raw_meta_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=4) as resp:
                remote_meta = json.loads(resp.read().decode('utf-8'))
                
            local_meta = self.get_draft_status()
            
            need_download = False
            if not local_meta.get('is_draft') and remote_meta.get('is_draft'):
                need_download = True
            elif remote_meta.get('is_draft') and (
                remote_meta.get('updated_at') != local_meta.get('updated_at') or
                remote_meta.get('uploaded_at') != local_meta.get('uploaded_at') or
                remote_meta.get('records') != local_meta.get('records') or
                remote_meta.get('filename') != local_meta.get('filename')
            ):
                need_download = True

            if need_download:
                req_excel = urllib.request.Request(raw_excel_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req_excel, timeout=8) as resp_excel:
                    excel_bytes = resp_excel.read()
                    default_path = os.path.join(DATA_DIR, "default_data.xlsx")
                    os.makedirs(DATA_DIR, exist_ok=True)
                    with open(default_path, 'wb') as f:
                        f.write(excel_bytes)
                    with open(DRAFT_METADATA_FILE, 'w', encoding='utf-8') as f_meta:
                        json.dump(remote_meta, f_meta, indent=2)
                    self.load_data(default_path)
                    return True
        except Exception:
            pass
        return False

    def ensure_loaded(self):
        self.sync_from_github_raw()
        target_path = self._find_best_candidate()
        if target_path and os.path.exists(target_path):
            try:
                current_mtime = os.path.getmtime(target_path)
            except Exception:
                current_mtime = 0
            if self.df is None or current_mtime != self.file_mtime or self.current_loaded_path != target_path:
                self.load_data(target_path)
        else:
            self.df = None
            self.file_mtime = 0
            self.current_loaded_path = None

    def load_data(self, file_path=None):
        target_path = file_path or self._find_best_candidate()
        if target_path and os.path.exists(target_path):
            try:
                if target_path.endswith('.csv'):
                    df = pd.read_csv(target_path)
                else:
                    df = pd.read_excel(target_path)
                self.df = self._clean_and_normalize(df)
                self.file_mtime = os.path.getmtime(target_path)
                self.current_loaded_path = target_path
                meta = self.get_draft_status()
                if meta.get('is_draft'):
                    self.last_sync_source = f"Draft Excel ({meta.get('filename')})"
                elif 'default_data' in target_path:
                    self.last_sync_source = "Bundled Standard Excel"
                return True, f"Successfully loaded {len(self.df)} records"
            except Exception as e:
                return False, f"Error loading data: {str(e)}"
        self.df = None
        self.file_mtime = 0
        self.current_loaded_path = None
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

            t_clean = tier_raw.lower().replace('-', ' ').strip()

            # 1. Exempted or Admin
            if 'exempted' in t_clean or 'exempted' in status_raw:
                return 'Exempted'
            if 'admin' in t_clean or 'admin' in status_raw:
                return 'Admin'
            if 'not created' in t_clean or 'not created' in status_raw:
                return 'DRP ID Not Created'

            # 2. Strict match with Spreadsheet/Excel 'Tier' column
            # If the sheet explicitly has Tier 1, Tier 2, Tier 3, Tier 4, respect it exactly!
            if 'tier 1' in t_clean or t_clean == 'tier1' or t_clean == 't1':
                return 'Tier 1'
            if 'tier 2' in t_clean or t_clean == 'tier2' or t_clean == 't2':
                return 'Tier 2'
            if 'tier 3' in t_clean or t_clean == 'tier3' or t_clean == 't3':
                return 'Tier 3'
            if 'tier 4' in t_clean or t_clean == 'tier4' or t_clean == 't4':
                return 'Tier 4'

            # 3. Only if Tier is blank, NaN, or unspecified in the sheet, calculate from score:
            if t_clean in ['nan', '', 'none', 'null', '0', 'tier 0', 'not specified']:
                if status_raw in ['nan', '', 'none'] or 'not created' in status_raw:
                    return 'DRP ID Not Created'
                if score >= 49:
                    return 'Tier 1'
                elif score >= 35:
                    return 'Tier 2'
                elif score >= 20:
                    return 'Tier 3'
                else:
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
                return gap, 'Tier 1 (49 pts)', f'Need {gap:.1f} more pts' if gap > 0 else 'Eligible for Tier 1'
            elif ntier == 'Tier 3':
                gap = max(0.0, 35.0 - score)
                return gap, 'Tier 2 (35 pts)', f'Need {gap:.1f} more pts' if gap > 0 else 'Eligible for Tier 2'
            elif ntier == 'Tier 4':
                gap = max(0.0, 20.0 - score)
                return gap, 'Tier 3 (20 pts)', f'Need {gap:.1f} more pts' if gap > 0 else 'Eligible for Tier 3'
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
        self.ensure_loaded()
        if self.df is None or len(self.df) == 0:
            return {
                'total_headcount': 0, 'active_tech_headcount': 0,
                'tier1_count': 0, 'tier1_pct': 0.0,
                'tier2_count': 0, 'tier2_pct': 0.0,
                'tier3_count': 0, 'tier3_pct': 0.0,
                'tier4_count': 0, 'tier4_pct': 0.0,
                'zero_score_count': 0, 'zero_score_pct': 0.0,
                'drp_not_created_count': 0, 'drp_not_created_pct': 0.0,
                'drp_created_count': 0, 'drp_created_pct': 0.0,
                'exempted_count': 0, 'avg_score': 0.0,
                'priority_t1_count': 0, 'priority_t2_count': 0,
                'priority_t3_count': 0, 'priority_t4_count': 0,
                'priority_zero_count': 0, 'priority_total_count': 0
            }
        
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

        # Sub-counts for 8 Google-priority products
        priority_names = [
            'BigQuery', 'Dataflow', 'Cloud SQL', 'Looker',
            'Dataproc', 'AlloyDB for PostgreSQL', 'Oracle', 'Spanner'
        ]
        p_cats = self.df['product'].apply(self.normalize_product_category)
        pdf = self.df[p_cats.isin(priority_names)]

        p_t1 = int((pdf['normalized_tier'] == 'Tier 1').sum())
        p_t2 = int((pdf['normalized_tier'] == 'Tier 2').sum())
        p_t3 = int((pdf['normalized_tier'] == 'Tier 3').sum())
        p_t4 = int(((pdf['normalized_tier'] == 'Tier 4') & (pdf['score'] > 0)).sum())
        p_zero = int((pdf['score'] == 0).sum())
        p_total = len(pdf)

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
            'avg_score': avg_score,
            'priority_t1_count': p_t1,
            'priority_t2_count': p_t2,
            'priority_t3_count': p_t3,
            'priority_t4_count': p_t4,
            'priority_zero_count': p_zero,
            'priority_total_count': p_total
        }

    def get_chart_data(self):
        self.ensure_loaded()
        if self.df is None or len(self.df) == 0:
            return {
                'cluster_dist': [],
                'product_items': [],
                'manager_leaderboard': [],
                'all_clusters': []
            }

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

    def get_priority_df(self):
        self.ensure_loaded()
        if self.df is None or len(self.df) == 0:
            return None
        priority_names = [
            'BigQuery', 'Dataflow', 'Cloud SQL', 'Looker',
            'Dataproc', 'AlloyDB for PostgreSQL', 'Oracle', 'Spanner'
        ]
        p_cats = self.df['product'].apply(self.normalize_product_category)
        return self.df[p_cats.isin(priority_names)].copy()

    def get_priority_kpis(self):
        pdf = self.get_priority_df()
        if pdf is None or len(pdf) == 0:
            return {
                'total_headcount': 0, 'active_tech_headcount': 0,
                'tier1_count': 0, 'tier1_pct': 0.0,
                'tier2_count': 0, 'tier2_pct': 0.0,
                'tier3_count': 0, 'tier3_pct': 0.0,
                'tier4_count': 0, 'tier4_pct': 0.0,
                'zero_score_count': 0, 'zero_score_pct': 0.0,
                'drp_not_created_count': 0, 'drp_not_created_pct': 0.0,
                'drp_created_count': 0, 'drp_created_pct': 0.0,
                'exempted_count': 0, 'avg_score': 0.0
            }
        
        total = len(pdf)
        counts = pdf['normalized_tier'].value_counts().to_dict()
        
        t1 = counts.get('Tier 1', 0)
        t2 = counts.get('Tier 2', 0)
        t3 = counts.get('Tier 3', 0)
        t4 = int(((pdf['normalized_tier'] == 'Tier 4') & (pdf['score'] > 0)).sum())
        zero_score = int((pdf['score'] == 0).sum())
        t0 = int(((pdf['drp_status'].str.lower().str.contains('not created')) | (pdf['drp_id'].isin(['None', '', 'nan']))).sum())
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

        active_scores = pdf[pdf['normalized_tier'].isin(['Tier 1', 'Tier 2', 'Tier 3', 'Tier 4'])]['score']
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

    def get_priority_chart_data(self):
        pdf = self.get_priority_df()
        if pdf is None or len(pdf) == 0:
            return {
                'cluster_dist': [],
                'product_items': [],
                'manager_leaderboard': [],
                'all_clusters': []
            }

        clusters = [c for c in pdf['cluster'].value_counts().index.tolist() if c and c != 'General']
        if not clusters:
            clusters = pdf['cluster'].value_counts().index.tolist()
        clusters = clusters[:10]

        cluster_tier_breakdown = []
        for c in clusters:
            cdf = pdf[pdf['cluster'] == c]
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

        prod_counts = pdf[pdf['product'] != 'Not Specified']['product'].value_counts().head(7)
        product_items = [{'name': k, 'count': int(v)} for k, v in prod_counts.items() if k]

        mgr_data = []
        for (mgr, clus), group in pdf.groupby(['manager', 'cluster']):
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
            'all_clusters': sorted(list(set(pdf['cluster'].dropna().tolist())))
        }

    def normalize_product_category(self, p_str):
        if not p_str or str(p_str).strip().lower() in ['not specified', 'nan', 'none', '']:
            return 'Not Specified'
        
        s = str(p_str).strip()
        s_low = s.lower()
        
        # Table A: 8 Priority Products
        if 'bigquery' in s_low:
            return 'BigQuery'
        if 'dataflow' in s_low:
            return 'Dataflow'
        if 'cloud sql' in s_low:
            return 'Cloud SQL'
        if 'looker' in s_low:
            return 'Looker'
        if 'dataproc' in s_low:
            return 'Dataproc'
        if 'alloydb' in s_low:
            return 'AlloyDB for PostgreSQL'
        if 'oracle' in s_low:
            return 'Oracle'
        if 'spanner' in s_low:
            return 'Spanner'
            
        # Table B: 17 Specified Products
        if 'threat intelligence' in s_low or s_low == 'gti':
            return 'Google Threat Intelligence'
        if 'security command center' in s_low or s_low == 'scc':
            return 'Security Command Center'
        if 'security operations' in s_low or 'secops' in s_low:
            return 'Security Operations'
        if 'cloud security' in s_low:
            return 'Cloud Security'
        if 'vmware engine' in s_low or 'gcve' in s_low:
            return 'Google Cloud VMware Engine'
        if 'sap on google' in s_low or s_low == 'sap':
            return 'SAP on Google Cloud'
        if 'distributed cloud' in s_low or 'gdc' in s_low:
            return 'Google Distributed Cloud'
        if 'compute engine' in s_low or 'gce' in s_low:
            return 'Google Compute Engine'
        if 'networking' in s_low:
            return 'Google Cloud Networking'
        if 'kubernetes' in s_low or 'gke' in s_low:
            return 'Google Kubernetes Engine'
        if 'apigee' in s_low:
            return 'Apigee API Management'
        if 'cloud run' in s_low:
            return 'Cloud Run'
        if 'gecx' in s_low or 'customer experience' in s_low:
            return 'Gemini Enterprise for Customer Experience'
        if 'agent platform' in s_low:
            return 'Gemini Enterprise Agent Platform'
        if 'ai applications' in s_low or 'ai apps' in s_low:
            return 'AI Applications'
        if 'gemini enterprise' in s_low:
            return 'Gemini Enterprise'
        if 'workspace' in s_low:
            return 'Workspace'
            
        return 'Other products'

    def get_product_tables(self):
        self.ensure_loaded()
        priority_names = [
            'BigQuery', 'Dataflow', 'Cloud SQL', 'Looker',
            'Dataproc', 'AlloyDB for PostgreSQL', 'Oracle', 'Spanner'
        ]

        other_named_names = [
            'Cloud Security',
            'Security Command Center',
            'Security Operations',
            'Google Threat Intelligence',
            'Google Compute Engine',
            'Google Cloud Networking',
            'SAP on Google Cloud',
            'Google Cloud VMware Engine',
            'Google Distributed Cloud',
            'Workspace',
            'Google Kubernetes Engine',
            'Apigee API Management',
            'Cloud Run',
            'Gemini Enterprise Agent Platform',
            'AI Applications',
            'Gemini Enterprise',
            'Gemini Enterprise for Customer Experience'
        ]

        if self.df is None or len(self.df) == 0:
            empty_gt = {'product': 'Grand Total', 't1': 0, 't2': 0, 't3': 0, 't4': 0, 'total': 0}
            rows_a = [{'product': p, 't1': 0, 't2': 0, 't3': 0, 't4': 0, 'total': 0} for p in priority_names]
            rows_b = [{'product': p, 't1': 0, 't2': 0, 't3': 0, 't4': 0, 'total': 0} for p in other_named_names + ['Other products']]
            return {
                'table_a': {'rows': rows_a, 'grand_total': empty_gt},
                'table_b': {'rows': rows_b, 'grand_total': empty_gt}
            }

        df_prod = self.df.copy()
        df_prod['cat'] = df_prod['product'].apply(self.normalize_product_category)

        def compute_row(p_label, matching_mask):
            m_df = df_prod[matching_mask]
            t1 = int((m_df['normalized_tier'] == 'Tier 1').sum())
            t2 = int((m_df['normalized_tier'] == 'Tier 2').sum())
            t3 = int((m_df['normalized_tier'] == 'Tier 3').sum())
            t4 = int((m_df['normalized_tier'] == 'Tier 4').sum())
            total = t1 + t2 + t3 + t4
            return {
                'product': p_label,
                't1': t1,
                't2': t2,
                't3': t3,
                't4': t4,
                'total': total
            }

        # Table A
        table_a_rows = []
        for pname in priority_names:
            mask = df_prod['cat'] == pname
            table_a_rows.append(compute_row(pname, mask))

        a_gt = {
            'product': 'Grand Total',
            't1': sum(r['t1'] for r in table_a_rows),
            't2': sum(r['t2'] for r in table_a_rows),
            't3': sum(r['t3'] for r in table_a_rows),
            't4': sum(r['t4'] for r in table_a_rows),
            'total': sum(r['total'] for r in table_a_rows)
        }

        # Table B
        table_b_rows = []
        for pname in other_named_names:
            mask = df_prod['cat'] == pname
            table_b_rows.append(compute_row(pname, mask))

        other_mask = df_prod['cat'] == 'Other products'
        table_b_rows.append(compute_row('Other products', other_mask))

        b_gt = {
            'product': 'Grand Total',
            't1': sum(r['t1'] for r in table_b_rows),
            't2': sum(r['t2'] for r in table_b_rows),
            't3': sum(r['t3'] for r in table_b_rows),
            't4': sum(r['t4'] for r in table_b_rows),
            'total': sum(r['total'] for r in table_b_rows)
        }

        return {
            'table_a': {'rows': table_a_rows, 'grand_total': a_gt},
            'table_b': {'rows': table_b_rows, 'grand_total': b_gt}
        }

    def get_user_scope(self, verified_email, role='user'):
        """
        Determines the accessible employee scope for a user based on their verified email.
        - Owner/Editor/Leader: full access across all employees.
        - Regular verified user: their own record + direct reports where they are manager.
        """
        self.ensure_loaded()
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
        self.ensure_loaded()
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
        self.ensure_loaded()
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
        self.ensure_loaded()
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
