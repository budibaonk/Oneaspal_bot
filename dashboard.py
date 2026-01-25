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
    layout="wide"
)

# --- CSS CUSTOM ---
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
    .delete-box {
        padding: 20px;
        background-color: #f8d7da;
        color: #721c24;
        border-radius: 10px;
        text-align: center;
        margin-bottom: 20px;
        border: 1px solid #f5c6cb;
    }
    /* Trik Centering Logo Login */
    div[data-testid="column"] {
        display: flex;
        align-items: center;
        justify-content: center;
    }
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
if 'delete_success' not in st.session_state: st.session_state['delete_success'] = False
if 'last_stats' not in st.session_state: st.session_state['last_stats'] = {}
if 'uploader_key' not in st.session_state: st.session_state['uploader_key'] = 0

# --- 4. FUNGSI INTELIJEN ---
@st.cache_data(ttl=60)
def get_total_asset_count():
    try: return supabase.table('kendaraan').select('*', count='exact', head=True).execute().count
    except: return 0

@st.cache_data(ttl=60)
def get_user_stats():
    try:
        res = supabase.table('users').select('nama_lengkap, agency, role, status, no_hp, alamat').execute()
        return pd.DataFrame(res.data)
    except: return pd.DataFrame()

@st.cache_data(ttl=300)
def get_leasing_distribution():
    try:
        res = supabase.table('kendaraan').select('finance').order('created_at', desc=True).limit(50000).execute()
        df = pd.DataFrame(res.data)
        if df.empty: return pd.DataFrame()
        counts = df['finance'].value_counts().reset_index()
        counts.columns = ['Leasing', 'Jumlah Unit (Sample)']
        return counts
    except: return pd.DataFrame()

# --- 5. LOGIKA CLEANING (Rename & Standardize) ---
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

# --- 6. AUTH & LOGO UTILS ---
# [PENTING] PASSWORD BARU CEO
ADMIN_PASSWORD = "@Budi2542136221"

def logout():
    st.session_state['authenticated'] = False
    st.session_state['upload_success'] = False
    st.session_state['delete_success'] = False

def check_password():
    # Menggunakan strip() untuk jaga-jaga ada spasi tak sengaja
    input_pass = st.session_state['password_input'].strip()
    if input_pass == ADMIN_PASSWORD:
        st.session_state['authenticated'] = True
        del st.session_state['password_input']
    else: st.error("⛔ Akses Ditolak! Password Salah.")

def render_logo(width=150):
    if os.path.exists("logo.png"):
        try: st.image("logo.png", width=width)
        except: st.markdown("# 🦅")
    else: st.markdown("# 🦅")

# --- LOGIN PAGE (CENTERED) ---
if not st.session_state['authenticated']:
    col1, col2, col3 = st.columns([3, 2, 3])
    with col2:
        render_logo(width=200)
        st.markdown("<h3 style='text-align: center;'>Login Commando</h3>", unsafe_allow_html=True)
        st.text_input("Password", type="password", key="password_input", on_change=check_password)
    st.stop()

# --- 7. SIDEBAR ---
with st.sidebar:
    render_logo(width=200)
    st.markdown("---")
    st.markdown("### 👤 Admin Panel")
    if st.button("🚪 LOGOUT", type="secondary"):
        logout()
        st.rerun()
    st.markdown("---")
    st.info("Versi: Commando v3.2\nStatus: Secured 🔒")

# --- 8. DASHBOARD HEADER ---
col_head1, col_head2 = st.columns([1, 4])
with col_head1: render_logo(width=100)
with col_head2:
    st.title("One Aspal Bot Commando")
    st.markdown("Laporan Intelijen & Manajemen Data Terpusat.")

st.markdown("---")

# === DATA INTELIJEN ===
m1, m2, m3 = st.columns(3)
total_assets = get_total_asset_count()
df_users = get_user_stats()
count_mitra = len(df_users[df_users['role'] != 'pic']) if not df_users.empty else 0
count_pic = len(df_users[df_users['role'] == 'pic']) if not df_users.empty else 0

m1.metric("📂 TOTAL DATA ASET", f"{total_assets:,}", delta="Real-time")
m2.metric("🛡️ MITRA LAPANGAN", f"{count_mitra}", delta="Agents")
m3.metric("🏦 MITRA LEASING", f"{count_pic}", delta="Users")

# === FITUR UTAMA (TABS) ===
tab_upload, tab_delete, tab_info = st.tabs(["📤 UPLOAD DATA (Insert/Update)", "🗑️ HAPUS DATA (Delete)", "📊 INFO INTELIJEN"])

# --------------------------------------------------------------------------------
# TAB 1: UPLOAD DATA
# --------------------------------------------------------------------------------
with tab_upload:
    if st.session_state['upload_success']:
        stats = st.session_state['last_stats']
        st.markdown(f"""<div class="success-box"><h2>✅ DATA MENGUDARA!</h2><p>Sukses menyimpan data ke markas.</p></div>""", unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Input", f"{stats.get('total', 0):,}")
        c2.metric("Sukses", f"{stats.get('suc', 0):,}")
        c3.metric("Gagal", f"{stats.get('fail', 0):,}")
        c4.metric("Waktu", f"{stats.get('time', 0)}s")
        if st.button("⬅️ Upload Lagi", key="btn_back_up"):
            st.session_state['upload_success'] = False
            st.rerun()
    else:
        st.write("Gunakan menu ini untuk memasukkan data baru atau update data lama.")
        uploaded_file = st.file_uploader("Drop file Excel/CSV/TXT:", type=['xlsx', 'xls', 'csv', 'txt'], key=f"up_{st.session_state['uploader_key']}")
        
        if uploaded_file:
            try:
                filename = uploaded_file.name.lower()
                # Support Excel, CSV, TXT
                if filename.endswith('.txt'):
                    try: df = pd.read_csv(uploaded_file, sep='\t', dtype=str, on_bad_lines='skip', encoding='utf-8')
                    except: df = pd.read_csv(uploaded_file, sep='\t', dtype=str, on_bad_lines='skip', encoding='latin1')
                elif filename.endswith('.csv'):
                    try: df = pd.read_csv(uploaded_file, sep=';', dtype=str, on_bad_lines='skip')
                    except: df = pd.read_csv(uploaded_file, sep=',', dtype=str, on_bad_lines='skip')
                else: 
                    # Excel Reader
                    df = pd.read_excel(uploaded_file, dtype=str)

                df, found = smart_rename_columns(df)
                if 'nopol' not in df.columns: st.error("❌ Kolom NOPOL tidak ditemukan!"); st.stop()
                
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

                st.info(f"✅ Siap memproses **{len(df):,}** data.")
                with st.expander("👀 Preview Data"): st.dataframe(df[valid_cols].head())

                if st.button("🚀 EKSEKUSI KE DATABASE", type="primary"):
                    progress_bar = st.progress(0); status_text = st.empty()
                    records = json.loads(json.dumps(df[valid_cols].to_dict(orient='records'), default=str))
                    total = len(records); suc = 0; fail = 0; start_time = time.time(); BATCH = 1000
                    
                    for i in range(0, total, BATCH):
                        batch = records[i:i+BATCH]
                        try:
                            supabase.table('kendaraan').upsert(batch, on_conflict='nopol', count=None).execute()
                            suc += len(batch)
                        except: fail += len(batch)
                        progress_bar.progress(min((i + BATCH) / total, 1.0))
                    
                    st.session_state['last_stats'] = {'total': total, 'suc': suc, 'fail': fail, 'time': round(time.time() - start_time, 2)}
                    st.session_state['upload_success'] = True
                    st.rerun()
            except Exception as e: st.error(f"Error: {e}")

# --------------------------------------------------------------------------------
# TAB 2: HAPUS DATA
# --------------------------------------------------------------------------------
with tab_delete:
    if st.session_state['delete_success']:
        stats = st.session_state['last_stats']
        st.markdown(f"""<div class="delete-box"><h2>🗑️ PEMBERSIHAN SELESAI!</h2><p>Data target telah dihapus permanen dari database.</p></div>""", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        c1.metric("Target Hapus", f"{stats.get('total', 0):,}")
        c2.metric("Waktu Eksekusi", f"{stats.get('time', 0)}s")
        if st.button("⬅️ Kembali", key="btn_back_del"):
            st.session_state['delete_success'] = False
            st.rerun()
    else:
        st.warning("⚠️ PERHATIAN: Upload file Excel berisi list NOPOL yang ingin DIHAPUS.")
        # [CONFIRMED] SUPPORT EXCEL
        del_file = st.file_uploader("Drop file Excel/CSV/TXT (List Hapus):", type=['xlsx', 'xls', 'csv', 'txt'], key=f"del_{st.session_state['uploader_key']}")

        if del_file:
            try:
                filename = del_file.name.lower()
                # Logic Baca File
                if filename.endswith('.txt'):
                    try: df_del = pd.read_csv(del_file, sep='\t', dtype=str, on_bad_lines='skip', encoding='utf-8')
                    except: df_del = pd.read_csv(del_file, sep='\t', dtype=str, on_bad_lines='skip', encoding='latin1')
                elif filename.endswith('.csv'):
                    try: df_del = pd.read_csv(del_file, sep=';', dtype=str, on_bad_lines='skip')
                    except: df_del = pd.read_csv(del_file, sep=',', dtype=str, on_bad_lines='skip')
                else: 
                    # Excel Reader Logic
                    df_del = pd.read_excel(del_file, dtype=str)

                df_del, found = smart_rename_columns(df_del)
                if 'nopol' not in df_del.columns: st.error("❌ Kolom NOPOL tidak ditemukan!"); st.stop()

                target_nopols = df_del['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper().tolist()
                target_nopols = list(set(target_nopols)) 
                
                st.error(f"🚨 **DITEMUKAN {len(target_nopols):,} NOPOL UNTUK DIHAPUS!**")
                with st.expander("👀 Lihat Daftar Target"): st.write(target_nopols[:50])

                if st.button("🔥 EKSEKUSI HAPUS PERMANEN", type="primary"):
                    progress_bar = st.progress(0); status_text = st.empty()
                    start_time = time.time()
                    BATCH_DEL = 200 
                    total = len(target_nopols)
                    
                    for i in range(0, total, BATCH_DEL):
                        batch = target_nopols[i:i+BATCH_DEL]
                        try:
                            supabase.table('kendaraan').delete().in_('nopol', batch).execute()
                        except Exception as e:
                            st.error(f"Gagal batch {i}: {e}")
                        
                        progress_bar.progress(min((i + BATCH_DEL) / total, 1.0))
                        status_text.text(f"🔥 Menghapus... {min(i+BATCH_DEL, total)}/{total}")
                    
                    st.session_state['last_stats'] = {'total': total, 'time': round(time.time() - start_time, 2)}
                    st.session_state['delete_success'] = True
                    st.rerun()

            except Exception as e: st.error(f"Error File: {e}")

# --------------------------------------------------------------------------------
# TAB 3: INFO INTELIJEN
# --------------------------------------------------------------------------------
with tab_info:
    with st.expander("📂 Breakdown Data Leasing"):
        st.write("Statistik berdasarkan sampel data terbaru:")
        df_leasing = get_leasing_distribution()
        if not df_leasing.empty:
            c_chart, c_table = st.columns([2, 1])
            with c_chart: st.bar_chart(df_leasing.set_index('Leasing'))
            with c_table: st.dataframe(df_leasing, use_container_width=True, height=300)
        else: st.warning("Data belum tersedia.")

    c_mitra, c_pic = st.columns(2)
    with c_mitra:
        with st.expander(f"🛡️ Daftar Mitra Lapangan"):
            if not df_users.empty:
                st.dataframe(df_users[df_users['role']!='pic'][['nama_lengkap', 'agency', 'no_hp']], use_container_width=True, hide_index=True)
    with c_pic:
        with st.expander(f"🏦 Daftar PIC Leasing"):
             if not df_users.empty:
                st.dataframe(df_users[df_users['role']=='pic'][['nama_lengkap', 'agency', 'no_hp']], use_container_width=True, hide_index=True)