-- ==============================================================================
-- TP2 - Persistencia e indexado vectorial en PostgreSQL / Supabase (pgvector)
-- Procesamiento del Lenguaje Natural - TUIA - FCEIA - UNR
-- ==============================================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- Configuración de full-text en español que además ignora acentos.
-- Las consultas de queries.json están escritas sin tildes ("crimenes", "espana"),
-- como las tipearía un usuario; sin unaccent el canal léxico no matchea "crímenes".
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'spanish_unaccent') THEN
        CREATE TEXT SEARCH CONFIGURATION spanish_unaccent (COPY = spanish);
        ALTER TEXT SEARCH CONFIGURATION spanish_unaccent
            ALTER MAPPING FOR hword, hword_part, word WITH unaccent, spanish_stem;
    END IF;
END $$;

DROP TABLE IF EXISTS libros_sbw CASCADE;
DROP TABLE IF EXISTS libros_sbert CASCADE;

-- ------------------------------------------------------------------------------
-- Una tabla por modelo. La columna vector(n) tiene dimensión fija: un vector de
-- 300 y uno de 512 no pueden compartir columna, y aunque se usara vector sin
-- dimensión, el índice HNSW exige que todas las filas tengan la misma (y la
-- distancia entre espacios distintos no está definida).
-- ------------------------------------------------------------------------------

-- Familia 1: promedio de word vectors pre-entrenados (SBW-vectors-300-min5)
CREATE TABLE libros_sbw (
    id         INTEGER PRIMARY KEY,
    titulo     TEXT NOT NULL,
    autores    TEXT[],
    generos    TEXT[],
    serie      TEXT,
    sinopsis   TEXT,
    url_libro  TEXT,
    embedding  VECTOR(300) NOT NULL,
    -- Segunda barrera después de la validación en Python: nada de vectores nulos
    CONSTRAINT sbw_vector_no_nulo CHECK (vector_norm(embedding) > 0)
);

-- Familia 2: modelo de oración (distiluse-base-multilingual-cased-v1)
CREATE TABLE libros_sbert (
    id         INTEGER PRIMARY KEY,
    titulo     TEXT NOT NULL,
    autores    TEXT[],
    generos    TEXT[],
    serie      TEXT,
    sinopsis   TEXT,
    url_libro  TEXT,
    -- Columna de full-text para la búsqueda híbrida (parte avanzada)
    fts_doc    TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('spanish_unaccent'::regconfig,
                    coalesce(titulo, '') || ' ' || coalesce(sinopsis, ''))
    ) STORED,
    embedding  VECTOR(512) NOT NULL,
    CONSTRAINT sbert_vector_no_nulo CHECK (vector_norm(embedding) > 0)
);

-- Índices HNSW. Todas las consultas usan el operador <=> (distancia coseno),
-- así que la opclass es vector_cosine_ops. Con vector_l2_ops el planificador
-- no puede usar el índice para ORDER BY embedding <=> ...
CREATE INDEX idx_libros_sbw_hnsw ON libros_sbw
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX idx_libros_sbert_hnsw ON libros_sbert
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

-- Filtro por metadata (género) y full-text
CREATE INDEX idx_libros_sbw_generos   ON libros_sbw   USING gin (generos);
CREATE INDEX idx_libros_sbert_generos ON libros_sbert USING gin (generos);
CREATE INDEX idx_libros_sbert_fts     ON libros_sbert USING gin (fts_doc);

-- ------------------------------------------------------------------------------
-- Búsqueda semántica con filtro opcional por género (similitud resuelta en SQL)
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION buscar_sbert(query_vector VECTOR(512), top_k INT DEFAULT 5,
                                        filtro_genero TEXT DEFAULT NULL)
RETURNS TABLE (id INT, titulo TEXT, generos TEXT[], similitud FLOAT)
LANGUAGE sql STABLE AS $$
    SELECT l.id, l.titulo, l.generos, (1 - (l.embedding <=> query_vector))::FLOAT
    FROM libros_sbert l
    WHERE filtro_genero IS NULL OR filtro_genero = ANY(l.generos)
    ORDER BY l.embedding <=> query_vector
    LIMIT top_k;
$$;

CREATE OR REPLACE FUNCTION buscar_sbw(query_vector VECTOR(300), top_k INT DEFAULT 5,
                                      filtro_genero TEXT DEFAULT NULL)
RETURNS TABLE (id INT, titulo TEXT, generos TEXT[], similitud FLOAT)
LANGUAGE sql STABLE AS $$
    SELECT l.id, l.titulo, l.generos, (1 - (l.embedding <=> query_vector))::FLOAT
    FROM libros_sbw l
    WHERE filtro_genero IS NULL OR filtro_genero = ANY(l.generos)
    ORDER BY l.embedding <=> query_vector
    LIMIT top_k;
$$;

-- ------------------------------------------------------------------------------
-- Ranking léxico con el full-text nativo (ts_rank).
-- plainto_tsquery une los términos con AND: una consulta de 10 palabras casi
-- nunca matchea entera. Se reemplaza & por | para que cada término sume.
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION consulta_or(query_text TEXT)
RETURNS tsquery LANGUAGE sql IMMUTABLE AS $$
    SELECT NULLIF(replace(plainto_tsquery('spanish_unaccent'::regconfig, query_text)::text,
                          '&', '|'), '')::tsquery;
$$;

CREATE OR REPLACE FUNCTION buscar_fts(query_text TEXT, top_k INT DEFAULT 5)
RETURNS TABLE (id INT, titulo TEXT, rank_fts FLOAT)
LANGUAGE sql STABLE AS $$
    SELECT l.id, l.titulo, ts_rank(l.fts_doc, consulta_or(query_text))::FLOAT
    FROM libros_sbert l
    WHERE l.fts_doc @@ consulta_or(query_text)
    ORDER BY 3 DESC, l.id
    LIMIT top_k;
$$;

-- ------------------------------------------------------------------------------
-- Búsqueda híbrida: Reciprocal Rank Fusion entre ts_rank y distancia coseno.
-- score(d) = 1/(rrf_k + rank_lexico) + 1/(rrf_k + rank_semantico)
-- Cada canal ordena ANTES de cortar en n_candidatos (un LIMIT sin ORDER BY
-- devolvería filas arbitrarias).
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION buscar_hibrido_rrf(query_text TEXT, query_vector VECTOR(512),
                                              top_k INT DEFAULT 5, filtro_genero TEXT DEFAULT NULL,
                                              rrf_k INT DEFAULT 60, n_candidatos INT DEFAULT 50)
RETURNS TABLE (id INT, titulo TEXT, rank_lexico BIGINT, rank_semantico BIGINT, rrf_score FLOAT)
LANGUAGE sql STABLE AS $$
    WITH lexico AS (
        SELECT c.id, ROW_NUMBER() OVER (ORDER BY c.r DESC, c.id) AS rk
        FROM (
            SELECT l.id, ts_rank(l.fts_doc, consulta_or(query_text)) AS r
            FROM libros_sbert l
            WHERE l.fts_doc @@ consulta_or(query_text)
              AND (filtro_genero IS NULL OR filtro_genero = ANY(l.generos))
            ORDER BY r DESC, l.id
            LIMIT n_candidatos
        ) c
    ),
    semantico AS (
        SELECT c.id, ROW_NUMBER() OVER (ORDER BY c.d, c.id) AS rk
        FROM (
            SELECT l.id, l.embedding <=> query_vector AS d
            FROM libros_sbert l
            WHERE filtro_genero IS NULL OR filtro_genero = ANY(l.generos)
            ORDER BY d, l.id
            LIMIT n_candidatos
        ) c
    )
    SELECT l.id, l.titulo, lx.rk, se.rk,
           (coalesce(1.0 / (rrf_k + lx.rk), 0) + coalesce(1.0 / (rrf_k + se.rk), 0))::FLOAT AS score
    FROM lexico lx
    FULL OUTER JOIN semantico se ON se.id = lx.id
    JOIN libros_sbert l ON l.id = coalesce(lx.id, se.id)
    ORDER BY score DESC, l.id
    LIMIT top_k;
$$;
