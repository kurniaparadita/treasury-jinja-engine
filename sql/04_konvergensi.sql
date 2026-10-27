-- ====================================================================
-- TEMPLATE SQL: KONVERGENSI GRAND MASTER ENGINE (TREASURY + PEMBIAYAAN)
-- PIC: Fathir
-- ====================================================================

-- TODO (Fathir): Amalgamasi hasil fact_ldp_interbank_ecl, fact_ldp_sukuk_ecl, 
-- dan fact pembiayaan HDP ke dalam fact_ldp_consolidated_gl
-- Parameter Jinja: {{ tgl_cut_off }}

SELECT 
    'Fathir - Modul Konvergensi siap diimplementasikan' AS info_status,
    '{{ tgl_cut_off }}' AS cut_off;
