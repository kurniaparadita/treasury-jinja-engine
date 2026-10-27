import argparse
import sys
from datetime import datetime
from common.logger import get_logger

from modules.master_counterparty.counterparty_sync import run_counterparty_sync
from modules.sukuk.sukuk_engine import run_sukuk_engine
from modules.interbank_nostro.interbank_engine import run_interbank_pipeline
from modules.konvergensi.grand_master_engine import run_convergence_engine

logger = get_logger("MainRunner")

def validate_date(date_str: str) -> str:
    """Validasi format tanggal YYYY-MM-DD."""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return date_str
    except ValueError:
        raise argparse.ArgumentTypeError(f"Format tanggal tidak valid: '{date_str}'. Harus berformat YYYY-MM-DD.")

def main():
    parser = argparse.ArgumentParser(
        description="Master Engine Pipeline - Treasury PSAK 413 (Bank Aceh Syariah)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh Penggunaan:
  # Menjalankan modul Penempatan Antar Bank & Nostro milik Yefta:
  python main.py --module interbank --cut-off 2026-10-31

  # Menjalankan seluruh proses engine secara berurutan:
  python main.py --module all --cut-off 2026-10-31
        """
    )
    
    parser.add_argument(
        "--module",
        choices=["all", "counterparty", "sukuk", "interbank", "konvergensi"],
        default="interbank",
        help="Pilih modul yang ingin dieksekusi (default: interbank)."
    )
    
    parser.add_argument(
        "--cut-off",
        required=True,
        type=validate_date,
        help="Tanggal Cut Off posisi pelaporan (format: YYYY-MM-DD, contoh: 2026-10-31)"
    )

    args = parser.parse_args()
    cut_off = args.cut_off
    selected_module = args.module

    logger.info("*" * 65)
    logger.info("   TREASURY PSAK 413 ENGINE (BANK ACEH SYARIAH)   ")
    logger.info(f"   Target Modul : [{selected_module.upper()}]")
    logger.info(f"   Tanggal Cut-off : {cut_off}")
    logger.info("*" * 65)

    try:
        # 1. Modul Ahmad
        if selected_module in ["counterparty", "all"]:
            logger.info(">>> [1/4] Menjalankan Modul Master Counterparty (Ahmad)...")
            run_counterparty_sync(cut_off)

        # 2. Modul Fathir (Sukuk)
        if selected_module in ["sukuk", "all"]:
            logger.info(">>> [2/4] Menjalankan Modul Sukuk (Fathir)...")
            run_sukuk_engine(cut_off)

        # 3. Modul Yefta (Penempatan Antar Bank & Nostro)
        if selected_module in ["interbank", "all"]:
            logger.info(">>> [3/4] Menjalankan Modul Penempatan Antar Bank & Nostro (Yefta)...")
            run_interbank_pipeline(cut_off)

        # 4. Modul Fathir (Konvergensi Grand Master)
        if selected_module in ["konvergensi", "all"]:
            logger.info(">>> [4/4] Menjalankan Modul Konvergensi Grand Master (Fathir)...")
            run_convergence_engine(cut_off)

        logger.info("=" * 65)
        logger.info("SELURUH TAHAP PROSES ENGINE BERHASIL DISELESAIKAN DENGAN SUKSES.")
        logger.info("=" * 65)
        sys.exit(0)

    except Exception as e:
        logger.error(f"Terjadi kesalahan saat mengeksekusi pipeline: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
