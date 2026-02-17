import os
from supabase import create_client
from dotenv import load_dotenv

# Load Environment Variables
load_dotenv()

def catat_log_kendaraan(sumber, leasing, jumlah):
    """Mencatat riwayat penambahan data kendaraan ke database log."""
    # Menyesuaikan dengan variabel di main.py Komandan
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    
    if not url or not key:
        print("❌ LOG ERROR: SUPABASE_URL atau SUPABASE_KEY tidak ditemukan.")
        return
        
    try:
        supabase = create_client(url, key)
        payload = {
            "sumber": sumber,
            "leasing": str(leasing).upper(),
            "jumlah": int(jumlah)
        }
        # Mengirim ke tabel riwayat_upload_kendaraan
        supabase.table("riwayat_upload_kendaraan").insert(payload).execute()
        print(f"📝 Log Recorded: {leasing} (+{jumlah}) via {sumber}")
    except Exception as e:
        print(f"⚠️ Log Error: {e}")