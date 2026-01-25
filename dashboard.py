import streamlit as st
import pandas as pd
import time
import json
import os
import altair as alt
from datetime import datetime, timedelta
from supabase import create_client, Client
from dotenv import load_dotenv

# --- 1. KONFIGURASI HALAMAN ---
st.set_page_config(
    page_title="One Aspal Bot Commando",
    page_icon="🦅",
    layout="wide"
)

# --- CSS CUSTOM (TAMPILAN ULTIMATE) ---
st.markdown("""
<style>
    /* Styling Tombol */
    .stButton>button {
        width: 100%;
        font-weight: bold;
        border-radius: 8px;
        height: 45px;
        transition: all 0.3s;
    }
    
    /* Styling Box */
    .success-box { padding: 20px; background-color: #d1e7dd; color: #0f5132; border-radius: 10px; text-align: center; margin-bottom: 20px; border: 1px solid #badbcc; }
    .delete-box { padding: 20px; background-color: #f8d7da; color: #721c24; border-radius: 10px; text-align: center; margin-bottom: 20px; border: 1px solid #f5c6cb; }
    
    /* LOGIN CENTERED */
    div[data-testid="column"] {
        display: flex;
        align-items: center;
        justify-content: center;
    }
    
    /* Sembunyikan footer streamlit */
    footer {visibility: hidden;}
    
</style>
""", unsafe_allow_html=True)

# --- 2. KONEKSI & SETUP ---
load_dotenv()
URL = os.getenv("SUPABASE_URL")
KEY = os.getenv("SUPABASE_KEY")

# [PENTING] Ambil Password dari .env
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

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

# --- 4. FUNGSI DATABASE (CRUD) ---

def get_total_asset_count():
    try: return supabase.table('kendaraan').select('*', count='exact', head=True).execute().count
    except: return 0

def get_all_users():
    try:
        res = supabase.table('users').select('*').execute()
        return pd.DataFrame(res.data)
    except: return pd.DataFrame()

def update_user_status(user_id, status):
    try: supabase.table('users').update({'status': status}).eq('user_id', user_id).execute(); return True
    except: return False

def add_user_quota(user_id, days):
    try:
        res = supabase.table('users').select('expiry_date').eq('user_id', user_id).execute()
        if not res.data: return False
        
        current_exp_str = res.data[0].get('expiry_date')
        now = datetime.utcnow()
        
        if current_exp_str:
            current_exp = datetime.fromisoformat(current_exp_str.replace('Z', ''))
            base_date = current_exp if current_exp > now else now
        else:
            base_date = now
            
        new_exp = base_date + timedelta(days=days)
        supabase.table('users').update({'expiry_date': new_exp.isoformat()}).eq('user_id', user_id).execute()
        return True
    except: return False

def delete_user_permanent(user_id):
    try: supabase.table('users').delete().eq('user_id', user_id).execute(); return True
    except: return False

@st.cache_data(ttl=300)
def get_leasing_distribution():
    try:
        res = supabase.table('kendaraan').select('finance').order('created_at', desc=True).limit(50000).execute()
        df = pd.DataFrame(res.data)
        if df.empty: return pd.DataFrame()
        counts = df['finance'].value_counts().reset_index()
        counts.columns = ['Leasing', 'Jumlah Unit']
        return counts
    except: return pd.DataFrame()

# --- 5. LOGIKA CLEANING & UTILS ---
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

def render_logo(width=150):
    if os.path.exists("logo.png"):
        try: st.image("logo.png", width=width)
        except: st.markdown("# 🦅")
    else: st.markdown("# 🦅")

# --- 6. HALAMAN LOGIN ---

def check_password():
    if not ADMIN_PASSWORD:
        st.error("⚠️ Password Admin belum disetting di .env atau Secrets!")
        return

    if st.session_state['password_input'] == ADMIN_PASSWORD:
        st.session_state['authenticated'] = True
        del st.session_state['password_input']
    else: st.error("⛔ Password Salah!")

if not st.session_state['authenticated']:
    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        st.markdown("<div style='margin-top: 50px;'></div>", unsafe_allow_html=True)
        col_img_1, col_img_2, col_img_3 = st.columns([1,2,1])
        with col_img_2:
            render_logo(width=180)
            
        st.markdown("<h3 style='text-align: center; margin-bottom: 20px;'>One Aspal Commando</h3>", unsafe_allow_html=True)
        
        st.text_input("Password Akses", type="password", key="password_input", on_change=check_password, placeholder="Masukkan Password Admin")
        st.caption("🔒 Secured System v4.0")
        
        if not ADMIN_PASSWORD:
            st.warning("Admin: Harap setting ADMIN_PASSWORD di .env")
            
    st.stop()

# --- 7. SIDEBAR ---
with st.sidebar:
    render_logo(width=200)
    st.markdown("---")
    st.markdown("### 👤 Control Panel")
    if st.button("🚪 LOGOUT", type="secondary"):
        st.session_state['authenticated'] = False; st.rerun()
    st.markdown("---")
    st.info("Status: **Online** 🟢\nRole: **Super Admin**")

# --- 8. HEADER UTAMA ---
c_h1, c_h2 = st.columns([1, 5])
with c_h1: render_logo(width=80)
with c_h2:
    st.title("One Aspal Bot Commando")
    st.markdown("**Pusat Komando & Manajemen Data Aset**")

# === STATS QUICK VIEW ===
df_users_raw = get_all_users()
total_assets = get_total_asset_count()
mitra_count = len(df_users_raw[df_users_raw['role']!='pic']) if not df_users_raw.empty else 0
pic_count = len(df_users_raw[df_users_raw['role']=='pic']) if not df_users_raw.empty else 0

m1, m2, m3 = st.columns(3)
m1.metric("📂 TOTAL DATA UNIT", f"{total_assets:,}")
m2.metric("🛡️ MITRA LAPANGAN", f"{mitra_count}")
m3.metric("🏦 MITRA LEASING", f"{pic_count}")

st.markdown("---")

# === TAB MENU UTAMA ===
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 ANALISA LEASING", 
    "🛡️ MANAJEMEN PERSONIL", 
    "📤 UPLOAD DATA", 
    "🗑️ HAPUS DATA"
])

# -----------------------------------------------------------------------------
# TAB 1: ANALISA LEASING (CHART)
# -----------------------------------------------------------------------------
with tab1:
    st.subheader("📊 Breakdown Data Leasing")
    df_leasing = get_leasing_distribution()
    
    if not df_leasing.empty:
        chart = alt.Chart(df_leasing).mark_bar().encode(
            x=alt.X('Jumlah Unit', title='Jumlah Data'),
            y=alt.Y('Leasing', sort='-x', title='Nama Leasing'),
            color=alt.Color('Jumlah Unit', legend=None, scale=alt.Scale(scheme='blues')),
            tooltip=['Leasing', 'Jumlah Unit']
        ).properties(height=600).interactive()
        
        st.altair_chart(chart, use_container_width=True)
        with st.expander("Lihat Data Mentah"): st.dataframe(df_leasing, use_container_width=True)
    else: st.info("Belum ada data unit yang cukup untuk dianalisa.")

# -----------------------------------------------------------------------------
# TAB 2: MANAJEMEN PERSONIL
# -----------------------------------------------------------------------------
with tab2:
    st.subheader("🛡️ Kontrol Personil & Mitra")
    
    if df_users_raw.empty:
        st.warning("Tidak ada user terdaftar.")
    else:
        mitra_df = df_users_raw[df_users_raw['role'] != 'pic'].sort_values(by='nama_lengkap')
        pic_df = df_users_raw[df_users_raw['role'] == 'pic'].sort_values(by='agency')
        
        type_choice = st.radio("Pilih Tipe User:", ["🛡️ Mitra Lapangan (Matel)", "🏦 PIC Leasing (Internal)"], horizontal=True)
        target_df = mitra_df if "Mitra" in type_choice else pic_df
        
        st.dataframe(target_df[['user_id', 'nama_lengkap', 'agency', 'no_hp', 'status', 'expiry_date']], use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.markdown("#### 🔧 Panel Eksekusi User")
        
        user_options = {f"{row['nama_lengkap']} - {row['agency']} (ID: {row['user_id']})": row['user_id'] for index, row in target_df.iterrows()}
        selected_label = st.selectbox("🎯 Pilih User untuk Diedit:", list(user_options.keys()))
        
        if selected_label:
            selected_uid = user_options[selected_label]
            user_detail = target_df[target_df['user_id'] == selected_uid].iloc[0]
            
            d1, d2, d3 = st.columns(3)
            d1.info(f"**Status:** {user_detail['status'].upper()}")
            d2.info(f"**Role:** {user_detail['role'].upper()}")
            d3.info(f"**Quota Exp:** {str(user_detail.get('expiry_date', '-'))[:10]}")
            
            c_act1, c_act2, c_act3 = st.columns(3)
            with c_act1:
                if st.button("➕ Tambah 30 Hari", type="primary"):
                    if add_user_quota(selected_uid, 30):
                        st.success(f"Masa aktif {user_detail['nama_lengkap']} ditambah 30 hari!")
                        time.sleep(1); st.rerun()
            with c_act2:
                if user_detail['status'] == 'active':
                    if st.button("⛔ BAN USER (Blokir)"):
                        update_user_status(selected_uid, 'banned')
                        st.warning(f"User {user_detail['nama_lengkap']} telah DIBLOKIR.")
                        time.sleep(1); st.rerun()
                else:
                    if st.button("✅ UNBAN (Aktifkan)"):
                        update_user_status(selected_uid, 'active')
                        st.success(f"User {user_detail['nama_lengkap']} telah DIAKTIFKAN.")
                        time.sleep(1); st.rerun()
            with c_act3:
                if st.button("🗑️ HAPUS PERMANEN"):
                    delete_user_permanent(selected_uid)
                    st.error(f"User {user_detail['nama_lengkap']} BERHASIL DIHAPUS selamanya.")
                    time.sleep(1); st.rerun()

# -----------------------------------------------------------------------------
# TAB 3: UPLOAD DATA (FULL LOGIC)
# -----------------------------------------------------------------------------
with tab3:
    st.subheader("📤 Upload Data Baru")
    
    if st.session_state['upload_success']:
        stats = st.session_state['last_stats']
        st.markdown(f"""<div class="success-box"><h2>✅ SUKSES!</h2><p>Data berhasil disimpan.</p></div>""", unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", f"{stats.get('total', 0):,}")
        c2.metric("Sukses", f"{stats.get('suc', 0):,}")
        c3.metric("Gagal", f"{stats.get('fail', 0):,}")
        c4.metric("Waktu", f"{stats.get('time', 0)}s")
        if st.button("⬅️ Upload Lagi"): st.session_state['upload_success'] = False; st.rerun()
    else:
        st.info("Support: Excel (.xlsx), CSV (.csv), Text (.txt)")
        uploaded_file = st.file_uploader("Drop File di sini", type=['xlsx','csv','txt'], key=f"up_{st.session_state['uploader_key']}")
        
        if uploaded_file:
            try:
                # 1. BACA FILE
                filename = uploaded_file.name.lower()
                if filename.endswith('.txt'):
                    try: df = pd.read_csv(uploaded_file, sep='\t', dtype=str, on_bad_lines='skip', encoding='utf-8')
                    except: df = pd.read_csv(uploaded_file, sep='\t', dtype=str, on_bad_lines='skip', encoding='latin1')
                elif filename.endswith('.csv'):
                    try: df = pd.read_csv(uploaded_file, sep=';', dtype=str, on_bad_lines='skip')
                    except: df = pd.read_csv(uploaded_file, sep=',', dtype=str, on_bad_lines='skip')
                else: 
                    df = pd.read_excel(uploaded_file, dtype=str)

                # 2. CLEANING
                df, found = smart_rename_columns(df)
                if 'nopol' not in df.columns: 
                    st.error("❌ Kolom NOPOL tidak ditemukan!")
                    st.stop()
                
                df['nopol'] = df['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
                df = df.drop_duplicates(subset=['nopol'], keep='last')
                if 'finance' not in df.columns: df['finance'] = "UNKNOWN"
                else: df['finance'] = df['finance'].apply(standardize_leasing_name)
                
                # Standardize Columns
                valid_cols = ['nopol', 'type', 'finance', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'branch']
                for c in valid_cols:
                    if c not in df.columns: df[c] = "-"
                    else: df[c] = df[c].fillna("-").replace(['nan','NaN','NULL',''], '-')

                st.success(f"Siap proses **{len(df):,}** data.")
                with st.expander("Preview"): st.dataframe(df[valid_cols].head())

                # 3. EKSEKUSI
                if st.button("🚀 EKSEKUSI DATABASE", type="primary"):
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

# -----------------------------------------------------------------------------
# TAB 4: HAPUS DATA (FULL LOGIC)
# -----------------------------------------------------------------------------
with tab4:
    st.subheader("🗑️ Hapus Data Massal")
    
    if st.session_state['delete_success']:
        stats = st.session_state['last_stats']
        st.markdown(f"""<div class="delete-box"><h2>🗑️ DATA TERHAPUS!</h2></div>""", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        c1.metric("Total Hapus", f"{stats.get('total', 0):,}")
        c2.metric("Waktu", f"{stats.get('time', 0)}s")
        if st.button("⬅️ Kembali"): st.session_state['delete_success'] = False; st.rerun()
    else:
        st.warning("Upload file berisi NOPOL yang akan dihapus permanen.")
        del_file = st.file_uploader("File List Hapus", type=['xlsx','csv','txt'], key="del_up")
        
        if del_file:
            try:
                filename = del_file.name.lower()
                if filename.endswith('.txt'):
                    try: df_del = pd.read_csv(del_file, sep='\t', dtype=str, on_bad_lines='skip', encoding='utf-8')
                    except: df_del = pd.read_csv(del_file, sep='\t', dtype=str, on_bad_lines='skip', encoding='latin1')
                elif filename.endswith('.csv'):
                    try: df_del = pd.read_csv(del_file, sep=';', dtype=str, on_bad_lines='skip')
                    except: df_del = pd.read_csv(del_file, sep=',', dtype=str, on_bad_lines='skip')
                else: 
                    df_del = pd.read_excel(del_file, dtype=str)

                df_del, found = smart_rename_columns(df_del)
                if 'nopol' not in df_del.columns: st.error("❌ Kolom NOPOL tidak ditemukan!"); st.stop()

                targets = df_del['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper().tolist()
                targets = list(set(targets))
                
                st.error(f"Terdeteksi **{len(targets):,}** Nopol untuk dihapus.")
                with st.expander("Lihat Sample"): st.write(targets[:20])

                if st.button("🔥 HAPUS PERMANEN", type="primary"):
                    progress_bar = st.progress(0); status_text = st.empty()
                    start_time = time.time()
                    BATCH_DEL = 200; total = len(targets)
                    
                    for i in range(0, total, BATCH_DEL):
                        batch = targets[i:i+BATCH_DEL]
                        try: supabase.table('kendaraan').delete().in_('nopol', batch).execute()
                        except: pass
                        progress_bar.progress(min((i + BATCH_DEL) / total, 1.0))
                    
                    st.session_state['last_stats'] = {'total': total, 'time': round(time.time() - start_time, 2)}
                    st.session_state['delete_success'] = True
                    st.rerun()
            except Exception as e: st.error(f"Error: {e}")