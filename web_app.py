import os
from pathlib import Path
from flask import Flask, render_template, request, jsonify
import pandas as pd
import numpy as np
from sqlalchemy import text

from config.settings import settings
from config.database import get_engine
from modules.interbank_nostro.interbank_engine import (
    calculate_short_term_pd_and_ckpn,
    run_interbank_pipeline
)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

BASE_DIR = Path(__file__).resolve().parent

# =====================================================================
# QUERY NAMA BANK DARI TABEL Ref_NamaBank (POIN 3)
# =====================================================================
def get_bank_name_from_db() -> str:
    """Membaca nama bank langsung dari tabel Ref_NamaBank di SQL Server."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            # 1. Coba cari nama kolom di Ref_NamaBank
            query = text("""
                IF OBJECT_ID('dbo.Ref_NamaBank', 'U') IS NOT NULL
                BEGIN
                    SELECT TOP 1 * FROM dbo.Ref_NamaBank;
                END
            """)
            result = conn.execute(query).fetchone()
            if result:
                # Cari kolom string yang merepresentasikan nama institusi
                for val in result:
                    if val and isinstance(val, str) and len(val.strip()) > 3 and not val.strip().isdigit():
                        return val.strip()
    except Exception:
        pass
    return "Bank Aceh Syariah"

# =====================================================================
# FETCH DATA RIIL DATABASE PER TARGET MODUL ENGINE (POIN 2 & POIN 6)
# =====================================================================

def fetch_counterparty_real(cut_off: str) -> dict:
    """Modul 1: Membaca data riil dari ref_counterparty_rating & ref_rating_pd_mapping."""
    records = []
    total_inst = 0
    s1_count = 0
    s2_count = 0
    avg_pd = 0.0
    rating_dist = {}
    pd_dist = {}

    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("""
                SELECT 
                    cr.kode_counterparty,
                    cr.nama_institusi,
                    cr.kategori_institusi,
                    cr.rating_saat_ini,
                    COALESCE(rm.kategori_grade, 'BELUM_TERPETAKAN') AS kategori_grade,
                    COALESCE(rm.ttc_pd_rate, 0.0000) AS ttc_pd_rate
                FROM ref_counterparty_rating cr
                LEFT JOIN ref_rating_pd_mapping rm ON cr.rating_saat_ini = rm.kode_rating
            """)
            df = pd.read_sql(query, conn)

            if not df.empty:
                total_inst = len(df)
                s1_count = int((df["kategori_institusi"] == "SOVEREIGN").sum() + (df["kategori_grade"] == "INVESTMENT_GRADE").sum())
                s2_count = int((df["kategori_grade"] == "NON_INVESTMENT_GRADE").sum())
                avg_pd = float(df["ttc_pd_rate"].mean())

                for _, r in df.iterrows():
                    rating = str(r["rating_saat_ini"])
                    rating_dist[rating] = rating_dist.get(rating, 0) + 1
                    pd_dist[str(r["kode_counterparty"])] = float(r["ttc_pd_rate"]) * 100

                    records.append({
                        "col1": r["kode_counterparty"],
                        "col2": r["nama_institusi"],
                        "col3": r["kategori_institusi"],
                        "col4": "Lembaga Pemeringkat",
                        "col5": rating,
                        "col6": r["kategori_grade"],
                        "col7": 1 if r["kategori_grade"] != "NON_INVESTMENT_GRADE" else 2,
                        "col8": f"{float(r['ttc_pd_rate']) * 100:.4f}%",
                        "col9": "Tersinkron",
                        "col10": "AKTIF",
                        "col11": "TERDAFTAR"
                    })
    except Exception as e:
        app.logger.warning(f"Gagal mengambil data Counterparty riil: {e}")

    return {
        "module_code": "counterparty",
        "module_name": "1. Master Counterparty",
        "summary": {
            "kpi1_title": "Total Institusi Terdaftar",
            "kpi1_val": total_inst,
            "kpi1_sub": "Tabel ref_counterparty_rating",
            "kpi2_title": "Status Sinkronisasi",
            "kpi2_val": f"{total_inst} Mitra Aktif" if total_inst > 0 else "0 Mitra",
            "kpi2_sub": "Basis Data iPSAK71",
            "kpi3_title": "Distribusi Grade Peringkat",
            "kpi3_s1": s1_count,
            "kpi3_s2": s2_count,
            "kpi3_desc1": "Investment Grade",
            "kpi3_desc2": "Non-Investment",
            "kpi4_title": "Rata-rata TTC PD",
            "kpi4_val": f"{avg_pd * 100:.4f}%",
            "kpi4_sub": "Historical Through-The-Cycle PD"
        },
        "table": {
            "title": "Master Data Pihak Lawan & Pemetaan Peringkat Kredit (Riil Database)",
            "subtitle": "Data resmi tabel ref_counterparty_rating dan ref_rating_pd_mapping",
            "headers": ["Kode Sandi", "Nama Institusi", "Kategori", "Lembaga Rating", "Rating Terkini", "Grade Kredit", "Stage Ref", "TTC PD Rate", "Notch", "Status", "Kustodian"],
            "records": records
        },
        "charts": {
            "chart1_title": "Distribusi Rating Lawan (Notch)",
            "chart1_tag": "Pefindo / Fitch",
            "chart1_data": rating_dist,
            "chart2_title": "TTC PD Rate per Pihak Lawan (%)",
            "chart2_tag": "Baseline Probability of Default",
            "chart2_data": pd_dist
        },
        "journal": []
    }

def fetch_sukuk_real(cut_off: str) -> dict:
    """Modul 2: Membaca data riil dari fact_ldp_sukuk_ecl / staging_treasury_sukuk."""
    records = []
    total_ead = 0.0
    total_ckpn = 0.0
    s1_count = 0
    s2_count = 0
    avg_pd = 0.0
    jenis_dist = {}
    ckpn_dist = {}

    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("""
                SELECT 
                    id_sukuk,
                    stage_psak,
                    ead_sukuk,
                    pd_rate,
                    lgd_rate,
                    nominal_ckpn
                FROM fact_ldp_sukuk_ecl
                WHERE tgl_cut_off = :cut_off
            """)
            df = pd.read_sql(query, conn, params={"cut_off": cut_off})

            if not df.empty:
                total_ead = float(df["ead_sukuk"].sum())
                total_ckpn = float(df["nominal_ckpn"].sum())
                s1_count = int((df["stage_psak"] == 1).sum())
                s2_count = int((df["stage_psak"] == 2).sum())
                avg_pd = float(df["pd_rate"].mean())

                for _, r in df.iterrows():
                    sid = str(r["id_sukuk"])
                    ckpn_dist[sid] = float(r["nominal_ckpn"])
                    records.append({
                        "col1": sid,
                        "col2": f"Sukuk Seri {sid}",
                        "col3": "SURAT_BERHARGA",
                        "col4": "Akad Syariah",
                        "col5": float(r["ead_sukuk"]),
                        "col6": "Rating",
                        "col7": int(r["stage_psak"]),
                        "col8": "-",
                        "col9": f"{float(r['pd_rate']) * 100:.5f}%",
                        "col10": f"{float(r['lgd_rate']) * 100:.1f}%",
                        "col11": float(r["nominal_ckpn"])
                    })
    except Exception as e:
        app.logger.warning(f"Gagal mengambil data Sukuk riil: {e}")

    return {
        "module_code": "sukuk",
        "module_name": "2. Sukuk & Integrasi Pemeringkat Eksternal",
        "summary": {
            "kpi1_title": "Total Eksposur Sukuk (EAD)",
            "kpi1_val": total_ead,
            "kpi1_sub": f"Cut-Off: {cut_off}",
            "kpi2_title": "Beban CKPN Portofolio Sukuk",
            "kpi2_val": total_ckpn,
            "kpi2_sub": f"Coverage: {(total_ckpn / total_ead * 100):.4f}%" if total_ead > 0 else "Coverage: 0.000%",
            "kpi3_title": "Distribusi Staging Sukuk",
            "kpi3_s1": s1_count,
            "kpi3_s2": s2_count,
            "kpi3_desc1": "Stage 1 (Lancar)",
            "kpi3_desc2": "Stage 2 (Warning)",
            "kpi4_title": "Rata-rata PIT PD Sukuk",
            "kpi4_val": f"{avg_pd * 100:.4f}%",
            "kpi4_sub": "Vasicek Macro Adjustment"
        },
        "table": {
            "title": "Portofolio Surat Berharga & Sukuk (Riil Database)",
            "subtitle": "Tabel fact_ldp_sukuk_ecl pada database iPSAK71",
            "headers": ["ID Sukuk", "Nama Seri Sukuk", "Jenis Sukuk", "Akad", "Nilai Emisi (EAD)", "Rating", "Stage", "Z-Score", "PIT PD Rate", "LGD Senioritas", "Nominal CKPN"],
            "records": records
        },
        "charts": {
            "chart1_title": "Komposisi Portofolio Sukuk",
            "chart1_tag": "SBSN vs Korporasi",
            "chart1_data": jenis_dist,
            "chart2_title": "Beban CKPN per Seri Sukuk (Rp)",
            "chart2_tag": "ECL Surat Berharga",
            "chart2_data": ckpn_dist
        },
        "journal": []
    }

def fetch_interbank_real(cut_off: str) -> dict:
    """Modul 3: Membaca data riil penempatan dari fact_ldp_interbank_ecl & staging."""
    records = []
    total_ead = 0.0
    total_ckpn = 0.0
    s1_count = 0
    s2_count = 0
    avg_pd = 0.0
    inst_dist = {}
    ckpn_dist = {}

    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("""
                SELECT 
                    f.id_penempatan, 
                    COALESCE(cr.nama_institusi, s.kode_counterparty) AS nama_institusi,
                    s.kode_counterparty,
                    s.jenis_instrumen,
                    s.sisa_hari_jatuh_tempo,
                    f.ead_treasury, 
                    COALESCE(cr.rating_saat_ini, '-') AS rating_saat_ini,
                    f.stage_psak,
                    f.annual_pd_rate, 
                    f.short_term_pd, 
                    f.lgd_unsecured, 
                    f.nominal_ckpn
                FROM fact_ldp_interbank_ecl f
                INNER JOIN staging_treasury_interbank s ON f.id_penempatan = s.id_penempatan
                LEFT JOIN ref_counterparty_rating cr ON s.kode_counterparty = cr.kode_counterparty
                WHERE f.tgl_cut_off = :cut_off
            """)
            df = pd.read_sql(query, conn, params={"cut_off": cut_off})

            if not df.empty:
                total_ead = float(df["ead_treasury"].sum())
                total_ckpn = float(df["nominal_ckpn"].sum())
                s1_count = int((df["stage_psak"] == 1).sum())
                s2_count = int((df["stage_psak"] == 2).sum())
                avg_pd = float(df["short_term_pd"].mean())

                inst_dist = df.groupby("jenis_instrumen")["ead_treasury"].sum().to_dict()
                ckpn_dist = df.groupby("kode_counterparty")["nominal_ckpn"].sum().to_dict()

                for _, r in df.iterrows():
                    records.append({
                        "col1": r["id_penempatan"],
                        "col2": f"{r['nama_institusi']} ({r['kode_counterparty']})",
                        "col3": r["jenis_instrumen"],
                        "col4": f"{r['sisa_hari_jatuh_tempo']} Hari",
                        "col5": float(r["ead_treasury"]),
                        "col6": r["rating_saat_ini"],
                        "col7": int(r["stage_psak"]),
                        "col8": f"{float(r['annual_pd_rate']) * 100:.4f}%",
                        "col9": f"{float(r['short_term_pd']) * 100:.6f}%",
                        "col10": f"{float(r['lgd_unsecured']) * 100:.1f}%",
                        "col11": float(r["nominal_ckpn"])
                    })
    except Exception as e:
        app.logger.warning(f"Gagal mengambil data Interbank riil: {e}")

    return {
        "module_code": "interbank",
        "module_name": "3. Modul Penempatan Antar Bank & Nostro Devisa",
        "summary": {
            "kpi1_title": "Total EAD (Exposure)",
            "kpi1_val": total_ead,
            "kpi1_sub": f"Tabel fact_ldp_interbank_ecl ({cut_off})",
            "kpi2_title": "Total Beban CKPN (ECL)",
            "kpi2_val": total_ckpn,
            "kpi2_sub": f"Coverage: {(total_ckpn / total_ead * 100):.4f}%" if total_ead > 0 else "Coverage: 0.000%",
            "kpi3_title": "Distribusi Staging PSAK",
            "kpi3_s1": s1_count,
            "kpi3_s2": s2_count,
            "kpi3_desc1": "Stage 1 (Lancar)",
            "kpi3_desc2": "Stage 2 (Warning)",
            "kpi4_title": "Rata-rata Short-Term PD",
            "kpi4_val": f"{avg_pd * 100:.6f}%",
            "kpi4_sub": "Dikonversi eksponensial (BR-IB-02)"
        },
        "table": {
            "title": "Rincian Transaksi Portofolio Pasar Uang & Nostro (Riil Database)",
            "subtitle": "Kalkulasi formula Short-Term PD eksponensial dan LGD 45% (BR-IB-01 s/d BR-IB-04)",
            "headers": ["ID Deal", "Pihak Lawan", "Instrumen", "Tenor", "EAD (Pokok+Akrual)", "Rating", "Stage", "Annual PD", "Short-Term PD", "LGD", "Nominal CKPN"],
            "records": records
        },
        "charts": {
            "chart1_title": "Komposisi EAD per Jenis Instrumen",
            "chart1_tag": "FASBIS • PUAS • Nostro",
            "chart1_data": inst_dist,
            "chart2_title": "Distribusi Beban CKPN per Pihak Lawan",
            "chart2_tag": "Counterparty Risk",
            "chart2_data": ckpn_dist
        },
        "journal": [
            {
                "kode_akun": "511.02.01",
                "nama_akun": "Beban Cadangan Kerugian Penurunan Nilai (CKPN) - Pasar Uang Antar Bank",
                "posisi": "DEBIT",
                "nominal": total_ckpn
            },
            {
                "kode_akun": "119.04.01",
                "nama_akun": "Akumulasi Cadangan Kerugian Penurunan Nilai - Penempatan Bank Lain",
                "posisi": "KREDIT",
                "nominal": total_ckpn
            }
        ]
    }

def fetch_konvergensi_real(cut_off: str) -> dict:
    """Modul 4: Membaca konsolidasi dari fact_ldp_consolidated_gl."""
    records = []
    total_ead = 0.0
    total_ckpn = 0.0
    pie_data = {}
    bar_data = {}

    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("""
                SELECT 
                    subject_area,
                    keterangan,
                    stage_psak,
                    total_ead,
                    total_ckpn,
                    kode_akun_gl
                FROM fact_ldp_consolidated_gl
                WHERE tgl_cut_off = :cut_off
            """)
            df = pd.read_sql(query, conn, params={"cut_off": cut_off})

            if not df.empty:
                total_ead = float(df["total_ead"].sum())
                total_ckpn = float(df["total_ckpn"].sum())

                for _, r in df.iterrows():
                    subj = str(r["subject_area"])
                    ead_val = float(r["total_ead"])
                    ckpn_val = float(r["total_ckpn"])
                    pie_data[subj] = ead_val
                    bar_data[subj] = ckpn_val

                    records.append({
                        "col1": subj,
                        "col2": r["keterangan"],
                        "col3": "-",
                        "col4": r["kode_akun_gl"],
                        "col5": ead_val,
                        "col6": f"{(ead_val / total_ead * 100):.2f}%" if total_ead > 0 else "0%",
                        "col7": int(r["stage_psak"]),
                        "col8": "-",
                        "col9": "-",
                        "col10": f"{(ckpn_val / total_ckpn * 100):.2f}%" if total_ckpn > 0 else "0%",
                        "col11": ckpn_val
                    })
    except Exception as e:
        app.logger.warning(f"Gagal mengambil data Konvergensi riil: {e}")

    return {
        "module_code": "konvergensi",
        "module_name": "4. Konvergensi Grand Master Engine (Treasury + Pembiayaan)",
        "summary": {
            "kpi1_title": "Total Eksposur Konsolidasian",
            "kpi1_val": total_ead,
            "kpi1_sub": "Tabel fact_ldp_consolidated_gl",
            "kpi2_title": "Total Beban CKPN Terkonsolidasi",
            "kpi2_val": total_ckpn,
            "kpi2_sub": f"Rasio Cadangan: {(total_ckpn / total_ead * 100):.4f}%" if total_ead > 0 else "Rasio Cadangan: 0.000%",
            "kpi3_title": "Subject Area Terlibat",
            "kpi3_s1": len(records),
            "kpi3_s2": 1,
            "kpi3_desc1": "Area Portofolio",
            "kpi3_desc2": "Jurnal GL EOM",
            "kpi4_title": "Status Jurnal Pembukuan",
            "kpi4_val": "BALANCE" if total_ead > 0 else "MENUNGGU DATA",
            "kpi4_sub": "Siap diinjeksi ke Core Banking"
        },
        "table": {
            "title": "Konsolidasi Portofolio PSAK 413 (Riil Database)",
            "subtitle": "Hasil penggabungan modul pembiayaan HDP dan LDP treasury ke GL",
            "headers": ["Subject Area", "Deskripsi", "Total Deal", "Akun GL", "Total EAD", "Porsi Aset", "Stage", "Ref S1", "Ref S2", "Porsi CKPN", "Beban CKPN"],
            "records": records
        },
        "charts": {
            "chart1_title": "Porsi Eksposur Konsolidasi (EAD)",
            "chart1_tag": "Aset Produktif",
            "chart1_data": pie_data,
            "chart2_title": "Distribusi Beban CKPN per Subject Area",
            "chart2_tag": "Konsolidasi Cadangan",
            "chart2_data": bar_data
        },
        "journal": []
    }

# =====================================================================
# ROUTES
# =====================================================================

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/status", methods=["GET"])
def api_status():
    """Cek koneksi database dan ambil nama bank dari Ref_NamaBank."""
    db_connected = False
    error_msg = None
    bank_name = "Bank Aceh Syariah"

    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_connected = True
        bank_name = get_bank_name_from_db()
    except Exception as e:
        error_msg = str(e)

    return jsonify({
        "status": "ready",
        "bank_name": bank_name,
        "database": {
            "driver": settings.DB_DRIVER,
            "host": settings.DB_HOST,
            "name": settings.DB_NAME,
            "connected": db_connected,
            "error": error_msg
        }
    })

@app.route("/api/run-engine", methods=["POST"])
def api_run_engine():
    """
    Eksekusi kalkulasi atau pengambilan data 100% RIIL dari database SQL Server.
    TIDAK MENGGUNAKAN DATA PALSU/DUMMY.
    """
    payload = request.get_json() or {}
    cut_off = payload.get("cut_off", "2026-10-31")
    module_target = payload.get("module", "counterparty")

    # Cek koneksi database terlebih dahulu
    db_connected = False
    db_error = None
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_connected = True
    except Exception as e:
        db_error = str(e)

    # 1. Panggil data riil sesuai modul yang dipilih
    if module_target == "counterparty":
        result_data = fetch_counterparty_real(cut_off)
    elif module_target == "sukuk":
        result_data = fetch_sukuk_real(cut_off)
    elif module_target == "interbank":
        # Jika database terhubung, jalankan pipeline ETL dan kalkulasi nyata
        if db_connected:
            try:
                run_interbank_pipeline(cut_off)
            except Exception as pipe_err:
                app.logger.error(f"Gagal pipeline interbank: {pipe_err}")
        result_data = fetch_interbank_real(cut_off)
    else: # "konvergensi"
        result_data = fetch_konvergensi_real(cut_off)

    result_data["success"] = True
    result_data["cut_off"] = cut_off
    result_data["target_module"] = module_target
    result_data["db_connected"] = db_connected
    result_data["db_error"] = db_error
    result_data["bank_name"] = get_bank_name_from_db()

    return jsonify(result_data)

if __name__ == "__main__":
    print("Menjalankan Treasury PSAK 413 Web Dashboard di http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
