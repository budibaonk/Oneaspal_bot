import streamlit as st
import pandas as pd
import time
import json
import os
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client
from dotenv import load_dotenv

# --- 1. KONFIGURASI HALAMAN (ULTRA WIDE & DARK) ---
st.set_page_config(
    page_title="One Aspal Command",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- 2. CSS MASTER (SLEEK CYBERPUNK - NORMAL FONT SIZE) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Orbitron:wght@500;700&display=swap');

    .stApp { background-color: #0e1117; font-family: 'Inter', sans-serif; font-size: 14px; }
    
    h1 { font-family: 'Orbitron', sans-serif !important; color: #ffffff; font-size: 1.8rem !important; letter-spacing: 1px; }
    h2 { font-family: 'Orbitron', sans-serif !important; color: #ffffff; font-size: 1.4rem !important; }
    h3 { font-family: 'Orbitron', sans-serif !important; color: #ffffff; font-size: 1.1rem !important; }
    
    div[data-testid="metric-container"] {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 10px;
        padding: 15px;
        backdrop-filter: blur(10px);
        transition: border-color 0.3s;
    }
    div[data-testid="metric-container"]:hover { border-color: #00f2ff; }
    div[data-testid="metric-container"] label { font-size: 0.8rem !important; color: #888 !important; }
    div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
        color: #00f2ff !important; 
        font-family: 'Orbitron', sans-serif; 
        font-size: 1.5rem !important;
    }

    .stButton>button {
        background: linear-gradient(90deg, #0061ff 0%, #60efff 100%);
        color: #000; border: none; border-radius: 6px; height: 40px;
        font-weight: 700; font-family: 'Orbitron', sans-serif; font-size: 0.9rem;
        letter-spacing: 0.5px; width: 100%;
    }
    .stButton>button:hover { box-shadow: 0 0 15px rgba(0, 242, 255, 0.4); color: #000; }

    .leaderboard-row {
        background: rgba(0, 242, 255, 0.03);
        padding: 10px 15px; margin-bottom: 5px; border-radius: 6px;
        border-left: 3px solid #00f2ff; display: flex; justify-content: space-between; align-items: center;
        transition: background 0.2s;
    }
    .leaderboard-row:hover { background: rgba(0, 242, 255, 0.08); }
    .leaderboard-val { font-family: 'Orbitron'; color: #00f2ff; font-weight: bold; font-size: 1rem; }
    .leaderboard-rank { font-size: 1.1rem; margin-right: 15px; font-weight:bold; color: #fff; width: 25px;}

    .tech-box { 
        background: rgba(0, 242, 255, 0.05); 
        border-left: 3px solid #00f2ff; 
        padding: 12px; border-radius: 5px; 
        margin-bottom: 15px; color: #ddd; 
        font-size: 0.9rem;
    }
    
    .stTabs [data-baseweb="tab"] { height: 40px; padding: 0 20px; font-size: 0.9rem; }
    
    header {visibility: hidden;} footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- 3. KONEKSI & SETUP ---
load_dotenv()
URL = os.getenv("SUPABASE_URL")
KEY = os.getenv("SUPABASE_KEY")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

@st.cache_resource
def init_connection():
    try: return create_client(URL, KEY)
    except: return None

supabase = init_connection()

if 'authenticated' not in st.session_state: st.session_state['authenticated'] = False
if 'upload_success' not in st.session_state: st.session_state['upload_success'] = False
if 'delete_success' not in st.session_state: st.session_state['delete_success'] = False
if 'last_stats' not in st.session_state: st.session_state['last_stats'] = {}
if 'uploader_key' not in st.session_state: st.session_state['uploader_key'] = 0

# --- DATABASE OPS ---
def get_total_asset_count():
    try: return supabase.table('kendaraan').select('*', count='exact', head=True).execute().count
    except: return 0

def get_all_users():
    try:
        res = supabase.table('users').select('*').execute()
        df = pd.DataFrame(res.data)
        if not df.empty: df['user_id'] = df['user_id'].astype(str) 
        return df
    except: return pd.DataFrame()

def get_hit_counts():
    try:
        res = supabase.table('finding_logs').select('user_id').execute()
        df_logs = pd.DataFrame(res.data)
        if df_logs.empty: return pd.Series()
        df_logs['user_id'] = df_logs['user_id'].astype(str)
        return df_logs['user_id'].value_counts()
    except: return pd.Series()

def get_active_hunters_30m():
    try:
        now = datetime.now(timezone.utc)
        time_threshold = now - timedelta(minutes=30)
        res = supabase.table('finding_logs').select('user_id').gte('created_at', time_threshold.isoformat()).execute()
        df = pd.DataFrame(res.data)
        if df.empty: return 0
        return df['user_id'].nunique()
    except: return 0

def update_user_status(user_id, status):
    try: supabase.table('users').update({'status': status}).eq('user_id', user_id).execute(); return True
    except: return False

def add_user_quota(user_id, days):
    try:
        res = supabase.table('users').select('expiry_date').eq('user_id', user_id).execute()
        current_exp_str = res.data[0].get('expiry_date') if res.data else None
        now = datetime.utcnow()
        base_date = datetime.fromisoformat(current_exp_str.replace('Z', '')) if (current_exp_str and datetime.fromisoformat(current_exp_str.replace('Z', '')) > now) else now
        new_exp = base_date + timedelta(days=days)
        supabase.table('users').update({'expiry_date': new_exp.isoformat()}).eq('user_id', user_id).execute()
        return True
    except: return False

def delete_user_permanent(user_id):
    try: supabase.table('users').delete().eq('user_id', user_id).execute(); return True
    except: return False

# --- KAMUS KOLOM (LENGKAP) ---
COLUMN_ALIASES = {
    'nopol': ['nopolisi', 'nomorpolisi', 'nopol', 'noplat', 'tnkb', 'licenseplate', 'plat', 'police_no', 'no polisi', 'plate_number', 'platenumber', 'plate_no'],
    'type': ['type', 'tipe', 'unit', 'model', 'vehicle', 'jenis', 'deskripsiunit', 'merk', 'object', 'kendaraan', 'item', 'brand', 'tipeunit'],
    'tahun': ['tahun', 'year', 'thn', 'rakitan', 'th', 'yearofmanufacture'],
    'warna': ['warna', 'color', 'colour', 'cat'],
    'noka': ['noka', 'norangka', 'nomorrangka', 'chassis', 'chasis', 'vin', 'rangka', 'no rangka', 'chassis_number'],
    'nosin': ['nosin', 'nomesin', 'nomormesin', 'engine', 'mesin', 'no mesin', 'engine_number'],
    'finance': ['finance', 'leasing', 'lising', 'multifinance', 'mitra', 'principal', 'client'],
    'ovd': ['ovd', 'overdue', 'dpd', 'keterlambatan', 'odh', 'hari', 'telat', 'aging', 'days_overdue', 'lates', 'over_due', 'od'],
    'branch': ['branch', 'area', 'kota', 'pos', 'cabang', 'lokasi', 'wilayah']
}

def normalize_text(text): return ''.join(e for e in str(text) if e.isalnum()).lower()

def smart_rename_columns(df):
    new = {}
    df.columns = [str(c).strip().replace('"', '').replace("'", "").replace('\ufeff', '') for c in df.columns]
    for col in df.columns:
        clean = normalize_text(col)
        renamed = False
        for std, aliases in COLUMN_ALIASES.items():
            aliases_clean = [normalize_text(a) for a in aliases]
            if clean == std or clean in aliases_clean:
                new[col] = std; renamed = True; break
        if not renamed: new[col] = col
    df.rename(columns=new, inplace=True)
    return df, df.columns

def standardize_leasing_name(name):
    clean = str(name).upper().strip().replace('"', '').replace("'", "")
    return "UNKNOWN" if clean in ['NAN', 'NULL', ''] else clean

def render_logo(width=150):
    if os.path.exists("logo.png"): st.image("logo.png", width=width)
    else: st.markdown("<h1>🦅</h1>", unsafe_allow_html=True)

# --- 4. HALAMAN LOGIN ---
def check_password():
    if st.session_state['password_input'] == ADMIN_PASSWORD:
        st.session_state['authenticated'] = True; del st.session_state['password_input']
    else: st.error("⛔ ACCESS DENIED")

if not st.session_state['authenticated']:
    col_ctr = st.columns([1, 8, 1])[1]
    with col_ctr:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        with st.container():
            c_img = st.columns([1,1,1])[1]
            with c_img: render_logo(width=200) 
            st.markdown("<h2 style='text-align: center; color: #00f2ff; margin-bottom: 5px;'>SYSTEM LOGIN</h2>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: #888; font-size: 0.9rem;'>ONE ASPAL COMMANDO v7.5</p>", unsafe_allow_html=True)
            st.text_input("PASSPHRASE", type="password", key="password_input", on_change=check_password, label_visibility="collapsed")
            if not ADMIN_PASSWORD: st.warning("⚠️ ENV NOT CONFIGURED")
    st.stop()

# --- 5. DASHBOARD UTAMA ---
with st.sidebar:
    render_logo(width=220) 
    st.markdown("### OPERATIONS")
    if st.button("🔄 REFRESH"): st.cache_data.clear(); st.rerun()
    if st.button("🚪 LOGOUT"): st.session_state['authenticated'] = False; st.rerun()
    st.markdown("---"); st.caption("STATUS: ONLINE 🟢")

c1, c2 = st.columns([1, 10])
with c1: render_logo(width=80) 
with c2: 
    st.markdown("<h2 style='margin-bottom:0;'>ONE ASPAL COMMANDO</h2>", unsafe_allow_html=True)
    st.markdown("<span style='color: #00f2ff; font-family: Orbitron; font-size: 0.8rem;'>⚡ LIVE INTELLIGENCE SYSTEM</span>", unsafe_allow_html=True)
st.markdown("---")

# --- DATA FETCHING ---
df_users_raw = get_all_users()
total_assets = get_total_asset_count()
hit_counts_series = get_hit_counts() 
active_hunters = get_active_hunters_30m()

# --- HITUNG METRIK UTAMA ---
mitra_total = 0
pic_total = 0
total_active_accounts = 0

if not df_users_raw.empty:
    mitra_total = len(df_users_raw[df_users_raw['role']!='pic'])
    pic_total = len(df_users_raw[df_users_raw['role']=='pic'])
    
    # [LOGIC BARU] Active = Status Active AND Quota > 0
    # Kita pastikan kolom quota dibaca sebagai angka, isi NaN dengan 0
    if 'quota' in df_users_raw.columns:
        df_users_raw['quota'] = pd.to_numeric(df_users_raw['quota'], errors='coerce').fillna(0)
    else:
        df_users_raw['quota'] = 0 # Jaga-jaga jika kolom tidak ada
        
    total_active_accounts = len(df_users_raw[
        (df_users_raw['status'] == 'active') & 
        (df_users_raw['quota'] > 0)
    ])

# --- METRICS (5 KOLOM RAPI) ---
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("ASSETS", f"{total_assets:,}", "DATABASE")
m2.metric("LIVE USERS", f"{active_hunters}", "30 MINS ACTIVE") 
m3.metric("TOTAL MITRA", f"{mitra_total}", "REGISTERED")
m4.metric("TOTAL PIC", f"{pic_total}", "LEASING HQ")
m5.metric("READY FOR DUTY", f"{total_active_accounts}", "ACTIVE & QUOTA > 0") # Updated Label
st.write("")

tab1, tab2, tab3, tab4 = st.tabs(["🏆 LEADERBOARD", "🛡️ PERSONIL", "📤 UPLOAD", "🗑️ HAPUS"])

# --- TAB 1: LEADERBOARD (TOP 10 ONLY) ---
with tab1:
    st.markdown("### 🏆 TOP 10 RANGERS (HIT COUNT)")
    if df_users_raw.empty or hit_counts_series.empty:
        st.info("NO DATA AVAILABLE YET.")
    else:
        df_rank = df_users_raw.copy()
        df_rank['real_hits'] = df_rank['user_id'].map(hit_counts_series).fillna(0).astype(int)
        df_rank = df_rank[df_rank['role'] != 'pic'].sort_values(by='real_hits', ascending=False).head(10)
        
        rank = 1
        for idx, row in df_rank.iterrows():
            medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"#{rank}"
            color = "#ffd700" if rank == 1 else "#c0c0c0" if rank == 2 else "#cd7f32" if rank == 3 else "#fff"
            st.markdown(f"""
            <div class="leaderboard-row">
                <div style="display:flex; align-items:center;">
                    <div class="leaderboard-rank" style="color:{color};">{medal}</div>
                    <div>
                        <div style="font-weight:bold; color:white; font-size:1rem;">{row['nama_lengkap']}</div>
                        <div style="font-size:0.8rem; color:#aaa;">AGENCY: {row['agency']}</div>
                    </div>
                </div>
                <div class="leaderboard-val">{row['real_hits']} HITS</div>
            </div>
            """, unsafe_allow_html=True)
            rank += 1

# --- TAB 2: PERSONIL ---
with tab2:
    if df_users_raw.empty: st.warning("NO USER DATA.")
    else:
        col_ka, col_ki = st.columns([1,3])
        with col_ka:
            type_choice = st.radio("DIVISION", ["🛡️ MATEL", "🏦 PIC"], horizontal=True, label_visibility="collapsed")
        
        target = df_users_raw[df_users_raw['role'] != 'pic'] if "MATEL" in type_choice else df_users_raw[df_users_raw['role'] == 'pic']
        target = target.sort_values('nama_lengkap')
        
        user_opts = {f"{r['nama_lengkap']} | {r['agency']}": r['user_id'] for i, r in target.iterrows()}
        sel = st.selectbox("SELECT AGENT", list(user_opts.keys()), label_visibility="collapsed")
        
        if sel:
            uid = user_opts[sel]; user = target[target['user_id'] == uid].iloc[0]
            real_hits = hit_counts_series.get(uid, 0)
            
            # INFO BOX COMPACT
            st.markdown(f"""
            <div class="tech-box">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <h3 style="margin:0; color:white; font-size:1.2rem;">{user['nama_lengkap']}</h3>
                    <span style="color:#00f2ff; font-weight:bold;">{user['agency']}</span>
                </div>
                <hr style="border-color: rgba(255,255,255,0.1); margin: 10px 0;">
                <div style="display:grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap:10px; font-size:0.85rem;">
                    <div>STATUS: <b style="color:{'#0f0' if user['status']=='active' else '#f00'}">{user['status'].upper()}</b></div>
                    <div>EXP: <b>{str(user.get('expiry_date','-'))[:10]}</b></div>
                    <div>QUOTA: <b>{user.get('quota', 0):,}</b></div>
                    <div>HITS: <b style="color:#00f2ff;">{real_hits}</b></div>
                </div>
            </div>""", unsafe_allow_html=True)
            
            c_in, c_btn = st.columns([1, 2])
            with c_in: days = st.number_input("DAYS", 1, 30, label_visibility="collapsed")
            with c_btn: 
                if st.button(f"➕ EXTEND ({days} DAYS)"): 
                    if add_user_quota(uid, days): st.success("EXTENDED."); time.sleep(1); st.rerun()
            st.divider()
            b1, b2 = st.columns(2)
            with b1:
                if user['status'] == 'active':
                    if st.button("⛔ FREEZE ACCOUNT"): update_user_status(uid, 'banned'); st.rerun()
                else:
                    if st.button("✅ ACTIVATE ACCOUNT"): update_user_status(uid, 'active'); st.rerun()
            with b2:
                if st.button("🗑️ DELETE USER"): delete_user_permanent(uid); st.rerun()

# --- TAB 3: UPLOAD ---
with tab3:
    st.markdown("### 📤 UPLOAD DATA")
    if st.session_state['upload_success']:
        st.markdown(f"""<div class="tech-box" style="border-color:#00ff00;">✅ COMPLETE: {st.session_state['last_stats'].get('suc',0):,} UNITS</div>""", unsafe_allow_html=True)
        if st.button("UPLOAD MORE"): st.session_state['upload_success'] = False; st.rerun()
    else:
        up_file = st.file_uploader("DROP FILE", type=['xlsx','csv','txt'], key=f"up_{st.session_state['uploader_key']}")
        if up_file and st.button("🚀 INITIATE UPLOAD"):
            try:
                fname = up_file.name.lower()
                if fname.endswith('.txt'): df = pd.read_csv(up_file, sep='\t', dtype=str, on_bad_lines='skip')
                elif fname.endswith('.csv'): 
                    try: df = pd.read_csv(up_file, sep=';', dtype=str, on_bad_lines='skip')
                    except: df = pd.read_csv(up_file, sep=',', dtype=str, on_bad_lines='skip')
                else: df = pd.read_excel(up_file, dtype=str)
                
                df, _ = smart_rename_columns(df)
                if 'nopol' not in df.columns: st.error("CRITICAL: NOPOL MISSING"); st.stop()
                
                valid_cols = ['nopol', 'type', 'finance', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'branch']
                for c in valid_cols:
                    if c not in df.columns: df[c] = "-"
                    else: df[c] = df[c].fillna("-").replace(['nan','NaN','NULL',''], '-')
                
                df['nopol'] = df['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
                df = df.drop_duplicates(subset=['nopol'], keep='last')
                df['finance'] = df['finance'].apply(standardize_leasing_name)
                
                records = json.loads(json.dumps(df[valid_cols].to_dict(orient='records'), default=str))
                prog = st.progress(0); total = len(records); suc = 0
                for i in range(0, total, 1000):
                    batch = records[i:i+1000]
                    try: supabase.table('kendaraan').upsert(batch, on_conflict='nopol', count=None).execute(); suc += len(batch)
                    except: pass
                    prog.progress(min((i+1000)/total, 1.0))
                
                st.session_state['last_stats'] = {'suc': suc}
                st.session_state['upload_success'] = True; st.rerun()
            except Exception as e: st.error(f"SYSTEM ERROR: {e}")

# --- TAB 4: HAPUS ---
with tab4:
    st.markdown("### 🗑️ DELETE DATA")
    if st.session_state['delete_success']:
        st.success("✅ DATA ELIMINATED.")
        if st.button("RETURN"): st.session_state['delete_success'] = False; st.rerun()
    else:
        del_file = st.file_uploader("TARGET LIST (NOPOL)", type=['xlsx','csv','txt'], key="del_up")
        if del_file and st.button("🔥 EXECUTE DELETE"):
            try:
                fname = del_file.name.lower()
                if fname.endswith('.txt'): df_del = pd.read_csv(del_file, sep='\t', dtype=str, on_bad_lines='skip')
                elif fname.endswith('.csv'): 
                    try: df_del = pd.read_csv(del_file, sep=';', dtype=str, on_bad_lines='skip')
                    except: df_del = pd.read_csv(del_file, sep=',', dtype=str, on_bad_lines='skip')
                else: df_del = pd.read_excel(del_file, dtype=str)
                
                df_del, _ = smart_rename_columns(df_del)
                if 'nopol' not in df_del.columns: st.error("NOPOL NOT FOUND"); st.stop()
                
                targets = list(set(df_del['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper().tolist()))
                prog = st.progress(0); total = len(targets)
                for i in range(0, total, 200):
                    batch = targets[i:i+200]
                    try: supabase.table('kendaraan').delete().in_('nopol', batch).execute()
                    except: pass
                    prog.progress(min((i+200)/total, 1.0))
                st.session_state['delete_success'] = True; st.rerun()
            except Exception as e: st.error(f"ERROR: {e}")