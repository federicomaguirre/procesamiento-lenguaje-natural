# Diseño del Sistema de Recomendación de Libros (scikit-learn)

Este documento registra formalmente las especificaciones técnicas y decisiones de diseño acordadas para el módulo de recomendación de libros en base a similitud semántica y vectorial sobre el dataset `data/libros.csv`.

---

## 1. Contexto del Proyecto

El sistema forma parte del proyecto de **Procesamiento del Lenguaje Natural** (UNR). Tras la fase de extracción y curaduría del corpus de libros clásicos (`data/libros.csv`), se requiere un mecanismo que permita a los usuarios expresar libremente en lenguaje natural qué desean leer y recibir las obras más afines disponibles en el catálogo.

---

## 2. Registro de Decisiones de Diseño

### Decisión 1: Modelo de Representación Vectorial
* **Opción seleccionada:** **TF-IDF (`TfidfVectorizer` de `scikit-learn`) + Similitud Coseno (`cosine_similarity`)**.
* **Justificación técnica:**
  * El modelo TF-IDF (*Term Frequency - Inverse Document Frequency*) equilibra la frecuencia local de un término en la descripción de una obra con su rareza global en el catálogo, atenuando términos genéricos y destacando conceptos temáticos distintivos (ej. "vampiro", "satélite", "crimen").
  * La similitud coseno mide el ángulo entre los vectores normalizados de la consulta y de cada libro en el espacio euclidiano, resultando invariante a diferencias de longitud entre descripciones cortas y extensas.
  * Se incorpora un preprocesamiento lingüístico en español: normalización Unicode (NFKD sin tildes), minúsculas y remoción de *stopwords* en español.
* **Alternativas evaluadas y descartadas:**
  * *CountVectorizer (Bolsa de palabras simple):* No pondera la discriminación léxica de las palabras, sobre-representando vocablos comunes.
  * *Embeddings densos / Transformers:* Se reserva para etapas posteriores de PLN profundo; para este alcance, `scikit-learn` provee la solución estándar, ligera y sin sobrecarga de dependencias pesadas.

---

### Decisión 2: Estructura del Código y Dependencias
* **Opción seleccionada:** **Creación de un nuevo script `src/recomendador_sklearn.py`**.
* **Justificación técnica:**
  * Se preserva el archivo previo `src/recomendador.py` (que contiene una implementación artesanal de TF-IDF en NumPy puro), permitiendo contrastar la implementación manual con el estándar de la industria.
  * Se añade formalmente `scikit-learn>=1.3.0` al archivo `requirements.txt` del entorno.
  * El nuevo script se diseñará con una clase modular reutilizable (`RecomendadorSklearn`) con métodos claros para carga, ajuste/vectorización y recomendación.

---

### Decisión 3: Construcción del Corpus (Texto Enriquecido)
* **Opción seleccionada:** **Concatenación de campos clave (`titulo`, `autores`, `generos`, `serie`, `sinopsis`)**.
* **Justificación técnica:**
  * Los usuarios pueden buscar tanto por temática o argumento ("viaje al espacio", "misterio de asesinatos") como por autores ("Julio Verne", "Edgar Allan Poe") o géneros específicos ("Terror", "Histórico").
  * La concatenación de todos los campos descriptivos de la obra en una única cadena enriquecida (*rich document string*) asegura que el vocabulario abarque todas estas dimensiones de consulta en un único espacio vectorial.
  * Se garantiza el parseo correcto de arrays serializados en el CSV (columnas `autores` y `generos`).

---

### Decisión 4: Interfaz de Usuario y Experiencia (Soporte Dual)
* **Opción seleccionada:** **Script con interfaz dual (CLI con `argparse` y Modo Interactivo)**.
* **Justificación técnica:**
  * **Modo Argumento CLI:** Permite llamadas directas por consola o integración en tuberías de scripts (ej. `python src/recomendador_sklearn.py --consulta "novela de aventuras" --top 5`).
  * **Modo Interactivo:** Si el script se ejecuta sin la bandera de consulta (`python src/recomendador_sklearn.py`), inicia un bucle de terminal con prompt interactivo amigable (`input()`) que permite hacer consultas continuas hasta que el usuario decida salir (`salir`, `exit`, `q`).
  * **Formato de Salida:** Muestra un ranking ordenado indicando posición, puntaje de similitud porcentual, ID, título, autor/es, género/s y un extracto limpio de la sinopsis con enlace directo a la obra.
