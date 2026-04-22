from datetime import datetime


def _escape_pdf_text(value):
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )


def build_simple_pdf(title, lines):
    safe_lines = [title, "Generated: " + datetime.now().strftime("%Y-%m-%d %H:%M")] + list(lines)
    pages = []
    chunk_size = 42

    for start in range(0, len(safe_lines), chunk_size):
        pages.append(safe_lines[start:start + chunk_size])

    objects = []

    def add_object(content):
        objects.append(content)
        return len(objects)

    font_object = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids = []

    for page_lines in pages:
      content_parts = ["BT", f"/F1 12 Tf", "50 780 Td", "16 TL"]
      for index, line in enumerate(page_lines):
          escaped = _escape_pdf_text(line)
          if index == 0:
              content_parts.append(f"({escaped}) Tj")
          else:
              content_parts.append("T*")
              content_parts.append(f"({escaped}) Tj")
      content_parts.append("ET")
      stream = "\n".join(content_parts).encode("latin-1", errors="replace")
      content_id = add_object(f"<< /Length {len(stream)} >>\nstream\n{stream.decode('latin-1')}\nendstream")
      page_id = add_object(
          f"<< /Type /Page /Parent 0 0 R /MediaBox [0 0 612 792] "
          f"/Resources << /Font << /F1 {font_object} 0 R >> >> /Contents {content_id} 0 R >>"
      )
      page_ids.append(page_id)

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    pages_object_id = add_object(f"<< /Type /Pages /Count {len(page_ids)} /Kids [{kids}] >>")
    catalog_id = add_object(f"<< /Type /Catalog /Pages {pages_object_id} 0 R >>")

    for page_id in page_ids:
        objects[page_id - 1] = objects[page_id - 1].replace("/Parent 0 0 R", f"/Parent {pages_object_id} 0 R")

    pdf = ["%PDF-1.4"]
    offsets = [0]

    for index, content in enumerate(objects, start=1):
        offsets.append(sum(len(part.encode("latin-1")) + 1 for part in pdf))
        pdf.append(f"{index} 0 obj\n{content}\nendobj")

    xref_start = sum(len(part.encode("latin-1")) + 1 for part in pdf)
    pdf.append(f"xref\n0 {len(objects) + 1}")
    pdf.append("0000000000 65535 f ")
    for offset in offsets[1:]:
        pdf.append(f"{offset:010d} 00000 n ")
    pdf.append(
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref_start}\n%%EOF"
    )

    return "\n".join(pdf).encode("latin-1", errors="replace")
