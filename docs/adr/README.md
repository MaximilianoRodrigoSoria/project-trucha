# Architecture Decision Records (ADR)

Este directorio guarda las decisiones de arquitectura del proyecto, una por archivo,
numeradas de forma incremental: `NNNN-titulo-en-kebab-case.md`.

La primera decision pendiente de cerrar es el **backend de memoria** (ver la seccion
"Decision tecnica" del README raiz): SQLite+FTS5 (+ sqlite-vec) vs ChromaDB / LanceDB /
pgvector. Cuando el equipo converja, se documenta como `0001-backend-de-memoria.md`.

Formato sugerido por ADR: Contexto -> Decision -> Alternativas evaluadas -> Consecuencias.
