# Estructura del RAG de logs de project-trucha

Este documento es el mapa completo del sistema de **RAG sobre logs**: qué hace cada pieza, en qué archivo vive y para qué se usa. Cubre tanto la parte **funcional** (el pipeline de los 6 pasos) como la **no funcional** (config, almacenamiento, infraestructura, calidad e interfaces).

> **Sistema dual.** `project-trucha` tiene dos RAGs que comparten `store`, `config` e interfaces: el **RAG de código** (indexado de repositorios → chunks → búsqueda híbrida → decisiones) y el **RAG de logs** (parseo → trazas → vector + grafo causal → respuesta). Este documento profundiza en el de **logs**; el de código se menciona solo donde comparte piezas.

---

## 1. Vista general

```
                  paso 0          pasos 1-2        paso 3                          paso 5      paso 6
logs.jsonl ──────────────┐                          ┌──▶ pgvector (traces) ──┐
                         ├──▶ eventos ─▶ trazas ──▶┤                        ├──▶ búsqueda ─▶ respuesta LLM
messy_logs.log ── parseo ┘  (resumen narrativo)     │   (embeddings 64d)     │   híbrida
                         paso 0  (causalidad/calidad)│                       │
                                                     └──▶ Neo4j (grafo causal)┘
                                                          nodos + CAUSED_BY
                                                              (paso 4)
```

| Paso | Nombre | Qué hace | Dónde |
| --- | --- | --- | --- |
| — | Generadores | Produce logs sintéticos: prolijos (`logs.jsonl`) y desprolijos (`messy_logs.log`) | `docs/ger/*.py` |
| 0 | Parseo y reparación | Convierte cualquier línea a schema unificado + `source_quality` | `src/trucha/logs/parse.py` |
| 1–2 | Reconstrucción de causalidad y resumen por traza | Agrupa eventos por `trace_id`, arma resumen narrativo, marca confiabilidad | `src/trucha/logs/trace.py` |
| 3 | Embeddings + vector store | Vectoriza el resumen y lo persiste en pgvector | `src/trucha/embed/`, `src/trucha/store/` |
| 4 | Grafo causal | Escribe nodos/relaciones de causa-efecto en Neo4j | `src/trucha/graph/` |
| 5 | Recuperación híbrida | Búsqueda semántica en pgvector + cadena causal desde el grafo | `src/trucha/services.py`, `src/trucha/retrieve/` |
| 6 | Capa de respuesta | Prompt con evidencia + respuesta del LLM (o fallback determinista) | `src/trucha/answer.py`, `src/trucha/llm/` |

---

## 2. Parte funcional — pipeline paso a paso

### Fuente de datos: los dos generadores

La virtud central del proyecto es trabajar con **dos calidades de entrada**: la misma transacción bien o mal estructurada.

| Archivo | Qué genera | En qué se diferencia |
| --- | --- | --- |
| `docs/ger/log_generator.py` | JSONL prolijo (`logs.jsonl`) | Schema fijo por línea, `event_id`, `caused_by` explícito, 50 `log_type` distintos. El parseo es `json.loads` directo → `source_quality="clean"`. |
| `docs/ger/messy_log_generator.py` | Texto desprolijo (`messy_logs.log`) | 5+ formatos mezclados por línea, timestamps incoherentes (sin año, epoch, logfmt…), niveles mal escritos, stack traces pegados, keys de trace variadas (`reqId`, `rid`, `'trc'`…). Toda línea conserva un trace_id compartido → `"repaired"` o `"low_confidence"`. |

Ambos emiten los mismos escenarios de negocio (consulta de usuario / pago) para poder comparar la ingesta de lo idéntico bien vs. mal estructurado.

### Paso 0 — Parseo y reparación (`src/trucha/logs/parse.py`)

Convierte una línea cruda al schema unificado
(`timestamp, trace_id, event_id, caused_by, service, level, message, user_id, payment_id, metadata, source_quality, timestamp_inferred`).

- `parse_line()` — **cascada de parsers**, en orden: `json.loads` (limpio) → `SLOPPY_RE` (dict de comilla simple) → `BARE_RE` (`[LEVEL] svc :: msg (user N, trc=...)`) → `STACK_RE` (stack trace pegado) → `SYSLOG_RE` (`ts host svc[pid]: lvl msg`) → logfmt (`_from_logfmt()`). Si nada matchea, la línea se descarta (`None`).
- `parse_timestamp()` — normaliza a ISO 8601 UTC. Detecta logfmt (`AugT16T04:20:18`, `16/08/2026T06:10`), epoch unix (`\d{9,}`), API voyante (con o sin tz), `Aug 15 09:47:15` y varios `strptime`. Sin año/hora → completa con la fecha de ingesta y marca `timestamp_inferred=true`.
- `normalize_level()` / `normalize_service()` — catálogos de sinónimos (`infoo→INFO`, `warn→WARN`, `api-gw→api-gateway`, …).
- `_extract_user()` / `_extract_payment()` — sacan `user_id` (regex multi-patrón) y `payment_id` (`pay_[0-9a-f]{8}`) del mensaje cuando el campo no viene explícito.
- `parse_file()` — recorre el archivo y degrada a `"low_confidence"` los eventos reparados sin `trace_id`.

### Pasos 1–2 — Trazas y resumen narrativo (`src/trucha/logs/trace.py`)

Agrupa los eventos normalizados por transacción y produce **el artefacto que se vectoriza**.

- `traces_from_events()` — orquesta: primero `_assign_fallback_traces()` (eventos sin trace_id, agrupados por `usuario+servicio` en ventana de 2 s, marca `"low_confidence"`), luego `_assign_synthetic_event_ids()` (da `event_id` determinista por hash blake2b de `trace|ordinal|timestamp|message` a los eventos que no lo tienen, para MERGEs idempotentes en el grafo).
- `_resolved_caused_by()` — causalidad: explícita en logs limpios (`causal_confidence=1.0`) o inferida como el evento anterior de la traza (`0.6`). Si toda la traza es inferida, degrada a `"repaired"`.
- `_worst_quality()` — el peor `source_quality` de la traza gana (`clean 3 > repaired 2 > low_confidence 1`): un solo evento reparado degrada la traza entera.
- `build_summary()` — resumen narrativo determinista con tipado de historia (`pago` / `usuario` / `infra` vía `_story_type()`), outcome (`infer_outcome()`: status code 200/4xx/5xx o nivel), monto y secuencia de eventos. Esto es lo que se vectoriza.
- `load_traces()` — atajo CLI: `parse_file` + `traces_from_events`.

### Paso 3 — Embeddings y vector store

- `src/trucha/embed/local.py::embed_text()` — embedding **local, determinista y sin dependencias**: cada token (regex `[\w.-]+`) suma a un bucket por hash blake2b con signo según un bit del digest, y el vector resultante se normaliza (64 dim por defecto). Nada sale de la máquina; es el certificado del principio *local-first*.
- `src/trucha/store/models.py::TraceModel` — tabla `traces`: `trace_id`, `summary`, `embedding VECTOR(64)`, `outcome`, `source_quality`, arrays de `services`/`levels`, `user_id`, `payment_id`, `status_code`, `source_path`, `event_count`. Único por `(source_path, trace_id)` → re-ingesta idempotente.
- `src/trucha/store/database.py` — engine async SQLAlchemy + `SessionFactory` + `get_session()`.
- `migrations/versions/0002_traces.py` — crea `traces` con índice HNSW de coseno sobre el embedding.

> **RAG de código que comparte el store:** en el mismo `models.py` viven `RepositoryModel`, `FileModel`, `ChunkModel` (con FTS `to_tsvector` e HNSW), `IndexRunModel` y `DecisionModel`; `services.py` tiene `create_repository`, `index_repository` y `hybrid_search` (fusión léxica + vectorial con RRF). Comparten tabla de conceptos pero son un pipeline ajeno a este documento.

### Paso 4 — Grafo causal (`src/trucha/graph/`)

Escribe en Neo4j el mapa causa-efecto de cada traza.

- `build.py` — funciones **puras** que devuelven queries Cypher (testeables sin Neo4j):
  - Nodos: `Trace` (con `source_quality`), `LogEvent`, y por PUT `Service`, `User`, `PaymentID`.
  - Relaciones: `CAUSED_BY` (causa→efecto, con `confidence` 1.0/0.6 en el arco), `PART_OF` (evento→traza), `EMITTED_BY` (evento→servicio), `INVOLVES` (traza→user/payment).
  - `build_trace_operations()` — arma todas las operaciones `{query, params}` de una traza.
- `client.py` — `GraphClient`: `connect()`/`open_graph()` (driver async), `sync_trace()`/`sync_traces()` (aplica las operaciones; el lote va en una sola transacción write), y `causal_chain()` — recupera la cadena `CAUSED_BY` de una traza en orden temporal con la confianza de cada eslabón (lo consume el Paso 5).

### Paso 5 — Recuperación híbrida (`src/trucha/services.py`)

- `hybrid_log_search()` — 1) embedding de la pregunta y búsqueda coseno en `traces.embedding` (pgvector, top-k); 2) opcionalmente entra al grafo con esos `trace_id` para pedir `causal_chain`; 3) arma el resultado final con `vector_score`, marca `low_confidence` si `source_quality != "clean"` y adjunta la cadena causal. **Degradación segura:** si el grafo falla, la búsqueda sigue devolviendo trazas con cadena vacía.
- `ingest_logs()` — Paso 3 de orquestación: parsea el archivo, genera trazas y las inserta (skip si ya existen por `source_path+trace_id`), con stats `sources/parsed/traces/inserted/skipped/errors`. Un archivo corrupto no aborta el resto.
- `src/trucha/retrieve/ranking.py::reciprocal_rank_fusion()` — RRF: fusiona rankings de distintos recuperadores en un score único (`∑ 1/(60+rank)`). Es la pieza que también usa `hybrid_search` del RAG de código.

### Paso 6 — Capa de respuesta (`src/trucha/answer.py` + `src/trucha/llm/`)

- `answer.py:answer_logs()` — recupera evidencia (`hybrid_log_search`), arma el prompt con `_build_prompt()` / `_format_evidence()` (traza, origen, niveles, servicios, status, resumen, cadena causal con confianza) instruyendo al modelo a marcar `[INFERIDA]/[REPARADA]` y citar la traza de cada dato.
- `llm/__init__.py` — `LLMProvider` (ABC, `complete(prompt)`), **`NoneProvider`** = fallback determinista que devuelve el contexto etiquetado sin API key (principio local-first), y `get_provider()` que resuelve `""→NoneProvider`, `openai`, `anthropic`.
- `llm/openai_provider.py` (`gpt-4o-mini`) y `llm/anthropic_provider.py` (`claude-3-5-haiku-latest`) — import diferido (dependencias opcionales), sistema "analista de observabilidad".

---

## 3. Interfaces

### CLI (`src/trucha/interface/cli.py`)

Entry point `trucha` (ver `pyproject.toml`). Subcomandos:

| Comando | Función |
| --- | --- |
| `trucha logs ingest PATH... [--graph]` | Pasos 0–3 (y 4 con `--graph`): parsea, vectoriza y escribe Neo4j |
| `trucha logs search QUERY [--limit N] [--graph]` | Paso 5: búsqueda híbrida (+ cadena causal si `--graph`) |
| `trucha logs answer QUERY [--limit N] [--graph]` | Paseo 6: respuesta con LLM o fallback |
| `trucha hello [name] [--agent]` / `trucha info` / `trucha hola-mundo` | Scaffold de integración (validación del ambiente) |
| `trucha mcp` | Levanta el servidor MCP por stdio |

### Servidor MCP (`src/trucha/interface/mcp.py`)

`trucha-mcp`, protocolo JSON-RPC por stdio. Solo expone tools del scaffold: `trucha_hello`, `trucha_project_info` y el prompt `hola-mundo`. Sin red ni claves — los comandos de logs **no** están expuestos por MCP hoy. Configuración cliente en `.mcp.json`.

### API FastAPI (`src/trucha/interface/api/`)

`trucha-api`, modulo `app.py` (builder `create_app()` + `app` global).

| Endpoint | Qué hace |
| --- | --- |
| `GET /health` | Liveness (SELECT 1 contra Postgres) |
| `POST /api/v1/logs/ingest` | `ingest_logs` (+ `sync_graph` opcional) |
| `POST /api/v1/logs/search` | `hybrid_log_search` (+ `sync_graph`` → cadena causal) |
| `POST /api/v1/logs/answer` | `answer_logs` |
| `POST /api/v1/repositories`, `POST /repositories/{id}/index`, `GET /index-runs/{id}` | RAG de código: alta e indexado incremental |
| `POST /api/v1/search` | RAG de código: búsqueda híbrida sobre chunks |
| `POST/GET /api/v1/decisions` | Memoria de decisiones (RAG de código) |

Los DTOs (Pydantic) están en `schemas.py` (`LogsIngestRequest`, `LogSearchRequest`, `AnswerRequest`, `TraceResult`, `CausalStep`, `AnswerResult`, …). El arranque por CLI está en `__main__.py` (`uvicorn`).

---

## 4. Parte no funcional

### Configuración (`src/trucha/config.py`)

`Settings` (pydantic-settings, prefijo `TRUCHA_`, `.env`):

| Variable | Default | Uso |
| --- | --- | --- |
| `TRUCHA_DATABASE_URL` | `postgresql+asyncpg://...` | Conexión async a PostgreSQL/pgvector |
| `TRUCHA_NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` | local | Grafo causal |
| `TRUCHA_EMBEDDING_DIMENSIONS` | `64` | Dimensiones del vector (debe coincidir con la migración) |
| `TRUCHA_CHUNK_SIZE_LINES` / `CHUNK_OVERLAP_LINES` | `80` / `10` | Chunking del RAG de código |
| `TRUCHA_ALLOWED_ROOTS` | cwd | Whitelist de raíces indexables (validada por `validate_repository_path`) |
| `TRUCHA_MAX_FILE_BYTES`, `SEARCH_CANDIDATE_LIMIT` | `1_000_000` / `40` | Límites de ingesta y de candidatos de búsqueda |
| `TRUCHA_LLM_PROVIDER` / `LLM_API_KEY` / `LLM_MODEL` | `""` | `""`=fallback, `openai`, `anthropic` |

`get_settings()` está cacheado (`lru_cache`).

### Almacenamiento y migraciones

- `src/trucha/store/database.py` — engine async (pool `pre_ping`), `Base(DeclarativeBase)`, `get_session()` para FastAPI.
- `migrations/versions/0001_initial.py` — extension `vector`, tablas del RAG de código (`repositories`, `files`, `chunks` con FTS Gin + HNSW, `index_runs`, `decisions`).
- `migrations/versions/0002_traces.py` — tabla `traces` + índice HNSW coseno.
- `migrations/env.py` + `alembic.ini` — configuración de Alembic.

### Infraestructura

| Archivo | Para qué se usa |
| --- | --- |
| `Dockerfile` | Imagen Python 3.12, instala el paquete e incluye entrypoint |
| `docker/entrypoint.sh` | Ejecuta `alembic upgrade head` antes de arrancar la API |
| `compose.yaml` | Orquesta `db` (pgvector/pgvector), `graph` (neo4j:5-community) y `api` (monta el repo ro en `/workspace`) |
| `compose.override.yaml` | Expone el puerto 5432 del Postgres para desarrollo local |
| `.env.example` | Plantilla de variables para despliegue |

### Calidad y tooling

- **Suite de pruebas** (`pytest`, 9 archivos, `asyncio_mode="auto"`):

| Archivo | Cubre |
| --- | --- |
| `tests/test_logs_trace.py` | Causalidad explícita 1.0, degradación `repaired`, causalidad inferida 0.6, event_id sintético determinista, peor calidad |
| `tests/test_log_search.py` | `hybrid_log_search` con/sin grafo, marca de `low_confidence`, cadena causal |
| `tests/test_answer.py` | Prompt con marcas de confianza, `answer_logs` con provider |
| `tests/test_graph_build.py` | Operaciones Cypher puras (sin Neo4j) |
| `tests/test_fastapi_core.py` | Endpoints de la API (health, repos, index, search) |
| `tests/test_cli.py`, `tests/test_mcp.py`, `tests/test_core.py`, `tests/test_config.py` | CLI, servidor MCP, `hello`/`project_info` y `Settings` |

- `pyproject.toml` — deps base (SQLAlchemy 2 async, asyncpg, pgvector, neo4j, fastapi, uvicorn, pydantic-settings, alembic), deps opcionales `dev` (pytest, httpx, ruff), entry points `trucha` / `trucha-mcp` / `trucha-api`, y config de `ruff` (ignora `B008` junto a FastAPI) y `pytest`. *Los SDKs de OpenAI/Anthropic son opcionales e importados en diferido.*
- Documentación cercana: `docs/ger/ingesta_hibrida.md` (diseño de los 6 pasos), `docs/ger/explicacion_facil.md` (analogía simple), `docs/despliegue-fastapi.md` (operación), `docs/adr/` (registro de decisiones), `README.md`.

---

## 5. Glosario

| Término | Significado |
| --- | --- |
| `source_quality` | Confiabilidad del dato de origen: `clean` (logueado prolijo), `repaired` (parseado de un log desprolijo), `low_confidence` (sin trace_id, agrupado por heurística) |
| `causal_confidence` | Peso de una relación cause→effect: `1.0` explícita (logs limpios), `0.6` inferida (orden temporal) |
| `timestamp_inferred` | El timestamp se completó con la fecha de ingesta (no viene en el log) |
| `RRF` (reciprocal rank fusion) | Fusión de rankings: `∑ 1/(60+rank)` sobre los resultados de distintos recuperadores |
| `event_id` sintético | Hash determinista blake2b (`trace|ordinal|timestamp|message`) para logs sin ID estable; permite `MERGE` idempotente en Neo4j |
| HNSW | Índice de aproximación para búsqueda vectorial por coseno en pgvector |
| `ingested_at` | Momento de ingesta; fecha usada para completar timestamps parciales |