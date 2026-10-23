# -*- coding: utf-8 -*-
import pandas as pd
import glob
import os

# ==============================================================================
# CONFIGURACIÓN DE RUTAS Y DIRECTORIOS
# ==============================================================================
DIR_BASE = os.getcwd()
DIR_DATOS = os.path.join(DIR_BASE, "Datos_mensuales")

PATH_PARQUET_RECT = os.path.join(DIR_BASE, "Tablero_Rectificaciones_Detalle.parquet")
PATH_PARQUET_SLA = os.path.join(DIR_BASE, "Tablero_SLA_Pedidos.parquet")
PATH_PARQUET_ANUL = os.path.join(DIR_BASE, "Tablero_Anulaciones_Detalle.parquet")

print("==================================================================")
print("🚀 EJECUTANDO ETL Y PROCESAMIENTO DE RECTIFICACIONES DEL PORTAL")
print(f"📂 DIRECTORIO BASE: {DIR_BASE}")
print("==================================================================")

def normalizar_pedido(val):
    if pd.isna(val):
        return ""
    s = str(val).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s.lstrip("0")

# ------------------------------------------------------------------------------
# 1. CARGAR Y PROCESAR CSV DEL PORTAL (CAUSAS DE ANULACIÓN Y APROBACIÓN)
# ------------------------------------------------------------------------------
archivos_causas = (
    glob.glob(os.path.join(DIR_DATOS, "*[Aa]nula*.csv")) +
    glob.glob(os.path.join(DIR_BASE, "*[Aa]nula*.csv")) +
    glob.glob(os.path.join(DIR_DATOS, "*[Cc]ausa*.csv")) +
    glob.glob(os.path.join(DIR_BASE, "*[Cc]ausa*.csv"))
)

list_causas = []
for f in set(archivos_causas):
    print(f"📌 Cargando archivo de Causas del Portal: {f}")
    try:
        df_c = pd.read_csv(f, sep=None, engine="python", encoding="latin1", dtype=str, on_bad_lines="skip")
        df_c.columns = df_c.columns.str.strip()
        list_causas.append(df_c)
    except Exception as e:
        print(f"    ⚠️ Error leyendo {f}: {e}")

if list_causas:
    df_portal = pd.concat(list_causas, ignore_index=True)
    df_portal.columns = df_portal.columns.str.strip()

    mapa_cols = {}
    for c in df_portal.columns:
        clow = c.lower()
        if "almac" in clow: mapa_cols[c] = "Almacen"
        elif "tienda" in clow or "sucursal" in clow: mapa_cols[c] = "Tienda"
        elif "pedido" in clow: mapa_cols[c] = "Pedido"
        elif "nota" in clow or "nro" in clow: mapa_cols[c] = "Nota_Nro"
        elif "fch. modif" in clow or "fch_modif" in clow or "fecha modif" in clow: mapa_cols[c] = "Fecha_Modif"
        elif "fech" in clow and "modif" not in clow: mapa_cols[c] = "Fecha"
        elif "tipo" in clow or "motivo_rect" in clow: mapa_cols[c] = "Tipo"
        elif "cnt" in clow or "blt" in clow or "bulto" in clow or "cant" in clow: mapa_cols[c] = "Cant_Blt"
        elif "imp" in clow or "monto" in clow or "importe" in clow: mapa_cols[c] = "Monto"
        elif "estado rp" in clow: mapa_cols[c] = "Estado_RP"
        elif "estado" in clow: mapa_cols[c] = "Estado"
        elif "motivo" in clow or "causa" in clow: mapa_cols[c] = "Causa_Anulacion"
        elif "lote" in clow or "rpa" in clow: mapa_cols[c] = "Lote_RPA"

    df_portal = df_portal.rename(columns=mapa_cols)

    # Limpieza de tipos de datos
    if "Pedido" in df_portal.columns: df_portal["Pedido"] = df_portal["Pedido"].apply(normalizar_pedido)
    if "Tienda" in df_portal.columns: df_portal["Tienda"] = df_portal["Tienda"].apply(normalizar_pedido)
    if "Almacen" in df_portal.columns: df_portal["Almacen"] = df_portal["Almacen"].astype(str).str.strip()
    if "Monto" in df_portal.columns: df_portal["Monto"] = pd.to_numeric(df_portal["Monto"].astype(str).str.replace(",", "."), errors="coerce").fillna(0.0)
    if "Cant_Blt" in df_portal.columns: df_portal["Cant_Blt"] = pd.to_numeric(df_portal["Cant_Blt"].astype(str).str.replace(",", "."), errors="coerce").fillna(0.0)

    # Normalización del Estado
    if "Estado" in df_portal.columns:
        df_portal["Estado_Clean"] = df_portal["Estado"].astype(str).str.strip().str.capitalize()
    else:
        df_portal["Estado_Clean"] = "Anulada"

    # Guardar Parquet exclusivo para la Hoja 6 del Portal
    df_portal.to_parquet(PATH_PARQUET_ANUL, index=False)
    print(f"✓ Archivo Parquet generado para Hoja 6: {PATH_PARQUET_ANUL} ({len(df_portal):,} registros).")

print("==================================================================")
print("✨ PROCESAMIENTO COMPLETADO EXITOSAMENTE.")
print("==================================================================")
