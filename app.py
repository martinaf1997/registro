import streamlit as st
import gspread
import pandas as pd
from datetime import datetime, timedelta
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
SHEET_NAME = "Finale - Iscrizione corso di italiano per adulti - Associazione Paroikia odv anno 2026-2027"
WORKSHEET_NAME = "ISCRIZIONI"

st.set_page_config(page_title="Presenze corso", layout="wide")

# ---------------------------
# UI -> Excel
# ---------------------------
PILL_TO_EXCEL = {
    "Assente": "",
    "Assente giustificato": "a",
    "Presente": "x",
}

# ---------------------------
# Excel -> UI
# ---------------------------
EXCEL_TO_PILL = {
    "": "Assente",
    "a": "Assente giustificato",
    "x": "Presente",
}

OFFERTE_OPTIONS = ["-", "5", "10"]

# ---------------------------
# GOOGLE SHEETS CONNECTION
# ---------------------------
@st.cache_resource
def connect_to_gsheet():
    gc = gspread.service_account_from_dict(
        st.secrets["gcp_service_account"]
    )
    sh = gc.open(SHEET_NAME)
    return sh.worksheet(WORKSHEET_NAME)


ws = connect_to_gsheet()

# ---------------------------
# LOAD DATA
# ---------------------------
data = ws.get_all_records()
df = pd.DataFrame(data)
df["_row"] = range(2, len(df) + 2)

# ---------------------------
# DATE COLUMNS
# ---------------------------
date_pattern = re.compile(r"\d{2}/\d{2}")
date_cols = [col for col in df.columns if date_pattern.fullmatch(str(col))]

today_col = datetime.today().strftime("%d/%m")
yest_col = (datetime.today() - timedelta(days=1)).strftime("%d/%m")

lezione_oggi = today_col in df.columns
lezione_ieri = yest_col in df.columns

if not (lezione_oggi or lezione_ieri):
    st.warning("⚠️ Oggi non c'è lezione: puoi solo stampare il registro")

# ---------------------------
# TEACHER SELECTION
# ---------------------------
teachers = sorted(df["Insegnanti"].dropna().unique())
teacher = st.selectbox("Seleziona insegnante", teachers)

df_teacher = df[df["Insegnanti"] == teacher].copy()

df_teacher["_num"] = pd.to_numeric(
    df_teacher["Numero di iscrizione"],
    errors="coerce"
)

df_teacher = df_teacher.sort_values("_num")

# ---------------------------
# ATTENDANCE STATISTICS
# ---------------------------
def get_student_stats(row, reference_col):
    """
    Calcola le statistiche dello studente fino alla lezione precedente
    rispetto a reference_col.

    x = presente
    a = assente giustificato
    vuoto = assente
    """

    if reference_col in date_cols:
        reference_index = date_cols.index(reference_col)
        past_dates = date_cols[:reference_index]
    else:
        # Se non c'è una lezione corrente, usa tutte le date fino a ieri.
        reference_dt = datetime.strptime(reference_col, "%d/%m")
        past_dates = [
            d for d in date_cols
            if datetime.strptime(d, "%d/%m") < reference_dt
        ]

    # Solo lezioni effettivamente già trascorse.
    values = []
    for col in past_dates:
        value = str(row.get(col, "")).strip().lower()
        if value not in ("x", "a", ""):
            value = ""
        values.append((col, value))

    lezioni_svolte = len(values)
    presenze = sum(value == "x" for _, value in values)
    giustificate = sum(value == "a" for _, value in values)
    assenze = sum(value == "" for _, value in values)

    ultima_presenza = None
    for col, value in reversed(values):
        if value == "x":
            ultima_presenza = col
            break

    percentuale = (
        round((presenze / lezioni_svolte) * 100)
        if lezioni_svolte > 0
        else 0
    )

    return {
        "lezioni_svolte": lezioni_svolte,
        "presenze": presenze,
        "giustificate": giustificate,
        "assenze": assenze,
        "percentuale": percentuale,
        "ultima_presenza": ultima_presenza,
    }


def show_student_stats(row, reference_col):
    stats = get_student_stats(row, reference_col)

    if stats["lezioni_svolte"] == 0:
        st.caption("Nessuna lezione precedente registrata")
        return

    ultima = stats["ultima_presenza"] or "mai"

    st.caption(
        f"📊 {stats['presenze']} presenze / {stats['lezioni_svolte']} lezioni"
        f"  ·  {stats['percentuale']}%"
        f"  ·  Ultima presenza: {ultima}"
        f"  ·  {stats['giustificate']} giustificate"
    )


# ---------------------------
# FORM
# ---------------------------
submitted = False

# Colonna su cui si registrano le presenze: oggi se c'è lezione, altrimenti ieri.
if lezione_oggi:
    active_col = today_col
elif lezione_ieri:
    active_col = yest_col
else:
    active_col = None

if active_col:
    st.markdown(f"### Presenze del {active_col}")

    presenze = {}
    offerte = {}

    for _, row in df_teacher.iterrows():
        sheet_row = int(row["_row"])

        # Riquadro per separare visivamente gli studenti.
        with st.container(border=True):
            st.markdown(
                f"**{row['Numero di iscrizione']} – {row['Cognome']} {row['Nome']}**"
            )

            # Se Offerte è già valorizzato (5 o 10), non mostrare il controllo.
            offerta_attuale = str(row.get("Offerte", "-")).strip()
            if not offerta_attuale or offerta_attuale.lower() == "nan":
                offerta_attuale = "-"

            if offerta_attuale == "-":
                offerta = st.pills(
                    "Offerte",
                    options=OFFERTE_OPTIONS,
                    selection_mode="single",
                    default="-",
                    key=f"offerta_{sheet_row}",
                )
                if offerta is None:
                    offerta = "-"
                offerte[sheet_row] = offerta

            # Statistiche riferite alle lezioni precedenti a quella attiva.
            show_student_stats(row, active_col)

            # Presenza (fuori da st.form: così Streamlit aggiorna il contatore subito).
            excel_value = str(row[active_col]).strip().lower()
            default_pill = EXCEL_TO_PILL.get(excel_value, "Assente")

            selected = st.pills(
                "Presenza",
                options=["Assente", "Assente giustificato", "Presente"],
                selection_mode="single",
                default=default_pill,
                key=f"pres_{sheet_row}"
            )

            if selected is None:
                selected = default_pill

            presenze[sheet_row] = PILL_TO_EXCEL[selected]

    # Riepilogo dei presenti in fondo all'elenco
    presenti_ora = sum(value == "x" for value in presenze.values())
    totale_studenti = len(df_teacher)

    st.info(f"👥 **Presenti selezionati: {presenti_ora} su {totale_studenti} studenti**")

    submitted = st.button("💾 Salva presenze")

else:
    st.markdown("### Presenze non disponibili oggi")



# ---------------------------
# RIEPILOGO ULTIME 8 LEZIONI
# ---------------------------
st.markdown("---")
st.subheader("Riepilogo presenze")

if "show_last8_pdf" not in st.session_state:
    st.session_state["show_last8_pdf"] = False

col_show, col_close = st.columns([1, 1])
with col_show:
    if st.button("📋 Mostra ultime 8 lezioni", key="show_last8_button"):
        st.session_state["show_last8_pdf"] = True
with col_close:
    if st.session_state["show_last8_pdf"]:
        if st.button("✖️ Chiudi riepilogo", key="close_last8_button"):
            st.session_state["show_last8_pdf"] = False

if st.session_state["show_last8_pdf"]:
    # Ricostruisce le date in ordine cronologico, gestendo dicembre/gennaio.
    today_dt = datetime.today()
    ordered_dates = []
    previous_month = None
    inferred_year = today_dt.year

    if date_cols:
        first_month = int(date_cols[0].split("/")[1])
        if first_month > today_dt.month:
            inferred_year -= 1

    for date_label in date_cols:
        day, month = map(int, date_label.split("/"))
        if previous_month is not None and month < previous_month:
            inferred_year += 1
        try:
            actual_date = datetime(inferred_year, month, day)
            if actual_date.date() <= today_dt.date():
                ordered_dates.append((actual_date, date_label))
        except ValueError:
            continue
        previous_month = month

    last8_dates = [label for _, label in ordered_dates[-8:]]

    if not last8_dates:
        st.info("Non risultano lezioni svolte fino a oggi.")
    else:
        pdf_buffer = BytesIO()
        styles = getSampleStyleSheet()
        cell_style = styles["Normal"]
        cell_style.fontSize = 7
        cell_style.leading = 8

        pdf_data = [[
            Paragraph("<b>N°</b>", cell_style),
            Paragraph("<b>Cognome</b>", cell_style),
            Paragraph("<b>Nome</b>", cell_style),
        ] + [Paragraph(f"<b>{d}</b>", cell_style) for d in last8_dates]]

        for _, student in df_teacher.iterrows():
            student_row = [
                Paragraph(str(student.get("Numero di iscrizione", "")), cell_style),
                Paragraph(str(student.get("Cognome", "")), cell_style),
                Paragraph(str(student.get("Nome", "")), cell_style),
            ]
            for date_label in last8_dates:
                value = str(student.get(date_label, "")).strip().lower()
                student_row.append({"x": "P", "a": "G"}.get(value, "A"))
            pdf_data.append(student_row)

        page_width, page_height = landscape(A4)
        left_margin, right_margin = 18, 18
        usable_width = page_width - left_margin - right_margin
        fixed_widths = [32, 105, 105]
        date_width = (usable_width - sum(fixed_widths)) / len(last8_dates)
        table = Table(
            pdf_data,
            colWidths=fixed_widths + [date_width] * len(last8_dates),
            repeatRows=1
        )
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))

        def last8_header(canvas, doc):
            canvas.saveState()
            canvas.setFont("Helvetica-Bold", 10)
            canvas.drawString(
                left_margin, page_height - 18,
                f"Presenze - {teacher} - ultime {len(last8_dates)} lezioni"
            )
            canvas.setFont("Helvetica", 7)
            canvas.drawRightString(
                page_width - right_margin, page_height - 18,
                "A = Assente   G = Giustificato   P = Presente"
            )
            canvas.restoreState()

        pdf_doc = SimpleDocTemplate(
            pdf_buffer,
            pagesize=landscape(A4),
            rightMargin=right_margin,
            leftMargin=left_margin,
            topMargin=30,
            bottomMargin=18
        )
        pdf_doc.build([table], onFirstPage=last8_header, onLaterPages=last8_header)
        pdf_buffer.seek(0)

        import base64
        pdf_base64 = base64.b64encode(pdf_buffer.getvalue()).decode("utf-8")
        st.components.v1.html(
            f'<iframe src="data:application/pdf;base64,{pdf_base64}" '
            'width="100%" height="650" '
            'style="border:1px solid #cccccc; border-radius:8px;" '
            'type="application/pdf"></iframe>',
            height=670,
            scrolling=False
        )
        st.caption("Legenda: P = Presente · G = Assente giustificato · A = Assente")

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
    date_cols = [col for col in df.columns if date_pattern.fullmatch(str(col))]

    # Ordina le date
    date_cols_sorted = sorted(
        date_cols,
        key=lambda x: datetime.strptime(x, "%d/%m")
    )

    today_dt = datetime.strptime(today_col, "%d/%m")

    # Se today_col non esiste nel foglio, cerca l'ultima data di lezione ≤ oggi
    if today_col in date_cols_sorted:
        last_filled_index = date_cols_sorted.index(today_col)
    else:
        past_dates = [
            d for d in date_cols_sorted
            if datetime.strptime(d, "%d/%m") <= today_dt
        ]

        if not past_dates:
            st.warning("Nessuna data di lezione trovata nel registro.")
            st.stop()

        last_filled_index = date_cols_sorted.index(past_dates[-1])

    # Selezione numero giorni
    n_gg = 15

    try:
        selected_dates = date_cols_sorted[
            last_filled_index:last_filled_index + n_gg
        ]
    except Exception:
        selected_dates = date_cols_sorted[last_filled_index:]

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
                row_data.append("")

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
        topMargin=25,
        bottomMargin=10
    )

    def header(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 8)

        # Nome insegnante in alto a sinistra
        canvas.drawString(
            10,
            landscape(A4)[1] - 20,
            f"Classe: {teacher}"
        )

        # Data di stampa in alto a destra
        data_stampa = datetime.today().strftime("%d/%m/%Y")

        canvas.drawRightString(
            landscape(A4)[0] - 10,
            landscape(A4)[1] - 20,
            f"Stampato il: {data_stampa}"
        )

        canvas.restoreState()

    col_widths = [40, 95, 95] + [25] * len(selected_dates)

    table = Table(
        table_data,
        colWidths=col_widths,
        repeatRows=1
    )

    style = TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.yellow),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
    ])

    table.setStyle(style)

    elements = [table]

    doc.build(
        elements,
        onFirstPage=header,
        onLaterPages=header
    )

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
if submitted and active_col:
    col_index = df.columns.get_loc(active_col) + 1
    offerte_col_index = df.columns.get_loc("Offerte") + 1
    updates = []

    for sheet_row, value in presenze.items():
        updates.append({
            "range": gspread.utils.rowcol_to_a1(sheet_row, col_index),
            "values": [[value]]
        })

    for sheet_row, value in offerte.items():
        updates.append({
            "range": gspread.utils.rowcol_to_a1(sheet_row, offerte_col_index),
            "values": [[value]]
        })

    ws.batch_update(updates)

    st.success("Presenze e offerte salvate correttamente ✅")
