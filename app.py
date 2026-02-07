import streamlit as st
import gspread
import pandas as pd
from datetime import datetime

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
today_col = "09/02"

if today_col not in df.columns:
    st.error(f"Oggi non c'è lezione!")
    st.stop()

# ---------------------------
# TEACHER SELECTION
# ---------------------------
teachers = sorted(df["Insegnanti"].dropna().unique())
teacher = st.selectbox("Seleziona insegnante", teachers)

df_teacher = df[df["Insegnanti"] == teacher].copy()
df_teacher = df_teacher[df_teacher["Escluso"] == "No"]

st.markdown(f"### Presenze del {today_col}")

# ---------------------------
# FORM
# ---------------------------
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
# WRITE BACK
# ---------------------------
if submitted:
    col_index = df.columns.get_loc(today_col) + 1  # +1 per Google Sheets
    updates = []

    for sheet_row, value in presenze.items():
        updates.append({
            "range": gspread.utils.rowcol_to_a1(sheet_row, col_index),
            "values": [[value]]
        })

    ws.batch_update(updates)
    st.success("Presenze salvate correttamente ✅")
