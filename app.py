import streamlit as st
import gspread
import pandas as pd
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from io import BytesIO
import re
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet

# ---------------------------
# CONFIG
# ---------------------------
SHEET_NAME = "FINALE - Iscrizione corso di italiano per adulti - Associazione Paroikia odv anno 2025-2026"
WORKSHEET_NAME = "ISCRIZIONI"

st.set_page_config(page_title="Presenze corso", layout="wide")

# UI -> Excel
PILL_TO_EXCEL = {
    "Assente": "",
    "Assente giustificato": "a",
    "Presente": "x",
}

# Excel -> UI
EXCEL_TO_PILL = {
    "": "Assente",
    "a": "Assente giustificato",
    "x": "Presente",
}

# ---------------------------
# GOOGLE SHEETS CONNECTION
# ---------------------------
@st.cache_resource
def connect_to_gsheet():
    gc = gspread.service_account_from_dict(
    st.secrets["gcp_service_account"])
    sh = gc.open("FINALE - Iscrizione corso di italiano per adulti - Associazione Paroikia odv anno 2025-2026")
    return sh.worksheet("ISCRIZIONI")

ws = connect_to_gsheet()

# ---------------------------
# LOAD DATA
# ---------------------------
data = ws.get_all_records()
df = pd.DataFrame(data)
df["_row"] = range(2, len(df) + 2)

# ---------------------------
# DATE COLUMN
# ---------------------------
#today_col = datetime.today().strftime("%d/%m")
today_col = "16/04"

lezione_oggi = today_col in df.columns
if not lezione_oggi:
    st.warning("⚠️ Oggi non c'è lezione: puoi solo stampare il registro")

# ---------------------------
# TEACHER SELECTION
# ---------------------------
teachers = sorted(df["Insegnanti"].dropna().unique())
teacher = st.selectbox("Seleziona insegnante", teachers)

df_teacher = df[df["Insegnanti"] == teacher].copy()
df_teacher = df_teacher[df_teacher["Escluso"] == "No"]

df_teacher["_num"] = pd.to_numeric(
    df_teacher["Numero di iscrizione"],
    errors="coerce"
)

df_teacher = df_teacher.sort_values("_num")

if lezione_oggi:
    st.markdown(f"### Presenze del {today_col}")
else:
    st.markdown("### Presenze non disponibili oggi")

# ---------------------------
# FORM
# ---------------------------
submitted = False
if lezione_oggi:

    with st.form("presenze_form"):
        presenze = {}
    
        for _, row in df_teacher.iterrows():
            sheet_row = row["_row"]
            key = f"pres_{sheet_row}"
    
            excel_value = str(row[today_col]).strip().lower()
            default_pill = EXCEL_TO_PILL.get(excel_value, "Assente")
    
            selected = st.pills(
                f"{row['Numero di iscrizione']} – {row['Cognome']} {row['Nome']}",
                options=["Assente", "Assente giustificato", "Presente"],
                selection_mode="single",
                default=default_pill,
                key=key
            )
    
            presenze[sheet_row] = PILL_TO_EXCEL[selected]
    
        submitted = st.form_submit_button("💾 Salva presenze")

# ---------------------------
# REGISTRO CARTACEO    
# ---------------------------

st.markdown("---")
st.subheader("Registro cartaceo")

if st.button("🖨️ Stampa registro"):

    styles = getSampleStyleSheet()
    styleN = styles["Normal"]
    styleN.fontSize = 7
    styleN.leading = 7
    
    # ---------------------------
    # IDENTIFICA COLONNE DATA
    # ---------------------------
    
    date_pattern = re.compile(r"\d{2}/\d{2}")
    date_cols = [col for col in df.columns if date_pattern.fullmatch(col)]
    
    # Ordina le date (importante!)
    date_cols_sorted = sorted(date_cols, key=lambda x: datetime.strptime(x, "%d/%m"))
    last_filled_index = date_cols_sorted.index(today_col)
    
    # Selezione numero giorni
    n_gg = 15
    selected_dates = date_cols_sorted[last_filled_index:last_filled_index + n_gg]
    
    # ---------------------------
    # COSTRUZIONE TABELLA
    # ---------------------------
    header = ["N°", "Cognome", "Nome"] + selected_dates
    
    table_data = [header]
    
    for _, row in df_teacher.iterrows():
        row_data = [
            Paragraph(str(row["Numero di iscrizione"]), styleN),
            Paragraph(str(row["Cognome"]), styleN),
            Paragraph(str(row["Nome"]), styleN),
        ]
        
        for i, col in enumerate(selected_dates):
            if i == 0:
                # Prima colonna = ultima lezione compilata → mostra dati reali
                value = str(row[col]).strip().lower()
                row_data.append(value)
            else:
                # Future → vuote
                row_data.append([""])
    
        table_data.append(row_data)
    
    # ---------------------------
    # CREA PDF
    # ---------------------------
    buffer = BytesIO()
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=10,
        leftMargin=10,
        topMargin=10,
        bottomMargin=10
    )
    
    col_widths = [40, 95, 95] + [25] * len(selected_dates)
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    
    style = TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.yellow),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
    ])
    
    table.setStyle(style)
    
    elements = [table]
    doc.build(elements)
    
    buffer.seek(0)
    
    # ---------------------------
    # DOWNLOAD
    # ---------------------------
    st.download_button(
        label="📥 Scarica PDF registro",
        data=buffer,
        file_name=f"registro_{teacher}.pdf",
        mime="application/pdf"
    )
    
# ---------------------------
# WRITE BACK
# ---------------------------
if submitted and lezione_oggi:
    col_index = df.columns.get_loc(today_col) + 1  # +1 per Google Sheets
    updates = []

    for sheet_row, value in presenze.items():
        updates.append({
            "range": gspread.utils.rowcol_to_a1(sheet_row, col_index),
            "values": [[value]]
        })

    ws.batch_update(updates)
    st.success("Presenze salvate correttamente ✅")
