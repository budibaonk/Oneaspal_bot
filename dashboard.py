import streamlit as st
import pandas as pd
import time
import json
import os
from datetime import datetime, timedelta
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
    .stButton>button { width: 100%; font-weight: bold; border-radius: 8px; height: 45px; transition: all 0.3s; }
    .success-box { padding: 15px; background-color: #d1e7dd; color: #0f5132; border-radius: 10px; text-align: center; margin-bottom: 15px; border: 1px solid #badbcc; }
    .warning-box { padding: 15px; background-color: #fff3cd; color: #856404; border-radius: 10px; text-align: center; margin-bottom: 15px; border: 1px solid #ffeeba; }
    div[data-testid="column"] { display: flex; align-items: center; justify-content: center; }
    footer {visibility: hidden;}
    /* Highlight Input Number */
    div[data-testid="stNumberInput"] input { font-weight: bold; color: #1f77b4; }
</style>
""", unsafe_allow_html=True)

# --- 2. KONEKSI & SETUP ---
load_dotenv()
URL = os.getenv("SUPABASE_URL")
KEY = os.getenv("SUPABASE_KEY")
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

# --- 4. FUNGSI DATABASE ---
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
        current_exp_str = res.data[0].get('expiry_date') if res.data else None
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

@st.cache_data(ttl=60) # Cache pendek agar update cepat
def get_leasing_list_clean():
    try:
        # Ambil data sample besar
        res = supabase.table('kendaraan').select('finance').order('created_at', desc=True).limit(50000).execute()
        df = pd.DataFrame(res.data)
        if df.empty: return pd.DataFrame()
        
        # CLEANING DATA (Buang Sampah)
        junk = ['TRUE','FALSE','NAN','NONE','UNKNOWN','-','']
        df['finance'] = df['finance'].astype(str).str.upper().str.strip()
        df = df[~df['finance'].isin(junk)]
        
        # HITUNG & URUTKAN (LIST)
        counts = df['finance'].value_counts().reset_index()
        counts.columns = ['Nama Leasing', 'Jumlah Data']
        counts = counts.sort_values(by='Jumlah Data', ascending=False).reset_index(drop=True)
        # Tambah nomor urut (Rank)
        counts.index += 1
        return counts
    except: return pd.DataFrame()

# --- 5. UTILS ---
COLUMN_ALIASES = {'nopol': ['nopolisi','nopol','plat','no polisi'], 'finance': ['finance','leasing','mitra']} 
def normalize_text(text): return ''.join(e for e in str(text) if e.isalnum()).lower()

def smart_rename_columns(df):
    new = {}
    df.columns = [str(c).strip().replace('"', '').replace("'", "").replace('\ufeff', '') for c in df.columns]
    for col in df.columns:
        clean = normalize_text(col)
        renamed = False
        for std, aliases in COLUMN_ALIASES.items():
            if clean == std or clean in aliases:
                new[col] = std; renamed = True; break
        if not renamed: new[col] = col
    df.rename(columns=new, inplace=True)
    return df, df.columns

def standardize_leasing_name(name):
    clean = str(name).upper().strip().replace('"', '').replace("'", "")
    return "UNKNOWN" if clean in ['NAN', 'NULL', ''] else clean

def render_logo(width=150):
    if os.path.exists("logo.png"):
        try: st.image("logo.png", width=width)
        except: st.markdown("# 🦅")
    else: st.markdown("# 🦅")

# --- 6. HALAMAN LOGIN ---
def check_password():
    if st.session_state['password_input'] == ADMIN_PASSWORD:
        st.session_state['authenticated'] = True
        del st.session_state['password_input']
    else: st.error("⛔ Password Salah!")

if not st.session_state['authenticated']:
    c1,c2,c3 = st.columns([1,1,1])
    with c2:
        st.write(""); st.write(""); st.write("")
        c_img1, c_img2, c_img3 = st.columns([1,2,1])
        with c_img2: render_logo(width=180)
        st.markdown("<h3 style='text-align: center;'>One Aspal Commando</h3>", unsafe_allow_html=True)
        st.text_input("Password", type="password", key="password_input", on_change=check_password)
        if not ADMIN_PASSWORD: st.warning("⚠️ Setup .env ADMIN_PASSWORD dulu!")
    st.stop()

# --- 7. SIDEBAR ---
with st.sidebar:
    render_logo(width=200)
    st.markdown("---")
    if st.button("🚪 LOGOUT", type="secondary"):
        st.session_state['authenticated'] = False; st.rerun()
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()
    st.markdown("---")
    st.info("Status: **Online** 🟢")

# --- 8. DASHBOARD HEADER ---
c_h1, c_h2 = st.columns([1, 6])
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

# === TABS ===
tab1, tab2, tab3, tab4 = st.tabs(["📊 LIST LEASING", "🛡️ MANAJEMEN PERSONIL", "📤 UPLOAD DATA", "🗑️ HAPUS DATA"])

# -----------------------------------------------------------------------------
# TAB 1: LIST LEASING (SIMPLE TABLE)
# -----------------------------------------------------------------------------
with tab1:
    st.subheader("📊 Peringkat Data Leasing (Terbanyak)")
    
    df_leasing = get_leasing_list_clean()
    
    if not df_leasing.empty:
        # Tampilkan sebagai Tabel Interaktif yang Rapi
        st.dataframe(
            df_leasing,
            use_container_width=True,
            column_config={
                "Nama Leasing": st.column_config.TextColumn("Nama Leasing (Agency)"),
                "Jumlah Data": st.column_config.ProgressColumn(
                    "Volume Data",
                    format="%d",
                    min_value=0,
                    max_value=int(df_leasing['Jumlah Data'].max()),
                ),
            },
            height=600
        )
    else:
        st.info("Data belum tersedia atau sedang loading...")

# -----------------------------------------------------------------------------
# TAB 2: MANAJEMEN PERSONIL (INPUT MANUAL EXPLICIT)
# -----------------------------------------------------------------------------
with tab2:
    st.subheader("🛡️ Kontrol Personil & Mitra")
    
    if df_users_raw.empty:
        st.warning("Tidak ada user.")
    else:
        mitra_df = df_users_raw[df_users_raw['role'] != 'pic'].sort_values(by='nama_lengkap')
        pic_df = df_users_raw[df_users_raw['role'] == 'pic'].sort_values(by='agency')
        
        type_choice = st.radio("Pilih Tipe:", ["🛡️ Mitra Lapangan", "🏦 PIC Leasing"], horizontal=True)
        target_df = mitra_df if "Mitra" in type_choice else pic_df
        
        st.dataframe(target_df[['user_id','nama_lengkap','agency','no_hp','status','expiry_date']], use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.markdown("### 🔧 EDIT USER")
        
        user_options = {f"{row['nama_lengkap']} - {row['agency']}": row['user_id'] for index, row in target_df.iterrows()}
        selected_label = st.selectbox("🎯 Pilih User:", list(user_options.keys()))
        
        if selected_label:
            selected_uid = user_options[selected_label]
            user_detail = target_df[target_df['user_id'] == selected_uid].iloc[0]
            
            # Info Box
            st.info(f"User: **{user_detail['nama_lengkap']}** | Status: **{user_detail['status']}** | Exp: **{str(user_detail.get('expiry_date','-'))[:10]}**")
            
            # --- BAGIAN INPUT MANUAL (DIBUAT SANGAT JELAS) ---
            st.markdown("#### 1. Tambah Masa Aktif (Topup)")
            
            c_input, c_btn = st.columns([1, 2])
            with c_input:
                # INPUT MANUAL DISINI
                days_input = st.number_input("Ketik Jumlah Hari:", min_value=1, value=30, step=1)
            with c_btn:
                st.write("") # Spacer biar tombol sejajar
                st.write("") 
                if st.button(f"➕ TAMBAH {days_input} HARI", type="primary"):
                    if add_user_quota(selected_uid, days_input):
                        st.success(f"✅ SUKSES! {user_detail['nama_lengkap']} +{days_input} Hari.")
                        time.sleep(2); st.rerun()
                    else: st.error("Gagal.")
            
            st.divider()
            
            # --- BAGIAN ACTION LAIN ---
            st.markdown("#### 2. Tindakan Lanjutan")
            c_ban, c_del = st.columns(2)
            
            with c_ban:
                if user_detail['status'] == 'active':
                    if st.button("⛔ BLOKIR USER (BAN)"):
                        update_user_status(selected_uid, 'banned')
                        st.warning("⛔ User DIBLOKIR."); time.sleep(2); st.rerun()
                else:
                    if st.button("✅ AKTIFKAN USER (UNBAN)"):
                        update_user_status(selected_uid, 'active')
                        st.success("✅ User DIAKTIFKAN."); time.sleep(2); st.rerun()
            
            with c_del:
                if st.button("🗑️ HAPUS PERMANEN"):
                    delete_user_permanent(selected_uid)
                    st.error("🗑️ User DIHAPUS."); time.sleep(2); st.rerun()

# -----------------------------------------------------------------------------
# TAB 3: UPLOAD
# -----------------------------------------------------------------------------
with tab3:
    st.subheader("📤 Upload Data")
    if st.session_state['upload_success']:
        stats = st.session_state['last_stats']
        st.success(f"✅ Selesai! Total: {stats.get('total',0):,} | Sukses: {stats.get('suc',0):,}")
        if st.button("Upload Lagi"): st.session_state['upload_success'] = False; st.rerun()
    else:
        uploaded_file = st.file_uploader("File Excel/CSV/TXT", type=['xlsx','csv','txt'], key=f"up_{st.session_state['uploader_key']}")
        if uploaded_file and st.button("🚀 EKSEKUSI"):
            try:
                fname = uploaded_file.name.lower()
                if fname.endswith('.txt'):
                    try: df = pd.read_csv(uploaded_file, sep='\t', dtype=str, on_bad_lines='skip')
                    except: df = pd.read_csv(uploaded_file, sep=',', dtype=str, on_bad_lines='skip')
                elif fname.endswith('.csv'):
                    try: df = pd.read_csv(uploaded_file, sep=';', dtype=str, on_bad_lines='skip')
                    except: df = pd.read_csv(uploaded_file, sep=',', dtype=str, on_bad_lines='skip')
                else: df = pd.read_excel(uploaded_file, dtype=str)
                
                df, _ = smart_rename_columns(df)
                if 'nopol' not in df.columns: st.error("No Nopol Column"); st.stop()
                
                df['nopol'] = df['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
                df = df.drop_duplicates(subset=['nopol'], keep='last')
                df['finance'] = df['finance'].apply(standardize_leasing_name)
                
                records = json.loads(json.dumps(df.to_dict(orient='records'), default=str))
                prog = st.progress(0); total = len(records); suc = 0; fail = 0; start = time.time()
                
                for i in range(0, total, 1000):
                    batch = records[i:i+1000]
                    try: supabase.table('kendaraan').upsert(batch, on_conflict='nopol', count=None).execute(); suc += len(batch)
                    except: fail += len(batch)
                    prog.progress(min((i+1000)/total, 1.0))
                
                st.session_state['last_stats'] = {'total': total, 'suc': suc, 'fail': fail, 'time': round(time.time()-start, 2)}
                st.session_state['upload_success'] = True; st.rerun()
            except Exception as e: st.error(str(e))

# -----------------------------------------------------------------------------
# TAB 4: HAPUS
# -----------------------------------------------------------------------------
with tab4:
    st.subheader("🗑️ Hapus Data")
    if st.session_state['delete_success']:
        st.success("✅ Data Terhapus!")
        if st.button("Kembali"): st.session_state['delete_success'] = False; st.rerun()
    else:
        del_file = st.file_uploader("File List Hapus", type=['xlsx','csv','txt'], key="del_up")
        if del_file and st.button("🔥 HAPUS PERMANEN"):
            try:
                fname = del_file.name.lower()
                if fname.endswith('.txt'): df_del = pd.read_csv(del_file, sep='\t', dtype=str, on_bad_lines='skip')
                elif fname.endswith('.csv'): df_del = pd.read_csv(del_file, sep=';', dtype=str, on_bad_lines='skip')
                else: df_del = pd.read_excel(del_file, dtype=str)
                
                df_del, _ = smart_rename_columns(df_del)
                if 'nopol' not in df_del.columns: st.error("No Nopol"); st.stop()
                
                targets = list(set(df_del['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper().tolist()))
                prog = st.progress(0); total = len(targets); start = time.time()
                
                for i in range(0, total, 200):
                    batch = targets[i:i+200]
                    try: supabase.table('kendaraan').delete().in_('nopol', batch).execute()
                    except: pass
                    prog.progress(min((i+200)/total, 1.0))
                
                st.session_state['last_stats'] = {'total': total, 'time': round(time.time()-start, 2)}
                st.session_state['delete_success'] = True; st.rerun()
            except Exception as e: st.error(str(e))