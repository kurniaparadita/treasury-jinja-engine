import json
from pathlib import Path
from typing import Optional, Dict, Any
from sqlalchemy import text
from sqlalchemy.engine import Engine

from common.logger import get_logger
from common.template_engine import render_sql
from config.database import get_engine

logger = get_logger("MasterCounterparty")

FIXTURE_PATH = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "mock_counterparty.json"


def ensure_counterparty_tables(engine: Optional[Engine] = None):
    """
    Memastikan tabel staging, master scale, dan target harmonized tersedia.
    Mendukung dialek SQL Server dan SQLite.
    """
    target_engine = engine or get_engine()
    is_sqlite = target_engine.dialect.name == "sqlite"

    with target_engine.begin() as conn:
        if is_sqlite:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS staging_master_antasena (
                    sandi_pihak_lawan TEXT PRIMARY KEY,
                    nama_institusi TEXT NOT NULL,
                    golongan_antasena TEXT NOT NULL,
                    status_aktif INTEGER DEFAULT 1
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS ref_master_rating_scale (
                    lembaga_rating TEXT NOT NULL,
                    kode_rating TEXT NOT NULL,
                    rating_grade INTEGER NOT NULL,
                    kategori_investasi TEXT NOT NULL,
                    historis_ttc_pd REAL NOT NULL,
                    PRIMARY KEY (lembaga_rating, kode_rating)
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS staging_external_ratings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sandi_pihak_lawan TEXT NOT NULL,
                    lembaga_rating TEXT NOT NULL,
                    kode_rating TEXT NOT NULL,
                    tanggal_pembaruan TEXT NOT NULL,
                    status_berlaku INTEGER DEFAULT 1
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS dim_counterparty_harmonized (
                    periode_data TEXT NOT NULL,
                    sandi_pihak_lawan TEXT NOT NULL,
                    nama_institusi TEXT NOT NULL,
                    golongan_antasena TEXT NOT NULL,
                    lembaga_rating_final TEXT NOT NULL,
                    kode_rating_final TEXT NOT NULL,
                    kategori_investasi TEXT NOT NULL,
                    base_ttc_pd REAL NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (periode_data, sandi_pihak_lawan)
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS ref_counterparty_rating (
                    kode_counterparty VARCHAR(20) PRIMARY KEY,
                    nama_institusi VARCHAR(100) NOT NULL,
                    kategori_institusi VARCHAR(20) NOT NULL,
                    rating_saat_ini VARCHAR(10) NOT NULL
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS ref_rating_pd_mapping (
                    lembaga_rating VARCHAR(30) NOT NULL DEFAULT 'PEFINDO',
                    kode_rating VARCHAR(10) PRIMARY KEY,
                    rating_grade INTEGER NOT NULL DEFAULT 0,
                    kategori_grade VARCHAR(30) NOT NULL,
                    ttc_pd_rate NUMERIC(14, 12) NOT NULL
                );
            """))
        else:
            # SQL Server DDL
            conn.execute(text("""
                IF OBJECT_ID('dbo.staging_master_antasena', 'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.staging_master_antasena (
                        sandi_pihak_lawan   VARCHAR(20) PRIMARY KEY,
                        nama_institusi      VARCHAR(100) NOT NULL,
                        golongan_antasena   VARCHAR(50) NOT NULL,
                        status_aktif        INT DEFAULT 1
                    );
                END;
            """))
            conn.execute(text("""
                IF OBJECT_ID('dbo.ref_master_rating_scale', 'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.ref_master_rating_scale (
                        lembaga_rating      VARCHAR(20) NOT NULL,
                        kode_rating         VARCHAR(10) NOT NULL,
                        rating_grade        INT NOT NULL,
                        kategori_investasi  VARCHAR(30) NOT NULL,
                        historis_ttc_pd     NUMERIC(14, 12) NOT NULL,
                        CONSTRAINT PK_ref_master_rating_scale PRIMARY KEY (lembaga_rating, kode_rating)
                    );
                END;
            """))
            conn.execute(text("""
                IF OBJECT_ID('dbo.staging_external_ratings', 'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.staging_external_ratings (
                        id                  INT IDENTITY(1,1) PRIMARY KEY,
                        sandi_pihak_lawan   VARCHAR(20) NOT NULL,
                        lembaga_rating      VARCHAR(20) NOT NULL,
                        kode_rating         VARCHAR(10) NOT NULL,
                        tanggal_pembaruan   DATE NOT NULL,
                        status_berlaku      INT DEFAULT 1
                    );
                END;
            """))
            conn.execute(text("""
                IF OBJECT_ID('dbo.dim_counterparty_harmonized', 'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.dim_counterparty_harmonized (
                        periode_data            VARCHAR(10) NOT NULL,
                        sandi_pihak_lawan       VARCHAR(20) NOT NULL,
                        nama_institusi          VARCHAR(100) NOT NULL,
                        golongan_antasena       VARCHAR(50) NOT NULL,
                        lembaga_rating_final    VARCHAR(30) NOT NULL,
                        kode_rating_final       VARCHAR(10) NOT NULL,
                        kategori_investasi      VARCHAR(30) NOT NULL,
                        base_ttc_pd             NUMERIC(14, 12) NOT NULL,
                        updated_at              DATETIME2 DEFAULT GETDATE(),
                        CONSTRAINT PK_dim_counterparty_harmonized PRIMARY KEY (periode_data, sandi_pihak_lawan)
                    );
                END
                ELSE
                BEGIN
                    -- Pastikan kolom periode_data ada jika tabel sudah pernah dibuat sebelumnya
                    IF COL_LENGTH('dbo.dim_counterparty_harmonized', 'periode_data') IS NULL
                    BEGIN
                        ALTER TABLE dbo.dim_counterparty_harmonized ADD periode_data VARCHAR(10) NULL;
                    END;

                    -- Update data lama yang periode_data nya NULL
                    UPDATE dbo.dim_counterparty_harmonized 
                    SET periode_data = '2026-10-31' 
                    WHERE periode_data IS NULL;

                    -- Ubah Primary Key lama (sandi_pihak_lawan saja) menjadi Composite PK (periode_data, sandi_pihak_lawan)
                    DECLARE @pk_col_count INT;
                    SELECT @pk_col_count = COUNT(*)
                    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                    WHERE TABLE_NAME = 'dim_counterparty_harmonized'
                      AND CONSTRAINT_NAME LIKE 'PK%';

                    IF @pk_col_count = 1
                    BEGIN
                        DECLARE @old_pk NVARCHAR(128);
                        SELECT TOP 1 @old_pk = CONSTRAINT_NAME
                        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                        WHERE TABLE_NAME = 'dim_counterparty_harmonized'
                          AND CONSTRAINT_NAME LIKE 'PK%';

                        IF @old_pk IS NOT NULL
                        BEGIN
                            DECLARE @drop_sql NVARCHAR(MAX) = 'ALTER TABLE dbo.dim_counterparty_harmonized DROP CONSTRAINT [' + @old_pk + '];';
                            EXEC sp_executesql @drop_sql;
                        END;

                        ALTER TABLE dbo.dim_counterparty_harmonized ALTER COLUMN periode_data VARCHAR(10) NOT NULL;
                        ALTER TABLE dbo.dim_counterparty_harmonized ALTER COLUMN sandi_pihak_lawan VARCHAR(20) NOT NULL;

                        ALTER TABLE dbo.dim_counterparty_harmonized 
                        ADD CONSTRAINT PK_dim_counterparty_harmonized PRIMARY KEY (periode_data, sandi_pihak_lawan);
                    END;
                END;
            """))
            conn.execute(text("""
                IF OBJECT_ID('dbo.ref_counterparty_rating', 'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.ref_counterparty_rating (
                        kode_counterparty   VARCHAR(20) PRIMARY KEY,
                        nama_institusi      VARCHAR(100) NOT NULL,
                        kategori_institusi  VARCHAR(20) NOT NULL,
                        rating_saat_ini     VARCHAR(10) NOT NULL
                    );
                END;
            """))
            conn.execute(text("""
                IF OBJECT_ID('dbo.ref_rating_pd_mapping', 'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.ref_rating_pd_mapping (
                        lembaga_rating      VARCHAR(30) NOT NULL DEFAULT 'PEFINDO',
                        kode_rating         VARCHAR(10) PRIMARY KEY,
                        rating_grade        INT NOT NULL DEFAULT 0,
                        kategori_grade      VARCHAR(30) NOT NULL,
                        ttc_pd_rate         NUMERIC(14, 12) NOT NULL
                    );
                END;
            """))

    logger.info("[Ahmad] Skema tabel Master Counterparty terverifikasi aktif.")


def seed_counterparty_fixtures(engine: Optional[Engine] = None, force: bool = False):
    """
    Mengisi data awal staging Antasena dan External Ratings dari fixture JSON jika tabel masih kosong.
    """
    target_engine = engine or get_engine()

    if not FIXTURE_PATH.exists():
        logger.warning(f"[Ahmad] File fixture {FIXTURE_PATH} tidak ditemukan.")
        return

    with target_engine.begin() as conn:
        count_existing = conn.execute(text("SELECT COUNT(*) FROM staging_master_antasena")).scalar()
        if count_existing > 0 and not force:
            logger.info(f"[Ahmad] Staging sudah memiliki {count_existing} data, seeding dilewati.")
            return

        with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 1. Bersihkan staging
        conn.execute(text("DELETE FROM staging_external_ratings"))
        conn.execute(text("DELETE FROM staging_master_antasena"))
        conn.execute(text("DELETE FROM ref_master_rating_scale"))

        # 2. Injeksi Master Rating Scale
        for item in data.get("ref_master_rating_scale", []):
            conn.execute(text("""
                INSERT INTO ref_master_rating_scale 
                (lembaga_rating, kode_rating, rating_grade, kategori_investasi, historis_ttc_pd)
                VALUES (:lembaga_rating, :kode_rating, :rating_grade, :kategori_investasi, :historis_ttc_pd)
            """), item)

        # 3. Injeksi Staging Antasena
        for item in data.get("staging_master_antasena", []):
            conn.execute(text("""
                INSERT INTO staging_master_antasena 
                (sandi_pihak_lawan, nama_institusi, golongan_antasena, status_aktif)
                VALUES (:sandi_pihak_lawan, :nama_institusi, :golongan_antasena, :status_aktif)
            """), item)

        # 4. Injeksi Staging External Ratings
        for item in data.get("staging_external_ratings", []):
            conn.execute(text("""
                INSERT INTO staging_external_ratings 
                (sandi_pihak_lawan, lembaga_rating, kode_rating, tanggal_pembaruan, status_berlaku)
                VALUES (:sandi_pihak_lawan, :lembaga_rating, :kode_rating, :tanggal_pembaruan, :status_berlaku)
            """), item)

    logger.info("[Ahmad] Seeding data simulasi Master Counterparty berhasil diselesaikan.")


def execute_counterparty_etl(cut_off: str, engine: Optional[Engine] = None):
    """
    Merender query Jinja 01_master_counterparty.sql dan mengeksekusinya ke database.
    """
    target_engine = engine or get_engine()
    logger.info(f"[Ahmad] Merender dan mengeksekusi template SQL 01_master_counterparty.sql untuk cut-off: {cut_off}")

    sql_script = render_sql("01_master_counterparty.sql", tgl_cut_off=cut_off)

    with target_engine.begin() as conn:
        statements = [stmt.strip() for stmt in sql_script.split(";") if stmt.strip()]
        for stmt in statements:
            conn.execute(text(stmt))

    logger.info("[Ahmad] SQL ETL Harmonisasi Counterparty berhasil dieksekusi.")


def run_counterparty_sync(cut_off: str, engine: Optional[Engine] = None) -> Dict[str, Any]:
    """
    [PIC: Ahmad] Pipeline Sinkronisasi Master Counterparty dan External Credit Rating.
    
    Langkah:
    1. Pastikan tabel skema (staging, ref, dim) tersedia.
    2. Jika data staging kosong, isi otomatis dari mock fixtures.
    3. Eksekusi query Jinja SQL 01_master_counterparty.sql.
    4. Ambil ringkasan hasil harmonisasi untuk logging dan dashboard.
    """
    logger.info("=" * 60)
    logger.info(f"[Ahmad] Menjalankan Sinkronisasi Master Counterparty (Cut-off: {cut_off})")
    logger.info("=" * 60)

    target_engine = engine or get_engine()

    # 1. Inisialisasi skema tabel jika belum ada
    ensure_counterparty_tables(target_engine)

    # 2. Cek apakah ada data di staging, jika belum lakukan auto-seed
    seed_counterparty_fixtures(target_engine, force=False)

    # 3. Jalankan ETL Harmonisasi via Jinja2
    execute_counterparty_etl(cut_off, target_engine)

    # 4. Ambil ringkasan hasil
    with target_engine.connect() as conn:
        total_dim = conn.execute(text("SELECT COUNT(*) FROM dim_counterparty_harmonized")).scalar() or 0
        total_sovereign = conn.execute(text("SELECT COUNT(*) FROM dim_counterparty_harmonized WHERE lembaga_rating_final = 'SOVEREIGN_OJK'")).scalar() or 0
        total_ig = conn.execute(text("SELECT COUNT(*) FROM dim_counterparty_harmonized WHERE kategori_investasi = 'INVESTMENT GRADE'")).scalar() or 0
        total_unrated = conn.execute(text("SELECT COUNT(*) FROM dim_counterparty_harmonized WHERE lembaga_rating_final = 'UNRATED_FALLBACK'")).scalar() or 0
        total_ref = conn.execute(text("SELECT COUNT(*) FROM ref_counterparty_rating")).scalar() or 0

    summary = {
        "status": "success",
        "cut_off": cut_off,
        "total_counterparty": total_dim,
        "total_sovereign": total_sovereign,
        "total_investment_grade": total_ig,
        "total_unrated": total_unrated,
        "synced_to_ref_counterparty": total_ref
    }

    logger.info(f"[Ahmad] Harmonisasi Selesai: {total_dim} entitas terharmonisasi "
                f"({total_sovereign} Sovereign, {total_ig} Investment Grade, {total_unrated} Fallback).")
    logger.info(f"[Ahmad] Tabel ref_counterparty_rating & ref_rating_pd_mapping siap dikonsumsi Modul Yefta & Fathir.")

    return summary
