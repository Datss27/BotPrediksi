from io import BytesIO
from datetime import datetime
from zoneinfo import ZoneInfo
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter
from settings import settings

TZ = ZoneInfo(settings.timezone)

def create_workbook(fixtures):
    wb = Workbook()
    ws = wb.active
    date_str = datetime.now(TZ).strftime("%Y-%m-%d")
    ws.title = f"Prediksi {date_str}"

    # Header dan Subheader
    headers = [
        "Negara", "Liga", "Home", "Away", "Tanggal", "Jam", "Saran",
        "Prob Home", "Prob Draw", "Prob Away",
        "Form", None,
        "ATT", None,
        "DEF", None,
        "Comp", None,
        "H2H", None
    ]
    subheaders = [""] * 10 + ["Home", "Away"] * 5

    # Tambahkan ke worksheet
    ws.append(headers)
    ws.append(subheaders)

    # Styling header
    header_fill = PatternFill("solid", fgColor="FFFF00")
    for row in ws.iter_rows(min_row=1, max_row=2):
        for cell in row:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.fill = header_fill

    # Merge header kolom tunggal
    for col in range(1, 11):
        ws.merge_cells(start_row=1, start_column=col, end_row=2, end_column=col)

    # Merge header ganda
    merge_groups = {
        "Form": (11, 12),
        "ATT": (13, 14),
        "DEF": (15, 16),
        "Comp": (17, 18),
        "H2H": (19,20)
    }
    for label, (start_col, end_col) in merge_groups.items():
        ws.merge_cells(start_row=1, start_column=start_col, end_row=1, end_column=end_col)

    total_matches = len(fixtures)  # Tetap hitung semua
    written_matches = 0            # Hanya yang punya prediksi ditulis

    for f in fixtures:
        row = _extract_row(f)
        if not row:
            continue  # Skip jika tidak ada prediksi

        ws.append(row)
        written_matches += 1

    # Otomatis atur lebar kolom
    for i, col_cells in enumerate(ws.columns, 1):
        col_letter = get_column_letter(i)
        max_len = max((len(str(c.value)) for c in col_cells if c.value), default=0)
        ws.column_dimensions[col_letter].width = max_len + 2

    # Simpan ke BytesIO
    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio, total_matches

def _extract_row(f):
    pred = f.get('prediction') or []
    if pred:
        p = pred[0]
        pr = p.get('predictions', {})
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
        hth = pred[0].get("comparison", {}).get("h2h", {})
        hth_home = hth.get("home", "-")
        hth_away = hth.get("away", "-")
    else:
        advice = hp = dp = ap = form = form_away = att = att_away = df = df_away = comp_home = comp_away = hth_home = hth_away = '-'

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
        advice,
        hp, dp, ap,
        form, form_away,
        att, att_away,
        df, df_away,
        comp_home, comp_away,
        hth_home, hth_away
    ]
