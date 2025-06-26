from io import BytesIO
from datetime import datetime
from zoneinfo import ZoneInfo
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter
from settings import settings

TZ = ZoneInfo(settings.timezone)

# Warna dasar
COLOR_GREEN = "C6EFCE"
COLOR_RED = "FFC7CE"
COLOR_YELLOW = "FFEB9C"

# Utilitas blend warna
def blend_color(base_hex, factor):
    base = tuple(int(base_hex[i:i+2], 16) for i in (0, 2, 4))
    result = tuple(int((1 - factor) * c + factor * 255) for c in base)
    return ''.join(f"{v:02X}" for v in result)

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
        if row:
            ws.append(row)
            count += 1

            # Pewarnaan cell Home vs Away
            last_row = ws.max_row
            compare_pairs = [(12, 13), (14, 15), (16, 17), (18, 19)]
            for col_h, col_a in compare_pairs:
                h_cell = ws.cell(row=last_row, column=col_h)
                a_cell = ws.cell(row=last_row, column=col_a)
                try:
                    hv = float(h_cell.value)
                    av = float(a_cell.value)
                    diff = abs(hv - av)
                    factor = min(diff / 0.5, 1.0)

                    if hv > av:
                        h_cell.fill = PatternFill("solid", fgColor=blend_color(COLOR_GREEN, 1 - factor))
                        a_cell.fill = PatternFill("solid", fgColor=blend_color("FFFFFF", factor))
                    elif av > hv:
                        a_cell.fill = PatternFill("solid", fgColor=blend_color(COLOR_RED, 1 - factor))
                        h_cell.fill = PatternFill("solid", fgColor=blend_color("FFFFFF", factor))
                    else:
                        h_cell.fill = a_cell.fill = PatternFill("solid", fgColor=COLOR_YELLOW)
                except Exception:
                    continue

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
    if pred:
        p = pred[0]
        pr = p.get('predictions', {})
        win = pr.get('winner', {}).get('name', '-')
        advice = pr.get('advice', '-')
        pct = pr.get('percent', {})
        hp, dp, ap = pct.get('home'), pct.get('draw'), pct.get('away')
        t = p.get('teams', {})
        home, away = t.get('home', {}), t.get('away', {})
        form = home.get('last_5', {}).get('form', '-')
        form_away = away.get('last_5', {}).get('form', '-')
        att = home.get('last_5', {}).get('att', '-')
        att_away = away.get('last_5', {}).get('att', '-')
        df = home.get('last_5', {}).get('def', '-')
        df_away = away.get('last_5', {}).get('def', '-')
        comparison = pred[0].get("comparison", {}).get("total", {})
        comp_home = comparison.get("home", "-")
        comp_away = comparison.get("away", "-")
    else:
        win = advice = hp = dp = ap = form = form_away = att = att_away = df = df_away = comp_home = comp_away = '-'

    dt = datetime.fromisoformat(f['fixture']['date'].replace('Z', '+00:00')).astimezone(TZ)
    date = dt.strftime("%d-%m-%Y")
    time = dt.strftime("%H:%M %Z")

    return [
        f['league']['country'],
        f['league']['name'],
        f['teams']['home']['name'],
        f['teams']['away']['name'],
        date,
        time,
        win,
        advice,
        hp, dp, ap,
        form, form_away,
        att, att_away,
        df, df_away,
        comp_home, comp_away
    ]
