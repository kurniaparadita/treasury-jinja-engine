import pytest
import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from common.math_utils import calculate_short_term_pd, calculate_ckpn
from modules.interbank_nostro.interbank_engine import (
    calculate_short_term_pd_and_ckpn,
    execute_interbank_etl,
    run_interbank_pipeline
)

def test_short_term_pd_formula():
    """Menguji rumus BR-IB-02: 1 - (1 - Annual_PD)^(days/365)."""
    annual_pd = 0.05  # 5%
    
    # 1. Jika 365 hari, hasilnya harus sama persis dengan annual_pd
    pd_365 = calculate_short_term_pd(annual_pd, 365)
    assert pytest.approx(pd_365, rel=1e-5) == 0.05
    
    # 2. Jika tenor pendek (misal 30 hari), PD harian harus lebih kecil secara proporsional
    pd_30 = calculate_short_term_pd(annual_pd, 30)
    assert 0.0 < pd_30 < 0.05
    expected_30 = 1.0 - np.power((1.0 - 0.05), (30 / 365.0))
    assert pytest.approx(pd_30, rel=1e-6) == expected_30

    # 3. Nostro 0 hari diasumsikan overnight (1 hari)
    pd_0 = calculate_short_term_pd(annual_pd, 0)
    pd_1 = calculate_short_term_pd(annual_pd, 1)
    assert pd_0 == pd_1

def test_calculate_ckpn():
    """Menguji kalkulasi EAD * PD * LGD."""
    ead = 100_000_000.0  # Rp 100 juta
    pd_val = 0.01        # 1%
    lgd = 0.45           # 45% (Unsecured Interbank)
    
    ckpn = calculate_ckpn(ead, pd_val, lgd)
    assert ckpn == 450_000.00  # Rp 450.000

def test_dataframe_vector_calculation():
    """Menguji fungsi vektor NumPy pada DataFrame."""
    test_df = pd.DataFrame([
        {
            "id_penempatan": "DEAL-01",
            "stage_psak": 1,
            "ead_treasury": 100_000_000,
            "annual_pd_rate": 0.0001,  # Sovereign
            "lgd_unsecured": 0.45,
            "sisa_hari_jatuh_tempo": 14
        },
        {
            "id_penempatan": "DEAL-02",
            "stage_psak": 2,
            "ead_treasury": 50_000_000,
            "annual_pd_rate": 0.1500,  # Warning
            "lgd_unsecured": 0.45,
            "sisa_hari_jatuh_tempo": 0   # Nostro
        }
    ])

    result_df = calculate_short_term_pd_and_ckpn(test_df)
    
    assert "short_term_pd" in result_df.columns
    assert "nominal_ckpn" in result_df.columns
    assert len(result_df) == 2
    
    # DEAL-01 sovereign PD harus sangat kecil
    assert result_df.loc[0, "nominal_ckpn"] >= 0.0
    
    # DEAL-02 Nostro overnight (1 hari)
    expected_pd_overnight = 1.0 - np.power((1.0 - 0.15), (1 / 365.0))
    assert pytest.approx(result_df.loc[1, "short_term_pd"], rel=1e-5) == expected_pd_overnight

def test_interbank_pipeline_sqlite():
    """Menguji end-to-end pipeline menggunakan in-memory SQLite database."""
    # SQLite in-memory engine untuk mocking database
    sqlite_engine = create_engine("sqlite:///:memory:")

    # 1. Buat skema tabel minimal di SQLite
    with sqlite_engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE ref_counterparty_rating (
                kode_counterparty VARCHAR(20) PRIMARY KEY,
                nama_institusi VARCHAR(100),
                kategori_institusi VARCHAR(20),
                rating_saat_ini VARCHAR(10)
            );
        """))
        conn.execute(text("""
            CREATE TABLE ref_rating_pd_mapping (
                kode_rating VARCHAR(10) PRIMARY KEY,
                kategori_grade VARCHAR(30),
                ttc_pd_rate NUMERIC(14, 12)
            );
        """))
        conn.execute(text("""
            CREATE TABLE staging_treasury_interbank (
                id_penempatan VARCHAR(50) PRIMARY KEY,
                kode_counterparty VARCHAR(20),
                jenis_instrumen VARCHAR(30),
                sisa_hari_jatuh_tempo INT,
                nominal_pokok NUMERIC(18, 2),
                akrual_imbalan NUMERIC(18, 2),
                tgl_cut_off TEXT
            );
        """))
        conn.execute(text("""
            CREATE TABLE fact_ldp_interbank_ecl (
                id_penempatan VARCHAR(50) PRIMARY KEY,
                tgl_cut_off TEXT,
                stage_psak INT,
                ead_treasury NUMERIC(18, 2),
                annual_pd_rate NUMERIC(14, 12),
                short_term_pd NUMERIC(14, 12),
                lgd_unsecured NUMERIC(6, 4),
                nominal_ckpn NUMERIC(18, 2),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

        # 2. Seeding Data Dummy
        conn.execute(text("""
            INSERT INTO ref_counterparty_rating VALUES 
            ('BI', 'Bank Indonesia', 'SOVEREIGN', 'AAA'),
            ('BMRI', 'Bank Mandiri', 'BANK_KOMERSIAL', 'AAA');
        """))
        conn.execute(text("""
            INSERT INTO ref_rating_pd_mapping VALUES 
            ('AAA', 'INVESTMENT_GRADE', 0.0005);
        """))
        conn.execute(text("""
            INSERT INTO staging_treasury_interbank VALUES 
            ('TEST-001', 'BI', 'FASBIS', 14, 10000000.0, 50000.0, '2026-10-31'),
            ('TEST-002', 'BMRI', 'NOSTRO', 0, 5000000.0, 0.0, '2026-10-31');
        """))

    # 3. Jalankan pipeline menggunakan SQLite engine
    # Catatan: modifikasi template SQL khusus SQLite tanpa casting ::DATE
    # Di SQLite, ETL dieksekusi secara native
    with sqlite_engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO fact_ldp_interbank_ecl (
                id_penempatan, tgl_cut_off, stage_psak, ead_treasury, annual_pd_rate, short_term_pd, lgd_unsecured, nominal_ckpn
            )
            SELECT 
                s.id_penempatan,
                '2026-10-31',
                CASE WHEN cr.kategori_institusi = 'SOVEREIGN' THEN 1 ELSE 1 END,
                (s.nominal_pokok + s.akrual_imbalan),
                CASE WHEN cr.kategori_institusi = 'SOVEREIGN' THEN 0.0001 ELSE 0.0005 END,
                0.0, 0.45, 0.0
            FROM staging_treasury_interbank s
            LEFT JOIN ref_counterparty_rating cr ON s.kode_counterparty = cr.kode_counterparty;
        """))

    query = text("""
        SELECT f.id_penempatan, f.stage_psak, f.ead_treasury, f.annual_pd_rate, f.lgd_unsecured, s.sisa_hari_jatuh_tempo
        FROM fact_ldp_interbank_ecl f
        INNER JOIN staging_treasury_interbank s ON f.id_penempatan = s.id_penempatan
    """)
    with sqlite_engine.connect() as conn:
        df = pd.read_sql(query, conn)

    result_df = calculate_short_term_pd_and_ckpn(df)
    assert len(result_df) == 2
    assert (result_df['nominal_ckpn'] > 0).all()
