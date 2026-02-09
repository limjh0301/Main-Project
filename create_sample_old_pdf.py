#!/usr/bin/env python3
"""Create a sample OLD format (2023-2024) vehicle operation log PDF for testing."""

from pathlib import Path

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm, mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph, PageBreak
    from reportlab.lib.styles import ParagraphStyle
except ImportError:
    import subprocess
    subprocess.check_call(["pip3", "install", "reportlab"])
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm, mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph, PageBreak
    from reportlab.lib.styles import ParagraphStyle


def find_korean_font():
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


def create_old_format_page(font_name, date_info, vehicle_no, manager, dept,
                           purpose, destination, depart_time, arrive_time,
                           start_km, end_km, driver_name, driver_dept,
                           prev_total, today_dist, curr_total):
    """Create elements for one page of old-format driving log."""
    elements = []

    title_style = ParagraphStyle("Title", fontName=font_name, fontSize=16, alignment=1, spaceAfter=10)
    elements.append(Paragraph("Vehicle Operation Log", title_style))
    elements.append(Spacer(1, 5*mm))

    # Header info table
    header_data = [
        ["Dept", dept, "Vehicle No.", vehicle_no, "Manager*", manager],
    ]
    ht = Table(header_data, colWidths=[60, 80, 60, 80, 70, 70])
    ht.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), font_name),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("GRID", (0,0), (-1,-1), 0.5, colors.black),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    elements.append(ht)
    elements.append(Spacer(1, 5*mm))

    # Date and purpose
    y, m, d, dow = date_info
    date_row = [[f"Vehicle Log", f"{y}year  {m}month  {d}day  {dow}"]]
    dt = Table(date_row, colWidths=[120, 300])
    dt.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), font_name),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("GRID", (0,0), (-1,-1), 0.5, colors.black),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
    ]))
    elements.append(dt)

    purp_row = [["Purpose", purpose]]
    pt = Table(purp_row, colWidths=[120, 300])
    pt.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), font_name),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("GRID", (0,0), (-1,-1), 0.5, colors.black),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
    ]))
    elements.append(pt)

    elements.append(Spacer(1, 3*mm))

    # Main trip table (matching old format structure)
    trip_header = ["", "", "Odometer", "", "Driver**", "", "Passenger", ""]
    trip_subheader = ["Destination", "Drive Time", "Depart", "Arrive", "Dept", "Name", "Dept", "Name"]
    trip_data = [
        destination,
        f"Dep:{depart_time}\nArr:{arrive_time}",
        str(start_km), str(end_km),
        driver_dept, driver_name,
        "", ""
    ]
    # Empty rows for additional trips
    empty_row = ["", "Dep:\nArr:", "", "", driver_dept, driver_name, "", ""]

    table_data = [trip_header, trip_subheader, trip_data, empty_row, empty_row, empty_row]
    mt = Table(table_data, colWidths=[70, 55, 40, 40, 55, 45, 55, 45])
    mt.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), font_name),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("GRID", (0,0), (-1,-1), 0.5, colors.black),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("SPAN", (2,0), (3,0)),  # Odometer header span
        ("SPAN", (4,0), (5,0)),  # Driver header span
        ("SPAN", (6,0), (7,0)),  # Passenger header span
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#E8E8E8")),
        ("BACKGROUND", (0,1), (-1,1), colors.HexColor("#F0F0F0")),
    ]))
    elements.append(mt)
    elements.append(Spacer(1, 3*mm))

    # Mileage summary
    mile_data = [
        ["Prev Total", f"{prev_total}km", "Fuel", "Qty", "-l"],
        ["Today Drive", f"{today_dist}km", "", "Amount", "-won"],
        ["Curr Total", f"{curr_total}km", "", "Station", ""],
    ]
    mlt = Table(mile_data, colWidths=[70, 80, 50, 60, 80])
    mlt.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), font_name),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("GRID", (0,0), (-1,-1), 0.5, colors.black),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    elements.append(mlt)

    return elements


def create_sample_old_pdf(output_path="sample_old_driving_log.pdf"):
    doc = SimpleDocTemplate(output_path, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    font_name = "Helvetica"
    korean_font = find_korean_font()
    if korean_font:
        try:
            pdfmetrics.registerFont(TTFont("Korean", korean_font))
            font_name = "Korean"
        except:
            pass

    all_elements = []

    # Sample data for multiple days
    days = [
        {
            "date_info": ("2023", "1", "3", "Tue"),
            "vehicle_no": "192ho2100", "manager": "Yoon SC", "dept": "Admin",
            "purpose": "Commute",
            "destination": "Lab\nDorm-Lab",
            "depart_time": "08:20", "arrive_time": "09:10",
            "start_km": "5655", "end_km": "5661",
            "driver_name": "Yoon SC", "driver_dept": "Ops Support",
            "prev_total": "5655", "today_dist": "6", "curr_total": "5661",
        },
        {
            "date_info": ("2023", "1", "4", "Wed"),
            "vehicle_no": "192ho2100", "manager": "Yoon SC", "dept": "Admin",
            "purpose": "Business",
            "destination": "Lab-\nCity Hall",
            "depart_time": "10:00", "arrive_time": "11:30",
            "start_km": "5661", "end_km": "5693",
            "driver_name": "Yoon SC", "driver_dept": "Ops Support",
            "prev_total": "5661", "today_dist": "32", "curr_total": "5693",
        },
        {
            "date_info": ("2023", "1", "5", "Thu"),
            "vehicle_no": "192ho2100", "manager": "Yoon SC", "dept": "Admin",
            "purpose": "Delivery",
            "destination": "Lab-\nPost Office",
            "depart_time": "14:00", "arrive_time": "15:20",
            "start_km": "5693", "end_km": "5715",
            "driver_name": "Yoon SC", "driver_dept": "Ops Support",
            "prev_total": "5693", "today_dist": "22", "curr_total": "5715",
        },
    ]

    for i, day in enumerate(days):
        page_elements = create_old_format_page(font_name, **day)
        all_elements.extend(page_elements)
        if i < len(days) - 1:
            all_elements.append(PageBreak())

    doc.build(all_elements)
    print(f"Sample old-format PDF created: {output_path}")


if __name__ == "__main__":
    create_sample_old_pdf()
