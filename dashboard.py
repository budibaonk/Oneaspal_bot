import streamlit as st
import pandas as pd
import time
import json
import os
from datetime import datetime, timedelta
from supabase import create_client, Client
from dotenv import load_dotenv

# --- 1. KONFIGURASI HALAMAN (MOBILE FRIENDLY) ---
st.set_page_config(
    page_title="One Aspal Commando",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="collapsed" # Sidebar tertutup di HP biar luas
)

# --- CSS KHUSUS MOBILE & UI ---
st.markdown("""
<style>
    /* Tombol Full Width & Ramah Jempol */
    .stButton>button { 
        width: 100%; 
        font-weight: bold; 
        border-radius: 12px; 
        height: 50px; 
        font-size: 16px;
        transition: transform 0.1s;
    }
    .stButton>button:active { transform: scale(0.98); }
    
    /* Card Style untuk Stats */
    div[data-testid="metric-container"] {
        background-color: #f8f9fa;
        border: 1px solid #e9ecef;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    /* Input Number Besar */
    div[data-testid="stNumberInput"] input { 
        font-size: 18px; 
        font-weight: bold; 
        color: #0d6efd; 
        text-align: center;
    }
    
    /* Login Screen Centering */
    .login-container { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 80vh; }
    
    /* Sembunyikan elemen pengganggu */
    footer {visibility: hidden;}
    #MainMenu {visibility: hidden;}
    
    /* Responsiveness text */
    @media (max-width: 640px) {
        h1 { font-size: 24px !important; }
        h3 { font-size: 18px !important; }
    }
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
        current_exp_str = res.data[0].get('expiry_date') if res.data else None
        now = datetime.utcnow()
        if current_exp_str:
            current_exp = datetime.fromisoformat(current_exp_str.replace('Z', ''))
            base_date = current_exp if current_exp > now else now
        else: base_date = now
        new_exp = base_date + timedelta(days=days)
        supabase.table('users').update({'expiry_date': new_exp.isoformat()}).eq('user_id', user_id).execute()
        return True
    except: return False

def delete_user_permanent(user_id):
    try: supabase.table('users').delete().eq('user_id', user_id).execute(); return True
    except: return False

# --- 5. UTILS ---
COLUMN_ALIASES = {'nopol': ['nopolisi','nopol','plat','no polisi'], 'finance': ['finance','leasing','mitra']} 
def standardize_leasing_name(name):
    clean = str(name).upper().strip().replace('"', '').replace("'", "")
    return "UNKNOWN" if clean in ['NAN', 'NULL', ''] else clean

def smart_rename_columns(df):
    new = {}
    df.columns = [str(c).strip().replace('"', '').replace("'", "").replace('\ufeff', '') for c in df.columns]
    for col in df.columns:
        clean = ''.join(e for e in str(col) if e.isalnum()).lower()
        renamed = False
        for std, aliases in COLUMN_ALIASES.items():
            if clean == std or clean in aliases:
                new[col] = std; renamed = True; break
        if not renamed: new[col] = col
    df.rename(columns=new, inplace=True)
    return df, df.columns

def render_logo(width=150):
    if os.path.exists("logo.png"):
        try: st.image("logo.png", width=width)
        except: st.markdown("<h1>🦅</h1>", unsafe_allow_html=True)
    else: st.markdown("<h1>🦅</h1>", unsafe_allow_html=True)

# --- 6. HALAMAN LOGIN (Mobile Centered) ---
def check_password():
    if st.session_state['password_input'] == ADMIN_PASSWORD:
        st.session_state['authenticated'] = True
        del st.session_state['password_input']
    else: st.error("⛔ Password Salah!")

if not st.session_state['authenticated']:
    col_ctr = st.columns([1, 8, 1])[1] # Kolom tengah lebar di HP
    with col_ctr:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        c_img = st.columns([1,1,1])[1]
        with c_img: render_logo(width=120)
        st.markdown("<h2 style='text-align: center;'>One Aspal Commando</h2>", unsafe_allow_html=True)
        st.text_input("Password Admin", type="password", key="password_input", on_change=check_password)
        if not ADMIN_PASSWORD: st.warning("⚠️ Setup .env dulu!")
    st.stop()

# --- 7. SIDEBAR (Hidden by default on mobile) ---
with st.sidebar:
    render_logo(width=150)
    st.markdown("### 🛠️ Menu Ops")
    if st.button("🔄 Refresh Data"): st.cache_data.clear(); st.rerun()
    if st.button("🚪 Logout"): st.session_state['authenticated'] = False; st.rerun()
    st.markdown("---")
    st.caption("Commando v5.0 (Mobile Ops)")

# --- 8. DASHBOARD HEADER ---
c1, c2 = st.columns([1, 5])
with c1: render_logo(width=60)
with c2:
    st.title("Command Center")
    st.caption("Management System")

# === STATS QUICK VIEW (Cards) ===
df_users_raw = get_all_users()
total_assets = get_total_asset_count()
mitra_count = len(df_users_raw[df_users_raw['role']!='pic']) if not df_users_raw.empty else 0
pic_count = len(df_users_raw[df_users_raw['role']=='pic']) if not df_users_raw.empty else 0

s1, s2, s3 = st.columns(3)
s1.metric("📂 Total Data", f"{total_assets:,}")
s2.metric("🛡️ Mitra", f"{mitra_count}")
s3.metric("🏦 PIC", f"{pic_count}")

st.markdown("---")

# === TABS UTAMA (FOKUS MANAGEMENT) ===
tab1, tab2, tab3 = st.tabs(["🛡️ USER", "📤 UPLOAD", "🗑️ HAPUS"])

# -----------------------------------------------------------------------------
# TAB 1: USER MANAGEMENT (MOBILE OPTIMIZED)
# -----------------------------------------------------------------------------
with tab1:
    if df_users_raw.empty:
        st.warning("Data user kosong.")
    else:
        # Pilihan Tipe User (Radio Button Horizontal)
        st.write("Pilih Divisi:")
        type_choice = st.radio("Divisi", ["🛡️ Mitra Lapangan", "🏦 PIC Leasing"], horizontal=True, label_visibility="collapsed")
        
        # Filter Data
        mitra_df = df_users_raw[df_users_raw['role'] != 'pic'].sort_values('nama_lengkap')
        pic_df = df_users_raw[df_users_raw['role'] == 'pic'].sort_values('agency')
        target_df = mitra_df if "Mitra" in type_choice else pic_df
        
        # Dropdown Search
        user_options = {f"{r['nama_lengkap']} ({r['agency']})": r['user_id'] for i, r in target_df.iterrows()}
        selected_label = st.selectbox("🎯 Cari Personil:", list(user_options.keys()))
        
        if selected_label:
            uid = user_options[selected_label]
            user = target_df[target_df['user_id'] == uid].iloc[0]
            
            # Kartu Info User
            st.info(f"**{user['nama_lengkap']}**\n\nAgency: {user['agency']}\nStatus: {user['status'].upper()}\nExp: {str(user.get('expiry_date','-'))[:10]}")
            
            # PANEL EKSEKUSI
            st.markdown("#### ⚡ Aksi Cepat")
            
            # 1. Topup Quota
            with st.container():
                c_in, c_btn = st.columns([1, 2])
                with c_in:
                    days = st.number_input("Hari", min_value=1, value=30, label_visibility="collapsed")
                with c_btn:
                    if st.button(f"➕ Tambah {days} Hari", type="primary"):
                        if add_user_quota(uid, days):
                            st.success("✅ Berhasil!"); time.sleep(1); st.rerun()
            
            st.write("") # Spacer
            
            # 2. Ban & Delete (Grid Layout)
            b1, b2 = st.columns(2)
            with b1:
                if user['status'] == 'active':
                    if st.button("⛔ Blokir"):
                        update_user_status(uid, 'banned'); st.warning("⛔ Diblokir!"); time.sleep(1); st.rerun()
                else:
                    if st.button("✅ Buka Blokir"):
                        update_user_status(uid, 'active'); st.success("✅ Aktif!"); time.sleep(1); st.rerun()
            with b2:
                if st.button("🗑️ Hapus User"):
                    delete_user_permanent(uid); st.error("🗑️ Dihapus!"); time.sleep(1); st.rerun()
                    
        st.markdown("---")
        with st.expander("📋 Lihat Semua Data User"):
            st.dataframe(target_df[['nama_lengkap','agency','no_hp','status']], use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------------
# TAB 2: UPLOAD DATA
# -----------------------------------------------------------------------------
with tab2:
    if st.session_state['upload_success']:
        stats = st.session_state['last_stats']
        st.success(f"✅ Masuk: {stats.get('suc',0):,} data")
        if st.button("Upload Lagi"): st.session_state['upload_success'] = False; st.rerun()
    else:
        st.caption("Support: Excel, CSV, TXT (Tab)")
        up_file = st.file_uploader("Pilih File", type=['xlsx','csv','txt'], key=f"up_{st.session_state['uploader_key']}")
        
        if up_file and st.button("🚀 EKSEKUSI UPLOAD", type="primary"):
            try:
                fname = up_file.name.lower()
                if fname.endswith('.txt'): df = pd.read_csv(up_file, sep='\t', dtype=str, on_bad_lines='skip')
                elif fname.endswith('.csv'): 
                    try: df = pd.read_csv(up_file, sep=';', dtype=str, on_bad_lines='skip')
                    except: df = pd.read_csv(up_file, sep=',', dtype=str, on_bad_lines='skip')
                else: df = pd.read_excel(up_file, dtype=str)
                
                df, _ = smart_rename_columns(df)
                if 'nopol' not in df.columns: st.error("❌ Tidak ada kolom NOPOL"); st.stop()
                
                df['nopol'] = df['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
                df = df.drop_duplicates(subset=['nopol'], keep='last')
                df['finance'] = df['finance'].apply(standardize_leasing_name)
                
                records = json.loads(json.dumps(df.to_dict(orient='records'), default=str))
                prog = st.progress(0); total = len(records); suc = 0
                
                for i in range(0, total, 1000):
                    batch = records[i:i+1000]
                    try: supabase.table('kendaraan').upsert(batch, on_conflict='nopol', count=None).execute(); suc += len(batch)
                    except: pass
                    prog.progress(min((i+1000)/total, 1.0))
                
                st.session_state['last_stats'] = {'suc': suc}
                st.session_state['upload_success'] = True; st.rerun()
            except Exception as e: st.error(f"Error: {e}")

# -----------------------------------------------------------------------------
# TAB 3: HAPUS DATA
# -----------------------------------------------------------------------------
with tab3:
    if st.session_state['delete_success']:
        st.success("✅ Data Terhapus!")
        if st.button("Hapus Lagi"): st.session_state['delete_success'] = False; st.rerun()
    else:
        st.warning("⚠️ Upload list NOPOL yang akan dihapus.")
        del_file = st.file_uploader("File List Hapus", type=['xlsx','csv','txt'], key="del_up")
        
        if del_file and st.button("🔥 HAPUS PERMANEN"):
            try:
                fname = del_file.name.lower()
                if fname.endswith('.txt'): df_del = pd.read_csv(del_file, sep='\t', dtype=str, on_bad_lines='skip')
                elif fname.endswith('.csv'): 
                    try: df_del = pd.read_csv(del_file, sep=';', dtype=str, on_bad_lines='skip')
                    except: df_del = pd.read_csv(del_file, sep=',', dtype=str, on_bad_lines='skip')
                else: df_del = pd.read_excel(del_file, dtype=str)
                
                df_del, _ = smart_rename_columns(df_del)
                if 'nopol' not in df_del.columns: st.error("❌ Tidak ada kolom NOPOL"); st.stop()
                
                targets = list(set(df_del['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper().tolist()))
                prog = st.progress(0); total = len(targets)
                
                for i in range(0, total, 200):
                    batch = targets[i:i+200]
                    try: supabase.table('kendaraan').delete().in_('nopol', batch).execute()
                    except: pass
                    prog.progress(min((i+200)/total, 1.0))
                
                st.session_state['delete_success'] = True; st.rerun()
            except Exception as e: st.error(f"Error: {e}")