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

# ---------------------------
# DATE COLUMN
# ---------------------------
today_col = datetime.today().strftime("%d/%m")

if today_col not in df.columns:
    st.error(f"La colonna per oggi ({today_col}) non esiste nel foglio.")
    st.stop()

# ---------------------------
# TEACHER SELECTION
# ---------------------------
teachers = sorted(df["Insegnanti"].dropna().unique())
teacher = st.selectbox("Seleziona insegnante", teachers)

df_teacher = df[df["Insegnanti"] == teacher].copy()
df_teacher = df_teacher[df_teacher["Escluso"].str.lower() == "no"]

st.markdown(f"### Presenze del {today_col}")

# ---------------------------
# FORM
# ---------------------------
with st.form("presenze_form"):
    presenze = {}

    for idx, row in df_teacher.iterrows():
        key = f"pres_{idx}"
        default = row[today_col] if row[today_col] in ["x", "a"] else ""

        presenze[idx] = st.radio(
            f"{row['Numero di iscrizione']} – {row['Cognome']} {row['Nome']}",
            options=["", "x", "a"],
            index=["", "x", "a"].index(default),
            horizontal=True,
            key=key
        )

    submitted = st.form_submit_button("💾 Salva presenze")

# ---------------------------
# WRITE BACK
# ---------------------------
if submitted:
    col_index = df.columns.get_loc(today_col) + 1  # +1 per Google Sheets
    updates = []

    for idx, value in presenze.items():
        row_number = idx + 2  # +2 per header + indice pandas
        updates.append({
            "range": gspread.utils.rowcol_to_a1(row_number, col_index),
            "values": [[value]]
        })

    ws.batch_update(updates)
    st.success("Presenze salvate correttamente ✅")
