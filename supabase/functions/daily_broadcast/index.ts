import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const TOKEN_RAW = Deno.env.get('TELEGRAM_TOKEN') || "";
const TOKEN = TOKEN_RAW.trim(); 
const SUPABASE_URL = Deno.env.get('SUPABASE_URL')
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')

Deno.serve(async (req: Request) => {
  const supabase = createClient(SUPABASE_URL!, SUPABASE_SERVICE_ROLE_KEY!)
  const url = new URL(req.url);
  const batch = parseInt(url.searchParams.get("batch") || "1");
  const limit = 100;
  const offset = (batch - 1) * limit;

  // 1. Ambil Data HANYA 48 Jam Terakhir
  const filterDate = new Date(Date.now() - 48 * 60 * 60 * 1000).toISOString();
  
  const { data: logs } = await supabase
    .from('riwayat_upload_kendaraan')
    .select('leasing, jumlah')
    .gte('created_at', filterDate);

  if (!logs || logs.length === 0) {
    return new Response(JSON.stringify({ status: "Empty", message: "Tidak ada update data dalam 48 jam terakhir." }));
  }

  // Logika Menjumlahkan (Grouping) Total per Leasing dari data 48 jam terakhir
  const totals: { [key: string]: number } = {};
  let grandTotal = 0;

  logs.forEach((log: any) => {
    const leasingName = log.leasing.toUpperCase();
    totals[leasingName] = (totals[leasingName] || 0) + (log.jumlah || 0);
    grandTotal += (log.jumlah || 0);
  });

  // Susun Teks Rekap
  const rekapText = Object.entries(totals)
    .map(([name, total]) => `📂 <b>${name}:</b> +${total.toLocaleString()} Unit`)
    .join('\n');

  const finalMsg = `☀️ <b>SEMANGAT PAGI, MITRA B-ONE!</b> 🦅\n\n` +
                   `<i>Laporan Update Data (48 Jam Terakhir):</i>\n\n` +
                   `${rekapText}\n\n` +
                   `📈 <b>TOTAL UPDATE: ${grandTotal.toLocaleString()} UNIT BARU!</b>\n\n` +
                   `<i>Data sudah siap di sistem. Gasspoll!</i> 🔥`;

  // 2. Ambil User (Order pendaftar pertama)
  const { data: users } = await supabase.from('users')
    .select('user_id')
    .order('created_at', { ascending: true })
    .range(offset, offset + limit - 1);

  if (!users || users.length === 0) return new Response("No Users");

  // 3. Eksekusi Kirim dengan JEDA ANTI-SPAM
  let count = 0;
  const telegramUrl = `https://api.telegram.org/bot${TOKEN}/sendMessage`;

  for (const user of users) {
    try {
      const res = await fetch(telegramUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: user.user_id, text: finalMsg, parse_mode: 'HTML' })
      });

      if (res.ok) count++;

      // JEDA ANTI-SPAM
      await new Promise(r => setTimeout(r, 100)); // Jeda 0.1 detik antar pesan
      if (count % 30 === 0) {
        await new Promise(r => setTimeout(r, 3000)); // Napas 3 detik setiap 30 pesan
      }
      
    } catch (e) {
      console.error(`Gagal ke ${user.user_id}`);
    }
  }

  return new Response(`BERHASIL: Update 48 jam terkirim ke ${count} user.`);
})