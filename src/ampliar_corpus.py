#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Amplía data/libros.csv con libros nuevos de la misma categoría (Clásico).

La consigna del TP2 pide un corpus de 100 a 200 libros y el del TP1 quedó en 99
(una de las 100 filas era la URL del listado general y se descartó). Este script:
- Recopila el catálogo completo con las mismas funciones de scraper.py.
- Excluye las URLs que ya están en el CSV.
- Elige al azar (semilla fija) los libros que faltan y extrae sus fichas.
- Los agrega AL FINAL con ids correlativos, sin tocar los ids existentes
  (queries.json referencia libros por id).
"""

import argparse
import os
import random
import sys

import pandas as pd
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scraper import (  # noqa: E402
    cargar_robots_txt,
    extract_book_urls,
    init_playwright,
    logger,
    scrape_book_details,
)


def parse_arguments():
    parser = argparse.ArgumentParser(description="Agrega libros nuevos al final de data/libros.csv.")
    parser.add_argument("--csv", type=str, default=os.path.join("data", "libros.csv"))
    parser.add_argument("--total", type=int, default=120,
                        help="Cantidad total de libros a alcanzar. Por defecto 120.")
    parser.add_argument("--seed", type=int, default=2026)
    return parser.parse_args()


def es_valido(libro):
    return (
        libro is not None
        and libro["titulo"] != "Sin título"
        and libro["autores"] != "Autor no especificado"
        and libro["sinopsis"] != "Sin sinopsis"
    )


def main():
    args = parse_arguments()
    random.seed(args.seed)

    df = pd.read_csv(args.csv, encoding="utf-8-sig")
    faltan = args.total - len(df)
    if faltan <= 0:
        print(f"El corpus ya tiene {len(df)} libros. No hay nada que agregar.")
        return

    base_url = "https://ww3.lectulandia.co/genero/clasico/"
    robots = cargar_robots_txt(base_url)
    existentes = set(df["url_libro"])
    nuevos = []

    with sync_playwright() as p:
        browser, context = init_playwright(p, headless=True)
        try:
            candidatas = [u for u in extract_book_urls(context, base_url, robots) if u not in existentes]
            random.shuffle(candidatas)
            for url in candidatas:
                if len(nuevos) == faltan:
                    break
                libro = scrape_book_details(context, url, "Clásico", robots)
                # Mismo problema que en el TP1: algunas fichas vuelven sin título/autor
                # en la primera carga. Se reintenta una vez antes de descartar.
                if not es_valido(libro):
                    libro = scrape_book_details(context, url, "Clásico", robots)
                if es_valido(libro):
                    nuevos.append(libro)
                else:
                    logger.warning(f"Ficha incompleta, se descarta: {url}")
        finally:
            browser.close()

    nuevos_df = pd.DataFrame(nuevos)
    for columna in ("autores", "generos"):
        nuevos_df[columna] = nuevos_df[columna].str.split(",").apply(lambda v: [x.strip() for x in v])
    nuevos_df.insert(0, "id", range(int(df["id"].max()) + 1, int(df["id"].max()) + 1 + len(nuevos_df)))

    final = pd.concat([df, nuevos_df[df.columns]], ignore_index=True)
    final.to_csv(args.csv, index=False, encoding="utf-8-sig")
    print(f"Se agregaron {len(nuevos_df)} libros. Total: {len(final)}.")


if __name__ == "__main__":
    main()
