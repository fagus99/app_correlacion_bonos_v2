import pandas as pd
import numpy as np
import streamlit as st

st.set_page_config(page_title="🎰 Bonos x1 & GGR – Correlaciones por Categoría", layout="wide")
st.title("🎰 Correlaciones por Categoría de Bonos")

st.caption("Subí un Excel con la columna 'Categoria_Bonos' y las métricas diarias. La app calculará correlaciones de Bonos vs variables clave según categoría, e interpretará si a mayor cantidad de bonos se infla el GGR y el importe apostado.")

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
interpretaciones = []
for cat, subdf in df.groupby('Categoria_Bonos'):
    entry = {"Categoria_Bonos": cat}
    interpretacion = [f"En días con {cat.lower()},"]
    for tgt in corr_targets:
        corr_val = subdf['BONOS'].corr(subdf[tgt])
        entry[f"BONOS vs {tgt}"] = corr_val
        # Interpretación simple para GGR y Apostado
        if tgt in ["GGR TOTAL", "APOSTADO"]:
            if corr_val >= 0.5:
                interpretacion.append(f"la correlación con {tgt} es alta ({corr_val:.3f}), lo que sugiere que mayores bonos podrían inflar {tgt}.")
            elif corr_val >= 0.2:
                interpretacion.append(f"la correlación con {tgt} es moderada ({corr_val:.3f}), posible influencia pero no concluyente.")
            else:
                interpretacion.append(f"la correlación con {tgt} es baja ({corr_val:.3f}), no indica un inflado claro.")
    results.append(entry)
    interpretaciones.append(" ".join(interpretacion))

res_df = pd.DataFrame(results)

# Mostrar resultados e interpretaciones
for interp in interpretaciones:
    st.write(interp)

st.markdown("---")
st.dataframe(res_df.style.format({col: "{:.3f}" for col in res_df.columns if col != "Categoria_Bonos"}))
