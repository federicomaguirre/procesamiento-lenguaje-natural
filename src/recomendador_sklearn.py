#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Recomendador de libros basado en representaciones vectoriales con scikit-learn.
Utiliza TfidfVectorizer y similitud coseno sobre un texto enriquecido del catálogo
(título, autores, géneros, serie y sinopsis).
"""

import argparse
import ast
import os
import re
import sys
import unicodedata
from typing import List, Union

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Lista curada de palabras vacías (stopwords) en español
STOPWORDS_ES = {
    "a", "al", "algo", "algunas", "algunos", "ante", "antes", "aquel", "aquella",
    "aquellas", "aquellos", "aqui", "aquí", "asi", "así", "cada", "como", "con",
    "contra", "cual", "cuales", "cuando", "de", "del", "desde", "donde", "durante",
    "e", "el", "ella", "ellas", "ello", "ellos", "en", "entre", "era", "erais",
    "eran", "eras", "eres", "es", "esa", "esas", "ese", "eso", "esos", "esta",
    "estaba", "estabais", "estaban", "estabas", "estad", "estada", "estadas",
    "estado", "estados", "estais", "estamos", "estan", "estando", "estar",
    "estaremos", "estara", "estaran", "estaras", "estare", "estareis", "estaria",
    "estariais", "estariamos", "estarian", "estarias", "estas", "este", "estemos",
    "esto", "estos", "estoy", "estuve", "estuviera", "estuvierais", "estuvieran",
    "estuvieras", "estuvieron", "estuviese", "estuvieseis", "estuviesen",
    "estuvieses", "estuvimos", "estuviste", "estuvisteis", "estuvo", "fue",
    "fuera", "fuerais", "fueran", "fueras", "fueron", "fuese", "fueseis",
    "fuesen", "fueses", "fui", "fuimos", "fuiste", "fuisteis", "ha", "habeis",
    "haber", "habia", "habiais", "habiamo", "habian", "habias", "habida",
    "habidas", "habido", "habidos", "habiendo", "habra", "habran", "habras",
    "habre", "habreis", "habremos", "habria", "habriais", "habriamos", "habrian",
    "habrias", "hace", "haceis", "hacemos", "hacen", "hacer", "hacerlo", "haces",
    "hacia", "haciendo", "hago", "han", "has", "hasta", "hay", "haya", "hayais",
    "hayan", "hayas", "hayamos", "he", "hemos", "hube", "hubiera", "hubierais",
    "hubieran", "hubieras", "hubieron", "hubiese", "hubieseis", "hubiesen",
    "hubieses", "hubimos", "hubiste", "hubisteis", "hubo", "la", "las", "le",
    "les", "lo", "los", "mas", "más", "me", "mi", "mia", "mias", "mio", "mios",
    "mis", "mucho", "muchos", "muy", "nada", "ni", "no", "nos", "nosotras",
    "nosotros", "nuestra", "nuestras", "nuestro", "nuestros", "o", "os", "otra",
    "otras", "otro", "otros", "para", "pero", "poco", "por", "porque", "que",
    "quien", "quienes", "se", "sea", "seais", "seamos", "sean", "seas", "ser",
    "sere", "sereis", "seremos", "sera", "seran", "seras", "seria", "seriais",
    "seriamos", "serian", "serias", "si", "sí", "sido", "siendo", "sin", "sobre",
    "sois", "somos", "son", "soy", "su", "sus", "suya", "suyas", "suyo", "suyos",
    "tambien", "también", "tanto", "te", "tendra", "tendran", "tendras", "tendre",
    "tendreis", "tendremos", "tendria", "tendriais", "tendriamos", "tendrian",
    "tendrias", "tened", "teneis", "tenemos", "tenga", "tengais", "tengamos",
    "tengan", "tengas", "tengo", "tenia", "teniais", "teniamos", "tenian",
    "tenias", "tenida", "tenidas", "tenido", "tenidos", "teniendo", "tener",
    "ti", "tiene", "tienen", "tienes", "todo", "todos", "tu", "tus", "tuve",
    "tuviera", "tuvierais", "tuvieran", "tuvieras", "tuvieron", "tuviese",
    "tuvieseis", "tuviesen", "tuvieses", "tuvimos", "tuviste", "tuvisteis",
    "tuvo", "tuya", "tuyas", "tuyo", "tuyos", "un", "una", "uno", "unos", "unas",
    "vosotras", "vosotros", "vuestra", "vuestras", "vuestro", "vuestros", "y",
    "ya", "yo",
}


def normalizar_texto(texto: str) -> str:
    """
    Normaliza el texto a minúsculas y remueve acentos/diacríticos (NFKD).
    """
    if not isinstance(texto, str):
        texto = "" if pd.isna(texto) else str(texto)
    texto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


# Normalizamos las stopwords con la misma función para consistencia léxica
STOPWORDS_ES_NORM = {normalizar_texto(w) for w in STOPWORDS_ES}


def parsear_campo_lista(valor: Union[str, list]) -> List[str]:
    """
    Parsea campos multivaluados ('autores', 'generos') ya sea que provengan
    como listas nativas, literales serializados ('[\"A\", \"B\"]') o cadenas
    separadas por comas ('A, B').
    """
    if isinstance(valor, (list, tuple)):
        return [str(item).strip() for item in valor if str(item).strip()]
    if pd.isna(valor) or not str(valor).strip():
        return []

    texto = str(valor).strip()
    if (texto.startswith("[") and texto.endswith("]")) or (texto.startswith("(") and texto.endswith(")")):
        try:
            parsed = ast.literal_eval(texto)
            if isinstance(parsed, (list, tuple)):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except (ValueError, SyntaxError):
            pass

    return [item.strip() for item in texto.split(",") if item.strip()]


def construir_documento_enriquecido(fila: pd.Series) -> str:
    """
    Genera una representación textual unificada y enriquecida por cada libro,
    combinando título, autores, géneros, serie y sinopsis.
    """
    partes: List[str] = []

    # Título
    titulo = fila.get("titulo")
    if pd.notna(titulo) and str(titulo).strip():
        partes.append(str(titulo).strip())

    # Autores
    autores = fila.get("autores")
    if isinstance(autores, list):
        partes.extend(autores)
    elif pd.notna(autores) and str(autores).strip():
        partes.append(str(autores).strip())

    # Géneros
    generos = fila.get("generos")
    if isinstance(generos, list):
        partes.extend(generos)
    elif pd.notna(generos) and str(generos).strip():
        partes.append(str(generos).strip())

    # Serie (si aplica)
    serie = fila.get("serie")
    if pd.notna(serie):
        serie_str = str(serie).strip()
        if serie_str.lower() not in ("no aplica", "none", "", "nan"):
            partes.append(serie_str)

    # Sinopsis
    sinopsis = fila.get("sinopsis")
    if pd.notna(sinopsis) and str(sinopsis).strip():
        partes.append(str(sinopsis).strip())

    return " ".join(partes)


class RecomendadorSklearn:
    """
    Sistema de recomendación de libros basado en TfidfVectorizer y similitud coseno.
    """

    def __init__(self, csv_path: str = os.path.join("data", "libros.csv")):
        self.csv_path = csv_path
        self.df = self._cargar_dataset(csv_path)
        self.vectorizer = TfidfVectorizer(
            preprocessor=normalizar_texto,
            stop_words=list(STOPWORDS_ES_NORM),
            token_pattern=r"\b[a-z0-9ñ]{2,}\b",
            sublinear_tf=True,
        )
        self._ajustar_modelo()

    def _cargar_dataset(self, csv_path: str) -> pd.DataFrame:
        """Carga el dataset y asegura la presencia de campos clave."""
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"No se encontró el archivo de datos en: {csv_path}")

        df = pd.read_csv(csv_path, encoding="utf-8-sig")

        # Asignar un 'id' numérico secuencial si no existe
        if "id" not in df.columns:
            df.insert(0, "id", range(len(df)))

        # Normalizar listas en autores y generos
        for col in ("autores", "generos"):
            if col in df.columns:
                df[col] = df[col].apply(parsear_campo_lista)

        return df

    def _ajustar_modelo(self) -> None:
        """Genera el corpus enriquecido y ajusta la matriz TF-IDF."""
        corpus = [construir_documento_enriquecido(fila) for _, fila in self.df.iterrows()]
        self.tfidf_matrix = self.vectorizer.fit_transform(corpus)

    def recomendar(self, consulta: str, top_n: int = 5) -> pd.DataFrame:
        """
        Calcula la similitud coseno entre la consulta y todos los libros del catálogo.
        Retorna un DataFrame con los top_n libros más relevantes con similitud > 0.
        """
        if not consulta or not consulta.strip():
            return pd.DataFrame(columns=list(self.df.columns) + ["similitud"])

        # Vectorizar la consulta
        vector_consulta = self.vectorizer.transform([consulta])

        # Si no hubo términos en común con el vocabulario, la norma es 0
        if vector_consulta.nnz == 0:
            return pd.DataFrame(columns=list(self.df.columns) + ["similitud"])

        # Similitud coseno entre la consulta y la matriz de libros
        similitudes = cosine_similarity(vector_consulta, self.tfidf_matrix).flatten()

        # Filtrar solo aquellos con similitud positiva y ordenar descendente
        indices_positivos = [i for i, sim in enumerate(similitudes) if sim > 0]
        if not indices_positivos:
            return pd.DataFrame(columns=list(self.df.columns) + ["similitud"])

        indices_ordenados = sorted(indices_positivos, key=lambda i: similitudes[i], reverse=True)[:top_n]

        resultado = self.df.iloc[indices_ordenados].copy()
        resultado["similitud"] = similitudes[indices_ordenados]
        return resultado


def formatear_lista(valores: Union[List[str], str]) -> str:
    """Convierte una lista a cadena legible separada por comas."""
    if isinstance(valores, list):
        return ", ".join(valores)
    return "" if pd.isna(valores) else str(valores)


def truncar_texto(texto: str, max_longitud: int = 220) -> str:
    """Trunca el texto para previsualizaciones en consola."""
    if not texto or pd.isna(texto):
        return "Sinopsis no disponible."
    limpio = " ".join(str(texto).split())
    if len(limpio) <= max_longitud:
        return limpio
    return limpio[:max_longitud].rstrip() + "..."


def mostrar_resultados(consulta: str, resultados: pd.DataFrame) -> None:
    """Imprime las recomendaciones de manera estructurada y visual."""
    print("\n" + "=" * 70)
    print(f"📖 RESULTADOS PARA: \"{consulta.strip()}\"")
    print("=" * 70)

    if resultados.empty:
        print("\n❌ No se encontraron libros con coincidencias para esa búsqueda.")
        print("💡 Sugerencia: Probá con otras palabras clave, géneros, temas o autores.\n")
        return

    for rank, (_, libro) in enumerate(resultados.iterrows(), 1):
        autores = formatear_lista(libro["autores"])
        generos = formatear_lista(libro["generos"])
        similitud_pct = libro["similitud"] * 100
        sinopsis_resumen = truncar_texto(libro.get("sinopsis", ""))

        print(f"\n{rank}. 📕 {libro['titulo']} — {autores}")
        print(f"   ├─ Similitud: {similitud_pct:.1f}% (Score: {libro['similitud']:.4f}) | ID: {libro['id']}")
        print(f"   ├─ Géneros:   {generos}")
        if pd.notna(libro.get("serie")) and str(libro["serie"]).lower() not in ("no aplica", "none", "", "nan"):
            print(f"   ├─ Serie:     {libro['serie']}")
        print(f"   ├─ Sinopsis:  {sinopsis_resumen}")
        print(f"   └─ Enlace:    {libro.get('url_libro', 'N/A')}")

    print("\n" + "=" * 70 + "\n")


def modo_interactivo(recomendador: RecomendadorSklearn, top_n: int = 5) -> None:
    """Inicia una sesión interactiva en consola (bucle REPL)."""
    print("\n" + "*" * 70)
    print("  📚  SISTEMA DE RECOMENDACIÓN DE LIBROS (scikit-learn TF-IDF)")
    print("  Catálogo: Clásicos | UNR - Procesamiento del Lenguaje Natural")
    print("*" * 70)
    print("\nDescribí libremente qué libro te gustaría leer.")
    print("Podés ingresar temas, argumentos, géneros, o nombres de autores.")
    print("Escribí 'salir', 'exit' o 'q' para finalizar.\n")

    while True:
        try:
            consulta = input("🔍 ¿Qué te gustaría leer hoy?: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n👋 ¡Hasta luego! Buenas lecturas.")
            break

        if not consulta:
            continue

        if consulta.lower() in ("salir", "exit", "quit", "q"):
            print("\n👋 ¡Hasta luego! Buenas lecturas.")
            break

        resultados = recomendador.recomendar(consulta, top_n=top_n)
        mostrar_resultados(consulta, resultados)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recomendador de libros clásicos con scikit-learn (TF-IDF + Similitud Coseno)."
    )
    parser.add_argument(
        "--consulta", "-q",
        type=str,
        default=None,
        help="Texto de consulta (si se omite, se abre en modo interactivo)."
    )
    parser.add_argument(
        "--top", "-n",
        type=int,
        default=5,
        help="Cantidad máxima de recomendaciones a devolver (por defecto: 5)."
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=os.path.join("data", "libros.csv"),
        help="Ruta al archivo CSV con los libros (por defecto: data/libros.csv)."
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    try:
        recomendador = RecomendadorSklearn(csv_path=args.csv)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.consulta:
        resultados = recomendador.recomendar(args.consulta, top_n=args.top)
        mostrar_resultados(args.consulta, resultados)
    else:
        modo_interactivo(recomendador, top_n=args.top)


if __name__ == "__main__":
    main()
