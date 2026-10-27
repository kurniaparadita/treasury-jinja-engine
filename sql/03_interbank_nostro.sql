-- ====================================================================
-- TEMPLATE SQL (T-SQL / SQL SERVER): MODUL PENEMPATAN ANTAR BANK & NOSTRO DEVISA
-- PIC: Yefta
-- Parameter Jinja: {{ tgl_cut_off }}
-- ====================================================================

-- 1. Bersihkan data fact pada tanggal cut-off yang sama (Idempotency)
DELETE FROM fact_ldp_interbank_ecl 
WHERE tgl_cut_off = CAST('{{ tgl_cut_off }}' AS DATE);

-- 2. Injeksi Kerangka EAD, LGD, dan Initial Annual PD
INSERT INTO fact_ldp_interbank_ecl (
    id_penempatan,
    tgl_cut_off,
    stage_psak,
    ead_treasury,
    annual_pd_rate,
    short_term_pd,
    lgd_unsecured,
    nominal_ckpn
)
SELECT 
    s.id_penempatan,
    CAST('{{ tgl_cut_off }}' AS DATE) AS tgl_cut_off,
    
    -- BR-IB-01 & BR-IB-04: Penentuan Stage Interbank
    CASE 
        WHEN cr.kategori_institusi = 'SOVEREIGN' THEN 1
        WHEN rm.kategori_grade = 'NON_INVESTMENT_GRADE' THEN 2 
        ELSE 1
    END AS stage_psak,
    
    -- Kalkulasi EAD: Pokok + Akrual
    (COALESCE(s.nominal_pokok, 0) + COALESCE(s.akrual_imbalan, 0)) AS ead_treasury,
    
    -- Mapping Annual PD berdasarkan Rating Pihak Lawan
    CASE 
        WHEN cr.kategori_institusi = 'SOVEREIGN' THEN 0.0001 -- Sovereign Risk-Free Floor
        ELSE COALESCE(rm.ttc_pd_rate, 0.0500) 
    END AS annual_pd_rate,
    
    -- Kolom Short-Term PD dan CKPN diinisialisasi 0, dihitung lanjut via Python
    0.0000 AS short_term_pd,
    
    -- BR-IB-03: Penerapan Unsecured Interbank LGD (Standar Basel: 45%)
    0.4500 AS lgd_unsecured,
    0.00 AS nominal_ckpn

FROM staging_treasury_interbank s
LEFT JOIN ref_counterparty_rating cr ON s.kode_counterparty = cr.kode_counterparty
LEFT JOIN ref_rating_pd_mapping rm ON cr.rating_saat_ini = rm.kode_rating;
