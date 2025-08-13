import io
import os
import base64
import unicodedata
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import seaborn as sns

# ============== CONFIGURACIÓN BÁSICA ==============
st.set_page_config(page_title="🎰 Bonos x1 & GGR – Análisis", layout="wide")
st.title("🎰 Análisis de Bonos con Rollover x1 y posible inflado del GGR")
st.caption("Subí un Excel diario y evaluá si los bonos con rollover x1 están inflando el GGR. Incluye correlaciones, tendencias, categorías de bonos y reporte en PDF.")

sns.set(style="whitegrid")

# ============== UTILIDADES ==============

REQ_COLS = [
    "FECHA",
    "GGR TOTAL",
    "APOSTADO",
    "PAGADO",
    "GGR SPORTS",
    "GGR CASINO",
    "GGR SLOTS",
    "ALTAS",
    "LOGGS",
    "BONOS",
    "ACREDITACIONES",
    "RETIROS",
    "TOTAL USUARIOS",
]

SYNONYMS = {
    "FECHA": ["FECHA", "DATE"],
    "GGR TOTAL": ["GGR TOTAL", "GGR_TOTAL", "TOTAL GGR", "GGR"],
    "APOSTADO": ["APOSTADO", "TOTAL APOSTADO", "BET", "TOTAL BET"],
    "PAGADO": ["PAGADO", "PAYOUT", "TOTAL PAGADO", "PREMIOS"],
    "GGR SPORTS": ["GGR SPORTS", "GGR_SPORTS", "SPORTS GGR", "GGR DEPORTES"],
    "GGR CASINO": ["GGR CASINO", "GGR_CASINO", "CASINO GGR"],
    "GGR SLOTS": ["GGR SLOTS", "GGR_SLOTS", "SLOTS GGR"],
    "ALTAS": ["ALTAS", "REGISTROS", "REGISTRADOS"],
    "LOGGS": ["LOGGS", "LOGINS", "SESSIONS", "INICIOS"],
    "BONOS": ["BONOS", "BONUS", "BONOS OTORGADOS"],
    "ACREDITACIONES": ["ACREDITACIONES", "DEPOSITOS", "DEPÓSITOS", "DEPOSITS"],
    "RETIROS": ["RETIROS", "WITHDRAWALS", "RETIROS TOTALES"],
    "TOTAL USUARIOS": ["TOTAL USUARIOS", "USUARIOS", "USERS", "TOTAL USERS"],
}

NUM_COLS = [c for c in REQ_COLS if c != "FECHA"]


def normalize(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    text = text.strip().upper()
    text = ''.join(ch for ch in unicodedata.normalize('NFD', text) if unicodedata.category(ch) != 'Mn')
    text = text.replace("_", " ")
    text = ' '.join(text.split())
    return text


def map_columns(df: pd.DataFrame) -> pd.DataFrame:
    colmap = {}
    normalized_cols = {normalize(c): c for c in df.columns}
    for target, alts in SYNONYMS.items():
        found = None
        for alt in alts:
            alt_norm = normalize(alt)
            if alt_norm in normalized_cols:
                found = normalized_cols[alt_norm]
                break
        if found is not None:
            colmap[found] = target
    df = df.rename(columns=colmap)
    return df


def ensure_required_columns(df: pd.DataFrame):
    missing = [c for c in REQ_COLS if c not in df.columns]
    return missing


def coerce_numeric(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for c in columns:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
    return df


def categorize_bonos_series(df: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """
    Replica la lógica del script del usuario (limpieza y categorización):
    - Detecta filas 'total' en BONOS y trunca hacia arriba.
    - Calcula un promedio 'recortado' (se eliminan 4 valores más bajos y 4 más altos si hay datos suficientes).
    - Define categorías en función de umbrales del promedio: 70%, 100%, 130%.
    """
    tmp = df.copy()

    # Convertir BONOS a str para buscar 'total'
    tmp['__BONOS_STR__'] = tmp['BONOS'].astype(str)
    total_idx = tmp[tmp['__BONOS_STR__'].str.lower().str.contains('total', na=False)].index
    if len(total_idx) > 0:
        tmp = tmp.loc[: total_idx[0] - 1]

    # Limpiar simbología si el origen trajo comas/puntos como separadores (ya forzamos numérico luego)
    tmp['BONOS'] = (
        tmp['__BONOS_STR__']
        .str.replace(',', '', regex=False)
        .str.replace('.', '', regex=False)
    )
    tmp['BONOS'] = pd.to_numeric(tmp['BONOS'], errors='coerce')
    tmp = tmp.dropna(subset=['BONOS'])

    # Promedio recortado (similar al del script adjunto)
    sorted_tmp = tmp.sort_values('BONOS')
    if len(sorted_tmp) >= 9:
        tmp_trim = sorted_tmp.iloc[4:-4]
    else:
        tmp_trim = sorted_tmp
    mean_bonos = float(tmp_trim['BONOS'].mean()) if not tmp_trim.empty else 0.0

    def _cat(v: float) -> str:
        low = mean_bonos * 0.70
        mid = mean_bonos * 1.00
        mid_high = mean_bonos * 1.30
        if v <= low:
            return 'Bonos bajos'
        elif v <= mid:
            return 'Bonos medios'
        elif v <= mid_high:
            return 'Bonos medios altos'
        else:
            return 'Bonos altos'

    df['CATEGORIA_BONOS'] = df['BONOS'].apply(_cat)
    return df, mean_bonos


def month_key(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors='coerce').dt.to_period('M').astype(str)


def safe_corr(x: pd.Series, y: pd.Series) -> float:
    x = pd.to_numeric(x, errors='coerce')
    y = pd.to_numeric(y, errors='coerce')
    if x.count() < 2 or y.count() < 2:
        return np.nan
    return x.corr(y)


# ============== SIDEBAR ==============
with st.sidebar:
    st.header("⚙️ Configuración")
    st.write("Subí un archivo .xlsx con columnas diarias (FECHA, GGR TOTAL, BONOS, etc.).")
    upl = st.file_uploader("📄 Subir archivo Excel (.xlsx)", type=["xlsx"])  # 1) CARGA DE DATOS
    sheet = st.text_input("Nombre de la hoja (opcional)", value="")
    show_clean_preview = st.checkbox("Mostrar previsualización limpia (5 filas)", value=True)

    st.markdown("---")
    st.subheader("Descargas")
    want_pdf = st.checkbox("Incluir sección de gráficos en PDF", value=True)


# ============== LECTURA Y PREPARACIÓN ==============
if upl is None:
    st.info("👆 Cargá el Excel para comenzar.")
    st.stop()

try:
    xl_kwargs = {"sheet_name": sheet} if sheet else {}
    raw_df = pd.read_excel(upl, **xl_kwargs)
except Exception as e:
    st.error(f"No pude leer el Excel: {e}")
    st.stop()

# Normalización de nombres y mapeo a requeridos
work = map_columns(raw_df.copy())

# Validación de columnas requeridas
missing = ensure_required_columns(work)
if missing:
    st.error(
        "Faltan columnas requeridas: " + ", ".join(missing) +
        "\nAsegurate de que existan con esos nombres o sinónimos (ver documentación en el código)."
    )
    st.dataframe(pd.DataFrame({"Columnas actuales": list(work.columns)}))
    st.stop()

# 2) CLASIFICAR NIVEL DE BONOS (incorporando lógica del script)
# Conversión de tipos + limpieza general
work['FECHA'] = pd.to_datetime(work['FECHA'], errors='coerce')
work = coerce_numeric(work, NUM_COLS)

# Columnas derivadas útiles
work['GGR AJUSTADO'] = work['GGR TOTAL'] - work['BONOS']
work['% BONOS/GGR'] = np.where(work['GGR TOTAL'] != 0, (work['BONOS'] / work['GGR TOTAL']) * 100, 0.0)

# Clasificación por categorías de bonos (basado en script adjunto)
work, mean_bonos = categorize_bonos_series(work)

if show_clean_preview:
    st.subheader("👀 Vista previa (5 filas)")
    st.dataframe(work.head(5))

# ============== DASHBOARD & FILTROS ==============
st.markdown("---")
st.header("📊 Dashboard Interactivo")
work['MES'] = month_key(work['FECHA'])
months = sorted(work['MES'].dropna().unique().tolist())
sel_months = st.multiselect("Filtrar por Mes", months, default=months)
if sel_months:
    df = work[work['MES'].isin(sel_months)].copy()
else:
    df = work.copy()

# ============== 4) CÁLCULO DE CORRELACIONES ==============
st.subheader("🔗 Correlaciones (Pearson)")

corr_targets = ["GGR TOTAL", "APOSTADO", "PAGADO", "ACREDITACIONES", "RETIROS"]

# Matriz de correlación de todas las variables numéricas
num_df = df.select_dtypes(include=[np.number])
fig_corr, ax = plt.subplots(figsize=(10, 6))
sns.heatmap(num_df.corr(method='pearson'), cmap="coolwarm", annot=False, ax=ax)
ax.set_title("Matriz de correlaciones (todas las variables numéricas)")
st.pyplot(fig_corr, use_container_width=True)

# Correlaciones BONOS vs targets (global y por categoría)
rows = []
for tgt in corr_targets:
    global_corr = safe_corr(df['BONOS'], df[tgt])
    rows.append({"Variable": tgt, "Correlación Global": global_corr})

cat_stats = []
for cat, dsub in df.groupby('CATEGORIA_BONOS'):
    entry = {"Categoría": cat}
    for tgt in corr_targets:
        entry[f"BONOS vs {tgt}"] = safe_corr(dsub['BONOS'], dsub[tgt])
    cat_stats.append(entry)

corr_table = pd.DataFrame(rows)
bycat_table = pd.DataFrame(cat_stats)

c1, c2 = st.columns(2)
with c1:
    st.markdown("**Correlaciones globales (BONOS vs …)**")
    st.dataframe(corr_table.style.format({"Correlación Global": "{:.3f}"}))
with c2:
    st.markdown("**Correlaciones por categoría de bonos**")
    st.dataframe(bycat_table.style.format({k: "{:.3f}" for k in bycat_table.columns if k != "Categoría"}))

# Scatter plots con línea de regresión
st.markdown("**Relaciones BONOS vs variables clave**")
for tgt in ["GGR TOTAL", "APOSTADO", "RETIROS"]:
    fig, ax = plt.subplots(figsize=(6, 4))
    sns.regplot(data=df, x='BONOS', y=tgt, scatter_kws={'alpha':0.6}, ax=ax)
    ax.set_title(f"BONOS vs {tgt}")
    st.pyplot(fig, use_container_width=True)

# ============== 5) OTRAS MÉTRICAS RELEVANTES ==============
st.header("📈 Tendencias y Métricas")

# Tendencias mensuales
monthly = (
    df.assign(MES=lambda x: month_key(x['FECHA']))
      .groupby('MES')[['GGR TOTAL', 'APOSTADO', 'BONOS', 'RETIROS', 'GGR AJUSTADO']]
      .mean(numeric_only=True)
      .reset_index()
)

c1, c2 = st.columns(2)
with c1:
    fig_m1, ax = plt.subplots(figsize=(7, 4))
    for col in ["GGR TOTAL", "GGR AJUSTADO", "BONOS"]:
        ax.plot(monthly['MES'], monthly[col], marker='o', label=col)
    ax.set_title("Promedios mensuales – GGR, GGR Ajustado y Bonos")
    ax.legend()
    plt.xticks(rotation=45)
    st.pyplot(fig_m1, use_container_width=True)

with c2:
    fig_m2, ax = plt.subplots(figsize=(7, 4))
    ax.plot(monthly['MES'], monthly['RETIROS'], marker='o', label='RETIROS')
    ax.plot(monthly['MES'], monthly['APOSTADO'], marker='o', label='APOSTADO')
    ax.set_title("Promedios mensuales – Retiros y Apostado")
    ax.legend()
    plt.xticks(rotation=45)
    st.pyplot(fig_m2, use_container_width=True)

# Correlación ajustada por mes (BONOS vs targets)
per_month_corr = []
for m, dsub in df.groupby('MES'):
    row = {"MES": m}
    for tgt in corr_targets:
        row[f"BONOS vs {tgt}"] = safe_corr(dsub['BONOS'], dsub[tgt])
    per_month_corr.append(row)
per_month_corr_df = pd.DataFrame(per_month_corr)

st.markdown("**Correlaciones por mes (BONOS vs …)**")
st.dataframe(per_month_corr_df.style.format({c: "{:.3f}" for c in per_month_corr_df.columns if c != "MES"}))

# Resumen estadístico
st.subheader("📘 Resumen estadístico (numérico)")
st.dataframe(df[REQ_COLS + ["GGR AJUSTADO", "% BONOS/GGR", "MES", "CATEGORIA_BONOS"]].describe(include=[np.number]).T)

# ============== 6) RESUMEN FINAL & INSIGHTS ==============
st.markdown("---")
st.header("🧠 Resumen e Insights")

# Indicadores clave para la narrativa
avg_bonus_share = df['% BONOS/GGR'].replace([np.inf, -np.inf], np.nan).dropna().mean()
cor_bonos_ggr = safe_corr(df['BONOS'], df['GGR TOTAL'])
cor_bonos_apostado = safe_corr(df['BONOS'], df['APOSTADO'])
cor_bonos_retiros = safe_corr(df['BONOS'], df['RETIROS'])

# Heurística de recomendación
inflation_flag = avg_bonus_share is not None and not np.isnan(avg_bonus_share) and avg_bonus_share >= 15
reco = []
if inflation_flag and (cor_bonos_ggr or 0) > 0.5:
    reco.append("Reducir temporalmente el monto de bonos o elevar requisitos no monetarios (p. ej., límite por usuario/día).")
    reco.append("Probar tests A/B por segmentos (VIP vs. nuevos) para medir GGR Ajustado.")
    reco.append("Monitorear '% BONOS/GGR' y mantenerlo debajo del 15%.")
else:
    reco.append("Mantener la política actual y seguir monitoreando el indicador '% BONOS/GGR'.")

st.markdown(
    f"""
**Hallazgos clave**  
- Promedio de *% Bonos/GGR*: **{avg_bonus_share:.2f}%**  
- Correlación BONOS–GGR TOTAL: **{cor_bonos_ggr:.2f}**  
- Correlación BONOS–APOSTADO: **{cor_bonos_apostado:.2f}**  
- Correlación BONOS–RETIROS: **{cor_bonos_retiros:.2f}**  

**Interpretación:** {'Existe una correlación positiva fuerte, lo que sugiere posible inflado del GGR.' if (cor_bonos_ggr or 0) >= 0.7 else 'No se observa correlación fuerte general; revisar por mes/categoría.'}
"""
)

st.markdown("**Recomendaciones:**")
st.write("\n".join([f"• {r}" for r in reco]))

# ============== 7) EXPORTS (CSV/XLSX/PDF) ==============
st.markdown("---")
st.header("📤 Exportar resultados")

# Procesado listo para exportar
export_cols = REQ_COLS + ["GGR AJUSTADO", "% BONOS/GGR", "MES", "CATEGORIA_BONOS"]
export_df = df[export_cols].copy()

# CSV
csv_bytes = export_df.to_csv(index=False).encode('utf-8')
st.download_button("⬇️ Descargar CSV procesado", data=csv_bytes, file_name="analisis_bonos_ggr.csv", mime="text/csv")

# XLSX
xlsx_buf = io.BytesIO()
with pd.ExcelWriter(xlsx_buf, engine='xlsxwriter') as writer:
    export_df.to_excel(writer, index=False, sheet_name='Analisis')
    corr_table.to_excel(writer, index=False, sheet_name='Correlaciones_globales')
    bycat_table.to_excel(writer, index=False, sheet_name='Correlaciones_por_categoria')
    per_month_corr_df.to_excel(writer, index=False, sheet_name='Correlaciones_por_mes')

st.download_button("⬇️ Descargar XLSX (full)", data=xlsx_buf.getvalue(), file_name="analisis_bonos_ggr.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# PDF (ReportLab)
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib import colors

pdf_buf = io.BytesIO()
doc = SimpleDocTemplate(pdf_buf, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=1.5*cm)
styles = getSampleStyleSheet()
story = []

story.append(Paragraph("<b>🎰 Informe – Bonos x1 & GGR</b>", styles['Title']))
story.append(Spacer(1, 0.3*cm))
now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
story.append(Paragraph(f"Generado: {now_str}", styles['Normal']))

# Tabla de KPIs
kpi_data = [
    ["% Bonos/GGR (promedio)", f"{avg_bonus_share:.2f}%"],
    ["Corr. BONOS–GGR TOTAL", f"{cor_bonos_ggr:.2f}"],
    ["Corr. BONOS–APOSTADO", f"{cor_bonos_apostado:.2f}"],
    ["Corr. BONOS–RETIROS", f"{cor_bonos_retiros:.2f}"],
]
kpitable = Table(kpi_data, hAlign='LEFT')
kpitable.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
    ('GRID', (0,0), (-1,-1), 0.25, colors.grey),
    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
]))
story.append(Spacer(1, 0.3*cm))
story.append(kpitable)

# Recomendaciones
story.append(Spacer(1, 0.3*cm))
story.append(Paragraph("<b>Recomendaciones</b>", styles['Heading2']))
for r in reco:
    story.append(Paragraph(f"• {r}", styles['Normal']))

# Gráficos (opcional)
img_paths = []
if want_pdf:
    # Guardar dos gráficos clave y embeber
    # 1) Matriz de correlaciones
    img1 = io.BytesIO()
    fig_corr.savefig(img1, format='png', bbox_inches='tight')
    img1.seek(0)
    img_paths.append(img1)

    # 2) Tendencias mensuales
    img2 = io.BytesIO()
    fig_m1.savefig(img2, format='png', bbox_inches='tight')
    img2.seek(0)
    img_paths.append(img2)

    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph("<b>Gráficos</b>", styles['Heading2']))
    for b in img_paths:
        story.append(Image(b, width=16*cm, height=9*cm))
        story.append(Spacer(1, 0.2*cm))

# Build PDF
doc.build(story)

st.download_button(
    "⬇️ Descargar PDF del informe",
    data=pdf_buf.getvalue(),
    file_name="informe_bonos_ggr.pdf",
    mime="application/pdf",
)

# ============== FOOTER ==============
st.markdown("---")
st.caption(
    "Esta app clasifica bonos (bajo/medio/medio alto/alto) a partir de un promedio recortado y analiza correlaciones y tendencias para detectar posible inflado del GGR.")
