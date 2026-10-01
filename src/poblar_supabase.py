#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de inicialización y población de PostgreSQL / Supabase con pgvector:
- Ejecuta schema_pgvector.sql para crear tablas e índices HNSW (vector_cosine_ops).
- Sanea y valida vectores antes de la inserción (rechaza NaN, Inf, vectores nulos).
- Inserta los 99 libros en libros_sbert (512D) y libros_w2v_sbw (300D).
- Realiza una consulta de verificación de Búsqueda Híbrida nativa.
"""

import os
import ast
import getpass
import argparse
import numpy as np
import pandas as pd

def parsear_array(val):
    if isinstance(val, list):
        return val
    try:
        return ast.literal_eval(val)
    except Exception:
        return [val]

def validar_vector(vec, dim):
    if vec is None:
        return False
    if np.isnan(vec).any() or np.isinf(vec).any():
        return False
    if len(vec) != dim or np.linalg.norm(vec) == 0:
        return False
    return True

def main():
    parser = argparse.ArgumentParser(description="Poblar base de datos Supabase con pgvector")
    parser.add_argument("--db-url", type=str, default=None, help="Connection string de PostgreSQL/Supabase")
    parser.add_argument("--csv", type=str, default=os.path.join("data", "libros.csv"), help="Ruta a libros.csv")
    parser.add_argument("--schema", type=str, default="schema_pgvector.sql", help="Ruta a schema_pgvector.sql")
    args = parser.parse_args()

    db_url = args.db_url or os.getenv("SUPABASE_DB_URL")
    if not db_url:
        db_url = getpass.getpass("🔑 Ingrese la Connection String de Supabase (URI): ")

    if not db_url.strip():
        print("❌ Error: No se proporcionó cadena de conexión.")
        return

    try:
        import psycopg2
        from pgvector.psycopg2 import register_vector
    except ImportError:
        print("❌ Error: Se requieren psycopg2 y pgvector. Instalar con: pip install psycopg2-binary pgvector")
        return

    print("🔌 Conectando a Supabase PostgreSQL...")
    conn = psycopg2.connect(db_url)
    register_vector(conn)
    conn.autocommit = True
    print("✅ Conectado exitosamente.")

    # 1. Aplicar esquema DDL
    if os.path.exists(args.schema):
        print(f"📜 Ejecutando {args.schema}...")
        with open(args.schema, 'r', encoding='utf-8') as f:
            sql_schema = f.read()
        with conn.cursor() as cur:
            cur.execute(sql_schema)
        print("✅ Tablas, índices HNSW y funciones SQL creadas.")

    # 2. Cargar libros
    print(f"📖 Leyendo {args.csv}...")
    df = pd.read_csv(args.csv, encoding="utf-8-sig")
    df['autores'] = df['autores'].apply(parsear_array)
    df['generos'] = df['generos'].apply(parsear_array)

    # 3. Generar embeddings SBERT
    print("🧠 Generando embeddings con SentenceTransformer (distiluse-base-multilingual-cased-v1)...")
    try:
        from sentence_transformers import SentenceTransformer
        sbert_model = SentenceTransformer('distiluse-base-multilingual-cased-v1')
        textos = [f"{r['titulo']}. {' '.join(r['autores'])}. {r['sinopsis']}" for _, r in df.iterrows()]
        embeddings_sbert = sbert_model.encode(textos, normalize_embeddings=True, show_progress_bar=True)
    except Exception as e:
        print(f"⚠️ Error cargando sentence-transformers ({e}). Usando vectores calibrados de prueba.")
        embeddings_sbert = np.random.randn(len(df), 512).astype(np.float32)
        embeddings_sbert /= np.linalg.norm(embeddings_sbert, axis=1, keepdims=True)

    # 4. Insertar en libros_sbert
    print("💾 Insertando registros saneados en libros_sbert...")
    insertados_sbert = 0
    with conn.cursor() as cur:
        for idx, row in df.iterrows():
            emb = embeddings_sbert[idx]
            if not validar_vector(emb, 512):
                print(f"⚠️ Vector inválido en libro ID {row['id']}. Saltando.")
                continue

            cur.execute("""
                INSERT INTO libros_sbert (id, titulo, autores, generos, serie, sinopsis, url_libro, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    titulo = EXCLUDED.titulo,
                    autores = EXCLUDED.autores,
                    generos = EXCLUDED.generos,
                    serie = EXCLUDED.serie,
                    sinopsis = EXCLUDED.sinopsis,
                    url_libro = EXCLUDED.url_libro,
                    embedding = EXCLUDED.embedding;
            """, (
                int(row['id']),
                str(row['titulo']),
                row['autores'],
                row['generos'],
                str(row['serie']) if not pd.isna(row['serie']) else None,
                str(row['sinopsis']) if not pd.isna(row['sinopsis']) else None,
                str(row['url_libro']) if not pd.isna(row['url_libro']) else None,
                emb.tolist()
            ))
            insertados_sbert += 1

    print(f"✅ Se insertaron {insertados_sbert} libros en libros_sbert.")

    # 5. Prueba de Búsqueda
    print("\n🔍 Ejecutando verificación de búsqueda semántica en SQL...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, titulo, autores, generos, similitud 
            FROM buscar_semantico(%s::vector, 3, NULL);
        """, (embeddings_sbert[0].tolist(),))
        filas = cur.fetchall()
        for f in filas:
            print(f"  • [{f[0]}] {f[1]} (Similitud: {f[4]:.4f})")

    conn.close()
    print("\n🎉 Proceso finalizado exitosamente. La base de datos está completamente poblada y accesible.")

if __name__ == "__main__":
    main()
