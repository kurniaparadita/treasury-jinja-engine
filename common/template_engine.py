import sys
from jinja2 import Environment, FileSystemLoader
from pathlib import Path

if getattr(sys, 'frozen', False):
    SQL_DIR = Path(sys.executable).resolve().parent / "sql"
    if not SQL_DIR.exists() and hasattr(sys, '_MEIPASS'):
        SQL_DIR = Path(sys._MEIPASS) / "sql"
else:
    SQL_DIR = Path(__file__).resolve().parent.parent / "sql"
jinja_env = Environment(
    loader=FileSystemLoader(str(SQL_DIR)),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True
)

def render_sql(template_name: str, **params) -> str:
    """
    Me-render query SQL dari file template Jinja2 di folder sql/.
    
    Contoh pemanggilan:
        sql = render_sql("03_interbank_nostro.sql", tgl_cut_off='2026-10-31')
    """
    template = jinja_env.get_template(template_name)
    return template.render(**params)
