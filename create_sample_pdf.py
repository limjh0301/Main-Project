#!/usr/bin/env python3
"""Create a sample vehicle operation log PDF for testing."""

from pathlib import Path

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
except ImportError:
    print("reportlab not installed. Installing...")
    import subprocess
    subprocess.check_call(["pip3", "install", "reportlab"])
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def find_korean_font():
    """Try to find an available Korean font."""
    font_paths = [
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/unfonts-core/UnDotum.ttf",
    ]
    for fp in font_paths:
        if Path(fp).exists():
            return fp
    return None


def create_sample_pdf(output_path: str = "sample_driving_log.pdf"):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=landscape(A4),
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    elements = []
    styles = getSampleStyleSheet()

    # Try to register Korean font
    korean_font = find_korean_font()
    font_name = "Helvetica"
    if korean_font:
        try:
            pdfmetrics.registerFont(TTFont("Korean", korean_font))
            font_name = "Korean"
        except Exception:
            pass

    # Title
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=18,
        spaceAfter=20,
    )
    elements.append(Paragraph("2026-01 Vehicle Operation Log", title_style))
    elements.append(Spacer(1, 10))

    # Table header and data
    header = [
        "Date",
        "Driver",
        "Vehicle No.",
        "Purpose",
        "Departure",
        "Destination",
        "Depart Time",
        "Return Time",
        "Start KM",
        "End KM",
        "Distance",
        "Fuel (L)",
        "Notes",
    ]

    data = [
        header,
        ["2026-01-02", "Kim", "12-3456", "Meeting", "HQ", "Gangnam", "09:00", "11:30", "45,230", "45,268", "38", "3.2", ""],
        ["2026-01-03", "Lee", "12-3456", "Delivery", "HQ", "Incheon", "08:30", "12:00", "45,268", "45,338", "70", "5.8", "Highway toll"],
        ["2026-01-05", "Park", "78-9012", "Client visit", "HQ", "Suwon", "10:00", "15:00", "32,100", "32,185", "85", "7.1", ""],
        ["2026-01-06", "Kim", "12-3456", "Training", "HQ", "Jamsil", "08:00", "18:00", "45,338", "45,390", "52", "4.3", "Parking fee"],
        ["2026-01-07", "Choi", "78-9012", "Inspection", "HQ", "Bundang", "09:30", "11:00", "32,185", "32,220", "35", "2.9", ""],
        ["2026-01-08", "Lee", "12-3456", "Meeting", "HQ", "Yeouido", "13:00", "16:30", "45,390", "45,425", "35", "2.9", ""],
        ["2026-01-09", "Park", "34-5678", "Delivery", "HQ", "Anyang", "07:30", "10:00", "18,500", "18,555", "55", "4.6", ""],
        ["2026-01-10", "Kim", "12-3456", "Seminar", "HQ", "COEX", "08:30", "17:00", "45,425", "45,470", "45", "3.8", "Parking fee"],
        ["2026-01-13", "Choi", "78-9012", "Client visit", "HQ", "Pangyo", "10:00", "13:00", "32,220", "32,260", "40", "3.3", ""],
        ["2026-01-14", "Lee", "34-5678", "Maintenance", "HQ", "Service Center", "09:00", "12:00", "18,555", "18,575", "20", "1.7", "Oil change"],
        ["2026-01-15", "Park", "12-3456", "Delivery", "HQ", "Gimpo", "08:00", "11:30", "45,470", "45,535", "65", "5.4", "Highway toll"],
        ["2026-01-16", "Kim", "78-9012", "Meeting", "HQ", "Songdo", "09:00", "14:00", "32,260", "32,355", "95", "7.9", "Highway toll"],
        ["2026-01-17", "Choi", "12-3456", "Training", "HQ", "Gwanghwamun", "08:30", "17:30", "45,535", "45,565", "30", "2.5", ""],
        ["2026-01-20", "Lee", "34-5678", "Client visit", "HQ", "Hanam", "10:00", "14:00", "18,575", "18,635", "60", "5.0", ""],
    ]

    # Add a totals row
    total_distance = sum(int(row[10]) for row in data[1:])
    total_fuel = sum(float(row[11]) for row in data[1:])
    data.append(["", "", "", "", "", "", "", "", "", "Total", str(total_distance), f"{total_fuel:.1f}", ""])

    col_widths = [65, 40, 55, 60, 40, 70, 50, 50, 52, 52, 45, 45, 70]

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2F5496")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#D6E4F0")]),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E2EFDA")),
                ("FONTNAME", (0, -1), (-1, -1), font_name),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )

    elements.append(table)
    doc.build(elements)
    print(f"Sample PDF created: {output_path}")


if __name__ == "__main__":
    create_sample_pdf()
