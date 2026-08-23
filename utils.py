import io
from urllib.parse import quote
from datetime import date
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib import colors

COACHING_NAME = "KC Coaching Classes"
BRAND_INK = colors.HexColor("#1B3A4B")
BRAND_MARIGOLD = colors.HexColor("#E2A63C")
BRAND_SAGE = colors.HexColor("#4C7A5D")
BRAND_BRICK = colors.HexColor("#C1503D")
BRAND_PAPER_LINE = colors.HexColor("#DCD5C3")
BRAND_TEXT = colors.HexColor("#1B3A4B")
BRAND_MUTED = colors.HexColor("#6E8592")


def whatsapp_link(number, message):
    """Build a wa.me deep link that opens WhatsApp with a pre-filled message.
    No WhatsApp Business API needed - this is completely free."""
    clean_number = "".join(ch for ch in number if ch.isdigit())
    return f"https://wa.me/{clean_number}?text={quote(message)}"


def fee_reminder_message(student, fee):
    return (
        f"Dear {student.parent_name or 'Parent'},\n"
        f"This is a reminder from {COACHING_NAME} regarding {student.name}'s fee "
        f"for {fee.period}.\n"
        f"Amount due: Rs. {fee.amount_due:.0f}\n"
        f"Amount paid: Rs. {fee.amount_paid:.0f}\n"
        f"Balance: Rs. {fee.balance():.0f}\n"
        f"Kindly clear the pending amount at the earliest. Thank you."
    )


def fee_receipt_message(student, fee):
    return (
        f"Dear {student.parent_name or 'Parent'},\n"
        f"Fee receipt from {COACHING_NAME} for {student.name} - {fee.period}.\n"
        f"Amount paid: Rs. {fee.amount_paid:.0f}\n"
        f"Status: {fee.status.upper()}\n"
        f"Thank you for your payment!"
    )


def attendance_alert_message(student, status, day):
    word = "absent" if status == "absent" else "present"
    return (
        f"Dear {student.parent_name or 'Parent'},\n"
        f"This is to inform you that {student.name} was marked {word} "
        f"at {COACHING_NAME} on {day.strftime('%d-%b-%Y')}."
    )


def generate_receipt_pdf(student, fee):
    """Generate a professional A5 fee receipt PDF (invoice-style) and return bytes."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A5)
    width, height = A5
    receipt_no = f"KC-{fee.period.replace('-', '')}-{fee.id:04d}"

    # ---------- Outer border ----------
    c.setStrokeColor(BRAND_PAPER_LINE)
    c.setLineWidth(0.8)
    c.rect(4 * mm, 4 * mm, width - 8 * mm, height - 8 * mm, fill=False, stroke=True)

    # ---------- Header band ----------
    header_h = 32 * mm
    c.setFillColor(BRAND_INK)
    c.rect(4 * mm, height - 4 * mm - header_h, width - 8 * mm, header_h, fill=True, stroke=False)

    # Logo mark (circle with "KC")
    cx, cy = 18 * mm, height - 4 * mm - header_h / 2
    c.setFillColor(BRAND_MARIGOLD)
    c.circle(cx, cy, 7 * mm, fill=True, stroke=False)
    c.setFillColor(BRAND_INK)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(cx, cy - 3.2, "KC")

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(28 * mm, height - 4 * mm - 12 * mm, COACHING_NAME)
    c.setFont("Helvetica", 8.5)
    c.setFillColor(BRAND_MARIGOLD)
    c.drawString(28 * mm, height - 4 * mm - 18 * mm, "FEE RECEIPT")

    # Receipt no. + date, top-right of header
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    c.drawRightString(width - 8 * mm, height - 4 * mm - 11 * mm, f"Receipt No: {receipt_no}")
    c.setFont("Helvetica", 8)
    c.drawRightString(width - 8 * mm, height - 4 * mm - 16 * mm,
                       f"Date: {date.today().strftime('%d-%b-%Y')}")

    # Thin marigold accent line under header
    c.setFillColor(BRAND_MARIGOLD)
    c.rect(4 * mm, height - 4 * mm - header_h - 1.2 * mm, width - 8 * mm, 1.2 * mm, fill=True, stroke=False)

    y = height - 4 * mm - header_h - 12 * mm

    # ---------- Billed To / Period info (two columns) ----------
    col1_x = 10 * mm
    col2_x = width / 2 + 4 * mm

    c.setFillColor(BRAND_MUTED)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(col1_x, y, "BILLED TO")
    c.drawString(col2_x, y, "FEE PERIOD")
    y -= 5 * mm

    c.setFillColor(BRAND_TEXT)
    c.setFont("Helvetica-Bold", 10.5)
    c.drawString(col1_x, y, student.name)
    c.drawString(col2_x, y, fee.period)
    y -= 5.5 * mm

    c.setFont("Helvetica", 8.5)
    c.setFillColor(BRAND_MUTED)
    c.drawString(col1_x, y, f"Batch: {student.batch}")
    due_str = fee.due_date.strftime('%d-%b-%Y') if fee.due_date else '-'
    c.drawString(col2_x, y, f"Due Date: {due_str}")
    y -= 4.6 * mm
    c.drawString(col1_x, y, f"Parent: {student.parent_name or '-'}")
    paid_str = fee.paid_date.strftime('%d-%b-%Y') if fee.paid_date else '-'
    c.drawString(col2_x, y, f"Paid Date: {paid_str}")

    y -= 9 * mm

    # ---------- Line-item table ----------
    table_x = 10 * mm
    table_w = width - 20 * mm
    row_h = 8 * mm
    col_desc_w = table_w * 0.62

    # Table header row
    c.setFillColor(BRAND_INK)
    c.rect(table_x, y - row_h, table_w, row_h, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(table_x + 3 * mm, y - row_h + 2.8 * mm, "DESCRIPTION")
    c.drawRightString(table_x + table_w - 3 * mm, y - row_h + 2.8 * mm, "AMOUNT (Rs.)")
    y -= row_h

    def table_row(label, amount, bold=False, fill=None, text_color=BRAND_TEXT):
        nonlocal y
        if fill:
            c.setFillColor(fill)
            c.rect(table_x, y - row_h, table_w, row_h, fill=True, stroke=False)
        c.setStrokeColor(BRAND_PAPER_LINE)
        c.setLineWidth(0.5)
        c.line(table_x, y - row_h, table_x + table_w, y - row_h)
        c.setFillColor(text_color)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 9)
        c.drawString(table_x + 3 * mm, y - row_h + 2.8 * mm, label)
        c.drawRightString(table_x + table_w - 3 * mm, y - row_h + 2.8 * mm, f"{amount:,.0f}")
        y -= row_h

    table_row(f"Tuition Fee — {fee.period}", fee.amount_due)
    table_row("Amount Paid", fee.amount_paid)
    table_row("Balance Due", fee.balance(), bold=True,
               fill=colors.HexColor("#F7E7E3") if fee.balance() > 0 else colors.HexColor("#E7F0E9"),
               text_color=BRAND_BRICK if fee.balance() > 0 else BRAND_SAGE)

    # Outer border for the table
    c.setStrokeColor(BRAND_INK)
    c.setLineWidth(0.8)
    c.rect(table_x, y, table_w, row_h * 4, fill=False, stroke=True)

    y -= 14 * mm

    # ---------- Status stamp + Terms (side by side, fills the space cleanly) ----------
    stamp_text = fee.status.upper()
    stamp_color = {"paid": BRAND_SAGE, "partial": BRAND_MARIGOLD, "pending": BRAND_BRICK, "waived": BRAND_MUTED}.get(
        fee.status, BRAND_MUTED
    )

    terms_top = y
    c.setFillColor(BRAND_MUTED)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(table_x, terms_top, "TERMS")
    c.setFont("Helvetica", 7.5)
    terms_lines = [
        "• Fees once paid are non-refundable.",
        "• Please retain this receipt for future reference.",
        "• For queries, contact the coaching office directly.",
    ]
    ty = terms_top - 5 * mm
    for line in terms_lines:
        c.drawString(table_x, ty, line)
        ty -= 4.4 * mm

    if fee.note:
        ty -= 1.5 * mm
        c.setFont("Helvetica-Oblique", 7.5)
        c.setFillColor(BRAND_TEXT)
        c.drawString(table_x, ty, f"Note: {fee.note}")
        ty -= 4.4 * mm

    # Stamp, positioned to the right of the terms block, clear of any numbers
    c.saveState()
    c.translate(width - 30 * mm, terms_top - 8 * mm)
    c.rotate(10)
    c.setStrokeColor(stamp_color)
    c.setLineWidth(1.6)
    c.roundRect(-18 * mm, -6 * mm, 36 * mm, 12 * mm, 2 * mm, fill=False, stroke=True)
    c.setFillColor(stamp_color)
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(0, -3.2 * mm, stamp_text)
    c.restoreState()

    y = min(ty, terms_top - 26 * mm) - 6 * mm

    # ---------- Footer ----------
    footer_y = 20 * mm
    c.setStrokeColor(BRAND_PAPER_LINE)
    c.setLineWidth(0.6)
    c.line(10 * mm, footer_y + 10 * mm, width - 10 * mm, footer_y + 10 * mm)

    c.setFont("Helvetica-Oblique", 8.5)
    c.setFillColor(BRAND_TEXT)
    c.drawString(10 * mm, footer_y + 5 * mm, "Thank you for your payment.")

    # Signature line
    c.setStrokeColor(BRAND_MUTED)
    c.setLineWidth(0.5)
    c.line(width - 55 * mm, footer_y + 8 * mm, width - 10 * mm, footer_y + 8 * mm)
    c.setFont("Helvetica", 7.5)
    c.setFillColor(BRAND_MUTED)
    c.drawCentredString(width - 32.5 * mm, footer_y + 4.5 * mm, "Authorized Signatory")

    c.setFont("Helvetica", 6.5)
    c.setFillColor(BRAND_MUTED)
    c.drawCentredString(width / 2, 8 * mm,
                         "This is a computer-generated receipt and does not require a physical signature.")

    c.showPage()
    c.save()
    buf.seek(0)
    return buf
