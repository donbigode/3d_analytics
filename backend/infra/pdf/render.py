from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

TEMPLATE_DIR = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
)


def render_quote_pdf(data: dict) -> bytes:
    tpl = _env.get_template("quote.html")
    html = tpl.render(**data)
    return HTML(string=html, base_url=str(TEMPLATE_DIR)).write_pdf()
