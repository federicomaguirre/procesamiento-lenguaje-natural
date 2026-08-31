# Diseño de la Extracción de Datos - Categoría: Clásicos

Este documento describe la planificación previa al desarrollo del web scraper para la **Unidad 1 - Extracción y procesamiento de texto** del curso de Procesamiento del Lenguaje Natural. 

---

## 1. Categoría Seleccionada y Criterios

*   **Nombre de la categoría:** Clásico
*   **URL de la categoría:** `https://ww3.lectulandia.co/genero/clasico/`
*   **Cantidad de libros a extraer:** 50 libros (de un universo aproximado de 374 libros totales en esta categoría).
*   **Criterio de selección de páginas y libros:** 
    *   **Muestreo Aleatorio Simple (MAS):** En lugar de extraer los primeros 50 libros secuencialmente, lo cual sesgaría el corpus hacia los libros agregados recientemente, implementaremos una estrategia de selección aleatoria sobre toda la población de la categoría.
    *   **Procedimiento:** 
        1.  El scraper navegará por las páginas de paginación de la categoría `https://ww3.lectulandia.co/genero/clasico/page/N/` para recopilar todas las URLs de libros del catálogo (universo completo de ~374 enlaces).
        2.  Una vez obtenido el listado completo de enlaces, se aplicará una selección aleatoria sin reemplazo mediante la función `random.sample()` de Python para quedarnos con un subconjunto exacto de **50 URLs**.
        3.  El scraper procederá a visitar únicamente esas 50 fichas individuales seleccionadas al azar para realizar la extracción detallada. Esto garantiza representatividad de toda la línea de tiempo de la categoría.

---

## 2. Datos a Extraer (Esquema del Dataset)

El dataset final se estructurará en formato tabular y se guardará como un archivo CSV (`libros.csv`) con los siguientes campos:

| Campo | Tipo | Descripción | Obligatorio |
| :--- | :--- | :--- | :--- |
| `titulo` | Texto | El título completo del libro. | Sí |
| `autores` | Texto | Nombre del autor o autores (enlazados por coma si hay más de uno). | Sí |
| `generos` | Texto | Géneros asignados en la ficha (separados por comas). | Sí |
| `serie` | Texto | Serie o saga a la que pertenece y su número de orden (ej. *Biblioteca Clásica Gredos - 13*). Si no pertenece a ninguna, se registrará "No aplica". | No (opcional) |
| `sinopsis` | Texto | El texto completo de la sinopsis o descripción del libro. | Sí |
| `url_libro` | Texto | URL absoluta de la ficha individual del libro. | Sí |
| `categoria_origen`| Texto | Categoría desde la que se inició la extracción (fijo: `Clásico`). | Sí |
| `fecha_extraccion`| Texto (ISO) | Fecha y hora en formato `YYYY-MM-DD HH:MM:SS` en que se extrajo el registro. | Sí |
| `url_portada` | Texto | Enlace absoluto a la imagen de portada del libro. | No (opcional) |

---

## 3. Localización de los Datos y Selectores HTML

A través de la inspección técnica del DOM de Lectulandia (`ww3.lectulandia.co`), se identificaron las siguientes etiquetas y selectores robustos basados en la semántica y rutas de navegación del sitio:

### A. Página de Listado / Categoría (`https://ww3.lectulandia.co/genero/clasico/`)
*   **Enlace de la Ficha Individual:**
    *   *Tipo de página:* Listado de categoría.
    *   *Etiqueta HTML:* `<a>`
    *   *Selector Propuesto:* Enlaces dentro de las tarjetas de los libros. Para hacerlo sumamente robusto y evitar dependencias de clases CSS que puedan cambiar, se buscarán elementos `a` cuyas URLs cumplan el patrón de la expresión regular o filtro de cadena `/book/` (que es el prefijo único para libros en Lectulandia) y que no contengan `/page/` (que se usa para paginación).
    *   *Selector CSS:* `div.card a[href*="/book/"]` o selectores por patrón en código.

### B. Ficha Individual (`https://ww3.lectulandia.co/book/nombre-del-libro/`)

| Dato | Tipo de página | Etiqueta HTML | Selector CSS Propuesto | Descripción / Estrategia de Extracción |
| :--- | :--- | :--- | :--- | :--- |
| **Título** | Ficha individual | `<h1>` | `h1` o `#title` | Habitualmente es el único tag `<h1>` del cuerpo principal que contiene el nombre de la obra en la parte superior. |
| **Autores** | Ficha individual | `<a>` | `a[href*="/autor/"]` | Se identifican por tener URLs que contienen `/autor/`. Si hay múltiples autores, se extrae el texto de todos ellos y se formatea como una lista unida por comas. |
| **Géneros** | Ficha individual | `<a>` | `a[href*="/genero/"]` | Se identifican por tener URLs que contienen `/genero/`. Se unen mediante comas en un solo campo de texto. |
| **Serie** | Ficha individual | `<a>` | `a[href*="/serie/"]` | Se identifican por tener URLs que contienen `/serie/`. Si no se encuentra ningún tag con este patrón de enlace, se guarda como "No aplica". |
| **Sinopsis** | Ficha individual | `<div>` / `<p>` | `#sinopsis` o `.sinopsis` | El contenedor principal de la sinopsis tiene el ID `sinopsis`. Se extraen todos los párrafos `<p>` que están dentro de este elemento para conformar un bloque de texto consolidado. |
| **Portada** | Ficha individual | `<img>` | `#portada img` o `div.portada img` | La imagen principal con la portada se sitúa en un contenedor con ID `portada` o clase `.portada`. Extraemos su atributo `src`. |

---

## 4. Estrategia de Extracción e Implementación

El proceso de extracción técnica se diseñará siguiendo un flujo de trabajo asíncrono-respetuoso que evita saturar el servidor y maneja errores de forma elegante:

1.  **Inicialización de Playwright:** Se abrirá un navegador Chromium en segundo plano (*headless*). Se configurará un User-Agent realista para emular un navegador normal y evitar ser bloqueados por firewalls básicos.
2.  **Recorrido del Catálogo (Fase 1):**
    *   Se navegará secuencialmente a través de las páginas de paginación de la categoría `https://ww3.lectulandia.co/genero/clasico/page/1/` hasta que no haya más páginas de libros (o hasta un límite prudencial que cubra los 374 libros).
    *   En cada página, se usará BeautifulSoup para extraer todas las URLs de libros encontradas.
    *   Se eliminarán duplicados intermedios.
3.  **Muestreo Aleatorio:** El listado consolidado de URLs se filtrará. Se aplicará `random.sample(urls_totales, 50)` para obtener un conjunto representativo de 50 libros únicos.
4.  **Raspado de Fichas (Fase 2):**
    *   Se iterará sobre las 50 URLs seleccionadas.
    *   Para cada una, Playwright abrirá la página del libro y pasará el contenido HTML a BeautifulSoup.
    *   **Pausa de Cortesía (Politeness Policy):** Se incluirá una pausa aleatoria de entre 1.5 y 3.5 segundos entre visitas para simular el comportamiento de un lector humano.
    *   **Control de Excepciones:** Cada extracción de ficha individual se envolverá en bloques `try-except`. Si un libro falla (por ejemplo, por una carga lenta o un error 404), el programa registrará el error y continuará con el siguiente libro sin detener el scraping completo.
5.  **Limpieza y Normalización de Datos:**
    *   Se eliminarán espacios en blanco al principio y al final de los textos (`strip()`).
    *   Se unificarán los saltos de línea múltiples en las sinopsis para que el CSV sea limpio.
    *   Se normalizarán los campos vacíos (por ejemplo, si no hay una serie) con el valor estructurado `No aplica`.
6.  **Guardado Incremental:** Cada vez que un libro se extraiga con éxito, se agregará inmediatamente al archivo CSV. De esta forma, si la ejecución se interrumpe, no se pierden los datos ya obtenidos.
7.  **Deduplicación Final:** Al final de la ejecución, se volverá a leer el archivo CSV y se aplicará `drop_duplicates(subset=['url_libro'])` con pandas para garantizar la absoluta integridad de los datos.
