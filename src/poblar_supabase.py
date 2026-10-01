#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Crea el esquema de schema_pgvector.sql y carga los embeddings del TP2 en Postgres/Supabase.

Usa los vectores que el notebook guarda en embeddings/ (no los recalcula), así lo
que queda en la base es exactamente lo que se evaluó.
- libros_sbw   <- embeddings/sbw_promedio_300.npy   (promedio de word vectors SBW)
- libros_sbert <- embeddings/sbert_distiluse_512.npy (modelo de oración)

Las credenciales se leen de la variable de entorno SUPABASE_DB_URL (o de un .env),
nunca del código. Uso:
    python src/poblar_supabase.py
"""

import ast
import getpass
import os

import numpy as np
import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TABLAS = {
    "libros_sbw": ("sbw_promedio_300.npy", 300),
    "libros_sbert": ("sbert_distiluse_512.npy", 512),
}


def obtener_db_url():
    """Busca la connection string en el entorno, en .env o en los secretos de Colab."""
    url = os.getenv("SUPABASE_DB_URL")
    if not url:
        try:
            from dotenv import load_dotenv
            load_dotenv(os.path.join(RAIZ, ".env"))
            url = os.getenv("SUPABASE_DB_URL")
        except ImportError:
            pass
    if not url:
        try:
            from google.colab import userdata
            url = userdata.get("SUPABASE_DB_URL")
        except Exception:
            pass
    if not url:
        url = getpass.getpass("Connection string de Supabase (no se muestra): ")
    return url.strip()


def conectar(url):
    import psycopg2
    from pgvector.psycopg2 import register_vector

    try:
        conn = psycopg2.connect(url)
    except psycopg2.OperationalError:
        # No se re-lanza el error original: su mensaje puede incluir host y usuario
        raise RuntimeError("No se pudo conectar a la base. Revisar SUPABASE_DB_URL.") from None
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    register_vector(conn)
    return conn


def aplicar_esquema(conn, ruta=os.path.join(RAIZ, "schema_pgvector.sql")):
    with open(ruta, encoding="utf-8") as f, conn.cursor() as cur:
        cur.execute(f.read())


def sanear(X, dim):
    """
    Devuelve (vectores normalizados, máscara de válidos).
    Un vector se descarta si tiene otra dimensión, algún NaN/inf o norma 0
    (p. ej. un libro sin ninguna palabra en el vocabulario de SBW).
    """
    X = np.asarray(X, dtype=np.float64)
    if X.ndim != 2 or X.shape[1] != dim:
        raise ValueError(f"Se esperaban vectores de dimensión {dim} y llegó {X.shape}")
    normas = np.linalg.norm(X, axis=1)
    validos = np.isfinite(X).all(axis=1) & np.isfinite(normas) & (normas > 0)
    Xn = np.zeros_like(X)
    Xn[validos] = X[validos] / normas[validos, None]
    return Xn.astype(np.float32), validos


def insertar_embeddings(conn, tabla, df, X, dim):
    """Inserta los libros con vector válido. Devuelve (insertados, ids descartados)."""
    from psycopg2.extras import execute_values

    Xn, validos = sanear(X, dim)
    filas = []
    for (_, r), v, ok in zip(df.iterrows(), Xn, validos):
        if not ok:
            continue
        serie = None if pd.isna(r["serie"]) or r["serie"] == "No aplica" else str(r["serie"])
        filas.append((int(r["id"]), r["titulo"], list(r["autores"]), list(r["generos"]),
                      serie, r["sinopsis"], r["url_libro"], v))
    with conn.cursor() as cur:
        execute_values(cur, f"""
            INSERT INTO {tabla} (id, titulo, autores, generos, serie, sinopsis, url_libro, embedding)
            VALUES %s
        """, filas)
    descartados = df.loc[~validos, "id"].tolist()
    return len(filas), descartados


def cargar_libros(ruta=os.path.join(RAIZ, "data", "libros.csv")):
    df = pd.read_csv(ruta, encoding="utf-8-sig")
    for col in ("autores", "generos"):
        df[col] = df[col].apply(ast.literal_eval)
    return df


def main():
    df = cargar_libros()
    ids = np.load(os.path.join(RAIZ, "embeddings", "ids.npy"))
    if not np.array_equal(ids, df["id"].to_numpy()):
        raise SystemExit("embeddings/ids.npy no coincide con data/libros.csv. Re-ejecutar el notebook.")

    conn = conectar(obtener_db_url())
    aplicar_esquema(conn)
    print("Esquema aplicado (tablas, índices HNSW y funciones).")

    for tabla, (archivo, dim) in TABLAS.items():
        X = np.load(os.path.join(RAIZ, "embeddings", archivo))
        n, descartados = insertar_embeddings(conn, tabla, df, X, dim)
        print(f"{tabla}: {n} libros insertados, descartados por vector inválido: {descartados or 'ninguno'}")

    conn.close()


if __name__ == "__main__":
    main()
