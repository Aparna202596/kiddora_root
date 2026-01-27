from io import BytesIO
from django.http import HttpResponse
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from django.utils.timezone import now
from orders.models import Order

def generate_invoice_pdf(order):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 50
    p.setFont("Helvetica-Bold", 14)
    p.drawString(50, y, "INVOICE")

    y -= 30
    p.setFont("Helvetica", 10)
    p.drawString(50, y, f"Order ID: {order.id}")
    y -= 15
    p.drawString(50, y, f"Customer: {order.user.username}")
    y -= 15
    p.drawString(50, y, f"Date: {now().strftime('%d-%m-%Y')}")

    y -= 30
    p.drawString(50, y, "Items:")
    y -= 20

    for item in order.items.all():
        p.drawString(50, y, f"{item.product.product_name} × {item.quantity}")
        p.drawRightString(500, y, f"{item.price * item.quantity}")
        y -= 15

    y -= 20
    p.drawString(50, y, "Total Amount:")
    p.drawRightString(500, y, str(order.final_amount))

    p.showPage()
    p.save()

    buffer.seek(0)
    return buffer
