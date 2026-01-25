import streamlit as st
import pandas as pd
import time
import json
import os
import base64
import re
import numpy as np
import io
import zipfile
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client
from dotenv import load_dotenv

# ##############################################################################
# BAGIAN 1: KONFIGURASI HALAMAN & THEME
# ##############################################################################
st.set_page_config(
    page_title="One Aspal Command",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- CSS MASTER: CYBER-TECH UI ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Orbitron:wght@500;700;900&display=swap');

    .stApp { background-color: #0e1117; font-family: 'Inter', sans-serif; font-size: 14px; }
    
    h1 { font-family: 'Orbitron', sans-serif !important; color: #ffffff; font-size: 1.8rem !important; letter-spacing: 1px; }
    h2 { font-family: 'Orbitron', sans-serif !important; color: #ffffff; font-size: 1.4rem !important; }
    h3 { font-family: 'Orbitron', sans-serif !important; color: #ffffff; font-size: 1.1rem !important; }
    
    /* GLASS MORPHISM METRIC CARDS */
    div[data-testid="metric-container"] {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 10px;
        padding: 15px;
        backdrop-filter: blur(10px);
        transition: border-color 0.3s, transform 0.2s;
    }
    div[data-testid="metric-container"]:hover { border-color: #00f2ff; transform: translateY(-2px); }
    div[data-testid="metric-container"] label { font-size: 0.8rem !important; color: #888 !important; }
    div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
        color: #00f2ff !important; font-family: 'Orbitron', sans-serif; font-size: 1.5rem !important;
    }

    /* NEON BUTTONS */
    .stButton>button {
        background: linear-gradient(90deg, #0061ff 0%, #60efff 100%);
        color: #000; border: none; border-radius: 6px; height: 40px;
        font-weight: 700; font-family: 'Orbitron', sans-serif; font-size: 0.9rem;
        letter-spacing: 0.5px; width: 100%; transition: all 0.3s;
    }
    .stButton>button:hover { box-shadow: 0 0 15px rgba(0, 242, 255, 0.4); transform: scale(1.02); color: #000; }

    /* LEADERBOARD TABLE */
    .leaderboard-row {
        background: rgba(0, 242, 255, 0.03);
        padding: 12px 15px; margin-bottom: 6px; border-radius: 6px;
        border-left: 3px solid #00f2ff; display: flex; justify-content: space-between; align-items: center;
    }
    .leaderboard-val { font-family: 'Orbitron'; color: #00f2ff; font-weight: bold; font-size: 1rem; }
    
    /* TECH BOX INFO */
    .tech-box { 
        background: rgba(0, 242, 255, 0.05); 
        border-left: 3px solid #00f2ff; 
        padding: 15px; border-radius: 5px; 
        margin-bottom: 15px; color: #ddd; 
    }
    
    /* TAB STYLING */
    .stTabs [data-baseweb="tab"] { height: 45px; padding: 0 25px; font-family: 'Orbitron'; font-size: 0.85rem; }
    
    header {visibility: hidden;} footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ##############################################################################
# BAGIAN 2: KONEKSI & DATABASE LOGIC
# ##############################################################################
load_dotenv()
URL = os.getenv("SUPABASE_URL")
KEY = os.getenv("SUPABASE_KEY")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

@st.cache_resource
def init_connection():
    try: return create_client(URL, KEY)
    except: return None

supabase = init_connection()

# --- INITIALIZE SESSION STATES ---
if 'authenticated' not in st.session_state: st.session_state['authenticated'] = False
if 'upload_stage' not in st.session_state: st.session_state['upload_stage'] = 'idle'
if 'upload_data_cache' not in st.session_state: st.session_state['upload_data_cache'] = None
if 'upload_found_cols' not in st.session_state: st.session_state['upload_found_cols'] = []
if 'delete_success' not in st.session_state: st.session_state['delete_success'] = False

# --- DATABASE OPERATIONS ---
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
        time_threshold = datetime.now(timezone.utc) - timedelta(minutes=30)
        res = supabase.table('finding_logs').select('user_id').gte('created_at', time_threshold.isoformat()).execute()
        df = pd.DataFrame(res.data)
        return df['user_id'].nunique() if not df.empty else 0
    except: return 0

def update_user_status(user_id, status):
    try: supabase.table('users').update({'status': status}).eq('user_id', user_id).execute(); return True
    except: return False

def add_user_quota(user_id, days):
    try:
        res = supabase.table('users').select('expiry_date').eq('user_id', user_id).execute()
        now = datetime.utcnow()
        if res.data and res.data[0]['expiry_date']:
            current_exp = datetime.fromisoformat(res.data[0]['expiry_date'].replace('Z', ''))
            base_date = current_exp if current_exp > now else now
        else: base_date = now
        new_exp = base_date + timedelta(days=days)
        supabase.table('users').update({'expiry_date': new_exp.isoformat()}).eq('user_id', user_id).execute()
        return True
    except: return False

def delete_user_permanent(user_id):
    try: supabase.table('users').delete().eq('user_id', user_id).execute(); return True
    except: return False

# ##############################################################################
# BAGIAN 3: UTILITIES (KAMUS & FILE ENGINE)
# ##############################################################################
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
    found = []
    df.columns = [str(c).strip().replace('"', '').replace("'", "").replace('\ufeff', '') for c in df.columns]
    
    for col in df.columns:
        clean = normalize_text(col)
        renamed = False
        for std, aliases in COLUMN_ALIASES.items():
            aliases_clean = [normalize_text(a) for a in aliases]
            if clean == std or clean in aliases_clean:
                # ANTI-DUPLICATE: Jangan biarkan ada 2 kolom nopol/finance
                if std not in new.values():
                    new[col] = std
                    found.append(std)
                renamed = True; break
        if not renamed: new[col] = col
    
    df.rename(columns=new, inplace=True)
    df = df.loc[:, ~df.columns.duplicated()] # Pastikan tidak ada kolom kembar
    return df, found

def standardize_leasing_name(name):
    clean = str(name).upper().strip().replace('"', '').replace("'", "")
    return "UNKNOWN" if clean in ['NAN', 'NULL', ''] else clean

def read_file_robust(uploaded_file):
    fname = uploaded_file.name.lower()
    content = uploaded_file.getvalue()
    if fname.endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            v = [x for x in z.namelist() if x.endswith(('.csv','.xlsx','.xls','.txt'))]
            if v: content = z.read(v[0]); fname = v[0].lower(); uploaded_file = io.BytesIO(content)
    try:
        if fname.endswith(('.xlsx', '.xls')): return pd.read_excel(uploaded_file, dtype=str)
        else:
            try: return pd.read_csv(uploaded_file, sep=';', dtype=str, on_bad_lines='skip')
            except: return pd.read_csv(uploaded_file, sep=',', dtype=str, on_bad_lines='skip')
    except: return pd.DataFrame()

def get_img_as_base64(file):
    with open(file, "rb") as f: return base64.b64encode(f.read()).decode()

def render_logo(width=150):
    if os.path.exists("logo.png"): st.image("logo.png", width=width)
    else: st.markdown("<h1>🦅</h1>", unsafe_allow_html=True)

# ##############################################################################
# BAGIAN 4: LOGIN PAGE (PRECISION CENTER)
# ##############################################################################
if not st.session_state['authenticated']:
    col_l1, col_l2, col_l3 = st.columns([1, 6, 1])
    with col_l2:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        if os.path.exists("logo.png"):
            b64 = get_img_as_base64("logo.png")
            st.markdown(f'<div style="display:flex;justify-content:center;margin-bottom:20px;"><img src="data:image/png;base64,{b64}" width="200" style="border-radius:10px;"></div>', unsafe_allow_html=True)
        st.markdown("<h2 style='text-align:center;color:#00f2ff;margin-bottom:5px;'>SYSTEM LOGIN</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center;color:#888;font-size:0.9rem;margin-bottom:20px;'>ONE ASPAL COMMANDO v7.9</p>", unsafe_allow_html=True)
        pwd_input = st.text_input("PASSPHRASE", type="password", label_visibility="collapsed")
        if pwd_input == ADMIN_PASSWORD:
            st.session_state['authenticated'] = True; st.rerun()
        elif pwd_input: st.error("⛔ ACCESS DENIED")
    st.stop()

# ##############################################################################
# BAGIAN 5: DASHBOARD UTAMA & METRICS
# ##############################################################################
with st.sidebar:
    render_logo(width=220)
    st.markdown("### OPERATIONS")
    if st.button("🔄 REFRESH SYSTEM"): st.cache_data.clear(); st.rerun()
    if st.button("🚪 LOGOUT SESSION"): st.session_state['authenticated'] = False; st.rerun()
    st.markdown("---")
    st.caption("ONE ASPAL SYSTEM\nStatus: ONLINE 🟢")

# --- HEADER ---
c_h1, c_h2 = st.columns([1, 10])
with c_h1: render_logo(width=80)
with c_h2:
    st.markdown("<h2 style='margin-bottom:0;'>ONE ASPAL COMMANDO</h2>", unsafe_allow_html=True)
    st.markdown("<span style='color: #00f2ff; font-family: Orbitron; font-size: 0.8rem;'>⚡ LIVE INTELLIGENCE SYSTEM</span>", unsafe_allow_html=True)
st.markdown("---")

# --- FETCH GLOBAL DATA ---
df_users = get_all_users()
total_assets = get_total_asset_count()
hit_counts = get_hit_counts()
active_hunters = get_active_hunters_30m()

# --- CALCULATE METRICS ---
mitra_total = 0; pic_total = 0; ready_count = 0
if not df_users.empty:
    mitra_total = len(df_users[df_users['role'] != 'pic'])
    pic_total = len(df_users[df_users['role'] == 'pic'])
    if 'quota' in df_users.columns:
        df_users['quota'] = pd.to_numeric(df_users['quota'], errors='coerce').fillna(0)
    else: df_users['quota'] = 0
    ready_count = len(df_users[(df_users['status'] == 'active') & (df_users['quota'] > 0)])

# --- METRIC GRID ---
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("ASSETS", f"{total_assets:,}", "DATABASE")
m2.metric("LIVE USERS", f"{active_hunters}", "30M ACTIVE")
m3.metric("TOTAL MITRA", f"{mitra_total}", "REGISTERED")
m4.metric("TOTAL PIC", f"{pic_total}", "LEASING HQ")
m5.metric("READY FOR DUTY", f"{ready_count}", "ACTIVE & QUOTA>0")
st.write("")

# ##############################################################################
# BAGIAN 6: TAB FEATURES
# ##############################################################################
tab1, tab2, tab3, tab4 = st.tabs(["🏆 LEADERBOARD", "🛡️ PERSONIL", "📤 UPLOAD", "🗑️ HAPUS"])

# --- TAB 1: LEADERBOARD (TOP 10) ---
with tab1:
    st.markdown("### 🏆 TOP 10 RANGERS (HIT COUNT)")
    if df_users.empty or hit_counts.empty: st.info("NO DATA AVAILABLE YET.")
    else:
        df_rank = df_users.copy()
        df_rank['real_hits'] = df_rank['user_id'].map(hit_counts).fillna(0).astype(int)
        df_rank = df_rank[df_rank['role'] != 'pic'].sort_values(by='real_hits', ascending=False).head(10)
        for i, row in enumerate(df_rank.iterrows(), 1):
            r = row[1]
            st.markdown(f"""
            <div class="leaderboard-row">
                <div><b>#{i} {r['nama_lengkap']}</b><br><small style="color:#888;">{r['agency']}</small></div>
                <div class="leaderboard-val">{r['real_hits']} HITS</div>
            </div>""", unsafe_allow_html=True)

# --- TAB 2: PERSONIL (DETAILED MANAGEMENT) ---
with tab2:
    if df_users.empty: st.warning("NO USER DATA.")
    else:
        c_div, c_blank = st.columns([1, 2])
        with c_div: div_choice = st.radio("SELECT DIVISION", ["🛡️ MATEL", "🏦 PIC"], horizontal=True, label_visibility="collapsed")
        
        target = df_users[df_users['role'] != 'pic'] if "MATEL" in div_choice else df_users[df_users['role'] == 'pic']
        target = target.sort_values('nama_lengkap')
        
        user_list = [f"{r['nama_lengkap']} | {r['agency']}" for i, r in target.iterrows()]
        sel_name = st.selectbox("SEARCH AGENT", user_list, label_visibility="collapsed")
        
        if sel_name:
            uid = target[target['nama_lengkap'] == sel_name.split(' | ')[0]].iloc[0]['user_id']
            u = target[target['user_id'] == uid].iloc[0]
            real_hits = hit_counts.get(uid, 0)
            
            st.markdown(f"""
            <div class="tech-box">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <h3 style="margin:0;">{u['nama_lengkap']}</h3>
                    <span style="color:#00f2ff; font-weight:bold;">{u['agency']}</span>
                </div>
                <hr style="border-color:rgba(255,255,255,0.1); margin:12px 0;">
                <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:15px; font-size:0.85rem;">
                    <div>STATUS: <b style="color:{'#0f0' if u['status']=='active' else '#f00'}">{u['status'].upper()}</b></div>
                    <div>EXP: <b>{str(u['expiry_date'])[:10]}</b></div>
                    <div>QUOTA: <b>{u['quota']:,}</b></div>
                    <div>TOTAL HITS: <b style="color:#00f2ff;">{real_hits}</b></div>
                </div>
            </div>""", unsafe_allow_html=True)
            
            c_days, c_ext = st.columns([1, 2])
            with c_days: days = st.number_input("DAYS", 1, 30, 30, label_visibility="collapsed")
            with c_ext:
                if st.button(f"➕ EXTEND ACCESS (+{days} DAYS)"):
                    if add_user_quota(uid, days): st.success("OK"); time.sleep(1); st.rerun()
            
            st.divider()
            b_ban, b_del = st.columns(2)
            with b_ban:
                if st.button("⛔ FREEZE ACCOUNT" if u['status']=='active' else "✅ ACTIVATE ACCOUNT"):
                    update_user_status(uid, 'banned' if u['status']=='active' else 'active'); st.rerun()
            with b_del:
                if st.button("🗑️ PERMANENT DELETE"): delete_user_permanent(uid); st.rerun()

# --- TAB 3: UPLOAD (INTELLIGENCE FLOW) ---
with tab3:
    st.markdown("### 📤 UPLOAD INTELLIGENCE")
    
    if st.session_state['upload_stage'] == 'idle':
        up_file = st.file_uploader("DROP INTELLIGENCE FILE", type=['xlsx','csv','txt','zip'], label_visibility="collapsed")
        if up_file and st.button("🔍 ANALISA FILE"):
            df_raw = read_file_robust(up_file)
            if not df_raw.empty:
                df_renamed, found_cols = smart_rename_columns(df_raw)
                if 'nopol' in df_renamed.columns:
                    st.session_state['upload_data_cache'] = df_renamed
                    st.session_state['upload_found_cols'] = found_cols
                    st.session_state['upload_stage'] = 'preview'
                    st.rerun()
                else: st.error("❌ CRITICAL: Kolom NOPOL tidak terdeteksi.")
            else: st.error("❌ Gagal membaca file.")

    elif st.session_state['upload_stage'] == 'preview':
        dfc = st.session_state['upload_data_cache']
        found = st.session_state['upload_found_cols']
        
        st.info(f"✅ **SCAN BERHASIL:** Ditemukan kolom {', '.join([x.upper() for x in found])} | 📊 **TOTAL:** {len(dfc):,} Baris")
        st.dataframe(dfc.head(), use_container_width=True)
        
        has_f = 'finance' in dfc.columns
        l_in = ""
        
        c_l1, c_l2 = st.columns([2, 1])
        with c_l1:
            if not has_f:
                st.error("⚠️ **LEASING TIDAK TERDETEKSI!**")
                l_in = st.text_input("👉 Masukkan Nama Leasing (WAJIB):").strip().upper()
            else:
                st.success("✅ **LEASING TERDETEKSI OTOMATIS**")
                if st.checkbox("Timpa nama leasing dari file?"):
                    l_in = st.text_input("Ketik Nama Leasing Baru:").strip().upper()

        st.markdown("<br>", unsafe_allow_html=True)
        c_b1, c_b2 = st.columns(2)
        with c_b1:
            if st.button("❌ BATAL / RESET"):
                st.session_state['upload_stage'] = 'idle'
                st.session_state['upload_data_cache'] = None
                st.rerun()
        with c_b2:
            is_ready = not (not has_f and not l_in)
            if st.button("🚀 UPDATE DATABASE", disabled=not is_ready):
                if l_in: dfc['finance'] = standardize_leasing_name(l_in)
                elif has_f: dfc['finance'] = dfc['finance'].apply(standardize_leasing_name)
                
                dfc['nopol'] = dfc['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
                dfc = dfc.drop_duplicates(subset=['nopol'], keep='last')
                
                valid_cols = ['nopol', 'type', 'finance', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'branch']
                for x in valid_cols:
                    if x not in dfc.columns: dfc[x] = "-"
                    else: dfc[x] = dfc[x].fillna("-")
                
                records = json.loads(json.dumps(dfc[valid_cols].to_dict('records'), default=str))
                pb = st.progress(0, text="🚀 Memasukkan data ke database...")
                for i in range(0, len(records), 1000):
                    supabase.table('kendaraan').upsert(records[i:i+1000], on_conflict='nopol').execute()
                    pb.progress(min((i+1000)/len(records), 1.0))
                
                st.success("✅ MISSION ACCOMPLISHED! Data updated.")
                st.session_state['upload_stage'] = 'idle'
                time.sleep(2); st.rerun()

# --- TAB 4: HAPUS (PURGE DATA) ---
with tab4:
    st.markdown("### 🗑️ PURGE DATA PROTOCOL")
    del_file = st.file_uploader("UPLOAD TARGET LIST (NOPOL)", type=['xlsx','csv','txt'])
    if del_file and st.button("🔥 EXECUTE DATA PURGE"):
        df_del = read_file_robust(del_file)
        df_del, _ = smart_rename_columns(df_del)
        if 'nopol' in df_del.columns:
            targets = list(set(df_del['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper().tolist()))
            pb_del = st.progress(0, text="🔥 Menghapus unit...")
            for i in range(0, len(targets), 200):
                supabase.table('kendaraan').delete().in_('nopol', targets[i:i+200]).execute()
                pb_del.progress(min((i+200)/len(targets), 1.0))
            st.success("✅ PURGE COMPLETED."); time.sleep(1); st.rerun()