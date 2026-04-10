from io import BytesIO

from django.conf import settings
from django.core.mail import send_mail


def build_simple_pdf(title, lines):
    text_lines = [title, "", *lines]
    stream = BytesIO()
    objects = []

    def add_object(payload):
        objects.append(payload)

    content_lines = ["BT", "/F1 12 Tf", "40 800 Td"]
    first = True
    for line in text_lines:
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if not first:
            content_lines.append("0 -20 Td")
        content_lines.append(f"({escaped}) Tj")
        first = False
    content_lines.append("ET")
    content = "\n".join(content_lines).encode("utf-8")

    add_object(b"<< /Type /Catalog /Pages 2 0 R >>")
    add_object(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    add_object(
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
    )
    add_object(f"<< /Length {len(content)} >>\nstream\n".encode("utf-8") + content + b"\nendstream")
    add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    stream.write(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(stream.tell())
        stream.write(f"{index} 0 obj\n".encode("utf-8"))
        stream.write(obj)
        stream.write(b"\nendobj\n")

    xref_start = stream.tell()
    stream.write(f"xref\n0 {len(offsets)}\n".encode("utf-8"))
    stream.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        stream.write(f"{offset:010d} 00000 n \n".encode("utf-8"))
    stream.write(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode(
            "utf-8"
        )
    )
    return stream.getvalue()


def build_credential_pdf_lines(order, unlocked_at):
    lines = [
        f"Order number: {order.order_number}",
        f"Product: {order.product.title}",
        f"Unlocked at: {unlocked_at.isoformat()}",
        "",
        "Credentials:",
    ]
    credentials = order.product.credentials_data or {}
    if isinstance(credentials, list):
        for index, item in enumerate(credentials, start=1):
            lines.append(f"Account {index}:")
            if isinstance(item, dict):
                for key, value in item.items():
                    lines.append(f"{key}: {value}")
            lines.append("")
    elif isinstance(credentials, dict):
        for key, value in credentials.items():
            lines.append(f"{key}: {value}")
    else:
        lines.append(str(credentials))
    return lines


def send_guest_order_email(order, subject, body_lines):
    if not order.guest_email:
        return
    message = "\n".join(str(line) for line in body_lines if line is not None)
    send_mail(
        subject=subject,
        message=message,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
        recipient_list=[order.guest_email],
        fail_silently=True,
    )
