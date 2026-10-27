import numpy as np

def calculate_short_term_pd(annual_pd: float, days: float) -> float:
    """
    BR-IB-02: Konversi PD Tahunan ke PD Harian / Short-Term PD
    Formula: 1.0 - (1.0 - Annual_PD) ^ (Days / 365.0)
    
    Catatan:
    - Jika sisa hari <= 0 (misal: Nostro harian tanpa tenor), diasumsikan risiko overnight (1 hari).
    - Jika Annual PD <= 0, return 0.0.
    """
    if annual_pd <= 0.0:
        return 0.0
    effective_days = max(float(days), 1.0)
    return float(1.0 - np.power((1.0 - float(annual_pd)), (effective_days / 365.0)))

def calculate_ckpn(ead: float, pd: float, lgd: float) -> float:
    """
    Kalkulasi Beban Kerugian Penurunan Nilai (CKPN) / Expected Credit Loss (ECL):
    Formula: EAD * PD * LGD
    """
    return round(float(ead) * float(pd) * float(lgd), 2)
