# Proyecto de Extracción de Metadatos y Sinopsis - Categoría: Clásicos

Este repositorio contiene la entrega del trabajo práctico para la **Unidad 1 - Extracción y procesamiento de texto** de la asignatura **Procesamiento del Lenguaje Natural** (Facultad de Ciencias Exactas, Ingeniería y Agrimensura - UNR).

El objetivo principal de este proyecto es construir un corpus lingüístico estructurado a partir de libros clásicos disponibles de forma pública en Lectulandia, sentando las bases para futuros análisis de procesamiento de texto y sistemas de recomendación.

---

## 👥 Integrantes del Grupo
*   Franco Venesia
*   Marisa Zappala
*   Agustin Amarquardt
*   Federico Aguirre

---

## 📚 Descripción del Proyecto

*   **Categoría Seleccionada:** Clásico (`https://ww3.lectulandia.co/genero/clasico/`)
*   **Cantidad de libros extraídos:** 50 libros (de un universo total de aproximadamente 374 libros en la categoría).
*   **Criterio de Selección:** **Muestreo Aleatorio Simple (MAS)**. En lugar de extraer de forma secuencial (lo cual sesga los datos hacia las adiciones más recientes), el script recopila el listado completo de URLs disponibles en el catálogo y selecciona aleatoriamente 50 URLs únicas empleando la función `random.sample()` de Python. Posteriormente, visita cada una de ellas de manera asíncrona y controlada para extraer la ficha individual.

---

## 📁 Estructura del Repositorio

```text
├── README.md                 <-- Presentación del proyecto y guía de uso (este archivo)
├── requirements.txt         <-- Dependencias requeridas para el proyecto
├── extraction.log           <-- Archivo de log generado durante la ejecución (opcional)
├── data/
│   └── libros.csv           <-- Dataset estructurado obtenido con los 50 registros
├── docs/
│   └── diseno_extraccion.md <-- Documento de análisis previo y selectores HTML
└── src/
    ├── scraper.py           <-- Código fuente documentado del web scraper
    ├── procesar_datos.py    <-- Corrige el CSV: agrega `id` y convierte autores/generos a arrays
    └── recomendador.py      <-- Recomendador de libros (TF-IDF + similitud coseno)
```

---

## 📊 Metadata: Descripción de Variables del Dataset

El archivo `data/libros.csv` queda normalizado mediante `src/procesar_datos.py`, que agrega un identificador único por libro y convierte los campos multivaluados (`autores`, `generos`) en arrays. Las variables finales del dataset son:

| Variable | Tipo | Descripción |
| :--- | :--- | :--- |
| `id` | `int` | Identificador numérico único y secuencial del libro (0 a N-1), generado a partir del índice del DataFrame. |
| `titulo` | `str` | Título completo del libro. |
| `autores` | `list[str]` | Autor o autores del libro. Se almacena como array (`libros['autores'].str.split(',')`), permitiendo más de un autor por ficha. |
| `generos` | `list[str]` | Géneros asignados al libro. Se almacena como array (`libros['generos'].str.split(',')`), permitiendo múltiples géneros por ficha. |
| `serie` | `str` | Serie o saga a la que pertenece el libro. Vale `"No aplica"` cuando el libro es autoconclusivo. |
| `sinopsis` | `str` | Texto completo de la sinopsis o descripción del libro. |
| `url_libro` | `str` | URL absoluta de la ficha individual del libro en el sitio de origen. |
| `categoria_origen` | `str` | Categoría del catálogo desde la que se extrajo el libro (fijo: `Clásico`). |
| `fecha_extraccion` | `str` (ISO `YYYY-MM-DD HH:MM:SS`) | Fecha y hora en que se extrajo el registro. |
| `url_portada` | `str` | URL absoluta de la imagen de portada del libro. |

> **Nota sobre `autores` y `generos`:** al guardarse en CSV, los arrays se serializan como el literal de lista de Python (ej. `"['Charles Dickens', 'Wilkie Collins']"`). Para reconstruirlos como listas reales al leer el archivo, usar `ast.literal_eval` (tal como hace `src/recomendador.py` al cargar el dataset).

Para regenerar esta normalización sobre un CSV recién extraído con el scraper:
```bash
python src/procesar_datos.py --csv data/libros.csv
```

---

## ⚙️ Requisitos e Instalación

Este proyecto está desarrollado en **Python 3.12** y requiere el uso de librerías para la automatización del navegador (**Playwright**), el parseo del contenido web (**BeautifulSoup**) y el manejo estructurado de datos (**pandas**).

### 1. Clonar el repositorio
Asegúrate de clonar el repositorio e ingresar a la carpeta del proyecto:
```bash
git clone <url-de-tu-repositorio>
cd <nombre-de-la-carpeta>
```

### 2. Configurar el Entorno Virtual (Recomendado)
Es altamente aconsejable aislar las dependencias del sistema:
```bash
# En Linux/macOS
python3 -m venv venv
source venv/bin/activate

# En Windows
python -m venv venv
venv\Scripts\activate
```

### 3. Instalar Dependencias
Instala los paquetes necesarios definidos en `requirements.txt`:
```bash
pip install -r requirements.txt
```

### 4. Inicializar Navegadores de Playwright
Playwright requiere descargar binarios ligeros del navegador Chromium para su funcionamiento autónomo. Instálalos con el siguiente comando:
```bash
playwright install chromium
```

---

## 🚀 Instrucciones de Ejecución

El script del scraper (`src/scraper.py`) es altamente paramétrico y flexible. Puede configurarse directamente mediante argumentos de línea de comandos:

### Ejecución Estándar (Recomendado)
Para extraer los 50 libros de forma aleatoria y guardarlos de manera incremental en `data/libros.csv` ejecutándose en segundo plano (*headless*):
```bash
python src/scraper.py --limit 50
```

### Argumentos de Configuración Disponibles

| Argumento | Tipo | Valor por defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--limit` | `int` | `50` | Cantidad exacta de libros a extraer del catálogo. |
| `--output` | `str` | `data/libros.csv` | Ruta del archivo CSV donde se guardarán los resultados. |
| `--seed` | `int` | `42` | Semilla aleatoria utilizada para garantizar la reproducibilidad del muestreo. |
| `--headless` | `bool`| `True` | Define si el navegador Chromium se ejecuta oculto (`True`) o visible (`False`). |

*Ejemplo de ejecución personalizada:*
```bash
# Extraer 75 libros con una semilla de aleatoriedad específica y mostrando el navegador de forma interactiva:
python src/scraper.py --limit 75 --seed 1234 --headless False
```

---

## 🛠️ Principales Dificultades Encontradas y Soluciones

Durante el diseño y desarrollo de la herramienta de extracción se presentaron varios desafíos técnicos que fueron resueltos con criterios de ingeniería de software:

1.  **Detección y Bloqueo de Servidores (Anti-Scraping):**
    *   *Problema:* Los servidores de Lectulandia emplean firewalls y sistemas de protección que bloquean peticiones HTTP masivas y repetitivas que se identifican como bots.
    *   *Solución:* Implementamos **Playwright** en lugar de peticiones planas de `requests`. Esto permite emular un motor de renderizado web real, configurando un *User-Agent* común y moderno, y estableciendo pausas de cortesía variables (`random.uniform(1.5, 3.5)`) entre cada petición para emular el patrón de un lector humano.
2.  **Mantenimiento del Criterio de Selección Aleatoria (MAS):**
    *   *Problema:* No es posible realizar un muestreo aleatorio directo en el servidor sin descargar primero el índice de libros. Descargar las fichas completas de todos los libros para luego elegir 50 sería sumamente ineficiente y agresivo con el sitio web.
    *   *Solución:* Dividimos el proceso en dos fases sumamente optimizadas. En la **Fase 1** recorremos únicamente la paginación del índice para capturar las URLs de los libros (un proceso sumamente rápido y de bajo costo de red). En la **Fase 2** aplicamos el muestreo aleatorio sobre el conjunto de URLs recopiladas en la memoria local y procedemos a descargar únicamente las 50 fichas seleccionadas.
3.  **Inconsistencia en los Datos de las Fichas:**
    *   *Problema:* No todos los libros de Lectulandia cuentan con los mismos campos de metadatos de forma estricta (por ejemplo, libros autoconclusivos sin campo de "serie/saga", o fichas con sinopsis vacías o múltiples autores enlazados).
    *   *Solución:* Diseñamos selectores CSS tolerantes a fallos utilizando búsquedas parciales de patrones semánticos en las URLs (por ejemplo, buscar enlaces que contengan `/autor/`, `/genero/` o `/serie/`). Además, cada campo se extrajo empleando estructuras `try-except` de Python para asegurar la robustez, normalizando los campos ausentes consistentemente con el valor `"No aplica"`.
4.  **Pérdida de Información por Interrupciones de Red:**
    *   *Problema:* Si la conexión a Internet falla en la ficha 45 de 50, se perdería todo el trabajo de raspado si los datos estuvieran almacenados únicamente en memoria.
    *   *Solución:* Implementamos un **esquema de guardado incremental directo en disco (CSV)**. Cada vez que el scraper procesa exitosamente una ficha, la información se anexa de inmediato en el archivo final. Al finalizar la ejecución completa, el script realiza un control de calidad post-procesamiento con pandas para eliminar duplicados y asegurar que el CSV esté impecable.

---

## 📋 Controles de Calidad Realizados

Antes de la entrega final, se validó la integridad del archivo resultante (`data/libros.csv`) verificando el cumplimiento de las directrices del trabajo práctico:
*   [x] **Sin duplicados:** Se verificó que todas las filas tengan una `url_libro` única utilizando `drop_duplicates()`.
*   [x] **Integridad:** El 100% de los registros cuenta con un título válido.
*   [x] **Presencia de Sinopsis:** La totalidad de las fichas seleccionadas cuenta con una sinopsis extensa de contenido descriptivo limpio.
*   [x] **Formato unificado:** Se limpiaron todos los espacios dobles, tabuladores y saltos de línea innecesarios en las sinopsis y títulos para un almacenamiento tabular óptimo.
*   [x] **Muestreo:** El archivo final contiene exactamente los 50 libros requeridos de la categoría "Clásico".
