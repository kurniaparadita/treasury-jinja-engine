-- ====================================================================
-- TEMPLATE SQL: MASTER COUNTERPARTY & RATING HARMONIZATION (PSAK 413)
-- PIC: Ahmad
-- Parameter Jinja: {{ tgl_cut_off }}
-- Dialect Compatibility: ANSI SQL / Microsoft SQL Server / SQLite
-- ====================================================================

-- 1. Bersihkan tabel hasil harmonisasi untuk periode EOM yang dipilih atau data lama bernilai NULL (Idempotency)
DELETE FROM dim_counterparty_harmonized 
WHERE periode_data = '{{ tgl_cut_off }}' OR periode_data IS NULL;

-- 2. Algoritma CTE Harmonization & Resolusi Multi-Rating
WITH Staging_Antasena AS (
    SELECT 
        sandi_pihak_lawan, 
        nama_institusi, 
        golongan_antasena 
    FROM staging_master_antasena
    WHERE status_aktif = 1
),
Master_Scale_Mapping AS (
    SELECT 
        lembaga_rating, 
        kode_rating, 
        rating_grade, 
        kategori_investasi, 
        historis_ttc_pd
    FROM ref_master_rating_scale
),
Raw_External_Ratings AS (
    SELECT 
        sandi_pihak_lawan, 
        lembaga_rating, 
        kode_rating, 
        tanggal_pembaruan,
        CASE 
            WHEN UPPER(lembaga_rating) = 'PEFINDO' THEN 1
            WHEN UPPER(lembaga_rating) = 'FITCH' THEN 2
            WHEN UPPER(lembaga_rating) = 'INTERNAL' THEN 3
            ELSE 4
        END AS prioritas_lembaga
    FROM staging_external_ratings
    WHERE status_berlaku = 1
),
Harmonizer_Engine AS (
    SELECT 
        r.sandi_pihak_lawan, 
        r.lembaga_rating, 
        r.kode_rating,
        m.rating_grade, 
        m.kategori_investasi, 
        m.historis_ttc_pd,
        ROW_NUMBER() OVER(
            PARTITION BY r.sandi_pihak_lawan 
            ORDER BY r.prioritas_lembaga ASC, m.rating_grade DESC
        ) AS rating_rank
    FROM Raw_External_Ratings r
    LEFT JOIN Master_Scale_Mapping m 
        ON UPPER(r.lembaga_rating) = UPPER(m.lembaga_rating) 
        AND UPPER(r.kode_rating) = UPPER(m.kode_rating)
)
INSERT INTO dim_counterparty_harmonized (
    periode_data,
    sandi_pihak_lawan, 
    nama_institusi, 
    golongan_antasena, 
    lembaga_rating_final, 
    kode_rating_final, 
    kategori_investasi, 
    base_ttc_pd
)
SELECT 
    '{{ tgl_cut_off }}' AS periode_data,
    a.sandi_pihak_lawan, 
    a.nama_institusi, 
    a.golongan_antasena,
    CASE 
        WHEN a.golongan_antasena IN ('Pemerintah Pusat', 'Bank Indonesia') THEN 'SOVEREIGN_OJK' 
        ELSE COALESCE(h.lembaga_rating, 'UNRATED_FALLBACK') 
    END AS lembaga_rating_final,
    CASE 
        WHEN a.golongan_antasena IN ('Pemerintah Pusat', 'Bank Indonesia') THEN 'idAAA' 
        ELSE COALESCE(h.kode_rating, 'UNRATED') 
    END AS kode_rating_final,
    CASE 
        WHEN a.golongan_antasena IN ('Pemerintah Pusat', 'Bank Indonesia') THEN 'INVESTMENT GRADE' 
        ELSE COALESCE(h.kategori_investasi, 'NON-INVESTMENT GRADE') 
    END AS kategori_investasi,
    CASE 
        WHEN a.golongan_antasena IN ('Pemerintah Pusat', 'Bank Indonesia') THEN 0.000100
        ELSE COALESCE(h.historis_ttc_pd, 0.050000) 
    END AS base_ttc_pd
FROM Staging_Antasena a
LEFT JOIN Harmonizer_Engine h 
    ON a.sandi_pihak_lawan = h.sandi_pihak_lawan AND h.rating_rank = 1;

-- 3. Sinkronisasi ke Tabel Konsumsi Engine LDP: ref_counterparty_rating
DELETE FROM ref_counterparty_rating;

INSERT INTO ref_counterparty_rating (
    kode_counterparty,
    nama_institusi,
    kategori_institusi,
    rating_saat_ini
)
SELECT 
    sandi_pihak_lawan AS kode_counterparty,
    nama_institusi,
    CASE 
        WHEN golongan_antasena IN ('Pemerintah Pusat', 'Bank Indonesia') THEN 'SOVEREIGN'
        ELSE 'BANK_KOMERSIAL'
    END AS kategori_institusi,
    kode_rating_final AS rating_saat_ini
FROM (
    SELECT 
        sandi_pihak_lawan,
        nama_institusi,
        golongan_antasena,
        kode_rating_final,
        ROW_NUMBER() OVER(
            PARTITION BY sandi_pihak_lawan 
            ORDER BY CASE WHEN periode_data = '{{ tgl_cut_off }}' THEN 1 ELSE 2 END, periode_data DESC
        ) AS rn
    FROM dim_counterparty_harmonized
) d
WHERE d.rn = 1;

-- 4. Sinkronisasi ke Tabel Master Pemetaan PD: ref_rating_pd_mapping
DELETE FROM ref_rating_pd_mapping;

INSERT INTO ref_rating_pd_mapping (
    lembaga_rating,
    kode_rating,
    rating_grade,
    kategori_grade,
    ttc_pd_rate
)
SELECT 
    lembaga_rating,
    kode_rating,
    rating_grade,
    CASE 
        WHEN UPPER(kategori_investasi) LIKE '%NON%INVESTMENT%' THEN 'NON_INVESTMENT_GRADE'
        ELSE 'INVESTMENT_GRADE'
    END AS kategori_grade,
    historis_ttc_pd AS ttc_pd_rate
FROM ref_master_rating_scale;

-- 5. Tambahkan fallback default UNRATED untuk stabilitas pipeline
INSERT INTO ref_rating_pd_mapping (
    lembaga_rating,
    kode_rating,
    rating_grade,
    kategori_grade,
    ttc_pd_rate
)
SELECT 
    'UNRATED_FALLBACK',
    'UNRATED',
    0,
    'NON_INVESTMENT_GRADE',
    0.050000
WHERE NOT EXISTS (SELECT 1 FROM ref_rating_pd_mapping WHERE kode_rating = 'UNRATED');
