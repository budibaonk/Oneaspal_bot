import os
import time
import requests
from supabase import create_client
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Init
load_dotenv()

# --- KONFIGURASI SINKRON (Sesuai main.py) ---
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
TOKEN = os.environ.get("TELEGRAM_TOKEN") # Sesuai variabel Komandan

# --- BATAS AMAN ANTI-SPAM ---
BATCH_SIZE = 20      
SLEEP_TIME = 2.0     

def get_recap_data():
    """Mengambil Data Log Terbaru (Bukan cuma kemarin)"""
    if not URL or not KEY: return None, None, 0
    supabase = create_client(URL, KEY)
    
    # Ambil tanggal hari ini untuk display laporan
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    try:
        # KUNCI: Kita ambil data yang 'updated_at' nya dalam 24 jam terakhir
        # Ini akan menangkap data baru DAN data lama yang di-update stamp-nya
        res = supabase.table('riwayat_upload_kendaraan')\
            .select('leasing, jumlah, updated_at')\
            .gte('updated_at', (datetime.now() - timedelta(days=1)).isoformat())\
            .execute()
        
        if not res.data: return None, today_str, 0
        
        rekap = {}
        total_all = 0
        for item in res.data:
            l = item['leasing']; j = item['jumlah']
            rekap[l] = rekap.get(l, 0) + j
            total_all += j
            
        return rekap, today_str, total_all
    except Exception as e:
        print(f"❌ Error DB: {e}")
        return None, today_str, 0

def get_all_users():
    """Ambil ID User dari tabel users (kolom telegram_id atau user_id)"""
    # Catatan: Sesuaikan kolom 'user_id' di bawah jika di tabel Komandan namanya 'telegram_id'
    if not URL or not KEY: return []
    try:
        supabase = create_client(URL, KEY)
        res = supabase.table('users').select('user_id').execute()
        ids = set()
        for u in res.data:
            if u.get('user_id'): ids.add(u['user_id'])
        return list(ids)
    except: return []

def send_message(chat_id, text):
    """Kirim pesan via API Telegram"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=5)
        return r.status_code == 200
    except: return False

def main():
    print("🦅 MEMULAI BROADCAST HARIAN...")
    
    if not TOKEN:
        print("❌ ERROR: TELEGRAM_TOKEN tidak ditemukan.")
        return

    # 1. SIAPKAN DATA
    rekap, tgl_kemarin, total = get_recap_data()
    
    if not rekap:
        print(f"✅ Tidak ada update data kendaraan pada {tgl_kemarin}.")
        return

    tgl_display = datetime.strptime(tgl_kemarin, '%Y-%m-%d').strftime('%d %B %Y')

    # 2. SUSUN PESAN
    msg = [f"☀️ <b>SEMANGAT PAGI, MITRA B-ONE!</b> 🦅"]
    msg.append(f"<i>Laporan Update Data Kendaraan: {tgl_display}</i>\n")
    for leasing, jml in rekap.items():
        msg.append(f"📂 <b>{leasing}:</b> +{jml:,} Unit")
    msg.append(f"\n📈 <b>TOTAL UPDATE: {total:,} UNIT BARU!</b>")
    msg.append(f"<i>Data sudah siap di sistem. Gasspoll!</i> 🔥")
    final_msg = "\n".join(msg)

    # 3. KIRIM PESAN (ANTI-SPAM)
    users = get_all_users()
    print(f"🎯 Target: {len(users)} User")

    sukses = 0
    for i, uid in enumerate(users):
        if send_message(uid, final_msg): sukses += 1
        print(f"\r⏳ Progress: {i+1}/{len(users)}", end="")
        if (i + 1) % BATCH_SIZE == 0:
            time.sleep(SLEEP_TIME)

    print(f"\n✅ SELESAI! Terkirim ke {sukses} user.")

if __name__ == "__main__":
    main()