import os
import sys
import math
from datetime import datetime, date, timedelta
from pathlib import Path
from flask import Flask, render_template, request, jsonify, redirect
import pandas as pd
import numpy as np
from sqlalchemy import text

from config.settings import settings
from config.database import get_engine

# Import Engine Modul 1 (Ahmad: Master Counterparty)
from modules.master_counterparty.counterparty_sync import run_counterparty_sync, seed_counterparty_fixtures

# Import Engine Modul 3 (User: Penempatan Antar Bank & Nostro Devisa)
from modules.interbank_nostro.interbank_engine import (
    calculate_short_term_pd_and_ckpn,
    run_interbank_pipeline
)

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).resolve().parent
    template_folder = str(BASE_DIR / "templates")
    static_folder = str(BASE_DIR / "static")
    if not (BASE_DIR / "templates").exists() and hasattr(sys, '_MEIPASS'):
        template_folder = str(Path(sys._MEIPASS) / "templates")
        static_folder = str(Path(sys._MEIPASS) / "static")
    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
else:
    BASE_DIR = Path(__file__).resolve().parent
    app = Flask(__name__, template_folder="templates", static_folder="static")

app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

def get_eom_prev_month(ref_date: date = None) -> str:
    """
    Menghitung akhir bulan dari bulan sebelumnya: EOMONTH(DATEADD(month, -1, ref_date))
    Contoh: Jika hari ini 2026-10-28 -> menghasilkan '2026-09-30'
    """
    today = ref_date or date.today()
    first_day_current_month = today.replace(day=1)
    last_day_prev_month = first_day_current_month - timedelta(days=1)
    return last_day_prev_month.strftime("%Y-%m-%d")

# =====================================================================
# QUERY NAMA BANK DARI TABEL Ref_NamaBank
# =====================================================================
def get_bank_name_from_db(conn=None) -> str:
    """Membaca nama bank langsung dari tabel Ref_NamaBank di SQL Server."""
    if conn is not None:
        try:
            query = text("""
                IF OBJECT_ID('dbo.Ref_NamaBank', 'U') IS NOT NULL
                BEGIN
                    SELECT TOP 1 * FROM dbo.Ref_NamaBank;
                END
            """)
            result = conn.execute(query).fetchone()
            if result:
                for val in result:
                    if val and isinstance(val, str) and len(val.strip()) > 3 and not val.strip().isdigit():
                        return val.strip()
        except Exception:
            pass
        return "Bank Aceh Syariah"

    try:
        engine = get_engine()
        with engine.connect() as c:
            query = text("""
                IF OBJECT_ID('dbo.Ref_NamaBank', 'U') IS NOT NULL
                BEGIN
                    SELECT TOP 1 * FROM dbo.Ref_NamaBank;
                END
            """)
            result = c.execute(query).fetchone()
            if result:
                for val in result:
                    if val and isinstance(val, str) and len(val.strip()) > 3 and not val.strip().isdigit():
                        return val.strip()
    except Exception:
        pass
    return "Bank Aceh Syariah"

# =====================================================================
# QUERY TANGGAL CUT-OFF DINAMIS PER MODUL
# =====================================================================
def get_column_max_date(conn, table_name: str, column_name: str = "tgl_cut_off"):
    """Cek apakah tabel dan kolom ada di database via INFORMATION_SCHEMA sebelum dieksekusi."""
    try:
        chk_query = text("""
            SELECT 1 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = :tbl AND COLUMN_NAME = :col
        """)
        has_col = conn.execute(chk_query, {"tbl": table_name, "col": column_name}).scalar()
        if has_col:
            fetch_query = text(f"SELECT CONVERT(VARCHAR(10), MAX({column_name}), 23) FROM dbo.{table_name} WHERE {column_name} IS NOT NULL")
            res = conn.execute(fetch_query).scalar()
            if res and str(res).strip():
                return str(res).strip()
    except Exception:
        pass
    return None

def get_latest_cutoff_for_module(module_target: str = "interbank") -> str:
    """Membaca tanggal cut-off terakhir secara dinamis dari tabel fact/staging masing-masing modul."""
    default_date = "2026-10-31"
    try:
        engine = get_engine()
        with engine.connect() as conn:
            if module_target == "interbank":
                # Prioritas 1: fact_ldp_interbank_ecl, Prioritas 2: staging_treasury_interbank
                d = get_column_max_date(conn, "fact_ldp_interbank_ecl", "tgl_cut_off")
                if not d:
                    d = get_column_max_date(conn, "staging_treasury_interbank", "tgl_cut_off")
                if d:
                    return d
            elif module_target == "counterparty":
                d = get_column_max_date(conn, "ref_counterparty_rating", "tgl_cut_off")
                if d:
                    return d
    except Exception as e:
        app.logger.warning(f"Gagal mengambil cut-off dinamis untuk {module_target}: {e}")
    return default_date

def get_latest_cutoff_for_interbank() -> str:
    return get_latest_cutoff_for_module("interbank")

# =====================================================================
# FETCH DATA RIIL MODUL 1: MASTER COUNTERPARTY (AHMAD)
# =====================================================================
def fetch_counterparty_real(cut_off: str) -> dict:
    """Modul 1: Membaca data riil langsung dari dim_counterparty_harmonized (Golden Record)."""
    records = []
    total_inst = 0
    sovereign_count = 0
    ig_count = 0
    non_ig_count = 0
    unrated_count = 0
    avg_pd = 0.0
    agency_dist = {}
    pd_dist = {}

    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("""
                SELECT 
                    sandi_pihak_lawan,
                    nama_institusi,
                    golongan_antasena,
                    lembaga_rating_final,
                    kode_rating_final,
                    kategori_investasi,
                    base_ttc_pd
                FROM dim_counterparty_harmonized
                ORDER BY sandi_pihak_lawan ASC
            """)
            df = pd.read_sql(query, conn)

            if not df.empty:
                total_inst = len(df)
                sovereign_count = int((df["lembaga_rating_final"] == "SOVEREIGN_OJK").sum())
                ig_count = int((df["kategori_investasi"] == "INVESTMENT GRADE").sum())
                non_ig_count = int((df["kategori_investasi"] == "NON-INVESTMENT GRADE").sum())
                unrated_count = int((df["lembaga_rating_final"] == "UNRATED_FALLBACK").sum())
                avg_pd = float(df["base_ttc_pd"].mean())

                for _, r in df.iterrows():
                    agency = str(r["lembaga_rating_final"])
                    agency_dist[agency] = agency_dist.get(agency, 0) + 1
                    pd_dist[str(r["sandi_pihak_lawan"])] = round(float(r["base_ttc_pd"]) * 100, 4)

                    records.append({
                        "col1": str(r["sandi_pihak_lawan"]),
                        "col2": str(r["nama_institusi"]),
                        "col3": str(r["golongan_antasena"]),
                        "col4": str(r["lembaga_rating_final"]),
                        "col5": str(r["kode_rating_final"]),
                        "col6": str(r["kategori_investasi"]),
                        "col7": 1 if r["kategori_investasi"] == "INVESTMENT GRADE" else 2,
                        "col8": f"{float(r['base_ttc_pd']) * 100:.4f}%",
                        "col9": f"{float(r['base_ttc_pd']):.6f}",
                        "col10": "HARMONIZED",
                        "col11": "AKTIF"
                    })
    except Exception as e:
        app.logger.warning(f"Gagal mengambil data dim_counterparty_harmonized riil: {e}")

    return {
        "module_code": "counterparty",
        "module_name": "1. Master Counterparty",
        "summary": {
            "kpi1_title": "Total Counterparty",
            "kpi1_val": f"{total_inst} Entitas",
            "kpi1_sub": "Master Pihak Lawan Terharmonisasi",
            "kpi2_title": "Sovereign (0.01% PD)",
            "kpi2_val": f"{sovereign_count} Entitas",
            "kpi2_sub": "Pemerintah Pusat & Bank Indonesia",
            "kpi3_title": "Distribusi Grade Investasi",
            "kpi3_s1": ig_count,
            "kpi3_s2": non_ig_count,
            "kpi3_desc1": "Investment Grade",
            "kpi3_desc2": "Non-Investment",
            "kpi4_title": "Unrated / Fallback (5.00%)",
            "kpi4_val": f"{unrated_count} Entitas",
            "kpi4_sub": f"Rata-rata PD: {avg_pd * 100:.4f}%"
        },
        "table": {
            "title": "Golden Record Master Counterparty",
            "subtitle": "Data resmi hasil konsolidasi & resolusi multi-rating (PSAK 413)",
            "headers": ["Sandi Pihak Lawan", "Nama Institusi", "Golongan Antasena", "Lembaga Final", "Rating Final", "Kategori Investasi", "Base TTC PD"],
            "records": records
        },
        "charts": {
            "chart1_title": "Distribusi Lembaga Pemeringkat",
            "chart1_tag": "Hasil Resolusi Konflik",
            "chart1_data": agency_dist,
            "chart2_title": "Base TTC PD Rate per Pihak Lawan (%)",
            "chart2_tag": "Baseline Probability of Default",
            "chart2_data": pd_dist
        },
        "journal": []
    }

# =====================================================================
# FETCH DATA RIIL MODUL 3: PENEMPATAN ANTAR BANK & NOSTRO DEVISA (USER)
# =====================================================================
def fetch_interbank_real(cut_off: str) -> dict:
    """Membaca data riil penempatan dari fact_ldp_interbank_ecl & staging_treasury_interbank."""
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

                # Bersihkan label jenis instrumen dan urutkan dari kontribusi terbesar
                raw_inst = df.groupby("jenis_instrumen")["ead_treasury"].sum().to_dict()
                clean_inst_dist = {}
                for k, v in raw_inst.items():
                    lbl = str(k).strip() if pd.notna(k) else "LAINNYA"
                    if not lbl or lbl == "None" or (lbl.isdigit() and len(lbl) > 4):
                        lbl = "FASBIS"
                    clean_inst_dist[lbl] = clean_inst_dist.get(lbl, 0.0) + float(v)
                
                inst_dist = dict(sorted(clean_inst_dist.items(), key=lambda x: x[1], reverse=True))
                # Agregasi CKPN per nama institusi (bukan kode)
                ckpn_dist = df.groupby("nama_institusi")["nominal_ckpn"].sum().to_dict()

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

    coverage_pct = (total_ckpn / total_ead * 100) if total_ead > 0 else 0.0

    return {
        "module_code": "interbank",
        "module_name": "3. Modul Penempatan Antar Bank & Nostro Devisa",
        "summary": {
            "kpi1_title": "Total EAD (Exposure)",
            "kpi1_val": total_ead,
            "kpi1_sub": f"Data Riil Database ({len(records)} Transaksi)",
            "kpi2_title": "Total Beban CKPN (ECL)",
            "kpi2_val": total_ckpn,
            "kpi2_sub": f"Coverage: {coverage_pct:.4f}%",
            "kpi3_title": "Distribusi Staging PSAK",
            "kpi3_s1": s1_count,
            "kpi3_s2": s2_count,
            "kpi3_desc1": "Stage 1 (Lancar)",
            "kpi3_desc2": "Stage 2 (Default)",
            "kpi4_title": "Rata-rata Short-Term PD",
            "kpi4_val": f"{avg_pd * 100:.6f}%",
            "kpi4_sub": "Probabilitas Default Tenor Riil"
        },
        "table": {
            "title": "Rincian Transaksi Portofolio Pasar Uang & Nostro",
            "subtitle": "Kalkulasi formula Short-Term PD eksponensial dan LGD 45%",
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

# =====================================================================
# ROUTES
# =====================================================================

@app.route("/")
def root():
    """Mengalihkan akses root langsung ke URL modul Penempatan Antar Bank milik Anda."""
    return redirect("/interbank")

# --- ROUTE MODUL 3: PENEMPATAN ANTAR BANK & NOSTRO DEVISA (USER) ---
@app.route("/interbank")
def page_interbank():
    """Halaman Dashboard Khusus: Modul Penempatan Antar Bank & Nostro Devisa."""
    return render_template("module3_interbank.html")

# --- ROUTE MODUL 1: MASTER COUNTERPARTY & PARAMETER EOM (AHMAD) ---
@app.route("/master-counterparty", endpoint="master_counterparty_view")
@app.route("/counterparty", endpoint="counterparty")
def master_counterparty():
    """Tampilan mandiri Modul 1: Master Counterparty & Parameter EOM (Ahmad)."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    search = request.args.get("search", "", type=str).strip()
    kategori = request.args.get("kategori", "", type=str).strip()
    start_date = request.args.get("start_date", "", type=str).strip()
    end_date = request.args.get("end_date", "", type=str).strip()

    db_connected = False
    db_error = None
    records = []
    total_records = 0
    total_pages = 1
    start_idx = 0
    end_idx = 0

    summary = {
        "total_counterparty": 0,
        "total_sovereign": 0,
        "total_ig": 0,
        "total_unrated": 0
    }

    bank_name = "Bank Aceh Syariah"

    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            db_connected = True
            bank_name = get_bank_name_from_db(conn)

            # Cek apakah kolom periode_data ada di tabel dim_counterparty_harmonized
            check_col_query = text("""
                SELECT 1 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'dim_counterparty_harmonized' 
                  AND COLUMN_NAME = 'periode_data'
            """)
            has_periode_col = False
            try:
                col_res = conn.execute(check_col_query).fetchone()
                has_periode_col = bool(col_res)
            except Exception:
                # SQLite fallback
                try:
                    pragma_res = conn.execute(text("PRAGMA table_info(dim_counterparty_harmonized)")).fetchall()
                    has_periode_col = any(col[1] == 'periode_data' for col in pragma_res)
                except Exception:
                    has_periode_col = False

            # Jika user belum memilih filter tanggal (tampilan awal refresh),
            # cari tanggal data terakhir (MAX(periode_data)), fallback ke EOM M-1 (akhir bulan lalu)
            eom_m1_str = get_eom_prev_month()
            if has_periode_col and not start_date and not end_date:
                max_date_query = text("SELECT MAX(periode_data) FROM dim_counterparty_harmonized WHERE periode_data IS NOT NULL")
                latest_date = conn.execute(max_date_query).scalar()
                if latest_date:
                    start_date = str(latest_date)
                    end_date = str(latest_date)
                else:
                    start_date = eom_m1_str
                    end_date = eom_m1_str

            # Bangun query data
            sql_select = """
                SELECT 
                    sandi_pihak_lawan,
                    nama_institusi,
                    golongan_antasena,
                    lembaga_rating_final,
                    kode_rating_final,
                    kategori_investasi,
                    CAST(base_ttc_pd AS FLOAT) AS base_ttc_pd
            """
            if has_periode_col:
                sql_select += ", periode_data "
            sql_select += " FROM dim_counterparty_harmonized WHERE 1=1 "

            params = {}
            if has_periode_col and start_date and end_date:
                sql_select += " AND periode_data BETWEEN :start_date AND :end_date "
                params["start_date"] = start_date
                params["end_date"] = end_date
            elif has_periode_col and start_date:
                sql_select += " AND periode_data >= :start_date "
                params["start_date"] = start_date
            elif has_periode_col and end_date:
                sql_select += " AND periode_data <= :end_date "
                params["end_date"] = end_date

            sql_select += " ORDER BY sandi_pihak_lawan ASC "

            df = pd.read_sql(text(sql_select), conn, params=params)

            if not df.empty:
                # Ringkasan KPI dihitung dari total data keseluruhan pada rentang tanggal terpilih
                summary["total_counterparty"] = len(df)
                summary["total_sovereign"] = int((df["lembaga_rating_final"] == "SOVEREIGN_OJK").sum())
                summary["total_ig"] = int((df["kategori_investasi"] == "INVESTMENT GRADE").sum())
                summary["total_unrated"] = int((df["kode_rating_final"] == "UNRATED").sum())

                # Filter Search
                if search:
                    mask = (
                        df["sandi_pihak_lawan"].astype(str).str.contains(search, case=False, na=False) |
                        df["nama_institusi"].astype(str).str.contains(search, case=False, na=False)
                    )
                    df = df[mask]

                # Filter Kategori Investasi
                if kategori:
                    df = df[df["kategori_investasi"] == kategori]

                total_records = len(df)
                total_pages = max(1, math.ceil(total_records / per_page))
                if page < 1:
                    page = 1
                elif page > total_pages:
                    page = total_pages

                start_pos = (page - 1) * per_page
                end_pos = start_pos + per_page
                sliced_df = df.iloc[start_pos:end_pos]

                start_idx = start_pos + 1 if total_records > 0 else 0
                end_idx = min(start_pos + len(sliced_df), total_records)
                records = sliced_df.to_dict(orient="records")

    except Exception as e:
        db_error = str(e)
        app.logger.error(f"Error fetching counterparty data: {e}")

    # Nilai default cut-off: Akhir bulan dari bulan sebelumnya (EOM M-1)
    eom_m1_str = get_eom_prev_month()
    cut_off_default = eom_m1_str

    return render_template(
        "counterparty.html",
        bank_name=bank_name,
        cut_off=cut_off_default,
        start_date=start_date,
        end_date=end_date,
        db_connected=db_connected,
        db_engine=settings.DB_DRIVER,
        db_host=settings.DB_HOST,
        db_port=settings.DB_PORT,
        db_error=db_error,
        records=records,
        summary=summary,
        total_records=total_records,
        page=page,
        total_pages=total_pages,
        start_idx=start_idx,
        end_idx=end_idx,
        has_prev=(page > 1),
        has_next=(page < total_pages),
        prev_page=page - 1,
        next_page=page + 1,
        search=search,
        kategori=kategori
    )

master_counterparty_view = master_counterparty

@app.route("/master-counterparty/harmonize", methods=["POST"])
def harmonize_counterparty():
    """Endpoint trigger eksekusi harmonisasi data counterparty (Ahmad)."""
    try:
        payload = request.get_json() or {}
        eom_m1_str = get_eom_prev_month()
        cut_off = payload.get("cut_off") or eom_m1_str
        run_counterparty_sync(cut_off)
        return jsonify({
            "success": True,
            "message": f"Sinkronisasi & Harmonisasi Rating Counterparty (Cut-off: {cut_off}) berhasil dieksekusi!"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Gagal mengeksekusi harmonisasi: {str(e)}"
        }), 500

@app.route("/api/counterparty/seed", methods=["POST"])
def api_seed_counterparty():
    """Endpoint untuk mengisi ulang data staging dari fixture uji (Ahmad)."""
    try:
        seed_counterparty_fixtures(force=True)
        run_counterparty_sync("2026-10-31")
        return jsonify({
            "success": True,
            "message": "Data staging berhasil di-seed ulang dan diharmonisasi!"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Gagal seed staging: {str(e)}"
        }), 500

# =====================================================================
# API STATUS & CUTOFF
# =====================================================================

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

@app.route("/api/module-cutoff", methods=["GET"])
def api_module_cutoff():
    """Mengembalikan tanggal cut-off terakhir untuk modul yang diminta."""
    module_target = request.args.get("module", "interbank")
    latest_cutoff = get_latest_cutoff_for_module(module_target)
    return jsonify({
        "module": module_target,
        "latest_cutoff": latest_cutoff
    })

# =====================================================================
# API ENGINE RUNNER & DATA GETTER
# =====================================================================

@app.route("/api/interbank/data", methods=["GET"])
def api_interbank_data():
    """Mengambil data riil penempatan interbank untuk cut-off yang dipilih tanpa re-run pipeline."""
    cut_off = request.args.get("cut_off", "2026-10-31")
    result_data = fetch_interbank_real(cut_off)
    result_data["success"] = True
    result_data["cut_off"] = cut_off
    result_data["target_module"] = "interbank"
    result_data["bank_name"] = get_bank_name_from_db()
    result_data["latest_cutoff"] = get_latest_cutoff_for_module("interbank")
    return jsonify(result_data)

@app.route("/api/run-engine", methods=["POST"])
def api_run_engine():
    """Eksekusi pipeline dan kalkulasi 100% riil sesuai modul yang diminta."""
    payload = request.get_json() or {}
    cut_off = payload.get("cut_off", "2026-10-31")
    module_target = payload.get("module", "interbank")

    db_connected = False
    db_error = None
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_connected = True
    except Exception as e:
        db_error = str(e)

    if module_target == "counterparty":
        # Eksekusi pipeline Modul 1 (Ahmad)
        if db_connected:
            try:
                run_counterparty_sync(cut_off)
            except Exception as pipe_err:
                app.logger.error(f"Gagal pipeline counterparty: {pipe_err}")
        result_data = fetch_counterparty_real(cut_off)
    else:
        # Default: Eksekusi pipeline Modul 3 Interbank & Nostro (User)
        if db_connected:
            try:
                run_interbank_pipeline(cut_off)
            except Exception as pipe_err:
                app.logger.error(f"Gagal pipeline interbank: {pipe_err}")
                db_error = str(pipe_err)
        result_data = fetch_interbank_real(cut_off)

    result_data["success"] = True
    result_data["cut_off"] = cut_off
    result_data["target_module"] = module_target
    result_data["db_connected"] = db_connected
    result_data["db_error"] = db_error
    result_data["bank_name"] = get_bank_name_from_db()
    result_data["latest_cutoff"] = get_latest_cutoff_for_module(module_target)

    return jsonify(result_data)

if __name__ == "__main__":
    host = os.getenv("SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("SERVER_PORT", "5000"))
    print("=" * 65)
    print("   TREASURY PSAK 413 ENGINE (BANK ACEH SYARIAH)")
    print(f"   Server berjalan pada host: {host}, port: {port}")
    print(f"   Modul 3 Interbank    : http://localhost:{port}/interbank")
    print(f"   Modul 1 Counterparty : http://localhost:{port}/counterparty")
    print("=" * 65)
    app.run(host=host, port=port, debug=False)
