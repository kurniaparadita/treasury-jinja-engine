import numpy as np
import pandas as pd
from sqlalchemy import text
from typing import Optional
from sqlalchemy.engine import Engine

from common.logger import get_logger
from common.template_engine import render_sql
from config.database import get_engine

logger = get_logger("InterbankEngine")

def execute_interbank_etl(cut_off: str, engine: Optional[Engine] = None):
    """
    Menjalankan query SQL ETL Jinja untuk mengekstrak data staging ke fact_ldp_interbank_ecl.
    """
    target_engine = engine or get_engine()
    logger.info(f"[Yefta] Merender dan mengeksekusi template SQL 03_interbank_nostro.sql untuk cut-off: {cut_off}")
    
    # 1. Render SQL via Jinja2
    sql_script = render_sql("03_interbank_nostro.sql", tgl_cut_off=cut_off)
    
    # 2. Eksekusi SQL ETL
    with target_engine.begin() as conn:
        # Menangani multiple statements jika dipisahkan titik koma
        statements = [stmt.strip() for stmt in sql_script.split(";") if stmt.strip()]
        for stmt in statements:
            conn.execute(text(stmt))
            
    logger.info("[Yefta] SQL ETL Staging ke Fact berhasil dieksekusi.")

def calculate_short_term_pd_and_ckpn(df: pd.DataFrame) -> pd.DataFrame:
    """
    Kalkulasi Matematis Vektor (NumPy) untuk:
    1. Short-Term PD = 1 - (1 - Annual_PD) ^ (Days / 365.0)  [BR-IB-02]
    2. Nominal CKPN  = EAD * Short_Term_PD * LGD_Unsecured   [ECL Formula]
    """
    if df.empty:
        logger.warning("[Yefta] DataFrame input kosong, tidak ada data yang dihitung.")
        return df

    # Salin agar tidak memodifikasi dataframe asli secara langsung
    df_calc = df.copy()

    # Pastikan tipe data numerik
    df_calc['annual_pd_rate'] = pd.to_numeric(df_calc['annual_pd_rate'], errors='coerce').fillna(0.0)
    df_calc['ead_treasury'] = pd.to_numeric(df_calc['ead_treasury'], errors='coerce').fillna(0.0)
    df_calc['lgd_unsecured'] = pd.to_numeric(df_calc['lgd_unsecured'], errors='coerce').fillna(0.45)
    
    # BR-IB-02: Nostro tanpa tenor (0 hari) diasumsikan overnight (1 hari)
    days = pd.to_numeric(df_calc['sisa_hari_jatuh_tempo'], errors='coerce').fillna(1.0)
    days = np.where(days > 0, days, 1.0)

    annual_pd = df_calc['annual_pd_rate'].values
    
    # Hitung Short-Term PD eksponensial
    short_term_pd = 1.0 - np.power((1.0 - annual_pd), (days / 365.0))
    # Batasi agar tidak negatif atau lebih dari 1.0
    short_term_pd = np.clip(short_term_pd, 0.0, 1.0)
    
    # Hitung Nominal CKPN
    nominal_ckpn = df_calc['ead_treasury'].values * short_term_pd * df_calc['lgd_unsecured'].values

    df_calc['short_term_pd'] = np.round(short_term_pd, 12)
    df_calc['nominal_ckpn'] = np.round(nominal_ckpn, 2)

    return df_calc

def update_fact_interbank(df_result: pd.DataFrame, engine: Optional[Engine] = None):
    """
    Memperbarui kolom short_term_pd dan nominal_ckpn pada fact_ldp_interbank_ecl.
    """
    target_engine = engine or get_engine()
    logger.info(f"[Yefta] Memperbarui {len(df_result)} baris hasil kalkulasi ke fact_ldp_interbank_ecl...")
    
    update_sql = text("""
        UPDATE fact_ldp_interbank_ecl
        SET short_term_pd = :short_term_pd,
            nominal_ckpn = :nominal_ckpn
        WHERE id_penempatan = :id_penempatan
    """)

    params = [
        {
            "short_term_pd": float(row["short_term_pd"]),
            "nominal_ckpn": float(row["nominal_ckpn"]),
            "id_penempatan": str(row["id_penempatan"])
        }
        for _, row in df_result.iterrows()
    ]

    with target_engine.begin() as conn:
        conn.execute(update_sql, params)

    logger.info("[Yefta] Pembaruan database selesai.")

def run_interbank_pipeline(cut_off: str, engine: Optional[Engine] = None) -> pd.DataFrame:
    """
    Pipeline Utama Modul Penempatan Antar Bank & Nostro Devisa (Fase 2).
    
    Langkah:
    1. Jalankan SQL ETL Jinja2.
    2. Ekstrak data yang membutuhkan kalkulasi eksponensial.
    3. Eksekusi kalkulasi Short-Term PD dan Nominal CKPN via Python.
    4. Simpan kembali hasil akhir ke tabel fact.
    """
    target_engine = engine or get_engine()
    logger.info("=" * 60)
    logger.info(f"[Yefta] MEMULAI ENGINE PENEMPATAN ANTAR BANK & NOSTRO (Cut-off: {cut_off})")
    logger.info("=" * 60)

    # 1. Jalankan ETL Staging -> Fact (SQL Jinja)
    execute_interbank_etl(cut_off, target_engine)

    # 2. Tarik Data Fact + Staging
    query = text("""
        SELECT 
            f.id_penempatan, 
            f.stage_psak,
            f.ead_treasury, 
            f.annual_pd_rate, 
            f.lgd_unsecured, 
            s.sisa_hari_jatuh_tempo
        FROM fact_ldp_interbank_ecl f
        INNER JOIN staging_treasury_interbank s ON f.id_penempatan = s.id_penempatan
        WHERE f.tgl_cut_off = :cut_off
    """)
    
    with target_engine.connect() as conn:
        df = pd.read_sql(query, conn, params={"cut_off": cut_off})

    logger.info(f"[Yefta] Terambil {len(df)} transaksi penempatan untuk dihitung.")

    if df.empty:
        logger.warning(f"[Yefta] Tidak ada transaksi penempatan ditemukan untuk cut-off: {cut_off}")
        return df

    # 3. Hitung Short-Term PD & CKPN
    df_result = calculate_short_term_pd_and_ckpn(df)

    # 4. Update Database
    update_fact_interbank(df_result, target_engine)

    # 5. Rekapitulasi Metrik
    total_ead = df_result['ead_treasury'].sum()
    total_ckpn = df_result['nominal_ckpn'].sum()
    count_stage1 = (df_result['stage_psak'] == 1).sum()
    count_stage2 = (df_result['stage_psak'] == 2).sum()

    logger.info("-" * 60)
    logger.info("[Yefta] REKAPITULASI KALKULASI TREASURY INTERBANK:")
    logger.info(f"  - Total Transaksi : {len(df_result):,} deal")
    logger.info(f"  - Stage 1 (Lancar): {count_stage1} deal")
    logger.info(f"  - Stage 2 (Default): {count_stage2} deal")
    logger.info(f"  - Total EAD       : Rp {total_ead:,.2f}")
    logger.info(f"  - Total CKPN      : Rp {total_ckpn:,.2f}")
    logger.info("=" * 60)

    return df_result
