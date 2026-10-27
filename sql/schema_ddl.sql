-- ====================================================================
-- SKEMA BASIS DATA TREASURY PSAK 413 (MICROSOFT SQL SERVER)
-- INSTITUSI: BANK ACEH SYARIAH
-- ====================================================================

-- 1. TABEL REFERENSI (PIC: Ahmad)
IF OBJECT_ID('dbo.ref_counterparty_rating', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ref_counterparty_rating (
        kode_counterparty   VARCHAR(20) PRIMARY KEY,
        nama_institusi      VARCHAR(100) NOT NULL,
        kategori_institusi  VARCHAR(20) NOT NULL, -- 'SOVEREIGN' atau 'BANK_KOMERSIAL'
        rating_saat_ini     VARCHAR(10) NOT NULL  -- 'AAA', 'AA', 'A', 'BBB', dll.
    );
END;

IF OBJECT_ID('dbo.ref_rating_pd_mapping', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ref_rating_pd_mapping (
        kode_rating         VARCHAR(10) PRIMARY KEY,
        kategori_grade      VARCHAR(30) NOT NULL, -- 'INVESTMENT_GRADE' atau 'NON_INVESTMENT_GRADE'
        ttc_pd_rate         NUMERIC(14, 12) NOT NULL -- Historical Through-The-Cycle PD
    );
END;

-- 2. TABEL STAGING SUMBER HARIAN (PIC: Yefta)
IF OBJECT_ID('dbo.staging_treasury_interbank', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.staging_treasury_interbank (
        id_penempatan           VARCHAR(50) PRIMARY KEY,
        kode_counterparty       VARCHAR(20) NOT NULL,
        jenis_instrumen         VARCHAR(30) NOT NULL, -- 'FASBIS', 'WADIAH_ANTAR_BANK', 'NOSTRO'
        sisa_hari_jatuh_tempo   INT NOT NULL DEFAULT 0,
        nominal_pokok           NUMERIC(18, 2) NOT NULL DEFAULT 0.00,
        akrual_imbalan          NUMERIC(18, 2) NOT NULL DEFAULT 0.00,
        tgl_cut_off             DATE NOT NULL
    );
END;
IF OBJECT_ID('dbo.staging_treasury_interbank', 'U') IS NOT NULL AND COL_LENGTH('dbo.staging_treasury_interbank', 'tgl_cut_off') IS NULL
BEGIN
    ALTER TABLE dbo.staging_treasury_interbank ADD tgl_cut_off DATE NULL;
END;

-- 3. TABEL TARGET HASIL KALKULASI FASE 2 LDP (PIC: Yefta)
IF OBJECT_ID('dbo.fact_ldp_interbank_ecl', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.fact_ldp_interbank_ecl (
        id_penempatan       VARCHAR(50) PRIMARY KEY,
        tgl_cut_off         DATE NOT NULL,
        stage_psak          INT NOT NULL DEFAULT 1,      -- Stage 1 (Lancar) atau Stage 2 (Default/Warning)
        ead_treasury        NUMERIC(18, 2) NOT NULL,     -- Pokok + Akrual
        annual_pd_rate      NUMERIC(14, 12) NOT NULL,    -- PD Tahunan berbasis rating
        short_term_pd       NUMERIC(14, 12) NOT NULL DEFAULT 0.0000, -- PD sesuai tenor hari
        lgd_unsecured       NUMERIC(6, 4) NOT NULL DEFAULT 0.4500,   -- Standar Unsecured Basel (45%)
        nominal_ckpn        NUMERIC(18, 2) NOT NULL DEFAULT 0.00,    -- Hasil akhir beban cadangan
        created_at          DATETIME2 DEFAULT GETDATE()
    );
END;
IF OBJECT_ID('dbo.fact_ldp_interbank_ecl', 'U') IS NOT NULL AND COL_LENGTH('dbo.fact_ldp_interbank_ecl', 'tgl_cut_off') IS NULL
BEGIN
    ALTER TABLE dbo.fact_ldp_interbank_ecl ADD tgl_cut_off DATE NULL;
END;

-- 4. TABEL TARGET HASIL SUKUK (PIC: Fathir)
IF OBJECT_ID('dbo.fact_ldp_sukuk_ecl', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.fact_ldp_sukuk_ecl (
        id_sukuk            VARCHAR(50) PRIMARY KEY,
        tgl_cut_off         DATE NOT NULL,
        stage_psak          INT NOT NULL DEFAULT 1,
        ead_sukuk           NUMERIC(18, 2) NOT NULL,
        pd_rate             NUMERIC(14, 12) NOT NULL,
        lgd_rate            NUMERIC(6, 4) NOT NULL,
        nominal_ckpn        NUMERIC(18, 2) NOT NULL DEFAULT 0.00,
        created_at          DATETIME2 DEFAULT GETDATE()
    );
END;

-- 5. TABEL KONSOLIDASI AKHIR GRAND MASTER / GL (PIC: Fathir)
IF OBJECT_ID('dbo.fact_ldp_consolidated_gl', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.fact_ldp_consolidated_gl (
        id_transaksi_gl     VARCHAR(50) PRIMARY KEY,
        tgl_cut_off         DATE NOT NULL,
        subject_area        VARCHAR(30) NOT NULL, -- 'INTERBANK', 'SUKUK', 'PEMBIAYAAN_HDP'
        stage_psak          INT NOT NULL,
        total_ead           NUMERIC(18, 2) NOT NULL,
        total_ckpn          NUMERIC(18, 2) NOT NULL,
        kode_akun_gl        VARCHAR(30),
        keterangan          TEXT,
        created_at          DATETIME2 DEFAULT GETDATE()
    );
END;
