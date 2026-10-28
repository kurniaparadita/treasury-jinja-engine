import os
import sys
import urllib.parse
from pathlib import Path
from dotenv import load_dotenv

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env if present
env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv(dotenv_path=BASE_DIR / ".env.example")

class Settings:
    # Server Settings
    SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
    SERVER_PORT: int = int(os.getenv("SERVER_PORT", "5000"))

    # SQL Server Driver & Connection (Default driver di Windows: "SQL Server")
    DB_DRIVER: str = os.getenv("DB_DRIVER", "SQL Server")
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: str = os.getenv("DB_PORT", "1433")
    DB_NAME: str = os.getenv("DB_NAME", "psak413_db")
    DB_USER: str = os.getenv("DB_USER", "sa")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    
    DB_TRUST_SERVER_CERTIFICATE: str = os.getenv("DB_TRUST_SERVER_CERTIFICATE", "yes")
    DB_USE_WINDOWS_AUTH: bool = os.getenv("DB_USE_WINDOWS_AUTH", "false").lower() == "true"

    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    APP_ENV: str = os.getenv("APP_ENV", "development")

    @property
    def is_legacy_driver(self) -> bool:
        """Driver bawaan 'SQL Server' adalah driver legacy Windows (SQLSRV32.DLL)."""
        return self.DB_DRIVER.strip().lower() == "sql server"

    @property
    def database_url(self) -> str:
        """
        Menghasilkan connection string SQLAlchemy untuk Microsoft SQL Server via pyodbc.
        Format: mssql+pyodbc://user:pass@host:port/dbname?driver=...
        """
        driver_encoded = urllib.parse.quote_plus(self.DB_DRIVER)
        params = [f"driver={driver_encoded}"]

        # Driver modern (ODBC Driver 17/18) mendukung TrustServerCertificate
        if not self.is_legacy_driver:
            params.append(f"TrustServerCertificate={self.DB_TRUST_SERVER_CERTIFICATE}")

        if self.DB_USE_WINDOWS_AUTH:
            params.append("trusted_connection=yes")
            query_string = "&".join(params)
            return f"mssql+pyodbc://@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?{query_string}"
        else:
            encoded_user = urllib.parse.quote_plus(self.DB_USER)
            encoded_pass = urllib.parse.quote_plus(self.DB_PASSWORD)
            query_string = "&".join(params)
            return f"mssql+pyodbc://{encoded_user}:{encoded_pass}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?{query_string}"

settings = Settings()
