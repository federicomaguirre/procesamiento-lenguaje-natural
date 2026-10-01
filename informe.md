# Informe Técnico — Trabajo Práctico N.º 2
## Representación Vectorial de Texto: Embeddings y Búsqueda Semántica
**Asignatura:** Procesamiento del Lenguaje Natural (PLN) — TUIA / FCEIA — Universidad Nacional de Rosario  
**Integrantes:** Franco Venesia, Marisa Zappala, Agustin Marquardt, Federico Aguirre  
**Fecha:** Septiembre 2026 | **Repositorio:** `federicomaguirre/procesamiento-lenguaje-natural`

---

### 1. ¿Qué modelo elegirían para producción y por qué?

Para un entorno de producción seleccionamos la arquitectura de **Búsqueda Híbrida (Hybrid Search)**, integrando el motor de búsqueda léxica nativo de **PostgreSQL (Full-Text Search)** con representaciones vectoriales densas generadas por **Sentence-BERT (`distiluse-base-multilingual-cased-v1`)**, fusionadas mediante **Reciprocal Rank Fusion (RRF)** sobre la extensión `pgvector`.

La elección no se fundamenta únicamente en el rendimiento de recuperación, sino en un balance riguroso de restricciones operativas:

1. **Costo computacional e infraestructura:**  
   `distiluse-base-multilingual-cased-v1` es un modelo destilado ultraligero ($\approx 135\text{M}$ parámetros, 512 dimensiones y $< 500\text{MB}$ de memoria RAM/VRAM). A diferencia de grandes modelos de lenguaje (LLMs) o embeddings generativos sobredimensionados, puede realizar inferencia en milisegundos sobre CPUs comerciales estándar sin exigir GPUs dedicadas. Además, la persistencia de vectores 512D con índices **HNSW** en PostgreSQL mantiene el uso de memoria RAM acotado y predecible.
2. **Privacidad y gobernanza de datos:**  
   El pipeline completo (base relacional y pesos de Hugging Face) opera de manera autónoma *on-premise* o en una VPC privada. No se envían las consultas de los usuarios ni los catálogos editoriales a APIs comerciales externas de terceros (evitando filtraciones, cambios imprevistos en términos de servicio y costos variables por token).
3. **Reproducibilidad y soberanía técnica:**  
   Los pesos del modelo son estáticos y de código abierto. Se elimina por completo el riesgo de *model drift*, latencias impredecibles de red o la deprecación repentina de endpoints propietarios que suele afectar a los servicios SaaS de embeddings.
4. **Resiliencia ante consultas heterogéneas:**  
   El modelo Word2Vec propio entrenado sobre 99 documentos sufre severamente por escasez de datos (falta de generalización y vocabulario reducido); el promedio de vectores de palabras descarta la sintaxis y las negaciones. Por su parte, SBERT sobresale en lenguaje natural difuso, pero puede confundir identificadores unívocos. La fusión RRF actúa como una red de seguridad operativa: si el vector semántico introduce ruido ante una búsqueda específica, el canal léxico garantiza la recuperación inmediata de las coincidencias literales.

---

### 2. ¿Cuánto mejor es que la línea de base TF-IDF? ¿En qué tipo de consulta gana y en cuál no?

En la evaluación global sobre el conjunto de prueba anotado (`queries.json`), los modelos semánticos y en particular la **Búsqueda Híbrida** superan con claridad la línea de base de **TF-IDF**:
* **$\text{Precision@1}$:** TF-IDF alcanza $0.5833$, mientras que SBERT y la Búsqueda Híbrida alcanzan $0.8333$ y $0.9167$ respectivamente (un incremento relativo superior al $57\%$).
* **$\text{Precision@3}$:** TF-IDF promedia $0.4444$, frente a $0.6667$ de SBERT y $0.7222$ del enfoque Híbrido.
* **Piso de azar:** El azar teórico y empírico se sitúa en $0.0381$ (dado que los libros relevantes representan entre el $1\%$ y el $8\%$ de la colección). Todas las soluciones superan ampliamente este piso, demostrando que capturan señal genuina y no ruido aleatorio.

#### ¿En qué tipo de consultas gana cada enfoque?
* **Dónde gana Sentence-BERT / Búsqueda Semántica:**  
  Triunfa contundentemente en consultas temáticas, conceptuales o expresadas mediante **paráfrasis y sinónimos sin coincidencia léxica**.  
  El caso paradigmático es la consulta testigo obligatoria **Q12**:  
  *“forajido justiciero arquero que despoja a tiranos feudales para auxiliar desamparados”*.  
  El documento objetivo es *Robin Hood* (ID 2). Dado que en su sinopsis no figura ninguno de esos vocablos exactos (el texto emplea "legendario héroe", "robaba a gobernantes", "entregar parte del botín a necesitados"), **TF-IDF obtiene similitud exactamente $0.0000$ (falla total por diseño)**. En contraste, Sentence-BERT proyecta la consulta en la misma vecindad semántica, recuperando el libro en la primera posición ($\text{similitud} = 0.6124$).
* **Dónde gana o empata TF-IDF:**  
  TF-IDF empata o supera a los embeddings en consultas orientadas a **nombres propios, personajes célebres o tecnicismos literarios exactos** (e.g., *"Sherlock Holmes"*, *"Dickens"*, *"Sócrates"*, *"Zalamea"*).  
  En estos casos, el factor $\text{IDF}(t) = \log\frac{N+1}{\text{DF}(t)+1} + 1$ asigna un peso colosal a términos exclusivos del catálogo. TF-IDF aísla quirúrgicamente los documentos pertinentes sin la dispersión o "ruido de vecindad" que los embeddings densos a veces introducen al asociar términos próximos en el espacio continuo.

---

### 3. ¿Qué mide y qué no mide la métrica que usaron?

La métrica principal adoptada es **$\text{Precision@}k$** ($\frac{\text{Aciertos en el Top-}k}{k}$) para $k \in \{1, 3, 5\}$.

* **Qué mide con eficacia:**  
  Mide la **pureza y relevancia del resultado inmediato visible**. En un motor de recomendación o catálogo digital, el usuario rara vez explora más allá de los primeros 3 a 5 resultados. $\text{Precision@}k$ cuantifica directamente qué proporción de los ítems recomendados en la "primera pantalla" satisface genuinamente la necesidad de información del usuario.
* **Qué NO mide (Límites estructurales de la métrica):**  
  1. **Indiferencia al orden interno dentro del Top-$k$:** Para $k=5$, un acierto en la posición 1 aporta exactamente lo mismo al numerador que un acierto en la posición 5. No premia que los mejores resultados aparezcan primeros (para lo cual se requerirían métricas sensibles al rango como **NDCG@$k$** o **MAP**).
  2. **Ausencia de noción de Recall:** Desconoce la proporción de documentos relevantes recuperados respecto al total existente en la base. Si una temática posee 8 libros en el corpus y el modelo devuelve 3 aciertos en el top-3 ($\text{Precision@3} = 1.0$), la métrica es perfecta, pero ignora que el $62.5\%$ de la colección relevante quedó oculta.
  3. **Suposición de relevancia binaria:** Trata la afinidad como una función discreta $\{0, 1\}$. En la experiencia literaria real, la afinidad es un gradiente continuo: un libro puede ser altamente relevante, moderadamente afín o totalmente ajeno.

---

### 4. Caso concreto donde la búsqueda falló e hipótesis causa-raíz

* **Caso de falla identificado:**  
  En la consulta **Q07**: *“brote epidémico contagio colectivo y confinamiento que revela la miseria moral de una ciudad”*, cuyo documento objetivo primordial es ***La peste* de Albert Camus (ID 90)**.  
  Al evaluar el modelo semántico puro (**Sentence-BERT**), *La peste* no se ubicó en el primer lugar del ranking, siendo desplazada en el Top-1 por *El desierto y otros cuentos* de Horacio Quiroga (ID 55).
* **Hipótesis causa-raíz del fallo:**  
  1. **Naturaleza promocional y abstracta de la sinopsis:** Al inspeccionar el texto crudo de la sinopsis de *La peste*, se constató que no menciona términos epidemiológicos específicos como "brote", "contagio", "enfermedad", "médico" o "cuarentena". La descripción se concentra en abstracciones morales y elogios editoriales: *"consecuencias del aislamiento de toda una ciudad... miedos, traiciones, solidaridad, compasión... novela apasionante de gran densidad de pensamiento y comprensión del ser humano... clásico de la literatura francesa"*.
  2. **Truncamiento por límite de secuencia en SBERT:** La sinopsis de *La peste* contiene 148 tokens, superando el límite de `max_seq_length = 128` del modelo, lo que causó el descarte de las oraciones finales.
  3. **Solapamiento conceptual espurio:** Las palabras "aislamiento", "miedos" y "traiciones" están fuertemente presentes en los relatos trágicos de Quiroga ambientados en la selva, provocando que la proximidad vectorial favoreciera a Quiroga sobre Camus.
* **Resolución mediante Búsqueda Híbrida:**  
  El canal léxico de la búsqueda híbrida detectó inmediatamente la presencia de palabras clave en el título y texto complementario, reordenando a *La peste* en el Top-1 definitivo gracias a la suma de rangos recíprocos de RRF.

---

### 5. Declaración de Uso de Asistentes de IA

En cumplimiento con la Sección 9 del enunciado, declaramos que hemos utilizado asistentes de inteligencia artificial (modelos de lenguaje) durante el desarrollo del trabajo práctico. Las herramientas de IA fueron empleadas para:  
1. Asistencia en la sintaxis de consultas PostgreSQL y configuración de la extensión `pgvector` con índices HNSW.  
2. Estructuración y formateo del archivo de evaluación `queries.json`.  
3. Aceleración en la generación de scripts de visualización con `seaborn` y `matplotlib`.  

El análisis conceptual, la curaduría manual de los juicios de relevancia (*ground truth*), la interpretación de las limitaciones de las métricas frente al piso de azar y la redacción de las conclusiones técnicas fueron realizados y verificados íntegramente por los autores humanos del trabajo.
