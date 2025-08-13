import pandas as pd
import numpy as np
import streamlit as st

st.set_page_config(page_title="🎰 Bonos x1 & GGR – Correlaciones por Categoría", layout="wide")
st.title("🎰 Correlaciones por Categoría de Bonos")

st.caption("Subí un Excel con la columna 'Categoria_Bonos' y las métricas diarias. La app calculará correlaciones de Bonos vs variables clave según categoría.")

# Variables objetivo para correlación
corr_targets = ["GGR TOTAL", "APOSTADO", "RETIROS", "ACREDITACIONES"]

# Subida de archivo
upl = st.file_uploader("📄 Subir archivo Excel (.xlsx)", type=["xlsx"])
if upl is None:
    st.info("👆 Cargá el Excel para comenzar.")
    st.stop()

try:
    df = pd.read_excel(upl)
except Exception as e:
    st.error(f"No pude leer el Excel: {e}")
    st.stop()

# Verificar columnas necesarias
if 'Categoria_Bonos' not in df.columns or 'BONOS' not in df.columns:
    st.error("El archivo debe contener las columnas 'Categoria_Bonos' y 'BONOS'.")
    st.stop()

for col in corr_targets:
    if col not in df.columns:
        st.error(f"Falta la columna requerida: {col}")
        st.stop()

# Forzar tipos numéricos
df['BONOS'] = pd.to_numeric(df['BONOS'], errors='coerce').fillna(0)
for col in corr_targets:
    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

# Calcular correlaciones por categoría
results = []
for cat, subdf in df.groupby('Categoria_Bonos'):
    entry = {"Categoria_Bonos": cat}
    for tgt in corr_targets:
        corr_val = subdf['BONOS'].corr(subdf[tgt])
        entry[f"BONOS vs {tgt}"] = corr_val
    results.append(entry)

res_df = pd.DataFrame(results)

# Mostrar resultados
for _, row in res_df.iterrows():
    st.subheader(f"📌 {row['Categoria_Bonos']}")
    st.write("En los días donde los bonos otorgados son **{}**, las correlaciones son:".format(row['Categoria_Bonos'].lower()))
    for tgt in corr_targets:
        st.write(f"• BONOS vs {tgt}: {row[f'BONOS vs {tgt}']:.3f}")

st.markdown("---")
st.dataframe(res_df.style.format({col: "{:.3f}" for col in res_df.columns if col != "Categoria_Bonos"}))
