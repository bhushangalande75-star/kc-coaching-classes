import io
from urllib.parse import quote
from datetime import date
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib import colors

COACHING_NAME = "KC Coaching Classes"


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
    """Generate a simple A5 fee receipt PDF and return bytes."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A5)
    width, height = A5

    # Header
    c.setFillColor(colors.HexColor("#1b3a4b"))
    c.rect(0, height - 30 * mm, width, 30 * mm, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, height - 15 * mm, COACHING_NAME)
    c.setFont("Helvetica", 9)
    c.drawCentredString(width / 2, height - 22 * mm, "Fee Receipt")

    y = height - 42 * mm
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 10)
    lines = [
        f"Receipt Date: {date.today().strftime('%d-%b-%Y')}",
        f"Student Name: {student.name}",
        f"Batch: {student.batch}",
        f"Parent Name: {student.parent_name or '-'}",
        f"Fee Period: {fee.period}",
        "",
        f"Amount Due: Rs. {fee.amount_due:.0f}",
        f"Amount Paid: Rs. {fee.amount_paid:.0f}",
        f"Balance: Rs. {fee.balance():.0f}",
        f"Status: {fee.status.upper()}",
        f"Paid Date: {fee.paid_date.strftime('%d-%b-%Y') if fee.paid_date else '-'}",
    ]
    for line in lines:
        c.drawString(15 * mm, y, line)
        y -= 7 * mm

    c.setFont("Helvetica-Oblique", 8)
    c.drawCentredString(width / 2, 10 * mm, "This is a computer-generated receipt.")
    c.showPage()
    c.save()
    buf.seek(0)
    return buf
