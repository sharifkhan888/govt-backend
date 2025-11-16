from pathlib import Path
import os
import tempfile
from datetime import datetime
from decimal import Decimal
from openpyxl import Workbook
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics

from .. import models

# Export directory strategy:
# 1) Prefer environment variable EXPORT_ROOT (absolute path)
# 2) Fallback to OS temp directory under a namespaced folder
_env_root = os.environ.get("EXPORT_ROOT")
if _env_root and _env_root.strip():
    EXPORT_DIR = Path(_env_root).expanduser().resolve()
else:
    EXPORT_DIR = Path(tempfile.gettempdir()) / "govt-exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def _timestamped(name: str, ext: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return EXPORT_DIR / f"{name}-{ts}.{ext}"

def _get_council_and_district() -> tuple[str, str]:
    s = models.Setting.objects.order_by("id").first()
    council = (s.council_name.strip() if s and s.council_name else "")
    district = (s.district_name.strip() if s and s.district_name else "")
    return council or "Council Name", district or "District Name"

def _format_district(d: str) -> str:
    if not d:
        return ""
    d2 = d.strip()
    return d2 if d2.lower().startswith("dist") else f"Dist. {d2}"

# Basic Marathi name converter: maps common city/district names and digits.
# Falls back to original text if no mapping.
def _to_marathi_name(text: str) -> str:
    if not text:
        return ""
    digits = str.maketrans({
        "0": "०", "1": "१", "2": "२", "3": "३", "4": "४",
        "5": "५", "6": "६", "7": "७", "8": "८", "9": "९",
    })
    t = text.strip()
    # Known mappings (extend as needed)
    known = {
        "jalgaon": "जळगाव",
        "jalgao": "जळगाव",
        "bhusawal": "भुसावळ",
        "bhusaval": "भुसावळ",
        "malkapur": "मलकापूर",
        "buldhana": "बुलढाणा",
        "mumbai": "मुंबई",
        "pune": "पुणे",
        "nagpur": "नागपूर",
        "nashik": "नाशिक",
        "nashirabad": "नशिराबाद",
        "akola": "अकोला",
    }
    key = t.lower()
    mr = known.get(key)
    if mr:
        return mr
    # If not found, keep original but convert digits to Marathi
    return t.translate(digits)


def export_bank_accounts_excel() -> str:
    wb = Workbook()
    ws = wb.active
    council, district = _get_council_and_district()
    ws.append([council])
    ws.append([_format_district(district)])
    ws.append([""])
    ws.append([
        "Account ID",
        "Account Name",
        "Account No",
        "Bank",
        "IFSC",
        "Manager",
        "Contact",
        "Address",
        "Status",
    ])
    for b in models.BankAccount.objects.all():
        ws.append([
            b.account_id,
            b.account_name,
            str(b.account_no or ""),
            b.bank_name,
            b.ifsc,
            b.bank_manager_name,
            b.bank_contact,
            b.bank_address,
            b.status,
        ])
    path = _timestamped("bank-accounts", "xlsx")
    wb.save(path)
    return str(path)


def export_contractors_excel() -> str:
    wb = Workbook()
    ws = wb.active
    council, district = _get_council_and_district()
    ws.append([council])
    ws.append([_format_district(district)])
    ws.append([""])
    ws.append(["ID", "Name", "Address", "Contact", "GST", "Bank", "IFSC", "Status"])
    for c in models.Contractor.objects.all():
        ws.append([
            c.contractor_id,
            c.contractor_name,
            c.contractor_address,
            c.contractor_contact_no,
            c.contractor_gst,
            c.contractor_bank,
            c.contractor_ifsc,
            c.status,
        ])
    path = _timestamped("contractors", "xlsx")
    wb.save(path)
    return str(path)


def export_report_pdf(report_type: str) -> str:
    path = _timestamped(f"{report_type}-report", "pdf")
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, 800, f"{report_type.title()} Report")
    c.setFont("Helvetica", 10)
    c.drawString(72, 780, datetime.now().strftime("Generated on %Y-%m-%d %H:%M"))
    c.line(72, 775, 520, 775)
    c.drawString(72, 760, "This is a placeholder report. Integrate with business logic as needed.")
    c.showPage()
    c.save()
    return str(path)


def export_transaction_register_pdf(start: str | None, end: str | None, scope: str = "both") -> str:
    """नगद वहिवाट (Transaction Register) PDF.

    - Marathi headers and clean boxed grid like other reports.
    - Auto-fit column widths; switches to landscape if needed.
    - Credit amounts appear in "प्राप्त" column, Debit in "खर्च".
    """
    path = _timestamped("transaction-register", "pdf")

    # Query rows
    qs = models.Transaction.objects.all()
    if start:
        qs = qs.filter(transaction_date__gte=start)
    if end:
        qs = qs.filter(transaction_date__lte=end)
    # Apply scope for rows: only Credit / only Debit / Both
    if scope == "credit":
        rows_qs = list(qs.filter(tx_type=models.Transaction.CREDIT).order_by("transaction_date", "transaction_id"))
    elif scope == "debit":
        rows_qs = list(qs.filter(tx_type=models.Transaction.DEBIT).order_by("transaction_date", "transaction_id"))
    else:
        rows_qs = list(qs.order_by("transaction_date", "transaction_id"))

    # Totals for selected range and balances (opening/closing)
    credit_total = _sum_amount(qs.filter(tx_type=models.Transaction.CREDIT))
    debit_total = _sum_amount(qs.filter(tx_type=models.Transaction.DEBIT))
    net_total = credit_total - debit_total

    # Balances relative to today:
    # - Previous Balance: net of all transactions before today
    # - Today Balance: previous balance + net of transactions on today
    from datetime import datetime as _dt
    _today = _dt.today().date()
    base_qs = models.Transaction.objects.all()
    prev_qs = base_qs.filter(transaction_date__lt=_today)
    prev_credit = _sum_amount(prev_qs.filter(tx_type=models.Transaction.CREDIT))
    prev_debit = _sum_amount(prev_qs.filter(tx_type=models.Transaction.DEBIT))
    previous_balance = prev_credit - prev_debit

    day_qs = base_qs.filter(transaction_date=_today)
    day_credit = _sum_amount(day_qs.filter(tx_type=models.Transaction.CREDIT))
    day_debit = _sum_amount(day_qs.filter(tx_type=models.Transaction.DEBIT))
    today_balance = previous_balance + (day_credit - day_debit)

    # Register Devanagari fonts (regular + bold) so Marathi glyphs render
    BODY_FONT = "Helvetica"
    HEADER_FONT = "Helvetica-Bold"
    TITLE_FONT = "Helvetica-Bold"
    def _register_dev_fonts() -> tuple[str | None, str | None]:
        try:
            from reportlab.pdfbase.ttfonts import TTFont
        except Exception:
            return (None, None)
        # Candidate locations for regular/bold
        reg_candidates = [
            Path(__file__).resolve().parents[3] / "assets" / "static" / "fonts" / "NotoSansDevanagari-Regular.ttf",
            Path("C:/Windows/Fonts/NotoSansDevanagari-Regular.ttf"),
            Path("C:/Windows/Fonts/Nirmala.ttf"),
            Path("C:/Windows/Fonts/Mangal.ttf"),
            Path("C:/Windows/Fonts/Kokila.ttf"),
            Path("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"),
        ]
        bold_candidates = [
            Path(__file__).resolve().parents[3] / "assets" / "static" / "fonts" / "NotoSansDevanagari-Bold.ttf",
            Path("C:/Windows/Fonts/NotoSansDevanagari-Bold.ttf"),
            Path("C:/Windows/Fonts/NirmalaB.ttf"),
            Path("C:/Windows/Fonts/MangalBold.ttf"),
            Path("C:/Windows/Fonts/KokilaBold.ttf"),
        ]
        reg_name = None
        bold_name = None
        # Register regular
        for p in reg_candidates:
            try:
                if p.exists():
                    pdfmetrics.registerFont(TTFont("Devanagari-Regular", str(p)))
                    reg_name = "Devanagari-Regular"
                    break
            except Exception:
                continue
        # Register bold (if available)
        for p in bold_candidates:
            try:
                if p.exists():
                    pdfmetrics.registerFont(TTFont("Devanagari-Bold", str(p)))
                    bold_name = "Devanagari-Bold"
                    break
            except Exception:
                continue
        return (reg_name, bold_name)

    dev_reg, dev_bold = _register_dev_fonts()
    if dev_reg:
        BODY_FONT = dev_reg
    if dev_bold:
        HEADER_FONT = dev_bold
        TITLE_FONT = dev_bold
    elif dev_reg:
        # If bold not found, use regular for headings too
        HEADER_FONT = dev_reg
        TITLE_FONT = dev_reg

    BODY_SIZE = 11
    HEADER_SIZE = 11
    CELL_PAD_X = 6
    CELL_PAD_Y = 6
    ROW_HEIGHT = max(22, BODY_SIZE + CELL_PAD_Y * 2)

    # Measurement helper
    def tw(text: str, font: str = BODY_FONT, size: int = BODY_SIZE) -> float:
        return pdfmetrics.stringWidth(str(text or "-"), font, size)

    # Marathi headers per requested mapping (include Sr.No)
    headers = [
        "Sr.No",
        "दिनांक",
        "प्रमाणपत्र क्र.",
        "प्रदाता / अपेता",
        "तपशील",
        "लेखा संकेतांक",
        "एल.एफ.",
        "प्राप्त रक्कम",
        "खर्च रक्कम",
    ]

    # Build data rows per user mapping
    # Sr.No, Date, Transaction ID, Contractor Name, Particular, Bank Name,
    # Credit Amount -> "प्राप्त रक्कम", Debit Amount -> "खर्च रक्कम", Type -> "एल.एफ."
    data_rows: list[tuple[str, str, str, str, str, str, str, str, str]] = []
    sr = 1
    for t in rows_qs:
        d = getattr(t, "transaction_date", None)
        date_str = d.isoformat() if d else "-"
        txid = str(getattr(t, "transaction_id", ""))
        contractor_name = (t.contractor_display_name or (t.contractor.contractor_name if t.contractor else "") or "-").strip() or "-"
        particular = (t.particular or t.remark or "-").strip() or "-"
        bank_label = (t.bank_display_name or "").strip()
        if not bank_label and t.bank_account:
            bank_label = (
                (t.bank_account.bank_name or "").strip()
                or (t.bank_account.account_name or "").strip()
                or (str(t.bank_account.account_no or "").strip())
            )
        bank_label = bank_label or "-"
        debit_amt = "-"
        credit_amt = "-"
        try:
            amt = f"{Decimal(str(t.amount or '0')):.2f}"
        except Exception:
            amt = str(t.amount or "0")
        txtype_en = (t.tx_type or "").strip().lower()
        if txtype_en == models.Transaction.DEBIT:
            debit_amt = amt
        elif txtype_en == models.Transaction.CREDIT:
            credit_amt = amt
        type_label = (t.tx_type or "").capitalize() or "-"
        # Column order per request: SrNo, Date, Voucher, Party, Particular, Account, Type, Received(Credit), Expense(Debit)
        data_rows.append((str(sr), date_str, txid, contractor_name, particular, bank_label, type_label, credit_amt, debit_amt))
        sr += 1

    # Minimum baseline widths tuned to fit within landscape page even when scaled
    # [SrNo, Date, Voucher, Party, Particular, Account, Type, Received, Expense]
    min_w = [35, 70, 55, 110, 120, 95, 50, 90, 90]
    max_w = [tw(h, HEADER_FONT, HEADER_SIZE) for h in headers]
    for r in data_rows:
        for i, cell in enumerate(r):
            max_w[i] = max(max_w[i], tw(cell))
    col_w = [max(min_w[i], max_w[i] + CELL_PAD_X * 2) for i in range(len(headers))]

    # Professional single-page Marathi register layout on landscape A4
    # Page margins (mm): 12mm left/right, 10mm top/bottom
    # 1mm ≈ 2.8346pt
    margin_l = int(12 * 2.8346)  # ≈ 34pt
    margin_r = int(12 * 2.8346)
    margin_t = int(10 * 2.8346)  # ≈ 28pt
    margin_b = int(10 * 2.8346)
    page_size = landscape(A4)

    c = canvas.Canvas(str(path), pagesize=page_size)
    width, height = page_size

    # Measure content widths and assign proportional column widths so text fits
    CONTENT_W = width - margin_l - margin_r
    max_w = [tw(h, HEADER_FONT, HEADER_SIZE) for h in headers]
    for r in data_rows:
        for i, cell in enumerate(r):
            max_w[i] = max(max_w[i], tw(cell))
    desired_w = [max(min_w[i], int(max_w[i] + CELL_PAD_X * 2)) for i in range(len(headers))]
    # Cap very wide text columns so numeric columns remain fully visible
    # Index map: 0 SrNo, 1 Date, 2 Voucher, 3 Party, 4 Particular, 5 Account, 6 Type, 7 Received, 8 Expense
    cap_particular = int((width - margin_l - margin_r) * 0.18)  # 18% of content width
    cap_party = int((width - margin_l - margin_r) * 0.18)       # 18% of content width
    if desired_w[4] > cap_particular:
        reduce_by = desired_w[4] - cap_particular
        desired_w[4] = cap_particular
        # Redistribute to numeric-heavy columns (amounts, account)
        for idx in (7, 8, 5):
            desired_w[idx] += int(reduce_by / 3)
    if desired_w[3] > cap_party:
        reduce_by = desired_w[3] - cap_party
        desired_w[3] = cap_party
        for idx in (7, 8, 5):
            desired_w[idx] += int(reduce_by / 3)
    total_desired = sum(desired_w)
    if total_desired <= CONTENT_W:
        col_w = desired_w
    else:
        # Scale all columns proportionally to fit within content width
        scale = CONTENT_W / total_desired
        col_w = [max(30, int(desired_w[i] * scale)) for i in range(len(headers))]
        # Distribute remaining points across columns prioritizing numeric cells
        remainder = CONTENT_W - sum(col_w)
        if remainder > 0:
            # Prioritize numeric columns (Received, Expense), then Account
            order = [7, 8, 5, 2, 0, 6, 1, 3, 4]
            idx = 0
            while remainder > 0:
                col_w[order[idx % len(order)]] += 1
                remainder -= 1
                idx += 1
        elif remainder < 0:
            # If we overshot, shave from text-heavy columns first
            order = [4, 3, 5, 1, 2]
            idx = 0
            while remainder < 0:
                take_idx = order[idx % len(order)]
                if col_w[take_idx] > 40:
                    col_w[take_idx] -= 1
                    remainder += 1
                idx += 1

    # Compute X positions for single table
    LEFT = margin_l
    X = [LEFT]
    for i in range(1, len(col_w)):
        X.append(X[i - 1] + col_w[i - 1])
    table_total_w = sum(col_w)

    # Header renderer
    page_no = 1
    # Fetch council/district from settings and convert to Marathi when possible
    council_en, district_en = _get_council_and_district()
    council_mr = _to_marathi_name(council_en) or council_en
    district_mr = _to_marathi_name(district_en) or district_en

    def _header(title_suffix: str | None = None):
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.8)
        c.setFont(TITLE_FONT, 20)
        # Title and subtitle as requested (bold)
        c.drawCentredString(width / 2, height - 40, f"{council_mr} नगरपरिषद व्यवहार नोंदवही")
        c.setFont(TITLE_FONT, 12)
        c.drawCentredString(width / 2, height - 60, f"जि. {district_mr}")
        # Additional Marathi lines below district (transaction register only)
        c.setFont(HEADER_FONT, 11)
        c.drawCentredString(width / 2, height - 78, "नमुना क्र.१")
        c.drawCentredString(width / 2, height - 94, "(नियम क्रमांक ४८, ४०, १४, ४७६ पहा)")
        c.drawCentredString(width / 2, height - 110, "सर्व साधारण लेखवही / लेखापालाची लेखवही")
        # Date range on left
        c.setFont(BODY_FONT, 10)
        c.drawString(margin_l, height - 128, f"From: {start or '-'}  To: {end or '-'}")
        # Page number at top-right
        c.setFillColor(colors.red)
        c.setFont(BODY_FONT, 12)
        c.drawRightString(width - margin_r, height - 40, str(page_no))
        c.setFillColor(colors.black)

    # Start lower to make room for additional header lines
    y_start = height - 140
    y = y_start

    # Text clipping helper
    def fit_text(text: str, max_width: float, font: str = BODY_FONT, size: int = BODY_SIZE) -> str:
        if text is None:
            return "-"
        t = str(text)
        if not t:
            return "-"
        w = pdfmetrics.stringWidth(t, font, size)
        if w <= max_width:
            return t
        ell = "…"
        lo, hi = 0, len(t)
        while lo < hi:
            mid = (lo + hi) // 2
            candidate = t[:mid] + ell
            if pdfmetrics.stringWidth(candidate, font, size) <= max_width:
                lo = mid + 1
            else:
                hi = mid
        return t[:max(1, lo - 1)] + ell
    def ensure_space(rows_needed: int = 1):
        nonlocal y, page_no
        if y - rows_needed * ROW_HEIGHT < margin_b:
            c.showPage()
            page_no += 1
            _header("Continued")
            y = y_start
            draw_column_headers()

    def draw_column_headers():
        nonlocal y
        c.setFont(HEADER_FONT, HEADER_SIZE)
        # Outer header row with thicker line
        # Thin borders for clean professional look
        c.setLineWidth(0.6)
        row_bottom = y - ROW_HEIGHT
        for i, h in enumerate(headers):
            c.rect(X[i], row_bottom, col_w[i], ROW_HEIGHT)
            text_y = row_bottom + (ROW_HEIGHT - HEADER_SIZE) / 2 + 1.5
            cx = X[i] + col_w[i] / 2
            c.drawCentredString(cx, text_y, h)
        c.setLineWidth(0.8)
        y = row_bottom

    def draw_blank_row():
        nonlocal y
        ensure_space(1)
        row_bottom = y - ROW_HEIGHT
        for i in range(len(headers)):
            c.rect(X[i], row_bottom, col_w[i], ROW_HEIGHT)
        y = row_bottom

    def draw_numbering_row():
        nonlocal y
        nums = ["(१)", "(२)", "(३)", "(४)", "(५)", "(६)", "(७)", "(८)", "(९)"]
        c.setFont(BODY_FONT, BODY_SIZE)
        row_bottom = y - ROW_HEIGHT
        for i, n in enumerate(nums):
            c.rect(X[i], row_bottom, col_w[i], ROW_HEIGHT)
            text_y = row_bottom + (ROW_HEIGHT - BODY_SIZE) / 2 + 1.5
            cx = X[i] + col_w[i] / 2
            c.drawCentredString(cx, text_y, n)
        y = row_bottom

    # Compose document
    _header(None)
    draw_column_headers()
    draw_numbering_row()
    # Render data rows
    def draw_row(row: tuple[str, str, str, str, str, str, str, str, str]):
        nonlocal y
        ensure_space(1)
        c.setFont(BODY_FONT, BODY_SIZE)
        row_bottom = y - ROW_HEIGHT
        for i, val in enumerate(row):
            c.rect(X[i], row_bottom, col_w[i], ROW_HEIGHT)
            text_y = row_bottom + (ROW_HEIGHT - BODY_SIZE) / 2 + 1.5
            available = col_w[i] - 2 * CELL_PAD_X
            txt = fit_text(val, available)
            cx = X[i] + col_w[i] / 2
            c.drawCentredString(cx, text_y, txt)
        y = row_bottom

    for r in data_rows:
        draw_row(r)

    # Summary rows (Marathi) under the table
    def draw_summary(label: str, value: str):
        nonlocal y
        # Make sure there's room for one summary row
        if y - ROW_HEIGHT < margin_b:
            c.showPage()
            _header("Continued")
            y = y_start
        label_w = table_total_w * 0.65
        value_w = table_total_w - label_w
        row_bottom = y - ROW_HEIGHT
        c.rect(LEFT, row_bottom, label_w, ROW_HEIGHT)
        c.rect(LEFT + label_w, row_bottom, value_w, ROW_HEIGHT)
        c.setFont(HEADER_FONT, 12)
        ty = row_bottom + (ROW_HEIGHT - 12) / 2 + 1.5
        c.drawString(LEFT + CELL_PAD_X, ty, label)
        c.drawRightString(LEFT + label_w + value_w - CELL_PAD_X, ty, value)
        y = row_bottom

    # Values formatted to two decimals
    def fmt(d: Decimal) -> str:
        try:
            return f"{Decimal(str(d)):.2f}"
        except Exception:
            return str(d)

    # Show totals according to scope selection
    if scope == "credit":
        draw_summary("एकूण मासिक जमा", fmt(credit_total))
        draw_summary("एकूण", fmt(net_total))
    elif scope == "debit":
        draw_summary("एकूण मासिक खर्च", fmt(debit_total))
        draw_summary("एकूण", fmt(net_total))
    else:
        draw_summary("एकूण मासिक जमा", fmt(credit_total))
        draw_summary("एकूण मासिक खर्च", fmt(debit_total))
        draw_summary("एकूण", fmt(net_total))
    draw_summary("प्रारंभिक शिल्लक", fmt(previous_balance))
    draw_summary("अखेरची शिल्लक", fmt(today_balance))

    c.showPage()
    c.save()
    return str(path)

# ---- New specialized report exports ----

def _sum_amount(qs) -> Decimal:
    total = Decimal("0")
    for t in qs:
        if t.amount is not None:
            total += Decimal(str(t.amount))
    return total


def export_profit_loss_pdf(start: str | None, end: str | None, scope: str = "both") -> str:
    """Export a professional Profit & Loss PDF with boxed grid.

    Requirements implemented:
    - Bold centered headings: Council (e.g., "Malkapur"), "Dist. Buldhana", and "Profit and Loss Report".
    - Date range line.
    - Excel-like grid: clear box borders around every column and row.
    - Auto-fit column widths based on content with padding; switches to landscape if needed.
    - Summary rows at bottom inside bordered boxes (Total Credit/Debit and Net).
    """
    path = _timestamped("profit-and-loss", "pdf")

    def _header(title_suffix: str | None = None):
        # Header
        c.setFont("Helvetica-Bold", 20)
        council, district = _get_council_and_district()
        c.drawCentredString(width / 2, height - 40, council)
        c.setFont("Helvetica", 12)
        c.drawCentredString(width / 2, height - 60, _format_district(district))
        c.setFont("Helvetica-Bold", 16)
        title = "Profit and Loss Report" if not title_suffix else f"Profit and Loss Report ({title_suffix})"
        c.drawCentredString(width / 2, height - 88, title)
        # Date range
        c.setFont("Helvetica", 10)
        c.drawString(60, height - 110, f"From: {start or '-'}  To: {end or '-'}")

    # Transactions in range
    qs = models.Transaction.objects.all()
    if start:
        qs = qs.filter(transaction_date__gte=start)
    if end:
        qs = qs.filter(transaction_date__lte=end)
    qs_credit = qs.filter(tx_type=models.Transaction.CREDIT).order_by("transaction_date", "transaction_id")
    qs_debit = qs.filter(tx_type=models.Transaction.DEBIT).order_by("transaction_date", "transaction_id")
    total_credit = _sum_amount(qs_credit)
    total_debit = _sum_amount(qs_debit)
    net = total_credit - total_debit

    # Balances relative to today:
    # - Previous Balance: net of all transactions before today
    # - Today Balance: previous balance + net of transactions on today
    from datetime import datetime as _dt
    _today = _dt.today().date()
    base_qs = models.Transaction.objects.all()
    prev_qs = base_qs.filter(transaction_date__lt=_today)
    prev_credit = _sum_amount(prev_qs.filter(tx_type=models.Transaction.CREDIT))
    prev_debit = _sum_amount(prev_qs.filter(tx_type=models.Transaction.DEBIT))
    previous_balance = prev_credit - prev_debit

    day_qs = base_qs.filter(transaction_date=_today)
    day_credit = _sum_amount(day_qs.filter(tx_type=models.Transaction.CREDIT))
    day_debit = _sum_amount(day_qs.filter(tx_type=models.Transaction.DEBIT))
    today_balance = previous_balance + (day_credit - day_debit)

    # Prepare dataset based on scope to measure widths before choosing page size
    qs = models.Transaction.objects.all()
    if start:
        qs = qs.filter(transaction_date__gte=start)
    if end:
        qs = qs.filter(transaction_date__lte=end)
    qs_credit = qs.filter(tx_type=models.Transaction.CREDIT).order_by("transaction_date", "transaction_id")
    qs_debit = qs.filter(tx_type=models.Transaction.DEBIT).order_by("transaction_date", "transaction_id")
    total_credit = _sum_amount(qs_credit)
    total_debit = _sum_amount(qs_debit)
    net = total_credit - total_debit

    if scope == "credit":
        rows_qs = list(qs_credit)
    elif scope == "debit":
        rows_qs = list(qs_debit)
    else:
        rows_qs = list(qs.order_by("transaction_date", "transaction_id"))

    # Fonts and spacing
    BODY_FONT = "Helvetica"
    BODY_SIZE = 10
    HEADER_FONT = "Helvetica-Bold"
    HEADER_SIZE = 10
    TITLE_FONT = "Helvetica-Bold"
    CELL_PAD_X = 6
    CELL_PAD_Y = 6
    ROW_HEIGHT = max(22, BODY_SIZE + CELL_PAD_Y * 2)

    # Helper to compute text widths (without canvas)
    def tw(text: str, font: str = BODY_FONT, size: int = BODY_SIZE) -> float:
        return pdfmetrics.stringWidth(str(text or "-"), font, size)

    headers = ["Id", "Date", "Type", "Amount", "Bank", "Contractor", "Account"]

    # Build list of row strings for measurement
    data_rows: list[tuple[str, str, str, str, str, str, str]] = []
    for t in rows_qs:
        d = getattr(t, "transaction_date", None)
        date_str = d.isoformat() if d else "-"
        txid = str(getattr(t, "transaction_id", ""))
        txtype = (t.tx_type or "").strip()
        try:
            amount = f"{Decimal(str(t.amount or '0')):.2f}"
        except Exception:
            amount = str(t.amount or "0")
        # Prefer persisted snapshot so Bank column stays populated even if FK deleted
        bank_name = (getattr(t, "bank_display_name", "") or "").strip()
        if not bank_name:
            if t.bank_account:
                bank_name = (t.bank_account.bank_name or t.bank_account.account_name or str(t.bank_account.account_no or "") or "").strip()
        if not bank_name:
            bank_name = "-"
        # Prefer stored snapshot to keep name after deletion
        contractor_name = (getattr(t, "contractor_display_name", "") or (t.contractor.contractor_name if t.contractor else "") or "-")
        account = (t.account or "").strip()
        data_rows.append((txid, date_str, txtype, amount, bank_name, contractor_name, account))

    # Minimum widths to keep the table readable
    min_w = [30, 80, 50, 90, 90, 100, 60]
    # Measure max content width per column including headers
    max_w = [tw(h, HEADER_FONT, HEADER_SIZE) for h in headers]
    for r in data_rows:
        for i, cell in enumerate(r):
            max_w[i] = max(max_w[i], tw(cell))
    # Add horizontal padding for each column
    col_w = [max(min_w[i], max_w[i] + CELL_PAD_X * 2) for i in range(len(headers))]

    # Decide page orientation: widen to landscape if portrait would overflow
    portrait_w, portrait_h = A4
    margin_l = 50
    margin_r = 50
    margin_t = 40
    margin_b = 60
    table_total_w = sum(col_w)
    content_w_portrait = portrait_w - margin_l - margin_r
    if table_total_w > content_w_portrait:
        page_size = landscape(A4)
    else:
        page_size = A4

    c = canvas.Canvas(str(path), pagesize=page_size)
    width, height = page_size

    # Re-check available width and scale down slightly if still overflowing
    LEFT_MARGIN = margin_l
    RIGHT_MARGIN = margin_r
    CONTENT_W = (width - LEFT_MARGIN - RIGHT_MARGIN)
    if table_total_w > CONTENT_W:
        scale = CONTENT_W / table_total_w
        col_w = [max(min_w[i], round(w * scale)) for i, w in enumerate(col_w)]
        table_total_w = sum(col_w)

    # Center the entire table horizontally
    LEFT = max(LEFT_MARGIN, (width - table_total_w) / 2)
    RIGHT = LEFT + table_total_w

    # Compute X positions for columns (no inter-column gaps since boxes touch)
    X = [LEFT]
    for i in range(1, len(col_w)):
        X.append(X[i - 1] + col_w[i - 1])

    # Header block
    def _header(title_suffix: str | None = None):
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.8)
        c.setFont(TITLE_FONT, 20)
        council, district = _get_council_and_district()
        c.drawCentredString(width / 2, height - 40, council)
        c.setFont("Helvetica", 12)
        c.drawCentredString(width / 2, height - 60, _format_district(district))
        c.setFont(TITLE_FONT, 16)
        title = "Profit and Loss Report" if not title_suffix else f"Profit and Loss Report ({title_suffix})"
        c.drawCentredString(width / 2, height - 88, title)
        c.setFont(BODY_FONT, 10)
        c.drawString(LEFT, height - 110, f"From: {start or '-'}  To: {end or '-'}")

    # Compute starting Y for table
    y_start = height - 136
    y = y_start

    # Text fitting helper (last-resort clipping)
    def fit_text(text: str, max_width: float, font: str = BODY_FONT, size: int = BODY_SIZE) -> str:
        if text is None:
            return "-"
        t = str(text)
        if not t:
            return "-"
        w = pdfmetrics.stringWidth(t, font, size)
        if w <= max_width:
            return t
        ell = "…"
        lo, hi = 0, len(t)
        while lo < hi:
            mid = (lo + hi) // 2
            candidate = t[:mid] + ell
            if pdfmetrics.stringWidth(candidate, font, size) <= max_width:
                lo = mid + 1
            else:
                hi = mid
        return t[:max(1, lo - 1)] + ell

    def ensure_space(rows_needed: int = 1):
        nonlocal y
        if y - rows_needed * ROW_HEIGHT < margin_b:
            c.showPage()
            _header("Continued")
            y = y_start
            # Redraw column headers on new page
            draw_column_headers()

    # Draw column headers with boxed cells
    def draw_column_headers():
        nonlocal y
        c.setFont(HEADER_FONT, HEADER_SIZE)
        row_bottom = y - ROW_HEIGHT
        for i, h in enumerate(headers):
            c.rect(X[i], row_bottom, col_w[i], ROW_HEIGHT)
            text_y = row_bottom + (ROW_HEIGHT - HEADER_SIZE) / 2 + 1.5
            cx = X[i] + col_w[i] / 2
            c.drawCentredString(cx, text_y, h)
        y = row_bottom

    # Draw data rows inside boxed cells
    def draw_row(row: tuple[str, str, str, str, str, str, str]):
        nonlocal y
        ensure_space(1)
        c.setFont(BODY_FONT, BODY_SIZE)
        row_bottom = y - ROW_HEIGHT
        for i, val in enumerate(row):
            c.rect(X[i], row_bottom, col_w[i], ROW_HEIGHT)
            text_y = row_bottom + (ROW_HEIGHT - BODY_SIZE) / 2 + 1.5
            available = col_w[i] - 2 * CELL_PAD_X
            cx = X[i] + col_w[i] / 2
            c.drawCentredString(cx, text_y, fit_text(val, available))
        y = row_bottom

    # Draw summary rows inside bordered boxes spanning the table width
    def draw_summary(label: str, value: str):
        nonlocal y
        ensure_space(1)
        label_w = table_total_w * 0.65
        value_w = table_total_w - label_w
        row_bottom = y - ROW_HEIGHT
        # Outer boxes
        c.rect(LEFT, row_bottom, label_w, ROW_HEIGHT)
        c.rect(LEFT + label_w, row_bottom, value_w, ROW_HEIGHT)
        # Bold text
        c.setFont("Helvetica-Bold", 12)
        ty = row_bottom + (ROW_HEIGHT - 12) / 2 + 1.5
        c.drawString(LEFT + CELL_PAD_X, ty, label)
        c.drawRightString(LEFT + label_w + value_w - CELL_PAD_X, ty, value)
        y = row_bottom

    # Text fitting helper to avoid column overlap
    def fit_text(text: str, max_width: float, font: str = "Helvetica", size: int = 10) -> str:
        """Return text clipped with ellipsis to fit within max_width.
        Uses current canvas for precise width measurement.
        """
        if text is None:
            return "-"
        t = str(text)
        if not t:
            return "-"
        w = c.stringWidth(t, font, size)
        if w <= max_width:
            return t
        ell = "…"
        # Binary trim for efficiency on long strings
        lo, hi = 0, len(t)
        while lo < hi:
            mid = (lo + hi) // 2
            candidate = t[:mid] + ell
            if c.stringWidth(candidate, font, size) <= max_width:
                lo = mid + 1
            else:
                hi = mid
        clipped = t[:max(1, lo - 1)] + ell
        return clipped

    def ensure_space(rows_needed: int = 1):
        nonlocal y
        if y - rows_needed * ROW_HEIGHT < 60:
            c.showPage()
            _header("Continued")
            y = y_start

    # Compose document
    _header(None)
    # Section label
    c.setFont("Helvetica-Bold", 12)
    c.drawString(LEFT, y, "Transactions")
    y -= 18

    # Column headers and rows
    draw_column_headers()
    for r in data_rows:
        draw_row(r)

    # Summary boxes
    if scope == "credit":
        draw_summary("Total Credit", f"{total_credit}")
        draw_summary("Net (Profit/Loss)", f"{net}")
        draw_summary("Previous Balance", f"{previous_balance}")
        draw_summary("Today Balance", f"{today_balance}")
    elif scope == "debit":
        draw_summary("Total Debit", f"{total_debit}")
        draw_summary("Net (Profit/Loss)", f"{net}")
        draw_summary("Previous Balance", f"{previous_balance}")
        draw_summary("Today Balance", f"{today_balance}")
    else:
        draw_summary("Total Credit", f"{total_credit}")
        draw_summary("Total Debit", f"{total_debit}")
        draw_summary("Net (Profit/Loss)", f"{net}")
        draw_summary("Previous Balance", f"{previous_balance}")
        draw_summary("Today Balance", f"{today_balance}")

    c.showPage()
    c.save()
    return str(path)


def export_bank_wise_pdf(start: str | None, end: str | None, bank_id: int | None, scope: str = "both") -> str:
    """Bank Account Wise Report using the same boxed table design.

    Supports scope filter:
    - "credit": include credit transactions and show Credit + Net
    - "debit": include debit transactions and show Debit + Net
    - "both": include all transactions and show Credit + Debit + Net
    """
    path = _timestamped("bank-wise", "pdf")

    # Query
    qs = models.Transaction.objects.all()
    if bank_id:
        qs = qs.filter(bank_account_id=bank_id)
    if start:
        qs = qs.filter(transaction_date__gte=start)
    if end:
        qs = qs.filter(transaction_date__lte=end)

    credit_qs = qs.filter(tx_type=models.Transaction.CREDIT)
    debit_qs = qs.filter(tx_type=models.Transaction.DEBIT)
    credit = _sum_amount(credit_qs)
    debit = _sum_amount(debit_qs)
    net = credit - debit
    # Today-based balances scoped to selected bank (ignore date filters)
    from datetime import datetime as _dt
    _today = _dt.today().date()
    base_qs = models.Transaction.objects.all()
    if bank_id:
        base_qs = base_qs.filter(bank_account_id=bank_id)
    prev_qs = base_qs.filter(transaction_date__lt=_today)
    prev_credit = _sum_amount(prev_qs.filter(tx_type=models.Transaction.CREDIT))
    prev_debit = _sum_amount(prev_qs.filter(tx_type=models.Transaction.DEBIT))
    previous_balance = prev_credit - prev_debit
    day_qs = base_qs.filter(transaction_date=_today)
    day_credit = _sum_amount(day_qs.filter(tx_type=models.Transaction.CREDIT))
    day_debit = _sum_amount(day_qs.filter(tx_type=models.Transaction.DEBIT))
    today_balance = previous_balance + (day_credit - day_debit)
    # Rows filtered by scope
    if scope == "credit":
        rows_qs = list(credit_qs.order_by("transaction_date", "transaction_id"))
    elif scope == "debit":
        rows_qs = list(debit_qs.order_by("transaction_date", "transaction_id"))
    else:
        rows_qs = list(qs.order_by("transaction_date", "transaction_id"))

    # Fonts and spacing
    BODY_FONT = "Helvetica"
    BODY_SIZE = 10
    HEADER_FONT = "Helvetica-Bold"
    HEADER_SIZE = 10
    TITLE_FONT = "Helvetica-Bold"
    CELL_PAD_X = 6
    CELL_PAD_Y = 6
    ROW_HEIGHT = max(22, BODY_SIZE + CELL_PAD_Y * 2)

    from reportlab.pdfbase import pdfmetrics
    def tw(text: str, font: str = BODY_FONT, size: int = BODY_SIZE) -> float:
        return pdfmetrics.stringWidth(str(text or "-"), font, size)

    headers = ["Id", "Date", "Type", "Amount", "Bank", "Contractor", "Account"]

    # Build measurement data
    data_rows = []
    for t in rows_qs:
        d = getattr(t, "transaction_date", None)
        date_str = d.isoformat() if d else "-"
        txid = str(getattr(t, "transaction_id", ""))
        txtype = (t.tx_type or "").strip()
        try:
            amount = f"{Decimal(str(t.amount or '0')):.2f}"
        except Exception:
            amount = str(t.amount or "0")
        # Use snapshot label first to handle deleted bank accounts gracefully
        bank_name = (getattr(t, "bank_display_name", "") or "").strip()
        if not bank_name:
            if t.bank_account:
                bank_name = (t.bank_account.bank_name or t.bank_account.account_name or str(t.bank_account.account_no or "") or "").strip()
        if not bank_name:
            bank_name = "-"
        # Prefer stored snapshot to keep contractor name even after deletion
        contractor_name = (
            (getattr(t, "contractor_display_name", "") or "").strip()
            or (t.contractor.contractor_name if t.contractor else "")
            or "-"
        )
        account = (t.account or "").strip()
        data_rows.append((txid, date_str, txtype, amount, bank_name, contractor_name, account))

    min_w = [30, 80, 50, 90, 90, 100, 60]
    max_w = [tw(h, HEADER_FONT, HEADER_SIZE) for h in headers]
    for r in data_rows:
        for i, cell in enumerate(r):
            max_w[i] = max(max_w[i], tw(cell))
    col_w = [max(min_w[i], max_w[i] + CELL_PAD_X * 2) for i in range(len(headers))]

    portrait_w, portrait_h = A4
    margin_l = 50
    margin_r = 50
    margin_t = 40
    margin_b = 60
    table_total_w = sum(col_w)
    content_w_portrait = portrait_w - margin_l - margin_r
    page_size = landscape(A4) if table_total_w > content_w_portrait else A4

    c = canvas.Canvas(str(path), pagesize=page_size)
    width, height = page_size

    CONTENT_W = (width - margin_l - margin_r)
    if table_total_w > CONTENT_W:
        scale = CONTENT_W / table_total_w
        col_w = [max(min_w[i], round(w * scale)) for i, w in enumerate(col_w)]
        table_total_w = sum(col_w)

    # Center table
    LEFT = max(margin_l, (width - table_total_w) / 2)
    RIGHT = LEFT + table_total_w
    X = [LEFT]
    for i in range(1, len(col_w)):
        X.append(X[i - 1] + col_w[i - 1])

    def _header(title_suffix: str | None = None):
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.8)
        c.setFont(TITLE_FONT, 20)
        council, district = _get_council_and_district()
        c.drawCentredString(width / 2, height - 40, council)
        c.setFont("Helvetica", 12)
        c.drawCentredString(width / 2, height - 60, _format_district(district))
        c.setFont(TITLE_FONT, 16)
        c.drawCentredString(width / 2, height - 88, "Bank Account Wise Report")
        c.setFont(BODY_FONT, 10)
        c.drawString(LEFT, height - 110, f"From: {start or '-'}  To: {end or '-'}")

    y_start = height - 136
    y = y_start

    def fit_text(text: str, max_width: float, font: str = BODY_FONT, size: int = BODY_SIZE) -> str:
        if text is None:
            return "-"
        t = str(text)
        if not t:
            return "-"
        w = pdfmetrics.stringWidth(t, font, size)
        if w <= max_width:
            return t
        ell = "…"
        lo, hi = 0, len(t)
        while lo < hi:
            mid = (lo + hi) // 2
            candidate = t[:mid] + ell
            if pdfmetrics.stringWidth(candidate, font, size) <= max_width:
                lo = mid + 1
            else:
                hi = mid
        return t[:max(1, lo - 1)] + ell

    def ensure_space(rows_needed: int = 1):
        nonlocal y
        if y - rows_needed * ROW_HEIGHT < margin_b:
            c.showPage()
            _header("Continued")
            y = y_start
            draw_column_headers()

    def draw_column_headers():
        nonlocal y
        c.setFont(HEADER_FONT, HEADER_SIZE)
        row_bottom = y - ROW_HEIGHT
        for i, h in enumerate(headers):
            c.rect(X[i], row_bottom, col_w[i], ROW_HEIGHT)
            text_y = row_bottom + (ROW_HEIGHT - HEADER_SIZE) / 2 + 1.5
            cx = X[i] + col_w[i] / 2
            c.drawCentredString(cx, text_y, h)
        y = row_bottom

    def draw_row(row):
        nonlocal y
        ensure_space(1)
        c.setFont(BODY_FONT, BODY_SIZE)
        row_bottom = y - ROW_HEIGHT
        for i, val in enumerate(row):
            c.rect(X[i], row_bottom, col_w[i], ROW_HEIGHT)
            text_y = row_bottom + (ROW_HEIGHT - BODY_SIZE) / 2 + 1.5
            available = col_w[i] - 2 * CELL_PAD_X
            cx = X[i] + col_w[i] / 2
            c.drawCentredString(cx, text_y, fit_text(val, available))
        y = row_bottom

    def draw_summary(label: str, value: str):
        nonlocal y
        ensure_space(1)
        label_w = table_total_w * 0.65
        value_w = table_total_w - label_w
        row_bottom = y - ROW_HEIGHT
        c.rect(LEFT, row_bottom, label_w, ROW_HEIGHT)
        c.rect(LEFT + label_w, row_bottom, value_w, ROW_HEIGHT)
        c.setFont("Helvetica-Bold", 12)
        ty = row_bottom + (ROW_HEIGHT - 12) / 2 + 1.5
        c.drawString(LEFT + CELL_PAD_X, ty, label)
        c.drawRightString(LEFT + label_w + value_w - CELL_PAD_X, ty, value)
        y = row_bottom

    # Compose document
    _header(None)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(LEFT, y, "Transactions")
    y -= 18
    draw_column_headers()
    for r in data_rows:
        draw_row(r)
    if scope == "credit":
        draw_summary("Total Credit", f"{credit}")
        draw_summary("Net (Profit/Loss)", f"{net}")
    elif scope == "debit":
        draw_summary("Total Debit", f"{debit}")
        draw_summary("Net (Profit/Loss)", f"{net}")
    else:
        draw_summary("Total Credit", f"{credit}")
        draw_summary("Total Debit", f"{debit}")
        draw_summary("Net (Profit/Loss)", f"{net}")
    # Common additional balances
    draw_summary("Previous Balance", f"{previous_balance}")
    draw_summary("Today Balance", f"{today_balance}")

    c.showPage()
    c.save()
    return str(path)


def export_contractor_wise_pdf(start: str | None, end: str | None, contractor_id: int | None, scope: str = "both") -> str:
    """Contractor Wise Report using the same boxed table design.

    Supports scope filter identical to Profit/Loss: Credit/Debit/Both.
    """
    path = _timestamped("contractor-wise", "pdf")

    qs = models.Transaction.objects.all()
    if contractor_id:
        qs = qs.filter(contractor_id=contractor_id)
    if start:
        qs = qs.filter(transaction_date__gte=start)
    if end:
        qs = qs.filter(transaction_date__lte=end)

    credit_qs = qs.filter(tx_type=models.Transaction.CREDIT)
    debit_qs = qs.filter(tx_type=models.Transaction.DEBIT)
    credit = _sum_amount(credit_qs)
    debit = _sum_amount(debit_qs)
    net = credit - debit
    # Today-based balances scoped to contractor (ignore date filters)
    from datetime import datetime as _dt
    _today = _dt.today().date()
    base_qs = models.Transaction.objects.all()
    if contractor_id:
        base_qs = base_qs.filter(contractor_id=contractor_id)
    prev_qs = base_qs.filter(transaction_date__lt=_today)
    prev_credit = _sum_amount(prev_qs.filter(tx_type=models.Transaction.CREDIT))
    prev_debit = _sum_amount(prev_qs.filter(tx_type=models.Transaction.DEBIT))
    previous_balance = prev_credit - prev_debit
    day_qs = base_qs.filter(transaction_date=_today)
    day_credit = _sum_amount(day_qs.filter(tx_type=models.Transaction.CREDIT))
    day_debit = _sum_amount(day_qs.filter(tx_type=models.Transaction.DEBIT))
    today_balance = previous_balance + (day_credit - day_debit)
    # Rows filtered by scope
    if scope == "credit":
        rows_qs = list(credit_qs.order_by("transaction_date", "transaction_id"))
    elif scope == "debit":
        rows_qs = list(debit_qs.order_by("transaction_date", "transaction_id"))
    else:
        rows_qs = list(qs.order_by("transaction_date", "transaction_id"))

    BODY_FONT = "Helvetica"
    BODY_SIZE = 10
    HEADER_FONT = "Helvetica-Bold"
    HEADER_SIZE = 10
    TITLE_FONT = "Helvetica-Bold"
    CELL_PAD_X = 6
    CELL_PAD_Y = 6
    ROW_HEIGHT = max(22, BODY_SIZE + CELL_PAD_Y * 2)

    from reportlab.pdfbase import pdfmetrics
    def tw(text: str, font: str = BODY_FONT, size: int = BODY_SIZE) -> float:
        return pdfmetrics.stringWidth(str(text or "-"), font, size)

    headers = ["Id", "Date", "Type", "Amount", "Bank", "Contractor", "Account"]
    data_rows = []
    for t in rows_qs:
        d = getattr(t, "transaction_date", None)
        date_str = d.isoformat() if d else "-"
        txid = str(getattr(t, "transaction_id", ""))
        txtype = (t.tx_type or "").strip()
        try:
            amount = f"{Decimal(str(t.amount or '0')):.2f}"
        except Exception:
            amount = str(t.amount or "0")
        # Prefer stored snapshot to keep bank name even after deletion
        bank_name = (getattr(t, "bank_display_name", "") or "").strip()
        if not bank_name:
            if t.bank_account:
                bank_name = (
                    (t.bank_account.account_name or "").strip()
                    or (str(t.bank_account.account_no or "").strip())
                    or (t.bank_account.bank_name or "").strip()
                )
        if not bank_name:
            bank_name = "-"
        # Prefer stored snapshot to keep name after deletion
        contractor_name = (getattr(t, "contractor_display_name", "") or (t.contractor.contractor_name if t.contractor else "") or "-")
        account = (t.account or "").strip()
        data_rows.append((txid, date_str, txtype, amount, bank_name, contractor_name, account))

    min_w = [30, 80, 50, 90, 90, 100, 60]
    max_w = [tw(h, HEADER_FONT, HEADER_SIZE) for h in headers]
    for r in data_rows:
        for i, cell in enumerate(r):
            max_w[i] = max(max_w[i], tw(cell))
    col_w = [max(min_w[i], max_w[i] + CELL_PAD_X * 2) for i in range(len(headers))]

    portrait_w, portrait_h = A4
    margin_l = 50
    margin_r = 50
    margin_t = 40
    margin_b = 60
    table_total_w = sum(col_w)
    content_w_portrait = portrait_w - margin_l - margin_r
    page_size = landscape(A4) if table_total_w > content_w_portrait else A4

    c = canvas.Canvas(str(path), pagesize=page_size)
    width, height = page_size

    CONTENT_W = (width - margin_l - margin_r)
    if table_total_w > CONTENT_W:
        scale = CONTENT_W / table_total_w
        col_w = [max(min_w[i], round(w * scale)) for i, w in enumerate(col_w)]
        table_total_w = sum(col_w)

    LEFT = max(margin_l, (width - table_total_w) / 2)
    RIGHT = LEFT + table_total_w
    X = [LEFT]
    for i in range(1, len(col_w)):
        X.append(X[i - 1] + col_w[i - 1])

    def _header(title_suffix: str | None = None):
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.8)
        c.setFont(TITLE_FONT, 20)
        council, district = _get_council_and_district()
        c.drawCentredString(width / 2, height - 40, council)
        c.setFont("Helvetica", 12)
        c.drawCentredString(width / 2, height - 60, _format_district(district))
        c.setFont(TITLE_FONT, 16)
        c.drawCentredString(width / 2, height - 88, "Contractor Wise Report")
        c.setFont(BODY_FONT, 10)
        c.drawString(LEFT, height - 110, f"From: {start or '-'}  To: {end or '-'}")

    y_start = height - 136
    y = y_start

    def fit_text(text: str, max_width: float, font: str = BODY_FONT, size: int = BODY_SIZE) -> str:
        if text is None:
            return "-"
        t = str(text)
        if not t:
            return "-"
        w = pdfmetrics.stringWidth(t, font, size)
        if w <= max_width:
            return t
        ell = "…"
        lo, hi = 0, len(t)
        while lo < hi:
            mid = (lo + hi) // 2
            candidate = t[:mid] + ell
            if pdfmetrics.stringWidth(candidate, font, size) <= max_width:
                lo = mid + 1
            else:
                hi = mid
        return t[:max(1, lo - 1)] + ell

    def ensure_space(rows_needed: int = 1):
        nonlocal y
        if y - rows_needed * ROW_HEIGHT < margin_b:
            c.showPage()
            _header("Continued")
            y = y_start
            draw_column_headers()

    def draw_column_headers():
        nonlocal y
        c.setFont(HEADER_FONT, HEADER_SIZE)
        row_bottom = y - ROW_HEIGHT
        for i, h in enumerate(headers):
            c.rect(X[i], row_bottom, col_w[i], ROW_HEIGHT)
            text_y = row_bottom + (ROW_HEIGHT - HEADER_SIZE) / 2 + 1.5
            cx = X[i] + col_w[i] / 2
            c.drawCentredString(cx, text_y, h)
        y = row_bottom

    def draw_row(row):
        nonlocal y
        ensure_space(1)
        c.setFont(BODY_FONT, BODY_SIZE)
        row_bottom = y - ROW_HEIGHT
        for i, val in enumerate(row):
            c.rect(X[i], row_bottom, col_w[i], ROW_HEIGHT)
            text_y = row_bottom + (ROW_HEIGHT - BODY_SIZE) / 2 + 1.5
            available = col_w[i] - 2 * CELL_PAD_X
            cx = X[i] + col_w[i] / 2
            c.drawCentredString(cx, text_y, fit_text(val, available))
        y = row_bottom

    def draw_summary(label: str, value: str):
        nonlocal y
        ensure_space(1)
        label_w = table_total_w * 0.65
        value_w = table_total_w - label_w
        row_bottom = y - ROW_HEIGHT
        c.rect(LEFT, row_bottom, label_w, ROW_HEIGHT)
        c.rect(LEFT + label_w, row_bottom, value_w, ROW_HEIGHT)
        c.setFont("Helvetica-Bold", 12)
        ty = row_bottom + (ROW_HEIGHT - 12) / 2 + 1.5
        c.drawString(LEFT + CELL_PAD_X, ty, label)
        c.drawRightString(LEFT + label_w + value_w - CELL_PAD_X, ty, value)
        y = row_bottom

    _header(None)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(LEFT, y, "Transactions")
    y -= 18
    draw_column_headers()
    for r in data_rows:
        draw_row(r)
    if scope == "credit":
        draw_summary("Total Credit", f"{credit}")
        draw_summary("Net (Profit/Loss)", f"{net}")
    elif scope == "debit":
        draw_summary("Total Debit", f"{debit}")
        draw_summary("Net (Profit/Loss)", f"{net}")
    else:
        draw_summary("Total Credit", f"{credit}")
        draw_summary("Total Debit", f"{debit}")
        draw_summary("Net (Profit/Loss)", f"{net}")
    # Common additional balances
    draw_summary("Previous Balance", f"{previous_balance}")
    draw_summary("Today Balance", f"{today_balance}")

    c.showPage()
    c.save()
    return str(path)


def export_bank_account_pdf(account_id: int) -> str:
    """Professional single Bank Account summary PDF that auto-sizes and wraps.

    - Dynamically measures content and expands box width (switches to landscape if needed).
    - Wraps long values (Bank Address/Bank Name) to avoid truncation or overlap.
    - Maintains equal margins, centered titles, and clean balanced layout.
    - Consistent two-column alignment; subtle dividers; soft green for 'active'.
    """

    b = models.BankAccount.objects.get(account_id=account_id)
    path = _timestamped(f"bank-account-{b.account_id}", "pdf")

    TITLE_FONT = "Helvetica-Bold"
    SECTION_FONT = "Helvetica-Bold"
    BODY_FONT = "Helvetica"
    TITLE_SIZE = 22
    SUBTITLE_SIZE = 12
    SECTION_SIZE = 16
    BODY_SIZE = 11

    MARGIN = 60
    BOX_PAD = 14
    CELL_PAD_X = 8
    CELL_PAD_Y = 6
    LINE_HEIGHT = BODY_SIZE + 3
    BORDER_COLOR = colors.HexColor("#444444")
    DIVIDER_COLOR = colors.HexColor("#DDDDDD")
    ACTIVE_COLOR = colors.HexColor("#2E7D32")

    from reportlab.pdfbase import pdfmetrics

    def tw(text: str, font: str = BODY_FONT, size: int = BODY_SIZE) -> float:
        return pdfmetrics.stringWidth(str(text or ""), font, size)

    def wrap_lines(text: str | None, max_w: float, font: str = BODY_FONT, size: int = BODY_SIZE) -> list[str]:
        s = str(text or "")
        if not s:
            return [""]
        words = s.split()
        lines: list[str] = []
        cur = ""
        for w in words:
            candidate = (cur + " " + w).strip()
            if tw(candidate, font, size) <= max_w:
                cur = candidate
                continue
            if cur:
                lines.append(cur)
                cur = ""
            # If the single word is longer than max_w, break it
            if tw(w, font, size) <= max_w:
                cur = w
            else:
                part = ""
                for ch in w:
                    if tw(part + ch, font, size) <= max_w:
                        part += ch
                    else:
                        if part:
                            lines.append(part)
                            part = ch
                cur = part
        if cur:
            lines.append(cur)
        return lines or [""]

    # Build row data (LL, LV, RL, RV)
    rows: list[tuple[str, str | None, str | None, str | None]] = [
        ("Account Name", b.account_name, None, None),
        ("Account No", str(b.account_no or ""), "Bank Name", b.bank_name),
        ("IFSC", b.ifsc, None, None),
        ("Bank Address", b.bank_address, None, None),
        ("Bank Manager", b.bank_manager_name, "Bank Contact", b.bank_contact),
        ("Scheme Name", b.scheme_name, None, None),
        ("Status", b.status, None, None),
    ]

    # Measure to decide orientation and panel width
    portrait_w, portrait_h = A4
    content_w_portrait = portrait_w - 2 * MARGIN
    LABEL_W = max(120, max(tw(r[0]) for r in rows) + 10)
    COLON_W = 12
    left_max_val_w = max(tw(r[1]) for r in rows if r[1] is not None)
    right_max_val_w = max([tw(r[3]) for r in rows if r[3] is not None] or [0])
    panel_req_left = LABEL_W + COLON_W + 2 * CELL_PAD_X + left_max_val_w
    panel_req_right = LABEL_W + COLON_W + 2 * CELL_PAD_X + right_max_val_w
    inner_req_w = panel_req_left + panel_req_right + 2 * BOX_PAD

    page_size = A4 if inner_req_w <= content_w_portrait else landscape(A4)
    c = canvas.Canvas(str(path), pagesize=page_size)
    width, height = page_size
    content_w = width - 2 * MARGIN

    # Final panel width (bounded by page content width)
    panel_w = min(max(panel_req_left, panel_req_right), (content_w - 2 * BOX_PAD) / 2)
    box_w = panel_w * 2 + 2 * BOX_PAD

    # Headings
    council, district = _get_council_and_district()
    c.setFont(TITLE_FONT, TITLE_SIZE)
    c.drawCentredString(width / 2, height - MARGIN, council)
    c.setFont(BODY_FONT, SUBTITLE_SIZE)
    c.drawCentredString(width / 2, height - MARGIN - 22, _format_district(district))
    c.setFont(SECTION_FONT, SECTION_SIZE)
    c.drawCentredString(width / 2, height - MARGIN - 22 - 28, "Accounts Summary")

    # Box geometry (centered)
    box_top = height - MARGIN - 22 - 28 - 28
    box_left = (width - box_w) / 2
    box_right = box_left + box_w

    # Column X positions
    x_l_label = box_left + BOX_PAD + CELL_PAD_X
    x_l_colon = x_l_label + LABEL_W
    x_l_value = x_l_colon + COLON_W
    x_r_label = box_left + BOX_PAD + panel_w + CELL_PAD_X
    x_r_colon = x_r_label + LABEL_W
    x_r_value = x_r_colon + COLON_W
    VAL_W = panel_w - LABEL_W - COLON_W - 2 * CELL_PAD_X

    # Pre-wrap values and compute row heights
    wrapped_rows: list[tuple[str, list[str], str | None, list[str]]] = []
    row_heights: list[float] = []
    for ll, lv, rl, rv in rows:
        left_lines = wrap_lines(lv, VAL_W)
        right_lines = wrap_lines(rv, VAL_W) if rl else []
        lines_count = max(len(left_lines), len(right_lines)) if rl else len(left_lines)
        row_h = CELL_PAD_Y * 2 + max(1, lines_count) * LINE_HEIGHT
        wrapped_rows.append((ll, left_lines, rl, right_lines))
        row_heights.append(row_h)

    # Border rectangle sized to content
    box_height = BOX_PAD * 2 + sum(row_heights)
    box_bottom = box_top - box_height
    c.setStrokeColor(BORDER_COLOR)
    c.setLineWidth(1.2)
    c.rect(box_left, box_bottom, box_right - box_left, box_height)

    # Draw rows with dividers
    y = box_top
    c.setFont(BODY_FONT, BODY_SIZE)
    for idx, (ll, left_lines, rl, right_lines) in enumerate(wrapped_rows):
        row_h = row_heights[idx]
        row_bottom = y - row_h

        # Baseline for first line
        first_line_y = row_bottom + row_h - CELL_PAD_Y - LINE_HEIGHT

        # Left label + colon on first line
        c.setFillColor(colors.black)
        c.drawString(x_l_label, first_line_y, str(ll))
        c.drawString(x_l_colon, first_line_y, ":")

        # Left value lines
        status_is_active = str(ll).strip().lower() == "status" and str((left_lines[0] if left_lines else "")).strip().lower() == "active"
        for i, seg in enumerate(left_lines):
            ly = row_bottom + row_h - CELL_PAD_Y - LINE_HEIGHT * (i + 1)
            if status_is_active and i == 0:
                c.setFillColor(ACTIVE_COLOR)
            else:
                c.setFillColor(colors.black)
            c.drawString(x_l_value, ly, seg)
        c.setFillColor(colors.black)

        # Right panel
        if rl:
            c.drawString(x_r_label, first_line_y, str(rl))
            c.drawString(x_r_colon, first_line_y, ":")
            for i, seg in enumerate(right_lines):
                ry = row_bottom + row_h - CELL_PAD_Y - LINE_HEIGHT * (i + 1)
                c.setFillColor(colors.black)
                c.drawString(x_r_value, ry, seg)
            c.setFillColor(colors.black)

        # Divider
        c.setStrokeColor(DIVIDER_COLOR)
        c.setLineWidth(0.8)
        c.line(box_left + BOX_PAD, row_bottom, box_right - BOX_PAD, row_bottom)
        c.setStrokeColor(BORDER_COLOR)
        c.setLineWidth(1.2)

        y = row_bottom

    c.showPage()
    c.save()
    return str(path)

def export_contractor_pdf(contractor_id: int) -> str:
    """Contractor Summary PDF in the same professional layout as Account Summary.

    - Equal margins, centered headers, clean border and dividers.
    - Two balanced panels with dynamic width (landscape if needed).
    - Wrap long values to ensure full visibility without truncation or overlap.
    """

    cobj = models.Contractor.objects.get(contractor_id=contractor_id)
    path = _timestamped(f"contractor-{cobj.contractor_id}", "pdf")

    TITLE_FONT = "Helvetica-Bold"
    SECTION_FONT = "Helvetica-Bold"
    BODY_FONT = "Helvetica"
    TITLE_SIZE = 22
    SUBTITLE_SIZE = 12
    SECTION_SIZE = 16
    BODY_SIZE = 11

    MARGIN = 60
    BOX_PAD = 14
    CELL_PAD_X = 8
    CELL_PAD_Y = 6
    LINE_HEIGHT = BODY_SIZE + 3
    BORDER_COLOR = colors.HexColor("#444444")
    DIVIDER_COLOR = colors.HexColor("#DDDDDD")
    ACTIVE_COLOR = colors.HexColor("#2E7D32")

    from reportlab.pdfbase import pdfmetrics

    def tw(text: str, font: str = BODY_FONT, size: int = BODY_SIZE) -> float:
        return pdfmetrics.stringWidth(str(text or ""), font, size)

    def wrap_lines(text: str | None, max_w: float, font: str = BODY_FONT, size: int = BODY_SIZE) -> list[str]:
        s = str(text or "")
        if not s:
            return [""]
        words = s.split()
        lines: list[str] = []
        cur = ""
        for w in words:
            candidate = (cur + " " + w).strip()
            if tw(candidate, font, size) <= max_w:
                cur = candidate
                continue
            if cur:
                lines.append(cur)
                cur = ""
            if tw(w, font, size) <= max_w:
                cur = w
            else:
                part = ""
                for ch in w:
                    if tw(part + ch, font, size) <= max_w:
                        part += ch
                    else:
                        if part:
                            lines.append(part)
                            part = ch
                cur = part
        if cur:
            lines.append(cur)
        return lines or [""]

    # Row definitions mirroring screenshot and bank account layout
    rows: list[tuple[str, str | None, str | None, str | None]] = [
        ("Contractor Name", cobj.contractor_name, None, None),
        ("Address", cobj.contractor_address, None, None),
        ("Contact No", cobj.contractor_contact_no, "PAN", cobj.contractor_pan),
        ("TAN", cobj.contractor_tan, "GST", cobj.contractor_gst),
        ("Bank A/C", cobj.contractor_bank_ac, "IFSC", cobj.contractor_ifsc),
        ("Bank Name", cobj.contractor_bank, "Status", cobj.status),
        ("Remark", cobj.remark, None, None),
    ]

    # Orientation and width measurement
    portrait_w, _ = A4
    content_w_portrait = portrait_w - 2 * MARGIN
    LABEL_W = max(120, max(tw(r[0]) for r in rows) + 10)
    COLON_W = 12
    left_max_val_w = max(tw(r[1]) for r in rows if r[1] is not None)
    right_max_val_w = max([tw(r[3]) for r in rows if r[3] is not None] or [0])
    panel_req_left = LABEL_W + COLON_W + 2 * CELL_PAD_X + left_max_val_w
    panel_req_right = LABEL_W + COLON_W + 2 * CELL_PAD_X + right_max_val_w
    inner_req_w = panel_req_left + panel_req_right + 2 * BOX_PAD

    page_size = A4 if inner_req_w <= content_w_portrait else landscape(A4)
    c = canvas.Canvas(str(path), pagesize=page_size)
    width, height = page_size
    content_w = width - 2 * MARGIN

    panel_w = min(max(panel_req_left, panel_req_right), (content_w - 2 * BOX_PAD) / 2)
    box_w = panel_w * 2 + 2 * BOX_PAD

    # Headers
    council, district = _get_council_and_district()
    c.setFont(TITLE_FONT, TITLE_SIZE)
    c.drawCentredString(width / 2, height - MARGIN, council)
    c.setFont(BODY_FONT, SUBTITLE_SIZE)
    c.drawCentredString(width / 2, height - MARGIN - 22, _format_district(district))
    c.setFont(SECTION_FONT, SECTION_SIZE)
    c.drawCentredString(width / 2, height - MARGIN - 22 - 28, "Contractor Summary")

    # Box geometry centered
    box_top = height - MARGIN - 22 - 28 - 28
    box_left = (width - box_w) / 2
    box_right = box_left + box_w

    # Column x positions and value width
    x_l_label = box_left + BOX_PAD + CELL_PAD_X
    x_l_colon = x_l_label + LABEL_W
    x_l_value = x_l_colon + COLON_W
    x_r_label = box_left + BOX_PAD + panel_w + CELL_PAD_X
    x_r_colon = x_r_label + LABEL_W
    x_r_value = x_r_colon + COLON_W
    VAL_W = panel_w - LABEL_W - COLON_W - 2 * CELL_PAD_X

    # Wrap and compute row heights
    wrapped_rows: list[tuple[str, list[str], str | None, list[str]]] = []
    row_heights: list[float] = []
    for ll, lv, rl, rv in rows:
        left_lines = wrap_lines(lv, VAL_W)
        right_lines = wrap_lines(rv, VAL_W) if rl else []
        lines_count = max(len(left_lines), len(right_lines)) if rl else len(left_lines)
        row_h = CELL_PAD_Y * 2 + max(1, lines_count) * LINE_HEIGHT
        wrapped_rows.append((ll, left_lines, rl, right_lines))
        row_heights.append(row_h)

    # Border sized to content
    box_height = BOX_PAD * 2 + sum(row_heights)
    box_bottom = box_top - box_height
    c.setStrokeColor(BORDER_COLOR)
    c.setLineWidth(1.2)
    c.rect(box_left, box_bottom, box_right - box_left, box_height)

    # Draw rows
    y = box_top
    c.setFont(BODY_FONT, BODY_SIZE)
    for idx, (ll, left_lines, rl, right_lines) in enumerate(wrapped_rows):
        row_h = row_heights[idx]
        row_bottom = y - row_h

        first_line_y = row_bottom + row_h - CELL_PAD_Y - LINE_HEIGHT

        c.setFillColor(colors.black)
        c.drawString(x_l_label, first_line_y, str(ll))
        c.drawString(x_l_colon, first_line_y, ":")

        # Left value lines
        status_is_active = str(ll).strip().lower() == "status" and str((left_lines[0] if left_lines else "")).strip().lower() == "active"
        for i, seg in enumerate(left_lines):
            ly = row_bottom + row_h - CELL_PAD_Y - LINE_HEIGHT * (i + 1)
            if status_is_active and i == 0:
                c.setFillColor(ACTIVE_COLOR)
            else:
                c.setFillColor(colors.black)
            c.drawString(x_l_value, ly, seg)
        c.setFillColor(colors.black)

        # Right panel
        if rl:
            c.drawString(x_r_label, first_line_y, str(rl))
            c.drawString(x_r_colon, first_line_y, ":")
            for i, seg in enumerate(right_lines):
                ry = row_bottom + row_h - CELL_PAD_Y - LINE_HEIGHT * (i + 1)
                c.setFillColor(colors.black)
                c.drawString(x_r_value, ry, seg)
            c.setFillColor(colors.black)

        # Divider
        c.setStrokeColor(DIVIDER_COLOR)
        c.setLineWidth(0.8)
        c.line(box_left + BOX_PAD, row_bottom, box_right - BOX_PAD, row_bottom)
        c.setStrokeColor(BORDER_COLOR)
        c.setLineWidth(1.2)

        y = row_bottom

    c.showPage()
    c.save()
    return str(path)


