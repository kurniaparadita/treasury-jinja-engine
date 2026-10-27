-- ====================================================================
-- TEMPLATE SQL: SUKUK & INTEGRASI PEMERINGKAT EKSTERNAL
-- PIC: Fathir
-- ====================================================================

-- TODO (Fathir): Lengkapi query staging sukuk, PIT adjustment, dan fact sukuk
-- Parameter Jinja: {{ tgl_cut_off }}

SELECT 
    'Fathir - Modul Sukuk siap diimplementasikan' AS info_status,
    '{{ tgl_cut_off }}' AS cut_off;
