from io import BytesIO
from datetime import datetime
from zoneinfo import ZoneInfo
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter
from settings import settings

TZ = ZoneInfo(settings.timezone)

# Warna dasar (ARGB)
COLOR_GREEN = "FFC6EFCE"   # hijau terang
COLOR_RED   = "FFFFC7CE"   # merah terang
COLOR_YELLOW= "FFFFEB9C"   # kuning
WHITE_RGB   = "FFFFFF"

def blend_color(base_rgb: str, factor: float) -> str:
    r, g, b = (int(base_rgb[i:i+2], 16) for i in (0,2,4))
    nr = int(r   + (255 - r) * factor)
    ng = int(g   + (255 - g) * factor)
    nb = int(b   + (255 - b) * factor)
    return f"FF{nr:02X}{ng:02X}{nb:02X}"
    
def safe_float(val):
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0

def create_workbook(fixtures):
    wb = Workbook()
    ws = wb.active
    date_str = datetime.now(TZ).strftime("%Y-%m-%d")
    ws.title = f"Prediksi {date_str}"

    # Header dan Subheader
    headers = [
        "Negara", "Liga", "Home", "Away", "Tanggal", "Jam", "Prediksi", "Saran",
        "Prob Home", "Prob Draw", "Prob Away",
        "Form", None,
        "ATT", None,
        "DEF", None,
        "Comp", None
    ]
    subheaders = [""] * 11 + ["Home", "Away"] * 4

    # Tambahkan ke worksheet
    ws.append(headers)
    ws.append(subheaders)

    # Styling
    header_fill = PatternFill("solid", fgColor="FFFF00")
    for row in ws.iter_rows(min_row=1, max_row=2):
        for cell in row:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.fill = header_fill

    # Merge header kolom tunggal (tanpa subheader)
    for col in range(1, 12):
        ws.merge_cells(start_row=1, start_column=col, end_row=2, end_column=col)

    # Merge header ganda (dengan subheader Home/Away)
    merge_groups = {
        "Form": (12, 13),
        "ATT": (14, 15),
        "DEF": (16, 17),
        "Comp": (18, 19)
    }
    for label, (start_col, end_col) in merge_groups.items():
        ws.merge_cells(start_row=1, start_column=start_col, end_row=1, end_column=end_col)

    # Tambahkan data dan warnai Comp
    count = 0
    for f in fixtures:
        row = _extract_row(f)
        if not row:
            continue
        ws.append(row)
        last = ws.max_row

        # Pasangan kolom Home vs Away untuk Form, ATT, DEF, Comp
        pairs = [(12,13), (14,15), (16,17), (18,19)]
        for home_col, away_col in pairs:
            h_cell = ws.cell(row=last, column=home_col)
            a_cell = ws.cell(row=last, column=away_col)
            try:
                hv = float(h_cell.value)
                av = float(a_cell.value)
            except (TypeError, ValueError):
                # Lewati jika bukan angka
                continue

            diff   = abs(hv - av)
            factor = min(diff / 100, 1.0)
            
            if h_cell.value is None or a_cell.value is None:
                continue

            if hv > av:
                # Home unggul: hijau → putih
                color_h = blend_color(COLOR_GREEN[2:], factor)
                color_a = f"FF{WHITE_RGB}"
            elif av > hv:
                # Away unggul: merah → putih
                color_a = blend_color(COLOR_RED[2:], factor)
                color_h = f"FF{WHITE_RGB}"
            else:
                # Seri: kuning solid
                color_h = color_a = COLOR_YELLOW

            h_cell.fill = PatternFill(fill_type="solid", fgColor=color_h)
            a_cell.fill = PatternFill(fill_type="solid", fgColor=color_a)

    # Otomatis atur lebar kolom
    for i, col_cells in enumerate(ws.columns, 1):
        col_letter = get_column_letter(i)
        max_len = max((len(str(c.value)) for c in col_cells if c.value), default=0)
        ws.column_dimensions[col_letter].width = max_len + 2

    # Simpan ke BytesIO
    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio, count


def _extract_row(f):
    pred = f.get('prediction') or []
    if not pred:
        return None

    p = pred[0]
    pr = p.get('predictions', {})
    pct = pr.get('percent', {})
    t = p.get('teams', {})
    home = t.get('home', {}) or {}
    away = t.get('away', {}) or {}

    comparison = p.get("comparison", {}).get("total", {})

    dt = datetime.fromisoformat(f['fixture']['date'].replace('Z', '+00:00')).astimezone(TZ)

    return {
        "Negara": f['league'].get('country', '-'),
        "Liga": f['league'].get('name', '-'),
        "Home": f['teams']['home'].get('name', '-'),
        "Away": f['teams']['away'].get('name', '-'),
        "Tanggal": dt.strftime("%d-%m-%Y"),
        "Jam": dt.strftime("%H:%M %Z"),
        "Prediksi": pr.get('winner', {}).get('name', '-'),
        "Saran": pr.get('advice', '-'),

        # Probabilitas
        "Prob Home": safe_float(pct.get('home')),
        "Prob Draw": safe_float(pct.get('draw')),
        "Prob Away": safe_float(pct.get('away')),

        # Statistik
        "Form Home": home.get('last_5', {}).get('form', '-'),
        "Form Away": away.get('last_5', {}).get('form', '-'),
        "ATT Home": safe_float(home.get('last_5', {}).get('att')),
        "ATT Away": safe_float(away.get('last_5', {}).get('att')),
        "DEF Home": safe_float(home.get('last_5', {}).get('def')),
        "DEF Away": safe_float(away.get('last_5', {}).get('def')),
        "Comp Home": safe_float(comparison.get('home')),
        "Comp Away": safe_float(comparison.get('away')),
    }
