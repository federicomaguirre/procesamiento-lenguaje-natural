#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Recomendador de libros basado en un algoritmo frecuentista (TF-IDF + similitud coseno).
Conecta con el dataset generado por scraper.py (data/libros.csv).
"""

import ast
import os
import re
import argparse
import unicodedata

import numpy as np
import pandas as pd

STOPWORDS_ES = {
    "a", "al", "algo", "algunas", "algunos", "ante", "antes", "como", "con", "contra",
    "cual", "cuando", "de", "del", "desde", "donde", "durante", "e", "el", "ella",
    "ellas", "ellos", "en", "entre", "era", "eran", "es", "esa", "esas", "ese", "esos",
    "esta", "estas", "este", "esto", "estos", "fue", "fueron", "ha", "hasta", "hay",
    "la", "las", "le", "les", "lo", "los", "más", "mas", "me", "mi", "mis", "mucho",
    "muchos", "muy", "nada", "ni", "no", "nos", "nosotros", "o", "os", "otra", "otras",
    "otro", "otros", "para", "pero", "poco", "por", "porque", "que", "quien", "se",
    "sin", "sobre", "son", "su", "sus", "tambien", "también", "te", "tiene", "tienen",
    "todo", "todos", "tu", "tus", "un", "una", "uno", "unos", "y", "ya", "yo",
}

TEXT_COLUMNS = ["titulo", "autores", "generos", "serie", "sinopsis"]
ARRAY_COLUMNS = ("autores", "generos")


def parsear_array(valor):
    """Convierte el literal de lista guardado en el CSV (ej. "['A', 'B']") a list."""
    if isinstance(valor, list):
        return valor
    try:
        return ast.literal_eval(valor)
    except (ValueError, SyntaxError):
        return [valor]


def texto_de_campo(valor):
    """Aplana listas (autores/generos) a texto plano para armar el corpus."""
    if isinstance(valor, list):
        return " ".join(valor)
    return "" if pd.isna(valor) else str(valor)


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto).lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto


def tokenizar(texto):
    tokens = re.findall(r"[a-záéíóúñ]+", normalizar(texto))
    return [t for t in tokens if t not in STOPWORDS_ES and len(t) > 1]


def construir_corpus(df):
    filas = (
        " ".join(texto_de_campo(valor) for valor in fila)
        for fila in df[TEXT_COLUMNS].itertuples(index=False)
    )
    return [tokenizar(texto) for texto in filas]


def calcular_tf(tokens, vocabulario):
    vector = np.zeros(len(vocabulario))
    for token in tokens:
        idx = vocabulario.get(token)
        if idx is not None:
            vector[idx] += 1
    total = vector.sum()
    return vector / total if total > 0 else vector


def calcular_idf(corpus_tokens, vocabulario):
    n_docs = len(corpus_tokens)
    idf = np.zeros(len(vocabulario))
    for tokens in corpus_tokens:
        for token in set(tokens):
            idx = vocabulario.get(token)
            if idx is not None:
                idf[idx] += 1
    # IDF suavizado para evitar división por cero con términos que no aparezcan
    return np.log((n_docs + 1) / (idf + 1)) + 1


class RecomendadorTFIDF:
    def __init__(self, csv_path):
        self.df = pd.read_csv(
            csv_path,
            encoding="utf-8-sig",
            converters={columna: parsear_array for columna in ARRAY_COLUMNS},
        )
        corpus_tokens = construir_corpus(self.df)

        vocab_ordenado = sorted({token for tokens in corpus_tokens for token in tokens})
        self.vocabulario = {token: i for i, token in enumerate(vocab_ordenado)}

        self.idf = calcular_idf(corpus_tokens, self.vocabulario)
        tf_matrix = np.array([calcular_tf(tokens, self.vocabulario) for tokens in corpus_tokens])
        self.tfidf_matrix = tf_matrix * self.idf

        normas = np.linalg.norm(self.tfidf_matrix, axis=1)
        self.normas = np.where(normas == 0, 1, normas)

    def vectorizar_consulta(self, texto):
        tokens = tokenizar(texto)
        tf = calcular_tf(tokens, self.vocabulario)
        return tf * self.idf

    def recomendar(self, consulta, top_n=5):
        vector_consulta = self.vectorizar_consulta(consulta)
        norma_consulta = np.linalg.norm(vector_consulta)
        if norma_consulta == 0:
            return pd.DataFrame(columns=list(self.df.columns) + ["similitud"])

        similitudes = (self.tfidf_matrix @ vector_consulta) / (self.normas * norma_consulta)

        top_indices = np.argsort(similitudes)[::-1][:top_n]
        resultado = self.df.iloc[top_indices].copy()
        resultado["similitud"] = similitudes[top_indices]
        return resultado[resultado["similitud"] > 0]


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Recomendador de libros por coincidencia frecuentista de palabras (TF-IDF)."
    )
    parser.add_argument("consulta", nargs="?", default=None, help="Texto de búsqueda o interés del usuario.")
    parser.add_argument("--csv", type=str, default=os.path.join("data", "libros.csv"), help="Ruta al dataset de libros.")
    parser.add_argument("--top", type=int, default=5, help="Cantidad de recomendaciones a mostrar.")
    return parser.parse_args()


def main():
    args = parse_arguments()
    recomendador = RecomendadorTFIDF(args.csv)

    consulta = args.consulta or input("¿Qué tipo de libro estás buscando?: ")

    resultados = recomendador.recomendar(consulta, top_n=args.top)

    if resultados.empty:
        print("No se encontraron libros relacionados con esa búsqueda.")
        return

    print(f"\nRecomendaciones para: \"{consulta}\"\n")
    for rank, (_, libro) in enumerate(resultados.iterrows(), 1):
        autores = texto_de_campo(libro["autores"])
        generos = texto_de_campo(libro["generos"])
        print(f"{rank}. [ID {libro['id']}] {libro['titulo']} — {autores} (similitud: {libro['similitud']:.3f})")
        print(f"   Géneros: {generos}")
        print(f"   {libro['url_libro']}\n")


if __name__ == "__main__":
    main()
