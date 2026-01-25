import streamlit as st
import pandas as pd
import time
import json
import os
from supabase import create_client, Client
from dotenv import load_dotenv

# --- 1. KONFIGURASI HALAMAN ---
st.set_page_config(
    page_title="One Aspal Command Center",
    page_icon="🦅",
    layout="centered"
)

# --- CSS CUSTOM ---
st.markdown("""
<style>
    .stButton>button {
        width: 100%;
        font-weight: bold;
        border-radius: 10px;
        height: 50px;
    }
    .success-box {
        padding: 20px;
        background-color: #d4edda;
        color: #155724;
        border-radius: 10px;
        text-align: center;
        margin-bottom: 20px;
    }
    .rocket-launch {
        font-size: 80px;
        text-align: center;
        animation: shake 0.5s;
        animation-iteration-count: infinite;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. SETUP & KONEKSI ---
load_dotenv()
URL = os.getenv("SUPABASE_URL")
KEY = os.getenv("SUPABASE_KEY")

@st.cache_resource
def init_connection():
    try: return create_client(URL, KEY)
    except: return None

supabase = init_connection()

# --- 3. SESSION STATE ---
if 'authenticated' not in st.session_state: st.session_state['authenticated'] = False
if 'upload_success' not in st.session_state: st.session_state['upload_success'] = False
if 'last_stats' not in st.session_state: st.session_state['last_stats'] = {}
if 'uploader_key' not in st.session_state: st.session_state['uploader_key'] = 0

# --- 4. LOGIKA CLEANING (SAMA SEPERTI SEBELUMNYA) ---
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
    if not isinstance(text, str): return str(text).lower()
    return ''.join(e for e in text if e.isalnum()).lower()

def smart_rename_columns(df):
    new = {}; found_cols = []
    df.columns = [str(c).strip().replace('"', '').replace("'", "").replace('\ufeff', '') for c in df.columns]
    for col in df.columns:
        clean = normalize_text(col)
        renamed = False
        for std, aliases in COLUMN_ALIASES.items():
            if clean == std or clean in aliases:
                new[col] = std; found_cols.append(std); renamed = True; break
        if not renamed: new[col] = col
    df.rename(columns=new, inplace=True)
    return df, found_cols

def standardize_leasing_name(name):
    if not name: return "UNKNOWN"
    clean = str(name).upper().strip().replace('"', '').replace("'", "")
    if clean in ['NAN', 'NULL', 'NONE', '']: return "UNKNOWN"
    return clean

# --- 5. LOGOUT FUNCTION ---
def logout():
    st.session_state['authenticated'] = False
    st.session_state['upload_success'] = False
    # st.rerun() # Otomatis rerun

# --- 6. HALAMAN LOGIN (PASSWORD BARU) ---
# [PENTING] Ganti "OneAspal2026" dengan password rahasia Anda sendiri
ADMIN_PASSWORD = "@Budi2542136221" 

def check_password():
    if st.session_state['password_input'] == ADMIN_PASSWORD:
        st.session_state['authenticated'] = True
        del st.session_state['password_input']
    else:
        st.error("⛔ Password Salah!")

if not st.session_state['authenticated']:
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown("<h1 style='text-align: center;'>🦅</h1>", unsafe_allow_html=True)
        st.markdown("<h3 style='text-align: center;'>Login Command Center</h3>", unsafe_allow_html=True)
        st.text_input("Masukkan Password", type="password", key="password_input", on_change=check_password)
    st.stop()

# --- 7. SIDEBAR (TOMBOL LOGOUT) ---
with st.sidebar:
    st.markdown("### 👤 Admin Panel")
    if st.button("🚪 LOGOUT", type="secondary"):
        logout()
        st.rerun()

# --- 8. DASHBOARD UTAMA ---
st.title("🦅 Command Center")

# === MODE SUKSES ===
if st.session_state['upload_success']:
    stats = st.session_state['last_stats']
    
    # EFEK ROKET MELUNCUR (Manual Animation)
    placeholder = st.empty()
    with placeholder.container():
        st.markdown("<div style='text-align: center; font-size: 100px;'>🚀</div>", unsafe_allow_html=True)
        st.markdown("<h2 style='text-align: center;'>MENGUDARA!</h2>", unsafe_allow_html=True)
        time.sleep(1.5) # Tahan sebentar biar efek roket terlihat
    placeholder.empty() # Hapus roket

    st.markdown(f"""
    <div class="success-box">
        <h2>✅ UPLOAD SUKSES!</h2>
        <p>Data berhasil mendarat di database One Aspal.</p>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Data", f"{stats.get('total', 0):,}")
    c2.metric("Sukses", f"{stats.get('suc', 0):,}")
    c3.metric("Gagal", f"{stats.get('fail', 0):,}")
    c4.metric("Waktu", f"{stats.get('time', 0)}s")

    st.markdown("---")
    
    col_back, col_out = st.columns([3, 1])
    with col_back:
        if st.button("⬅️ Upload File Lain", type="primary"):
            st.session_state['upload_success'] = False
            st.session_state['last_stats'] = {}
            st.session_state['uploader_key'] += 1
            st.rerun()
    with col_out:
        if st.button("🚪 Logout"):
            logout()
            st.rerun()

# === MODE UPLOAD ===
else:
    st.markdown("### 📤 Upload Data")
    
    uploaded_file = st.file_uploader(
        "Drop file di sini:", 
        type=['xlsx', 'xls', 'csv', 'txt'], 
        key=f"uploader_{st.session_state['uploader_key']}"
    )

    if uploaded_file is not None:
        with st.status("🔍 Menganalisa File...", expanded=True) as status:
            try:
                filename = uploaded_file.name.lower()
                
                # Baca File (Support TXT Tab)
                if filename.endswith('.txt'):
                    try: df = pd.read_csv(uploaded_file, sep='\t', dtype=str, on_bad_lines='skip', encoding='utf-8')
                    except: df = pd.read_csv(uploaded_file, sep='\t', dtype=str, on_bad_lines='skip', encoding='latin1')
                elif filename.endswith('.csv'):
                    try: df = pd.read_csv(uploaded_file, sep=';', dtype=str, on_bad_lines='skip')
                    except: df = pd.read_csv(uploaded_file, sep=',', dtype=str, on_bad_lines='skip')
                else:
                    df = pd.read_excel(uploaded_file, dtype=str)

                df, found = smart_rename_columns(df)
                
                if 'nopol' not in df.columns:
                    status.update(label="❌ Error: Kolom Nopol Hilang!", state="error")
                    st.error("Header file tidak valid. Pastikan ada kolom NOPOL.")
                    st.stop()

                df['nopol'] = df['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
                df = df.drop_duplicates(subset=['nopol'], keep='last')

                if 'finance' not in df.columns:
                    df['finance'] = "UNKNOWN"
                else:
                    df['finance'] = df['finance'].apply(standardize_leasing_name)

                valid_cols = ['nopol', 'type', 'finance', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'branch']
                for c in valid_cols:
                    if c not in df.columns: df[c] = "-"
                    else: 
                        df[c] = df[c].fillna("-")
                        df[c] = df[c].replace(['nan', 'NaN', 'NULL', 'null', 'None', ''], '-')
                
                status.update(label="✅ Siap Upload!", state="complete")
                
                with st.expander("👀 Preview Data"):
                    st.dataframe(df[valid_cols].head(10), use_container_width=True)
                
                st.info(f"📊 Total Data Bersih: **{len(df):,}** Baris")

                if st.button("🚀 EKSEKUSI KE DATABASE", type="primary"):
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    records = df[valid_cols].to_dict(orient='records')
                    records = json.loads(json.dumps(records, default=str))
                    
                    BATCH_SIZE = 1000
                    total = len(records)
                    suc = 0
                    fail = 0
                    start_time = time.time()
                    
                    for i in range(0, total, BATCH_SIZE):
                        batch = records[i:i+BATCH_SIZE]
                        try:
                            supabase.table('kendaraan').upsert(batch, on_conflict='nopol', count=None).execute()
                            suc += len(batch)
                        except:
                            fail += len(batch)
                        
                        prog = min((i + BATCH_SIZE) / total, 1.0)
                        progress_bar.progress(prog)
                        status_text.text(f"⏳ Uploading... {suc}/{total}")
                    
                    st.session_state['last_stats'] = {
                        'total': total, 'suc': suc, 'fail': fail,
                        'time': round(time.time() - start_time, 2)
                    }
                    st.session_state['upload_success'] = True
                    st.rerun()

            except Exception as e:
                status.update(label="❌ Terjadi Kesalahan", state="error")
                st.error(f"Error Detail: {e}")