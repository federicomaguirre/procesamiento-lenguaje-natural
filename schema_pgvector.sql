-- ==============================================================================
-- TRABAJO PRÁCTICO N.º 2: PERSISTENCIA E INDEXACIÓN VECTORIAL EN POSTGRESQL / SUPABASE
-- Asignatura: Procesamiento del Lenguaje Natural (TUIA - UNR)
-- ==============================================================================

-- 1. Habilitar la extensión de pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Limpieza de tablas previas si existen (opcional durante desarrollo)
DROP TABLE IF EXISTS libros_w2v_sbw CASCADE;
DROP TABLE IF EXISTS libros_sbert CASCADE;

-- ------------------------------------------------------------------------------
-- 3. Tabla para Word2Vec (Spanish Billion Words - SBW-300: 300 dimensiones)
-- ------------------------------------------------------------------------------
-- Explanación técnica: Se crea una tabla específica para vectores de 300D.
-- No pueden convivir vectores de 300D y 512D en la misma columna indexada porque
-- el tipo vector(n) exige dimensionalidad afín fija y las métricas de distancia
-- (euclidiana, coseno) requieren formalmente que ambos vectores residan en el mismo R^n.
CREATE TABLE libros_w2v_sbw (
    id INTEGER PRIMARY KEY,
    titulo TEXT NOT NULL,
    autores TEXT[],
    generos TEXT[],
    serie TEXT,
    sinopsis TEXT,
    url_libro TEXT,
    embedding VECTOR(300) NOT NULL
);

-- Índice HNSW con opclass 'vector_cosine_ops' para búsqueda por distancia coseno (<=>)
CREATE INDEX IF NOT EXISTS idx_libros_w2v_hnsw 
ON libros_w2v_sbw 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- ------------------------------------------------------------------------------
-- 4. Tabla para Sentence-BERT (distiluse-base-multilingual-cased-v1: 512 dimensiones)
-- ------------------------------------------------------------------------------
CREATE TABLE libros_sbert (
    id INTEGER PRIMARY KEY,
    titulo TEXT NOT NULL,
    autores TEXT[],
    generos TEXT[],
    serie TEXT,
    sinopsis TEXT,
    url_libro TEXT,
    -- Columna de texto completo generada para Búsqueda Híbrida nativa (tsvector en español)
    fts_doc TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('spanish', coalesce(titulo, '') || ' ' || coalesce(sinopsis, ''))
    ) STORED,
    embedding VECTOR(512) NOT NULL
);

-- Índice HNSW con opclass 'vector_cosine_ops' para el modelo SBERT
CREATE INDEX IF NOT EXISTS idx_libros_sbert_hnsw 
ON libros_sbert 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Índice GIN para acelerar las consultas léxicas de Full-Text Search
CREATE INDEX IF NOT EXISTS idx_libros_sbert_fts 
ON libros_sbert 
USING gin (fts_doc);

-- Índice GIN sobre géneros para filtros selectivos por metadata
CREATE INDEX IF NOT EXISTS idx_libros_sbert_generos 
ON libros_sbert 
USING gin (generos);

-- ------------------------------------------------------------------------------
-- 5. Función SQL para Búsqueda Semántica Pura con Filtro por Metadata
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION buscar_semantico(
    query_vector VECTOR(512),
    top_k INT DEFAULT 5,
    filtro_genero TEXT DEFAULT NULL
)
RETURNS TABLE (
    id INT,
    titulo TEXT,
    autores TEXT[],
    generos TEXT[],
    sinopsis TEXT,
    similitud FLOAT
)
LANGUAGE sql
STABLE
AS $$
    SELECT 
        l.id,
        l.titulo,
        l.autores,
        l.generos,
        l.sinopsis,
        (1 - (l.embedding <=> query_vector))::FLOAT AS similitud
    FROM libros_sbert l
    WHERE (filtro_genero IS NULL OR filtro_genero = ANY(l.generos))
    ORDER BY l.embedding <=> query_vector ASC
    LIMIT top_k;
$$;

-- ------------------------------------------------------------------------------
-- 6. Función SQL para Búsqueda Híbrida con Reciprocal Rank Fusion (RRF)
-- ------------------------------------------------------------------------------
-- Combina el ranking léxico (ts_rank) y el ranking semántico (distancia coseno <=>).
-- Aplica la fórmula estándar de RRF: Score = 1/(k + rank_lex) + 1/(k + rank_sem)
CREATE OR REPLACE FUNCTION buscar_hibrido_rrf(
    query_text TEXT,
    query_embedding VECTOR(512),
    top_k INT DEFAULT 5,
    filtro_genero TEXT DEFAULT NULL,
    rrf_k INT DEFAULT 60
)
RETURNS TABLE (
    id INT,
    titulo TEXT,
    autores TEXT[],
    generos TEXT[],
    sinopsis TEXT,
    rank_lexico BIGINT,
    rank_semantico BIGINT,
    rrf_score FLOAT
)
LANGUAGE sql
STABLE
AS $$
    WITH candidatos_lexicos AS (
        SELECT 
            l.id,
            ROW_NUMBER() OVER (ORDER BY ts_rank(l.fts_doc, plainto_tsquery('spanish', query_text)) DESC) AS rank_lex
        FROM libros_sbert l
        WHERE (filtro_genero IS NULL OR filtro_genero = ANY(l.generos))
          AND l.fts_doc @@ plainto_tsquery('spanish', query_text)
        LIMIT 50
    ),
    candidatos_semanticos AS (
        SELECT 
            l.id,
            ROW_NUMBER() OVER (ORDER BY l.embedding <=> query_embedding ASC) AS rank_sem
        FROM libros_sbert l
        WHERE (filtro_genero IS NULL OR filtro_genero = ANY(l.generos))
        LIMIT 50
    ),
    fusion AS (
        SELECT 
            coalesce(c_lex.id, c_sem.id) AS id,
            c_lex.rank_lex,
            c_sem.rank_sem,
            (coalesce(1.0 / (rrf_k + c_lex.rank_lex), 0.0) + 
             coalesce(1.0 / (rrf_k + c_sem.rank_sem), 0.0))::FLOAT AS score
        FROM candidatos_lexicos c_lex
        FULL OUTER JOIN candidatos_semanticos c_sem ON c_lex.id = c_sem.id
    )
    SELECT 
        l.id,
        l.titulo,
        l.autores,
        l.generos,
        l.sinopsis,
        f.rank_lex,
        f.rank_sem,
        f.score AS rrf_score
    FROM fusion f
    JOIN libros_sbert l ON l.id = f.id
    ORDER BY f.score DESC
    LIMIT top_k;
$$;
