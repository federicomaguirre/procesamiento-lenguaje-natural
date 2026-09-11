#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de corrección/normalización de data/libros.csv:
- Genera un id numérico único por libro (índice secuencial).
- Convierte las columnas 'autores' y 'generos' de texto separado por comas a arrays.
"""

import argparse
import os

import pandas as pd


def normalizar_dataset(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reset_index(drop=True)
    df.insert(0, "id", df.index)

    for columna in ("autores", "generos"):
        df[columna] = df[columna].str.split(",").apply(
            lambda valores: [v.strip() for v in valores]
        )

    return df


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Agrega 'id' y convierte 'autores'/'generos' a arrays en data/libros.csv."
    )
    parser.add_argument("--csv", type=str, default=os.path.join("data", "libros.csv"),
                         help="Ruta al dataset de libros a corregir (se sobrescribe).")
    return parser.parse_args()


def main():
    args = parse_arguments()

    df = pd.read_csv(args.csv, encoding="utf-8-sig")
    df = normalizar_dataset(df)
    df.to_csv(args.csv, index=False, encoding="utf-8-sig")

    print(f"Dataset actualizado: {len(df)} libros con id (0..{len(df) - 1}).")
    print("Columnas 'autores' y 'generos' convertidas a arrays.")


if __name__ == "__main__":
    main()
