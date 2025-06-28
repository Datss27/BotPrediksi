from io import BytesIO
from datetime import datetime
from zoneinfo import ZoneInfo
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter
from settings import settings
from openpyxl.formatting.rule import ColorScaleRule, FormulaRule
from openpyxl.styles import PatternFill

TZ = ZoneInfo(settings.timezone)

def _parse_percent(value):
    if isinstance(value, str) and "%" in value:
        try:
            return float(value.replace("%", ""))
        except ValueError:
            return "-"
    return value if isinstance(value, (int, float)) else "-"
    
def create_workbook(fixtures):
    wb = Workbook()
    ws = wb.active
    date_str = datetime.now(TZ).strftime("%Y-%m-%d")
    ws.title = f"Prediksi {date_str}"

    headers = [
        "Negara", "Liga", "Home", "Away", "Tanggal", "Jam", "Saran",
        "Probabilitas (H/D/A)",
        "History", None,
        "Form", None,
        "ATT", None,
        "DEF", None,
        "Comp", None,
        "H2H", None
    ]
    subheaders = [""] * 8 + ["Home", "Away"] * 6

    ws.append(headers)
    ws.append(subheaders)

    # Style header
    header_fill = PatternFill("solid", fgColor="FFFF00")
    for row in ws.iter_rows(min_row=1, max_row=2):
        for cell in row:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.fill = header_fill

    for col in range(1, 9):
        ws.merge_cells(start_row=1, start_column=col, end_row=2, end_column=col)

    merge_groups = {
        "History": (9, 10),
        "Form": (11, 12),
        "ATT": (13, 14),
        "DEF": (15, 16),
        "Comp": (17, 18),
        "H2H": (19, 20)
    }
    for _, (start_col, end_col) in merge_groups.items():
        ws.merge_cells(start_row=1, start_column=start_col, end_row=1, end_column=end_col)

    written_matches = 0
    for f in fixtures:
        row = _extract_row(f)
        if not row:
            continue
        ws.append(row)
        written_matches += 1

    # ⏬ Tambahkan setelah semua data ditulis

    # 1. Gradient formatting (kolom 11–20)
    gradient_columns = range(11, 21)
    color_rule = ColorScaleRule(
        start_type='min', start_color='F8696B',
        mid_type='percentile', mid_value=50, mid_color='FFEB84',
        end_type='max', end_color='63BE7B'
    )
    for col_idx in gradient_columns:
        col_letter = get_column_letter(col_idx)
        ws.conditional_formatting.add(
            f"{col_letter}3:{col_letter}{ws.max_row}",
            color_rule
        )

    # 2. Biru jika nilai sama
    blue_fill = PatternFill(start_color="ADD8E6", end_color="ADD8E6", fill_type="solid")
    pairs = [(11, 12), (13, 14), (15, 16), (17, 18), (19, 20)]
    for col_home, col_away in pairs:
        h = get_column_letter(col_home)
        a = get_column_letter(col_away)
        formula = f"${h}3=${a}3"
        ws.conditional_formatting.add(f"{h}3:{h}{ws.max_row}", FormulaRule(formula=[formula], fill=blue_fill))
        ws.conditional_formatting.add(f"{a}3:{a}{ws.max_row}", FormulaRule(formula=[formula], fill=blue_fill))

    # Auto width
    for i, col_cells in enumerate(ws.columns, 1):
        col_letter = get_column_letter(i)
        max_len = max((len(str(c.value)) for c in col_cells if c.value), default=0)
        ws.column_dimensions[col_letter].width = max_len + 2

    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio, written_matches

def _extract_row(f):
    pred = f.get('prediction') or []
    if not pred or not pred[0].get('predictions'):
        return None

    p = pred[0]
    pr = p.get('predictions', {})
    advice = pr.get('advice', '-')
    pct = pr.get('percent', {})
    hp = pct.get('home', '-')
    dp = pct.get('draw', '-')
    ap = pct.get('away', '-')
    prob_summary = f"{hp} / {dp} / {ap}"
    t = p.get('teams', {})
    home, away = t.get('home', {}), t.get('away', {})
    home_stats, away_stats = home.get("league", {}).get("fixtures", {}), away.get("league", {}).get("fixtures", {})
    h_played = home_stats.get("played", {}).get("total", "-")
    h_wins = home_stats.get("wins", {}).get("total", "-")
    h_draws = home_stats.get("draws", {}).get("total", "-")
    h_loses = home_stats.get("loses", {}).get("total", "-")
    a_played = away_stats.get("played", {}).get("total", "-")
    a_wins = away_stats.get("wins", {}).get("total", "-")
    a_draws = away_stats.get("draws", {}).get("total", "-")
    a_loses = away_stats.get("loses", {}).get("total", "-")
    home_sum = f"{h_played} : {h_wins} / {h_draws} / {h_loses}"
    away_sum = f"{a_played} : {a_wins} / {a_draws} / {a_loses}"
    form = _parse_percent(home.get('last_5', {}).get('form'))
    form_away = _parse_percent(away.get('last_5', {}).get('form'))
    att = _parse_percent(home.get('last_5', {}).get('att'))
    att_away = _parse_percent(away.get('last_5', {}).get('att'))
    df = _parse_percent(home.get('last_5', {}).get('def'))
    df_away = _parse_percent(away.get('last_5', {}).get('def'))

    comparison = p.get("comparison", {}).get("total", {})
    comp_home = _parse_percent(comparison.get("home"))
    comp_away = _parse_percent(comparison.get("away"))
    hth = p.get("comparison", {}).get("h2h", {})
    hth_home = _parse_percent(hth.get("home"))
    hth_away = _parse_percent(hth.get("away"))

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
        prob_summary,
        home_sum, away_sum,
        form, form_away,
        att, att_away,
        df, df_away,
        comp_home, comp_away,
        hth_home, hth_away
    ]
