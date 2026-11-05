# TP3 · Recomendador personalizado de libros

Procesamiento del Lenguaje Natural · TUIA · FCEIA · UNR

Integrantes: Franco Venesia, Marisa Zappala, Agustín Marquardt, Federico Aguirre

Todo el trabajo se hizo en un único notebook de Google Colab, `TP3_marquardt_aguirre_venesia_zappala.ipynb`. Los commits de esta carpeta siguen cómo avanzó ese notebook, paso por paso de la consigna.

## Archivos

| Archivo | Contenido |
|---|---|
| `data/catalogo_tp3.jsonl`, `data/muestra_etiquetada.csv` | Datos entregados por la cátedra |
| `TP3_marquardt_aguirre_venesia_zappala.ipynb` | Notebook ejecutado, organizado en los ocho pasos de la consigna |
| `grupo_marquardt_aguirre_venesia_zappala_sospechosos.csv` | 423 libros marcados en la auditoría (paso 2), con las columnas `slug` y `motivo` |
| `grupo_marquardt_aguirre_venesia_zappala_preferencias.csv` | 150 libros recorridos por el lector: 111 valorados (`interes` 1 o 0), 39 abstenciones y la columna `conjunto` |
| `informe.pdf` | Respuestas a las cinco preguntas de la consigna |

## Cómo ejecutar el notebook

El notebook está pensado para Google Colab. Antes de ejecutarlo hay que subir a `/content/` los dos archivos de `data/`. El paso 3 lee las valoraciones del lector desde `preferencias.csv`: alcanza con subir el CSV de preferencias de esta carpeta con ese nombre.

## Valores en `motivo`

| Motivo | Detector |
|---|---|
| `regex` | Expresión regular de URLs, correos y teléfonos sobre el texto normalizado |
| `copia` | Sinopsis copiada de otro libro del catálogo con autor distinto |
| `clasificadores` | Coinciden el clasificador de oraciones TF-IDF y el de embeddings |
| `tfidf_alto` / `embeddings_alto` | Un solo clasificador con probabilidad de alta confianza |
| `muestra_etiquetada` | Libro contaminado según la muestra de la cátedra que ningún detector marcó |

Cuando un libro fue marcado por varios detectores, los motivos aparecen unidos con `+`.
