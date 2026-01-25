################################################################################
#                                                                              #
#                      PROJECT: ONEASPAL COMMAND CENTER                        #
#                      VERSION: 8.5 (FINAL ABSOLUTE EDITION)                   #
#                      ROLE:    ADMIN DASHBOARD CORE                           #
#                      AUTHOR:  CTO (GEMINI) & CEO (BAONK)                     #
#                                                                              #
################################################################################

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
# BAGIAN 1: KONFIGURASI HALAMAN & TEMA VISUAL
# ##############################################################################
st.set_page_config(
    page_title="One Aspal Command",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- CSS MASTER (CYBERPUNK GLASS-MORPHISM UI) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Orbitron:wght@500;700;900&display=swap');

    .stApp { background-color: #0e1117; font-family: 'Inter', sans-serif; font-size: 14px; }
    
    /* JUDUL & HEADER */
    h1, h2, h3 { 
        font-family: 'Orbitron', sans-serif !important; 
        color: #ffffff; 
        text-transform: uppercase; 
        letter-spacing: 1px; 
    }
    
    /* KOTAK STATISTIK (METRIC CARDS) */
    div[data-testid="metric-container"] {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 20px;
        backdrop-filter: blur(10px);
        transition: all 0.3s ease;
    }
    div[data-testid="metric-container"]:hover { 
        border-color: #00f2ff; 
        transform: translateY(-3px);
        box-shadow: 0 5px 15px rgba(0, 242, 255, 0.2);
    }
    div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
        color: #00f2ff !important; 
        font-family: 'Orbitron', sans-serif; 
        font-size: 1.6rem !important;
    }
    
    /* TOMBOL NEON */
    .stButton>button {
        background: linear-gradient(90deg, #0061ff 0%, #60efff 100%);
        color: #000; 
        border: none; 
        border-radius: 8px; 
        height: 45px;
        font-weight: 800; 
        font-family: 'Orbitron', sans-serif; 
        width: 100%;
        transition: all 0.3s;
    }
    .stButton>button:hover { 
        box-shadow: 0 0 20px rgba(0, 242, 255, 0.5); 
        transform: scale(1.01);
    }

    /* LEADERBOARD DESIGN */
    .leaderboard-row {
        background: rgba(0, 242, 255, 0.04);
        padding: 15px; 
        margin-bottom: 8px;
        border-radius: 8px;
        border-left: 4px solid #00f2ff;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .leaderboard-val { 
        font-family: 'Orbitron'; 
        color: #00f2ff; 
        font-weight: bold; 
        font-size: 1.1rem;
    }

    /* TECH BOX & GRID PERSONIL */
    .tech-box { 
        background: rgba(0, 242, 255, 0.05); 
        border-left: 4px solid #00f2ff; 
        padding: 20px; 
        border-radius: 8px; 
        color: #ddd; 
        margin-bottom: 20px; 
    }
    .info-grid { 
        display: grid; 
        grid-template-columns: repeat(2, 1fr); 
        gap: 12px; 
        margin-top: 15px; 
    }
    .info-item { 
        background: rgba(255,255,255,0.05); 
        padding: 12px; 
        border-radius: 6px; 
    }
    .info-label { 
        color: #888; 
        font-size: 0.8rem; 
        display: block; 
        margin-bottom: 4px;
        text-transform: uppercase;
    }
    .info-value { 
        color: #fff; 
        font-weight: bold; 
        font-family: 'Orbitron'; 
        font-size: 1.1rem; 
    }

    /* SIDEBAR & TABS */
    .stTabs [data-baseweb="tab"] { 
        height: 50px; 
        padding: 0 30px; 
        font-family: 'Orbitron'; 
        font-size: 0.9rem; 
    }
    
    header {visibility: hidden;} 
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ##############################################################################
# BAGIAN 2: LOGIKA KONEKSI & DATABASE
# ##############################################################################
load_dotenv()
URL = os.getenv("SUPABASE_URL")
KEY = os.getenv("SUPABASE_KEY")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

@st.cache_resource
def init_connection():
    try:
        return create_client(URL, KEY)
    except Exception as e:
        st.error(f"Gagal koneksi ke database: {e}")
        return None

supabase = init_connection()

# --- MANAJEMEN STATUS DASHBOARD (SESSION STATE) ---
if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False

if 'upload_stage' not in st.session_state:
    st.session_state['upload_stage'] = 'idle'

if 'upload_data_cache' not in st.session_state:
    st.session_state['upload_data_cache'] = None

if 'upload_found_cols' not in st.session_state:
    st.session_state['upload_found_cols'] = []

if 'upload_result' not in st.session_state:
    st.session_state['upload_result'] = None

# --- DATABASE CRUD FUNCTIONS ---
def get_total_asset_count():
    try:
        res = supabase.table('kendaraan').select('*', count='exact', head=True).execute()
        return res.count
    except:
        return 0

def get_all_users():
    try:
        res = supabase.table('users').select('*').execute()
        df = pd.DataFrame(res.data)
        if not df.empty:
            df['user_id'] = df['user_id'].astype(str)
        return df
    except:
        return pd.DataFrame()

def get_hit_counts():
    try:
        res = supabase.table('finding_logs').select('user_id').execute()
        df_logs = pd.DataFrame(res.data)
        if df_logs.empty:
            return pd.Series()
        return df_logs['user_id'].astype(str).value_counts()
    except:
        return pd.Series()

def get_active_hunters_30m():
    try:
        # Waktu 30 menit yang lalu
        threshold = datetime.now(timezone.utc) - timedelta(minutes=30)
        res = supabase.table('finding_logs').select('user_id').gte('created_at', threshold.isoformat()).execute()
        df = pd.DataFrame(res.data)
        if df.empty:
            return 0
        return df['user_id'].nunique()
    except:
        return 0

def update_user_status(user_id, new_status):
    try:
        supabase.table('users').update({'status': new_status}).eq('user_id', user_id).execute()
        return True
    except:
        return False

def add_user_quota(user_id, days):
    try:
        res = supabase.table('users').select('expiry_date').eq('user_id', user_id).execute()
        now = datetime.utcnow()
        
        if res.data and res.data[0]['expiry_date']:
            curr_exp = datetime.fromisoformat(res.data[0]['expiry_date'].replace('Z', ''))
            base_date = curr_exp if curr_exp > now else now
        else:
            base_date = now
            
        new_expiry = (base_date + timedelta(days=days)).isoformat()
        supabase.table('users').update({'expiry_date': new_expiry}).eq('user_id', user_id).execute()
        return True
    except:
        return False

def delete_user_permanent(user_id):
    try:
        supabase.table('users').delete().eq('user_id', user_id).execute()
        return True
    except:
        return False

# ##############################################################################
# BAGIAN 3: ENGINE PINTAR (ANTI-ERROR & UPLOAD)
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

def normalize_text(text):
    return ''.join(e for e in str(text) if e.isalnum()).lower()

def fix_header_position(df):
    """Mencari lokasi header yang benar (MTF Fix)."""
    target_aliases = [normalize_text(a) for a in COLUMN_ALIASES['nopol']]
    for i in range(min(30, len(df))):
        row_vals = [normalize_text(str(x)) for x in df.iloc[i].values]
        if any(alias in row_vals for alias in target_aliases):
            df.columns = df.iloc[i]
            df = df.iloc[i+1:].reset_index(drop=True)
            return df
    return df

def smart_rename_columns(df):
    """Rename kolom dengan proteksi duplikat."""
    new_cols = {}
    found_std_cols = []
    df.columns = [str(c).strip().replace('"', '').replace("'", "").replace('\ufeff', '') for c in df.columns]
    
    for col in df.columns:
        clean_name = normalize_text(col)
        renamed = False
        for std_name, aliases in COLUMN_ALIASES.items():
            aliases_clean = [normalize_text(a) for a in aliases]
            if clean_name == std_name or clean_name in aliases_clean:
                # ANTI-DUPLICATE CHECK
                if std_name not in new_cols.values():
                    new_cols[col] = std_name
                    found_std_cols.append(std_name)
                renamed = True
                break
        if not renamed:
            new_cols[col] = col
            
    df.rename(columns=new_cols, inplace=True)
    # Buang kolom kembar jika ada
    df = df.loc[:, ~df.columns.duplicated()]
    return df, found_std_cols

def standardize_leasing_name(name):
    clean = str(name).upper().strip().replace('"', '').replace("'", "")
    return "UNKNOWN" if clean in ['NAN', 'NULL', '', 'NONE'] else clean

def read_file_robust(uploaded_file):
    """Membaca file dengan berbagai format."""
    fname = uploaded_file.name.lower()
    content = uploaded_file.getvalue()
    
    if fname.endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            valid_files = [x for x in z.namelist() if x.endswith(('.csv','.xlsx','.xls','.txt'))]
            if valid_files:
                content = z.read(valid_files[0])
                fname = valid_files[0].lower()
                uploaded_file = io.BytesIO(content)
    else:
        uploaded_file = io.BytesIO(content)
        
    try:
        if fname.endswith(('.xlsx', '.xls')):
            return pd.read_excel(uploaded_file, dtype=str)
        else:
            try: return pd.read_csv(uploaded_file, sep=';', dtype=str, on_bad_lines='skip')
            except: return pd.read_csv(uploaded_file, sep=',', dtype=str, on_bad_lines='skip')
    except:
        return pd.DataFrame()

# ##############################################################################
# BAGIAN 4: TAMPILAN LOGIN & LOGO
# ##############################################################################
def get_img_as_base64(file):
    try:
        with open(file, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except:
        return ""

if not st.session_state['authenticated']:
    # Layout Tengah (Login)
    c_l1, c_l2, c_l3 = st.columns([1, 6, 1])
    with c_l2:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        # Menampilkan Logo Resolusi Tinggi
        if os.path.exists("logo.png"):
            b64_logo = get_img_as_base64("logo.png")
            st.markdown(f'''
                <div style="display:flex;justify-content:center;margin-bottom:30px;">
                    <img src="data:image/png;base64,{b64_logo}" width="220" style="border-radius:15px; filter: drop-shadow(0 0 10px rgba(0,242,255,0.3));">
                </div>
            ''', unsafe_allow_html=True)
        
        st.markdown("<h2 style='text-align:center;color:#00f2ff;margin-bottom:10px;'>SYSTEM LOGIN</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center;color:#888;margin-bottom:20px;'>ONE ASPAL COMMANDO v8.5</p>", unsafe_allow_html=True)
        
        passphrase = st.text_input("PASSPHRASE", type="password", label_visibility="collapsed")
        
        if passphrase == ADMIN_PASSWORD:
            st.session_state['authenticated'] = True
            st.rerun()
        elif passphrase:
            st.error("⛔ ACCESS DENIED: Passphrase Salah.")
    st.stop()

# ##############################################################################
# BAGIAN 5: DASHBOARD UTAMA
# ##############################################################################
with st.sidebar:
    # Menampilkan Logo di Sidebar
    if os.path.exists("logo.png"):
        st.image("logo.png", width=220)
    
    st.markdown("### OPERATIONS")
    
    # Tombol Refresh System
    if st.button("🔄 REFRESH SYSTEM"):
        st.cache_data.clear()
        st.rerun()
    
    # Tombol Logout (Menghapus Sesi Login)
    if st.button("🚪 LOGOUT SESSION"):
        st.session_state['authenticated'] = False
        st.rerun()
        
    st.markdown("---")
    st.caption("ONE ASPAL SYSTEM\nStatus: ONLINE 🟢")

# --- HEADER DASHBOARD ---
st.markdown("## ONE ASPAL COMMANDO v8.5")
st.markdown("<span style='color: #00f2ff; font-family: Orbitron; font-size: 0.8rem;'>⚡ LIVE INTELLIGENCE COMMAND CENTER</span>", unsafe_allow_html=True)
st.markdown("---")

# --- METRIK UTAMA (5 KOLOM RAPI) ---
df_all_users = get_all_users()
total_data_assets = get_total_asset_count()
hit_stats = get_hit_counts()
hunters_30m = get_active_hunters_30m()

# Hitung data metrik
mitra_reg = 0
pic_reg = 0
ready_duty = 0

if not df_all_users.empty:
    mitra_reg = len(df_all_users[df_all_users['role'] != 'pic'])
    pic_reg = len(df_all_users[df_all_users['role'] == 'pic'])
    # Pastikan quota angka
    df_all_users['quota'] = pd.to_numeric(df_all_users['quota'], errors='coerce').fillna(0)
    ready_duty = len(df_all_users[(df_all_users['status'] == 'active') & (df_all_users['quota'] > 0)])

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("ASSETS", f"{total_data_assets:,}", "DATABASE")
m2.metric("LIVE USERS", f"{hunters_30m}", "30M ACTIVE")
m3.metric("TOTAL MITRA", f"{mitra_reg}", "REGISTERED")
m4.metric("READY", f"{ready_duty}", "ACTIVE & QUOTA > 0")
m5.metric("Pic Leasing", f"{pic_reg}", "INTERNAL")

st.write("")

# ##############################################################################
# BAGIAN 6: FITUR TABS
# ##############################################################################
tab1, tab2, tab3, tab4 = st.tabs(["🏆 LEADERBOARD", "🛡️ PERSONIL", "📤 UPLOAD", "🗑️ HAPUS"])

# --- TAB 1: LEADERBOARD (TOP 10) ---
with tab1:
    st.markdown("### 🏆 TOP 10 RANGERS (LIVE HITS)")
    if df_all_users.empty or hit_stats.empty:
        st.info("BELUM ADA DATA TEMUAN HARI INI.")
    else:
        df_rank = df_all_users.copy()
        df_rank['real_hits'] = df_rank['user_id'].map(hit_stats).fillna(0).astype(int)
        # Filter hanya Matel/Korlap
        df_rank = df_rank[df_rank['role'] != 'pic'].sort_values(by='real_hits', ascending=False).head(10)
        
        for i, row in enumerate(df_rank.iterrows(), 1):
            data = row[1]
            st.markdown(f'''
                <div class="leaderboard-row">
                    <div>
                        <b>#{i} {data['nama_lengkap']}</b><br>
                        <small style="color:#888;">AGENCY: {data['agency']}</small>
                    </div>
                    <div class="leaderboard-val">{data['real_hits']} HITS</div>
                </div>
            ''', unsafe_allow_html=True)

# --- TAB 2: PERSONIL (GRID LENGKAP + SEMUA TOMBOL) ---
with tab2:
    if df_all_users.empty:
        st.warning("DATABASE USER KOSONG.")
    else:
        c_div, c_none = st.columns([1, 2])
        with c_div:
            div_sel = st.radio("SELECT DIVISION", ["🛡️ MATEL", "🏦 Pic Leasing"], horizontal=True, label_visibility="collapsed")
        
        target_df = df_all_users[df_all_users['role'] != 'pic'] if "MATEL" in div_sel else df_all_users[df_all_users['role'] == 'pic']
        target_df = target_df.sort_values('nama_lengkap')
        
        agent_list = [f"{r['nama_lengkap']} | {r['agency']}" for idx, r in target_df.iterrows()]
        search_agent = st.selectbox("SEARCH AGENT", agent_list, label_visibility="collapsed")
        
        if search_agent:
            # Ambil User ID dari string terpilih
            selected_nama = search_agent.split(' | ')[0]
            user_data = target_df[target_df['nama_lengkap'] == selected_nama].iloc[0]
            uid = user_data['user_id']
            real_total_hits = hit_stats.get(uid, 0)
            
            # --- INFO GRID (KEMBALI UTUH) ---
            st.markdown(f'''
                <div class="tech-box">
                    <h3 style="margin:0;">{user_data['nama_lengkap']} | <span style="color:#00f2ff;">{user_data['agency']}</span></h3>
                    <hr style="border-color:rgba(255,255,255,0.1); margin:15px 0;">
                    <div class="info-grid">
                        <div class="info-item">
                            <span class="info-label">STATUS</span>
                            <span class="info-value" style="color:{'#0f0' if user_data['status']=='active' else '#f44'}">{user_data['status'].upper()}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">EXPIRY DATE</span>
                            <span class="info-value">{str(user_data['expiry_date'])[:10]}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">REMAINING QUOTA</span>
                            <span class="info-value">{user_data.get('quota',0):,}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">USAGE (TODAY)</span>
                            <span class="info-value">{user_data.get('daily_usage',0)}x</span>
                        </div>
                        <div class="info-item" style="grid-column: span 2; border: 1px solid #00f2ff;">
                            <span class="info-label">LIFETIME FIELD HITS</span>
                            <span class="info-value" style="color:#00f2ff; font-size:1.4rem;">{real_total_hits} UNITS FOUND</span>
                        </div>
                    </div>
                </div>
            ''', unsafe_allow_html=True)
            
            # --- TOMBOL MANAJEMEN ---
            c_in, c_ext = st.columns([1, 2])
            with c_in:
                days_add = st.number_input("DAYS", 1, 365, 30, label_visibility="collapsed")
            with c_ext:
                if st.button(f"➕ EXTEND ACCESS (+{days_add} DAYS)"):
                    if add_user_quota(uid, days_add):
                        st.success("MASA AKTIF DIPERPANJANG."); time.sleep(1); st.rerun()
            
            st.divider()
            
            b_freeze, b_delete = st.columns(2)
            with b_freeze:
                if user_data['status'] == 'active':
                    if st.button("⛔ FREEZE ACCOUNT (BAN)"):
                        update_user_status(uid, 'banned'); st.rerun()
                else:
                    if st.button("✅ ACTIVATE ACCOUNT"):
                        update_user_status(uid, 'active'); st.rerun()
            
            with b_delete:
                if st.button("🗑️ DELETE PERMANENT"):
                    if delete_user_permanent(uid):
                        st.warning("USER TELAH DIHAPUS."); time.sleep(1); st.rerun()

# --- TAB 3: UPLOAD (INTELLIGENCE MODE + REPORTING) ---
with tab3:
    st.markdown("### 📤 UPLOAD INTELLIGENCE")
    
    # TAHAP 1: IDLE (Upload File)
    if st.session_state['upload_stage'] == 'idle':
        file_up = st.file_uploader("DROP DATA FILE", type=['xlsx','csv','txt','zip'], label_visibility="collapsed")
        if file_up and st.button("🔍 ANALISA FILE"):
            df_raw_file = read_file_robust(file_up)
            if not df_raw_file.empty:
                # MTF Fix: Scan Header
                df_fixed_header = fix_header_position(df_raw_file)
                df_standard, found_cols = smart_rename_columns(df_fixed_header)
                
                if 'nopol' in df_standard.columns:
                    st.session_state['upload_data_cache'] = df_standard
                    st.session_state['upload_found_cols'] = found_cols
                    st.session_state['upload_stage'] = 'preview'
                    st.rerun()
                else:
                    st.error("❌ CRITICAL ERROR: Kolom NOPOL tidak ditemukan dalam file.")
            else:
                st.error("❌ FILE KOSONG ATAU TIDAK TERBACA.")

    # TAHAP 2: PREVIEW
    elif st.session_state['upload_stage'] == 'preview':
        df_preview = st.session_state['upload_data_cache']
        cols_found = st.session_state['upload_found_cols']
        
        st.info(f"✅ SCAN BERHASIL: Ditemukan {', '.join([x.upper() for x in cols_found])} | 📊 TOTAL: {len(df_preview):,} Unit")
        st.dataframe(df_preview.head(10), use_container_width=True)
        
        has_leasing_col = 'finance' in df_preview.columns
        input_leasing = ""
        
        col_l1, col_l2 = st.columns([2, 1])
        with col_l1:
            if not has_leasing_col:
                st.error("⚠️ LEASING TIDAK TERDETEKSI!")
                input_leasing = st.text_input("👉 Masukkan Nama Leasing (WAJIB):").strip().upper()
            else:
                st.success("✅ LEASING TERDETEKSI OTOMATIS")
                if st.checkbox("Timpa nama leasing dari file?"):
                    input_leasing = st.text_input("Ketik Nama Leasing Baru:").strip().upper()
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        btn_cancel, btn_update = st.columns(2)
        with btn_cancel:
            if st.button("❌ BATAL / RESET"):
                st.session_state['upload_stage'] = 'idle'
                st.session_state['upload_data_cache'] = None
                st.rerun()
        
        with btn_update:
            is_valid_to_upload = not (not has_leasing_col and not input_leasing)
            if st.button("🚀 UPDATE DATABASE", disabled=not is_valid_to_upload):
                # Terapkan Nama Leasing
                if input_leasing:
                    df_preview['finance'] = standardize_leasing_name(input_leasing)
                elif has_leasing_col:
                    df_preview['finance'] = df_preview['finance'].apply(standardize_leasing_name)
                
                # Pembersihan Akhir
                df_preview['nopol'] = df_preview['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
                df_preview = df_preview.drop_duplicates(subset=['nopol'], keep='last')
                
                # Pastikan semua kolom ada
                db_cols = ['nopol', 'type', 'finance', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'branch']
                for c in db_cols:
                    if c not in df_preview.columns:
                        df_preview[c] = "-"
                    else:
                        df_preview[c] = df_preview[c].fillna("-")
                
                # Konversi ke JSON records
                final_records = json.loads(json.dumps(df_preview[db_cols].to_dict('records'), default=str))
                
                # --- PROSES UPLOAD ---
                suc_count, fail_count = 0, 0
                prog_bar = st.progress(0, text="🚀 Memulai Sinkronisasi...")
                
                for i in range(0, len(final_records), 1000):
                    batch = final_records[i:i+1000]
                    try:
                        supabase.table('kendaraan').upsert(batch, on_conflict='nopol').execute()
                        suc_count += len(batch)
                    except:
                        fail_count += len(batch)
                    
                    prog_bar.progress(min((i+1000)/len(final_records), 1.0), text=f"🚀 Memproses {min(i+1000, len(final_records)):,} / {len(final_records):,}...")
                
                st.session_state['upload_result'] = {'suc': suc_count, 'fail': fail_count}
                st.session_state['upload_stage'] = 'complete'
                st.rerun()

    # TAHAP 3: COMPLETE (REPORTING)
    elif st.session_state['upload_stage'] == 'complete':
        res = st.session_state.get('upload_result', {'suc': 0, 'fail': 0})
        st.markdown(f'''
            <div class="tech-box" style="border-color:#00ff00;">
                <h3 style="color:#00ff00; margin:0;">MISSION COMPLETE</h3>
                <p style="margin:10px 0;">Data Sinkronisasi Berhasil Diproses:</p>
                <div class="info-grid">
                    <div class="info-item">
                        <span class="info-label">BERHASIL DIUPDATE</span>
                        <span class="info-value" style="color:#0f0;">{res['suc']:,} UNITS</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">GAGAL (ERROR)</span>
                        <span class="info-value" style="color:#f44;">{res['fail']:,} UNITS</span>
                    </div>
                </div>
            </div>
        ''', unsafe_allow_html=True)
        
        if st.button("⬅️ BACK TO DASHBOARD"):
            st.session_state['upload_stage'] = 'idle'
            st.session_state['upload_data_cache'] = None
            st.rerun()

# --- TAB 4: HAPUS ---
with tab4:
    st.markdown("### 🗑️ PURGE DATA PROTOCOL")
    purge_file = st.file_uploader("UPLOAD TARGET LIST (NOPOL)", type=['xlsx','csv','txt'])
    
    if purge_file and st.button("🔥 EXECUTE DATA PURGE"):
        df_purge = read_file_robust(purge_file)
        if not df_purge.empty:
            df_purge, _ = smart_rename_columns(df_purge)
            if 'nopol' in df_purge.columns:
                targets = list(set(df_purge['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper().tolist()))
                
                pb_purge = st.progress(0, text="🔥 Menghapus unit dari database...")
                for i in range(0, len(targets), 200):
                    batch_del = targets[i:i+200]
                    supabase.table('kendaraan').delete().in_('nopol', batch_del).execute()
                    pb_purge.progress(min((i+200)/len(targets), 1.0))
                
                st.success(f"✅ BERHASIL: {len(targets):,} Unit Telah Dihapus."); time.sleep(1); st.rerun()
            else:
                st.error("❌ KOLOM NOPOL TIDAK DITEMUKAN.")