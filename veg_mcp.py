"""
Vegetable catalog MCP server for OpenClaw.

Exposes three tools over streamable-HTTP, protected by a bearer token:
  list_vegetables()          -> the whole catalog
  get_price(name)            -> price for one vegetable (tolerates typos/plurals)
  create_purchase_order(...)  -> writes a PO PDF, returns its path

All arithmetic happens here, in Python, so the model never does the maths.

Run:  VEG_MCP_TOKEN=<token> python veg_mcp.py
"""

import difflib
import json
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs

import uvicorn
from mcp.server.fastmcp import FastMCP
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

BASE_DIR = Path(__file__).resolve().parent
CATALOG_PATH = BASE_DIR / "catalog.json"
ORDERS_DIR = BASE_DIR / "orders"
ORDERS_DIR.mkdir(exist_ok=True)

TOKEN = os.environ.get("VEG_MCP_TOKEN", "")
HOST = os.environ.get("VEG_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("VEG_MCP_PORT", "8765"))
SUPPLIER = os.environ.get("VEG_MCP_SUPPLIER", "Green Valley Vegetables")
CURRENCY = os.environ.get("VEG_MCP_CURRENCY", "INR")

mcp = FastMCP("veggies", stateless_http=True)


def load_catalog() -> dict[str, float]:
    """Read the catalog from disk on every call, so edits apply without a restart."""
    with open(CATALOG_PATH, encoding="utf-8") as fh:
        return {k.strip().lower(): float(v) for k, v in json.load(fh).items()}


def resolve(name: str, catalog: dict[str, float]) -> str | None:
    """Match a chat-typed name to a catalog key: exact, then singular, then fuzzy."""
    key = name.strip().lower()
    if key in catalog:
        return key
    if key.endswith("es") and key[:-2] in catalog:
        return key[:-2]
    if key.endswith("s") and key[:-1] in catalog:
        return key[:-1]
    match = difflib.get_close_matches(key, catalog.keys(), n=1, cutoff=0.75)
    return match[0] if match else None


@mcp.tool()
def list_vegetables() -> dict:
    """List every vegetable available with its price per kg."""
    catalog = load_catalog()
    return {
        "currency": CURRENCY,
        "count": len(catalog),
        "items": [{"name": n, "price_per_kg": p} for n, p in sorted(catalog.items())],
    }


@mcp.tool()
def get_price(name: str) -> dict:
    """Get the per-kg price of one vegetable. Handles plurals and minor misspellings."""
    catalog = load_catalog()
    key = resolve(name, catalog)
    if key is None:
        near = difflib.get_close_matches(name.strip().lower(), catalog.keys(), n=3, cutoff=0.4)
        return {"found": False, "query": name, "did_you_mean": near}
    return {
        "found": True,
        "name": key,
        "price_per_kg": catalog[key],
        "currency": CURRENCY,
        "matched_from": name,
    }


@mcp.tool()
def create_purchase_order(
    items: list[dict],
    buyer: str,
    notes: str = "",
    tax_percent: float = 0.0,
) -> dict:
    """Generate a purchase order PDF and return the file path.

    items: list of {"name": "tomato", "quantity_kg": 5}
    buyer: name of the person or business placing the order
    notes: optional free text printed under the table
    tax_percent: optional tax added to the subtotal, e.g. 5 for 5%

    Unknown vegetable names are rejected rather than guessed at.
    """
    catalog = load_catalog()

    if not items:
        return {"ok": False, "error": "No items supplied."}

    lines, unknown = [], []
    for entry in items:
        raw_name = str(entry.get("name", "")).strip()
        key = resolve(raw_name, catalog)
        if key is None:
            unknown.append(raw_name)
            continue
        try:
            qty = float(entry.get("quantity_kg", 0))
        except (TypeError, ValueError):
            return {"ok": False, "error": f"Bad quantity for {raw_name!r}."}
        if qty <= 0:
            return {"ok": False, "error": f"Quantity for {key} must be greater than zero."}
        rate = catalog[key]
        lines.append(
            {
                "name": key,
                "quantity_kg": round(qty, 3),
                "rate_per_kg": rate,
                "amount": round(qty * rate, 2),
            }
        )

    if unknown:
        return {
            "ok": False,
            "error": "Not in catalog: " + ", ".join(unknown),
            "hint": "Call list_vegetables to see valid names.",
        }

    subtotal = round(sum(line["amount"] for line in lines), 2)
    tax = round(subtotal * tax_percent / 100.0, 2)
    total = round(subtotal + tax, 2)

    now = datetime.now()
    po_number = f"PO-{now:%Y%m%d-%H%M%S}"
    pdf_path = ORDERS_DIR / f"{po_number}.pdf"
    _render_pdf(pdf_path, po_number, now, buyer, lines, subtotal, tax, tax_percent, total, notes)

    return {
        "ok": True,
        "po_number": po_number,
        "pdf_path": str(pdf_path),
        "buyer": buyer,
        "currency": CURRENCY,
        "lines": lines,
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
    }


def _render_pdf(path, po_number, when, buyer, lines, subtotal, tax, tax_percent, total, notes):
    styles = getSampleStyleSheet()
    title = ParagraphStyle("title", parent=styles["Heading1"], fontSize=16, spaceAfter=2)
    meta = ParagraphStyle("meta", parent=styles["Normal"], fontSize=9, textColor=colors.grey)

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        title=po_number,
    )

    story = [
        Paragraph("PURCHASE ORDER", title),
        Paragraph(f"{po_number} &nbsp;&middot;&nbsp; {when:%d %b %Y, %H:%M}", meta),
        Spacer(1, 10 * mm),
        Paragraph(f"<b>Supplier:</b> {SUPPLIER}", styles["Normal"]),
        Paragraph(f"<b>Buyer:</b> {buyer}", styles["Normal"]),
        Spacer(1, 8 * mm),
    ]

    data = [["#", "Item", "Qty (kg)", f"Rate ({CURRENCY}/kg)", f"Amount ({CURRENCY})"]]
    for i, line in enumerate(lines, 1):
        data.append(
            [
                str(i),
                line["name"].title(),
                f"{line['quantity_kg']:g}",
                f"{line['rate_per_kg']:,.2f}",
                f"{line['amount']:,.2f}",
            ]
        )

    data.append(["", "", "", "Subtotal", f"{subtotal:,.2f}"])
    if tax_percent:
        data.append(["", "", "", f"Tax ({tax_percent:g}%)", f"{tax:,.2f}"])
    data.append(["", "", "", "Total", f"{total:,.2f}"])

    total_rows = len(data)
    tax_rows = 1 if tax_percent else 0
    first_summary = total_rows - (2 + tax_rows)

    table = Table(data, colWidths=[12 * mm, 62 * mm, 25 * mm, 38 * mm, 37 * mm])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
                ("LINEBELOW", (0, 1), (-1, first_summary - 1), 0.25, colors.HexColor("#cccccc")),
                ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LINEABOVE", (3, first_summary), (-1, first_summary), 0.8, colors.black),
                ("FONTNAME", (3, -1), (-1, -1), "Helvetica-Bold"),
            ]
        )
    )
    story.append(table)

    if notes:
        story += [Spacer(1, 8 * mm), Paragraph(f"<b>Notes:</b> {notes}", styles["Normal"])]

    story += [
        Spacer(1, 14 * mm),
        Paragraph("Generated automatically. Prices are indicative and subject to change.", meta),
    ]
    doc.build(story)


class BearerAuth:
    """Minimal ASGI middleware: every HTTP request needs the shared token.

    Accepts either an ``Authorization: Bearer <token>`` header or ``?token=<token>``.
    """

    def __init__(self, app, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self.token:
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        supplied = headers.get(b"authorization", b"").decode()
        # Fall back to ?token=... for clients that cannot set a custom header.
        query = parse_qs(scope.get("query_string", b"").decode())
        from_query = (query.get("token") or [""])[0]
        if supplied != f"Bearer {self.token}" and from_query != self.token:
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": b'{"error":"unauthorized"}'})
            return
        await self.app(scope, receive, send)


app = BearerAuth(mcp.streamable_http_app(), TOKEN)

if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("VEG_MCP_TOKEN is not set. Refusing to start without a token.")
    print(f"veggies MCP server on http://{HOST}:{PORT}/mcp  (orders -> {ORDERS_DIR})")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
