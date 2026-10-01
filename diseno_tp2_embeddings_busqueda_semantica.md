# Diseño del Sistema de Representación Vectorial y Búsqueda Semántica (TP2)

Este documento registra formalmente las especificaciones técnicas, fundamentos teóricos y decisiones de diseño implementadas para el **Trabajo Práctico N.º 2: Representación vectorial de texto: embeddings y búsqueda semántica** sobre el catálogo curado en el TP1 (`data/libros.csv`), en el marco de la asignatura **Procesamiento del Lenguaje Natural** (TUIA - Facultad de Ciencias Exactas, Ingeniería y Agrimensura - UNR).

---

## 1. Contexto y Objetivos

En el TP1 se construyó un recomendador de libros basado en **TF-IDF** (vectores dispersos del tamaño del vocabulario). Aunque eficiente para coincidencias léxicas exactas, dicho modelo sufre de una limitación fundamental de la Unidad 2: **no captura la semántica**. Términos sinónimos o conceptualmente cercanos sin solapamiento léxico ("piratas" vs. "bucaneros") presentan similitud coseno exactamente cero.

El objetivo del TP2 es superar este techo mediante:
1. Representación en espacios vectoriales densos continuos (Word2Vec propio, modelo pre-entrenado Spanish Billion Word Corpus `SBW-vectors-300-min5` y modelos de oración Sentence-BERT `distiluse-base-multilingual-cased-v1`).
2. Persistencia e indexación vectorial en **PostgreSQL / Supabase** utilizando la extensión **`pgvector`** e índices aproximados **HNSW**.
3. Evaluación empírica rigurosa con un benchmark propio (`queries.json`), midiendo $\text{Precision@}k$ con respecto a líneas de base (TF-IDF) y piso de azar.
4. Implementación de una extensión avanzada: **Búsqueda Híbrida (Hybrid Search)** combinando búsqueda léxica nativa y búsqueda semántica vectorial mediante **Reciprocal Rank Fusion (RRF)**.

---

## 2. Decisiones de Preprocesamiento del Corpus

### 2.1 Pérdida deliberada de información
Toda transformación sobre el texto sin procesar constituye una pérdida deliberada de información que debe justificarse en función de la tarea downstream:
* **Minúsculas (Lowercasing):** Colapsa diferencias ortográficas de inicio de oración, pero destruye la capacidad de distinguir entidades nombradas y nombres propios frente a sustantivos comunes (ej. `Madrid` vs. `madrid`, `Rosa` vs. `rosa`).
* **Remoción de diacríticos y acentos:** Normaliza errores tipográficos y variaciones de codificación, pero colapsa pares mínimos con cambio semántico o funcional determinante (ej. `si` condicional vs. `sí` afirmativo, `el` artículo vs. `él` pronombre).
* **Eliminación de signos de puntuación:** Facilita la extracción de unigramas limpios, pero elimina los delimitadores de cláusulas y oraciones, destruyendo la prosodia y la sintaxis.
* **Filtrado de palabras vacías (Stopwords):** Reduce la dimensionalidad en modelos de bolsa de palabras, pero elimina negaciones (`no`, `sin`, `ni`) y conectores relacionales que alteran por completo el sentido de un enunciado.

### 2.2 Principio de diseño: "El preprocesamiento pertenece al modelo, no al corpus"
Se generan dos versiones persistentes de los textos en memoria y base de datos:
1. **Versión tokenizada y limpia (`texto_limpio`):** Texto normalizado a minúsculas, sin puntuación y sin stopwords. Apropiado para modelos de espacio vectorial disperso (TF-IDF) y para el entrenamiento de Word2Vec a nivel unigrama.
2. **Versión cruda/natural (`texto_crudo`):** Preserva mayúsculas, acentuación original, signos de puntuación y palabras funcionales. **Indispensable para Sentence-BERT (SBERT)**, ya que los modelos basados en Transformers fueron pre-entrenados sobre texto natural continuo y utilizan la atención posicional y las partículas sintácticas para construir el significado oracional.

### 2.3 Respuestas al Análisis Inicial del Corpus
1. **Estabilidad léxica en TF-IDF con pocos documentos:**
   * Con apenas 12 documentos, el término inverso de documento ($\text{IDF}(t) = \log\frac{N+1}{\text{DF}(t)+1} + 1$) oscila violentamente ante la adición de un único libro que contenga un vocablo previamente infrecuente.
   * Para alcanzar estabilidad en los términos característicos se requieren típicamente cientos de documentos representativos por categoría temática (ley de Heaps, saturación del vocabulario central).
   * **¿Cómo medirlo empíricamente?** Mediante muestreo por remuestreo (*bootstrap*): se toman submuestras aleatorias del $80\%$ del corpus en múltiples iteraciones, se calcula el ranking de los términos con mayor TF-IDF para cada documento, y se mide la similitud de Jaccard o el coeficiente de correlación de rangos de Spearman entre las listas de términos top a lo largo de las particiones. Cuando la correlación promedio supera un umbral ($\rho > 0.85$), el espacio léxico se considera estable.
2. **Sesgo del texto promocional en sinopsis:**
   * Las sinopsis editoriales están redactadas con una función apelativa y comercial (captar compradores), empleando adjetivos hiperbólicos ("inolvidable", "emocionante", "obra cumbre", "fascinante historia").
   * Si se entrena un clasificador supervisado de género literario sobre este texto, el modelo corre el riesgo de asociar estos adjetivos promocionales generalistas como rasgos discriminativos espurios, degradando su generalización ante descripciones objetivas o fragmentos de la propia obra.
3. **Clasificación multi-etiqueta vs. multi-clase:**
   * En el corpus, un libro puede pertenecer simultáneamente a varios géneros (ej. `['Clásico', 'Intriga', 'Policíaco']`). Esto transforma la tarea de multi-clase (distribución categórica con $\sum p_i = 1$) en multi-etiqueta (conjunto de decisiones binarias independientes o dependientes).
   * La evaluación cambia radicalmente: la precisión simple (*Accuracy* o *Exact Match Ratio*) exige acertar exactamente el conjunto idéntico de etiquetas y resulta excesivamente punitiva. En su lugar se deben emplear métricas multi-etiqueta: **Hamming Loss** (fracción de etiquetas predichas erróneamente), **Micro/Macro F1-Score** ponderado por etiqueta, y métricas de ranking como **Coverage** o **Average Precision**.
4. **Detección de idioma ante obras multilingües (gallego, catalán, español):**
   * En catálogos editoriales españoles aparecen ocasionalmente títulos o sinopsis en catalán o gallego.
   * Aplicar una lista de stopwords en español a un texto en catalán o gallego no remueve las palabras vacías de esa lengua (e.g. *amb*, *dels*, *molt*, *mais*) y tokeniza raíces con desinencias imprevistas.
   * La decisión arquitectónica correcta es aplicar un clasificador de identificación de idioma previo (e.g. `langdetect` o `fasttext`) antes del pipeline de tokenización para enrutar el documento al stemmer/stopwords correspondiente, o emplear de forma directa modelos oracionales verdaderamente multilingües (como `distiluse-base-multilingual-cased-v1`).

---

## 3. Modelos de Embeddings de Palabras (Word2Vec / FastText)

### 3.1 Justificación de Hiperparámetros del Modelo Propio
Se entrena un modelo Word2Vec utilizando Gensim sobre las sinopsis tokenizadas del catálogo:
* **`vector_size = 100`:** Dado que el corpus es pequeño (120 libros, $\approx 10.600$ tokens después de sacar stopwords), fijar 300 dimensiones conduciría a una dispersión excesiva y sobreajuste del espacio latente. Una dimensionalidad de 100 ofrece suficiente capacidad representativa sin sobredimensionar la matriz de pesos.
* **`window = 5`:** Ventana simétrica estándar que captura relaciones colocacionales y de coocurrencia temática local inmediata en oraciones en español.
* **`min_count = 2`:** Al ser un corpus acotado, fijar un umbral alto (como `min_count=5`) eliminaría sustantivos propios y tecnicismos cruciales para discriminar géneros.
* **`sg = 1` (Skip-gram):** La teoría de la Unidad 2 señala que CBOW promedia las palabras del contexto para predecir la central, favoreciendo términos muy frecuentes. Skip-gram, en cambio, utiliza la palabra central para predecir cada contexto de forma independiente, demostrando un rendimiento superior para aprender representaciones útiles de palabras infrecuentes en corpus chicos.

### 3.2 Fundamento Teórico: Negative Sampling vs. Softmax Completo
En el modelo Skip-gram estándar, la probabilidad condicional de observar la palabra de contexto $w_O$ dada la palabra central $w_I$ viene dada por la función Softmax:
$$P(w_O | w_I) = \frac{\exp({v'_{w_O}}^\top v_{w_I})}{\sum_{w=1}^{|V|} \exp({v'_w}^\top v_{w_I})}$$
* **Inviabilidad computacional:** En cada paso de propagación hacia adelante y hacia atrás, el cálculo del denominador requiere sumar el producto interno sobre la totalidad del vocabulario $|V|$. Con vocabularios de cientos de miles o millones de términos ($|V| \ge 10^5$), el costo $O(|V|)$ por cada actualización de gradiente resulta prohibitivo.
* **Solución de Negative Sampling:** Reformula la tarea de clasificación multiclase como múltiples problemas de regresión logística binaria. El modelo aprende a distinguir la palabra real observada en el contexto (ejemplo positivo) de $K$ palabras seleccionadas aleatoriamente del vocabulario siguiendo una distribución unigrama achatada $P_n(w)^{3/4}$ (ejemplos de ruido o negativos):
$$\mathcal{L}_{\text{NEG}} = \log \sigma({v'_{w_O}}^\top v_{w_I}) + \sum_{i=1}^K \mathbb{E}_{w_i \sim P_n(w)} \left[ \log \sigma(-{v'_{w_i}}^\top v_{w_I}) \right]$$
El costo computacional desciende de $O(|V|)$ a $O(K)$, donde $K \in [5, 20]$ en corpus pequeños, tornando viable el entrenamiento.

### 3.3 Construcción del Vector de Documento por Promedio (Mean Pooling)
Para representar cada libro a partir de sus vectores de palabras constitutivos $v_w$, se calcula el promedio aritmético de sus vectores normalizados:
$$v_{\text{doc}} = \frac{1}{|D|} \sum_{w \in D} v_w$$
* **Pérdida de información:**
  1. **Orden sintáctico:** Como demuestra el contraejemplo de la Unidad 2 ("this is cool" vs. "is this cool"), el promedio conmuta y genera exactamente el mismo vector representativo.
  2. **Negación y composición:** Frases de sentido opuesto ("novela con final feliz" vs. "novela sin final feliz") tienen una similitud cercana a 1.0 por compartir la casi totalidad de los términos.
  3. **Dilución semántica:** Palabras temáticas muy específicas quedan diluidas por la acumulación lineal de vocablos neutros o genéricos.
* **Justificación de uso:** Se adopta por ser computacionalmente inmediato ($O(N)$ operaciones de suma), no requerir hiperparámetros adicionales y servir como puente continuo y denso frente a la rigidez ortogonal de TF-IDF.

---

## 4. Modelo de Oración Pre-entrenado: SBERT

Se adopta **`distiluse-base-multilingual-cased-v1`** de la librería `sentence-transformers`:
* **Arquitectura:** Red siamesa/triplete basada en DistilBERT multilingüe (6 capas de Transformer, 512 dimensiones de salida), pre-entrenada con funciones de pérdida de contraste para optimizar directamente la similitud coseno entre oraciones.
* **Límite de tokens (`max_seq_length`):** **128 tokens**.
* **Diagnóstico de truncamiento (medido en el notebook con el tokenizer del modelo):** el texto de cada libro (título, autores, serie y sinopsis) tiene una mediana de 220 tokens. **109 de 120 libros (91 %) superan el límite** y la mitad de los tokens del corpus nunca llega al modelo: en la práctica SBERT ve el título, el autor y las primeras oraciones de la sinopsis.

---

## 5. Visualización y Geometría del Espacio

Para evaluar la discriminabilidad de los espacios generados:
1. **Distribución de Similitudes entre Pares Aleatorios:**
   * Se calcula la similitud coseno de todos los pares de libros distintos (7.140 pares).
   * Se reporta media, desviación estándar y rango.
   * *Criterio de calidad:* Un espacio colapsado donde todos los pares arrojan similitud entre $0.85$ y $0.98$ carece de resolución discriminativa; un espacio de calidad distribuye sus pares no relacionados cerca de $0.0$ o con varianza apreciable.
2. **Proyección 2D (PCA vs. t-SNE):**
   * **t-SNE:** Se ajusta el parámetro `perplexity` (se usa 15 para 120 puntos). **Advertencia metodológica:** t-SNE preserva exclusivamente vecindades locales; las distancias entre clusters distantes no reflejan distancias métricas en el espacio original y las densidades relativas son arbitrarias.
   * **PCA:** Técnica lineal que maximiza la varianza. **Advertencia metodológica:** Se reporta el porcentaje de varianza explicada acumulada por $PC_1 + PC_2$ (usualmente $< 25\%$ en espacios de 512D). Una superposición en la proyección 2D no implica falta de separabilidad en las 510 dimensiones restantes.

---

## 6. Persistencia e Indexación Vectorial (PostgreSQL + pgvector)

### 6.1 Separación de Esquemas por Modelo
Se crean dos tablas relacionales independientes:
* `libros_sbw` con columna `embedding vector(300)` (promedio de vectores SBW)
* `libros_sbert` con columna `embedding vector(512)`

**Fundamentación de por qué no pueden convivir dos dimensiones en la misma columna indexada:**
1. **Restricción de tipo estricta:** En PostgreSQL, `vector(n)` es un tipo de dato fuertemente tipado que fija la longitud del array numérico a nivel de catálogo.
2. **Fundamento algebraico:** Toda métrica métrica (distancia euclidiana, distancia angular/coseno, producto interno) está definida formalmente sobre vectores en el mismo espacio afín $\mathbb{R}^n$. Computar un producto punto o norma entre un vector de 300 dimensiones y uno de 512 carece de significado matemático.
3. **Estructura del índice:** Los índices aproximados (HNSW o IVFFlat) construyen grafos o particiones espaciales basados en distancias entre nodos en $\mathbb{R}^n$; la inserción de un elemento con dimensionalidad dispar corrompe la topología de búsqueda del índice.

### 6.2 Configuración del Índice HNSW y Opclass
* **Operador de consulta:** Distancia coseno `<=>` (definida como $1 - \cos(\theta)$).
* **Opclass requerida:** **`vector_cosine_ops`**.
```sql
CREATE INDEX idx_libros_sbert_hnsw 
ON libros_sbert 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```
* **Riesgo técnico:** Si se construyera el índice con `vector_l2_ops` o `vector_ip_ops` y la consulta ejecutara `<=>`, PostgreSQL no emplearía el índice HNSW o produciría un ordenamiento erróneo si los vectores no estuviesen normalizados a norma unitaria.

### 6.3 Manejo de Vectores Nulos o No Finitos
Se implementa una función de saneamiento previo a la inserción SQL:
* Comprobación estricta de valores `NaN`, `Inf` o vector nulo (norma cero).
* Los registros que no generen embeddings válidos se descartan antes del `INSERT` (no se imputan) y la tabla además tiene un `CHECK (vector_norm(embedding) > 0)`, garantizando el cumplimiento de los criterios de evaluación.

---

## 7. Búsqueda Semántica y Filtro por Metadatos

### 7.1 Implementación en SQL
La similitud semántica y el filtrado por metadatos se resuelven nativamente en PostgreSQL:
```sql
SELECT id, titulo, autores, generos, 
       1 - (embedding <=> %(query_vector)s::vector) AS similitud
FROM libros_sbert
WHERE (%(filtro_genero)s IS NULL OR %(filtro_genero)s = ANY(generos))
ORDER BY embedding <=> %(query_vector)s::vector ASC
LIMIT %(top_k)s;
```

### 7.2 El Problema de Recall en Índices Aproximados con Filtro Selectivo
Al combinar un índice HNSW con un predicado `WHERE` restrictivo surgen dos problemáticas críticas de recuperación (*Recall drop*):
1. **Post-filtering clásico:** El índice HNSW explora los $k$ nodos más cercanos en el grafo completo sin considerar el filtro, y posteriormente la cláusula `WHERE` descarta aquellos que no cumplen la condición. Si el filtro es altamente selectivo (ej. un subgénero que cubre sólo el $3\%$ de la colección), es muy probable que ninguno de los $k$ candidatos iniciales pase el filtro, retornando una lista vacía o incompleta.
2. **Pre-filtering sobre grafos aproximados:** Si se intenta restringir la navegación exclusivamente a los nodos válidos, el subgrafo inducido puede quedar disconexo o presentar pocos caminos viables, provocando que la búsqueda golpee mínimos locales lejanos al óptimo real.

**Estrategias de mitigación:**
* **Iterative Index Scan (`hnsw.iterative_scan`, disponible desde pgvector 0.8.0):** El índice sigue expandiendo la frontera de búsqueda en el grafo hasta reunir los $k$ elementos que superen el filtro.
* **Aumento temporal de `hnsw.ef_search`:** Aumentar `SET hnsw.ef_search = 100` durante consultas filtradas para examinar una vecindad sustancialmente más amplia.
* **Exact Scan Fallback:** Para condiciones con selectividad menor al $10\%$, deshabilitar el índice vectorial (`SET enable_indexscan = off;`) y ejecutar escaneo secuencial exacto asistido por índices B-Tree/GIN sobre los metadatos.

---

## 8. Evaluación de Modelos (queries.json y Precision@k)

Se define el conjunto de evaluación en `queries.json` con más de 10 consultas representativas:
* Consultas léxicas directas (orientadas a palabras clave y nombres de autores).
* Consultas semánticas abstractas (temáticas y conflictos humanos).
* **Consulta de prueba sin solapamiento léxico ("piratas vs. bucaneros"):**
  * Consulta (Q12): *"forajido justiciero arquero que despoja a tiranos feudales para auxiliar desamparados"*
  * Documento relevante: *Robin Hood* (ID 2).
  * Ningún término de la consulta aparece en la sinopsis, así que TF-IDF da similitud 0 a todos los libros y no recupera nada. **Resultado:** los modelos semánticos tampoco la resuelven (SBERT pone a Robin Hood 12.º), porque las palabras elegidas son poco frecuentes y el tokenizer las parte en fragmentos. Con la misma idea en palabras comunes, SBERT lo pone 1.º. Ver el análisis en el notebook (5.5) y en el informe.

Métrica de evaluación:
$$\text{Precision@}k = \frac{\sum_{i=1}^k \mathbb{I}(\text{doc}_i \in \text{Relevantes})}{k}$$
* Se computa para $k \in \{1, 3, 5, 10\}$, junto con el techo de cada consulta ($\min(|R|, k)/k$) y un test de permutación pareado contra TF-IDF.
* Se contrasta contra una línea de base de **selección al azar (piso de azar)** calculada sobre el total de libros del catálogo ($|R|/N$), verificada con 10.000 rankings aleatorios (se reporta también su percentil 95).

---

## 9. Parte Avanzada: Búsqueda Híbrida con Reciprocal Rank Fusion (RRF)

### 9.1 Justificación Técnica
La búsqueda híbrida integra lo mejor de ambos paradigmas:
1. **Canal Léxico:** PostgreSQL Full-Text Search (`tsvector`, `tsquery`, `ts_rank`) para precisión quirúrgica ante términos unívocos, nombres de personajes y tecnicismos.
2. **Canal Semántico:** Búsqueda vectorial (`pgvector` + SBERT) para capturar afinidad temática, paráfrasis y sinónimos.

### 9.2 Algoritmo Reciprocal Rank Fusion
Para evitar los problemas de normalización de escalas dispares entre puntuaciones de similitud coseno ($[-1, 1]$) y valores `ts_rank` ($[0, \infty)$), se utiliza **RRF**, un método no paramétrico basado exclusivamente en el rango posicional de cada documento en las listas ordenadas:
$$\text{RRF\_Score}(d) = \frac{1}{k_{\text{RRF}} + \text{rank}_{\text{lex}}(d)} + \frac{1}{k_{\text{RRF}} + \text{rank}_{\text{sem}}(d)}$$
donde $k_{\text{RRF}} = 60$ es una constante de suavizado que penaliza caídas pronunciadas en el ranking superior sin castigar excesivamente documentos relevantes situados en posiciones medias.

Se evalúa empíricamente si la combinación RRF supera a cada componente individual en $\text{Precision@}k$. **Resultado:** supera al canal léxico (P@5 0,35 contra 0,30) pero no a SBERT solo (0,38): el canal léxico es débil en las consultas con poco solapamiento y mete ruido en el top-5.
