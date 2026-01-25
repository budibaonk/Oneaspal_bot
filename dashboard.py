import streamlit as st
import pandas as pd
import time
import json
import os
from supabase import create_client, Client
from dotenv import load_dotenv

# --- 1. KONFIGURASI HALAMAN ---
st.set_page_config(
    page_title="One Aspal Bot Commando",
    page_icon="🦅",
    layout="wide" # Layout WIDE agar muat banyak data statistik
)

# --- CSS CUSTOM (TAMPILAN COMMANDO) ---
st.markdown("""
<style>
    .stButton>button {
        width: 100%;
        font-weight: bold;
        border-radius: 8px;
        height: 45px;
    }
    .success-box {
        padding: 20px;
        background-color: #d1e7dd;
        color: #0f5132;
        border-radius: 10px;
        text-align: center;
        margin-bottom: 20px;
        border: 1px solid #badbcc;
    }
    .stat-card {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        text-align: center;
        border: 1px solid #e0e0e0;
    }
    .big-number {
        font-size: 32px;
        font-weight: bold;
        color: #1f2937;
    }
    .stat-label {
        color: #6b7280;
        font-size: 14px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    h1 { color: #111827; }
</style>
""", unsafe_allow_html=True)

# --- 2. KONEKSI & SETUP ---
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

# --- 4. FUNGSI INTELIJEN (DATA STATS) ---

@st.cache_data(ttl=60) # Cache 60 detik biar gak berat loading terus
def get_total_asset_count():
    try:
        # Mengambil jumlah total data (Head request only, sangat cepat)
        count = supabase.table('kendaraan').select('*', count='exact', head=True).execute().count
        return count
    except: return 0

@st.cache_data(ttl=60)
def get_user_stats():
    try:
        # Ambil semua user (ringan karena kolom tertentu saja)
        res = supabase.table('users').select('nama_lengkap, agency, role, status, no_hp, alamat').execute()
        df = pd.DataFrame(res.data)
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=300) # Cache 5 menit karena query leasing berat
def get_leasing_distribution():
    # CATATAN: Untuk jutaan data, sebaiknya pakai RPC Supabase. 
    # Ini versi Python (Fetch Finance Column Only)
    try:
        # Kita ambil sample 10.000 data terakhir untuk tren, atau semua kalau kuat
        # Agar tidak crash memory, kita batasi fetch misal 50.000 baris terbaru
        res = supabase.table('kendaraan').select('finance').order('created_at', desc=True).limit(50000).execute()
        df = pd.DataFrame(res.data)
        if df.empty: return pd.DataFrame()
        
        # Hitung distribusi
        counts = df['finance'].value_counts().reset_index()
        counts.columns = ['Leasing', 'Jumlah Unit (Sample)']
        return counts
    except: return pd.DataFrame()

# --- 5. LOGIKA CLEANING (SAMA) ---
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

# --- 6. LOGOUT & LOGIN ---
ADMIN_PASSWORD = "@Budi2542136221" 

def logout():
    st.session_state['authenticated'] = False
    st.session_state['upload_success'] = False

def check_password():
    if st.session_state['password_input'] == ADMIN_PASSWORD:
        st.session_state['authenticated'] = True
        del st.session_state['password_input']
    else: st.error("⛔ Akses Ditolak!")

if not st.session_state['authenticated']:
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        # Placeholder Logo jika file belum ada
        if os.path.exists("logo.png"): st.image("logo.png", width=150)
        else: st.markdown("# 🦅")
        st.markdown("<h3 style='text-align: center;'>Login Commando</h3>", unsafe_allow_html=True)
        st.text_input("Password", type="password", key="password_input", on_change=check_password)
    st.stop()

# --- 7. SIDEBAR ---
with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", width=200)
    else: st.markdown("# 🦅 ONE ASPAL")
    
    st.markdown("---")
    st.markdown("### 👤 Admin Panel")
    if st.button("🚪 LOGOUT", type="secondary"):
        logout()
        st.rerun()
    st.markdown("---")
    st.info("Versi: Commando v3.0\nStatus: Online 🟢")

# --- 8. DASHBOARD UTAMA (COMMANDO UI) ---
col_head1, col_head2 = st.columns([1, 4])
with col_head1:
    # Logo kecil di header (opsional)
    if os.path.exists("logo.png"): st.image("logo.png", width=100)
    else: st.markdown("# 🦅")
with col_head2:
    st.title("One Aspal Bot Commando")
    st.markdown("Selamat datang, Komandan! Berikut laporan intelijen hari ini.")

st.markdown("---")

# === BAGIAN INTELIJEN (DATA STATISTIK) ===
# Ambil Data (Cached)
total_assets = get_total_asset_count()
df_users = get_user_stats()

# Filter User
if not df_users.empty:
    mitra_lapangan = df_users[df_users['role'] != 'pic']
    mitra_leasing = df_users[df_users['role'] == 'pic']
    count_mitra = len(mitra_lapangan)
    count_pic = len(mitra_leasing)
else:
    count_mitra = 0; count_pic = 0; mitra_lapangan = pd.DataFrame(); mitra_leasing = pd.DataFrame()

# TAMPILAN KARTU STATISTIK (METRIC)
m1, m2, m3 = st.columns(3)
m1.metric("📂 TOTAL DATA ASET", f"{total_assets:,}", delta="Real-time DB")
m2.metric("🛡️ MITRA LAPANGAN", f"{count_mitra} Personil", delta="Active Agents")
m3.metric("🏦 MITRA LEASING (PIC)", f"{count_pic} User", delta="Internal")

st.markdown("### 📊 Laporan Detail")

# EXPANDER 1: LEASING STATS
with st.expander("📂 Breakdown Data Leasing (Klik untuk Buka)"):
    st.write("Generating statistics from sample data...")
    df_leasing = get_leasing_distribution()
    if not df_leasing.empty:
        # Tampilkan Chart & Tabel Side-by-Side
        c_chart, c_table = st.columns([2, 1])
        with c_chart:
            st.bar_chart(df_leasing.set_index('Leasing'))
        with c_table:
            st.dataframe(df_leasing, use_container_width=True, height=300)
    else:
        st.warning("Data leasing belum tersedia atau koneksi lambat.")

# EXPANDER 2: DAFTAR PERSONIL
c_mitra, c_pic = st.columns(2)

with c_mitra:
    with st.expander(f"🛡️ Daftar Mitra Lapangan ({count_mitra})"):
        if not mitra_lapangan.empty:
            show_cols_mitra = mitra_lapangan[['nama_lengkap', 'agency', 'no_hp', 'alamat']]
            st.dataframe(show_cols_mitra, use_container_width=True, hide_index=True)
        else: st.text("Kosong.")

with c_pic:
    with st.expander(f"🏦 Daftar PIC Leasing ({count_pic})"):
        if not mitra_leasing.empty:
            show_cols_pic = mitra_leasing[['nama_lengkap', 'agency', 'no_hp']]
            st.dataframe(show_cols_pic, use_container_width=True, hide_index=True)
        else: st.text("Kosong.")

st.markdown("---")

# === BAGIAN UPLOADER (OPERASIONAL) ===
if st.session_state['upload_success']:
    # MODE SUKSES (ROKET)
    stats = st.session_state['last_stats']
    placeholder = st.empty()
    with placeholder.container():
        st.markdown("<div style='text-align: center; font-size: 100px;'>🚀</div>", unsafe_allow_html=True)
        st.markdown("<h2 style='text-align: center;'>DATA MENGUDARA!</h2>", unsafe_allow_html=True)
        time.sleep(1.5) 
    placeholder.empty()

    st.markdown(f"""<div class="success-box"><h2>✅ MISI BERHASIL!</h2><p>Data sukses diamankan di markas pusat.</p></div>""", unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Input", f"{stats.get('total', 0):,}")
    c2.metric("Sukses", f"{stats.get('suc', 0):,}")
    c3.metric("Gagal", f"{stats.get('fail', 0):,}")
    c4.metric("Waktu", f"{stats.get('time', 0)}s")

    if st.button("⬅️ Upload File Lain", type="primary"):
        st.session_state['upload_success'] = False
        st.session_state['last_stats'] = {}
        st.session_state['uploader_key'] += 1
        st.rerun()

else:
    # MODE UPLOAD
    st.markdown("### 📤 Upload Data Intelijen Baru")
    uploaded_file = st.file_uploader("Drop file Excel/CSV/TXT di sini:", type=['xlsx', 'xls', 'csv', 'txt'], key=f"uploader_{st.session_state['uploader_key']}")

    if uploaded_file is not None:
        with st.status("🔍 Menganalisa Dokumen...", expanded=True) as status:
            try:
                filename = uploaded_file.name.lower()
                if filename.endswith('.txt'):
                    try: df = pd.read_csv(uploaded_file, sep='\t', dtype=str, on_bad_lines='skip', encoding='utf-8')
                    except: df = pd.read_csv(uploaded_file, sep='\t', dtype=str, on_bad_lines='skip', encoding='latin1')
                elif filename.endswith('.csv'):
                    try: df = pd.read_csv(uploaded_file, sep=';', dtype=str, on_bad_lines='skip')
                    except: df = pd.read_csv(uploaded_file, sep=',', dtype=str, on_bad_lines='skip')
                else: df = pd.read_excel(uploaded_file, dtype=str)

                df, found = smart_rename_columns(df)
                if 'nopol' not in df.columns:
                    status.update(label="❌ Error: Target Nopol Tidak Ditemukan!", state="error"); st.stop()

                df['nopol'] = df['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
                df = df.drop_duplicates(subset=['nopol'], keep='last')
                
                if 'finance' not in df.columns: df['finance'] = "UNKNOWN"
                else: df['finance'] = df['finance'].apply(standardize_leasing_name)

                valid_cols = ['nopol', 'type', 'finance', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'branch']
                for c in valid_cols:
                    if c not in df.columns: df[c] = "-"
                    else: 
                        df[c] = df[c].fillna("-")
                        df[c] = df[c].replace(['nan', 'NaN', 'NULL', 'null', 'None', ''], '-')
                
                status.update(label="✅ Analisa Selesai. Data Siap!", state="complete")
                
                with st.expander("👀 Preview Data Intelijen"):
                    st.dataframe(df[valid_cols].head(10), use_container_width=True)
                
                if st.button("🚀 EKSEKUSI KE DATABASE", type="primary"):
                    progress_bar = st.progress(0); status_text = st.empty()
                    records = json.loads(json.dumps(df[valid_cols].to_dict(orient='records'), default=str))
                    total = len(records); suc = 0; fail = 0; start_time = time.time(); BATCH_SIZE = 1000
                    
                    for i in range(0, total, BATCH_SIZE):
                        batch = records[i:i+BATCH_SIZE]
                        try:
                            supabase.table('kendaraan').upsert(batch, on_conflict='nopol', count=None).execute()
                            suc += len(batch)
                        except: fail += len(batch)
                        progress_bar.progress(min((i + BATCH_SIZE) / total, 1.0))
                        status_text.text(f"⏳ Uploading... {suc}/{total}")
                    
                    st.session_state['last_stats'] = {'total': total, 'suc': suc, 'fail': fail, 'time': round(time.time() - start_time, 2)}
                    st.session_state['upload_success'] = True
                    st.rerun()

            except Exception as e:
                status.update(label="❌ Dokumen Rusak/Tidak Valid", state="error")
                st.error(f"Error: {e}")