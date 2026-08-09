# Alternativas para el stack de Project Trucha

> [!WARNING]
> **Decisión pendiente para Gerard y Yoel.** Este documento compara caminos
> posibles, pero no reemplaza el ADR de arquitectura. Antes de implementar el
> núcleo deben acordar qué optimizar primero: simplicidad local, velocidad,
> familiaridad del equipo o capacidad de crecer como servicio.

<p align="center">
  <a href="#1-python--sqlite-fts5--sqlite-vec"><img src="img/stack-python-sqlite.svg" width="190" alt="Python y SQLite"></a>
  <a href="#2-typescript--nodejs--lancedb"><img src="img/stack-typescript-lancedb.svg" width="190" alt="TypeScript y LanceDB"></a>
  <a href="#3-rust--tantivy--qdrant-edge"><img src="img/stack-rust-tantivy.svg" width="190" alt="Rust y Tantivy"></a>
</p>
<p align="center">
  <a href="#4-kotlinjvm--apache-lucene"><img src="img/stack-kotlin-lucene.svg" width="190" alt="Kotlin y Lucene"></a>
  <a href="#5-go--bleve--qdrant"><img src="img/stack-go-bleve.svg" width="190" alt="Go y Bleve"></a>
  <a href="#6-python--fastapi--postgresql--pgvector"><img src="img/stack-python-pgvector.svg" width="190" alt="Python y pgvector"></a>
</p>

## Objetivo común

Las seis alternativas buscan construir el mismo producto:

- indexado incremental de repositorios;
- búsqueda léxica y semántica;
- memoria local de decisiones;
- CLI y servidor MCP para agentes;
- operación local-first con un camino razonable de evolución.

## Comparación rápida

| # | Alternativa | Despliegue | Fortaleza principal | Complejidad inicial |
|---|---|---|---|---|
| 1 | Python + SQLite | Archivo local | Velocidad de desarrollo | Baja |
| 2 | TypeScript + LanceDB | Directorio local | Ecosistema de agentes | Baja–media |
| 3 | Rust + Tantivy + Qdrant Edge | Binario local | Rendimiento y portabilidad | Alta |
| 4 | Kotlin/JVM + Lucene | JVM local | Búsqueda léxica madura | Media–alta |
| 5 | Go + Bleve + Qdrant | Binario + proceso opcional | Operación simple | Media |
| 6 | Python/FastAPI + PostgreSQL/pgvector | Servicio | Colaboración y escala | Alta |

## 1. Python + SQLite FTS5 + sqlite-vec

**Componentes:** Python 3.11+, SQLite/FTS5, `sqlite-vec`, SDK MCP de Python,
Typer o `argparse` para CLI.

```mermaid
flowchart LR
    R["Repositorio local"] --> I["Python · walker y chunker"]
    I --> L["SQLite FTS5 · índice léxico"]
    I --> E["Modelo de embeddings"]
    E --> V["sqlite-vec · índice vectorial"]
    L --> F["Fusión híbrida · RRF"]
    V --> F
    F --> C["Core de Project Trucha"]
    C --> CLI["CLI"]
    C --> MCP["Servidor MCP stdio"]

    classDef input fill:#143A7E,color:#fff,stroke:#5B9BD5,stroke-width:2px;
    classDef process fill:#075985,color:#fff,stroke:#22D3EE,stroke-width:2px;
    classDef storage fill:#064E3B,color:#fff,stroke:#02ECB6,stroke-width:2px;
    classDef output fill:#4C1D95,color:#fff,stroke:#C4B5FD,stroke-width:2px;
    class R input;
    class I,E,F,C process;
    class L,V storage;
    class CLI,MCP output;
```

### Pros

- Menor cambio respecto del scaffold actual.
- Un solo archivo de datos, fácil de copiar, respaldar y eliminar.
- FTS5 ofrece búsqueda full-text integrada en SQLite.
- Excelente para experimentar con chunking, ranking y embeddings.
- Sin servidor ni Docker para el caso individual.

### Contras

- El paralelismo de escritura y la escala multiusuario son limitados.
- `sqlite-vec` agrega una extensión nativa que debe distribuirse por plataforma.
- Python exige cuidar tiempos de arranque y empaquetado si se busca un binario.

**Elegirla si:** la prioridad es entregar el MVP local-first rápidamente.

## 2. TypeScript + Node.js + LanceDB

**Componentes:** TypeScript, Node.js, LanceDB embebido, SDK MCP de TypeScript,
Commander o oclif para CLI.

```mermaid
flowchart LR
    R["Repositorio local"] --> N["Node.js · TypeScript"]
    N --> P["Parser y chunker"]
    P --> L["LanceDB · full-text"]
    P --> E["Proveedor de embeddings"]
    E --> V["LanceDB · vectores"]
    L --> H["Búsqueda híbrida"]
    V --> H
    H --> S["Servicio TypeScript"]
    S --> CLI["Commander / oclif"]
    S --> MCP["SDK MCP TypeScript"]

    classDef input fill:#1E3A8A,color:#fff,stroke:#60A5FA,stroke-width:2px;
    classDef process fill:#164E63,color:#fff,stroke:#22D3EE,stroke-width:2px;
    classDef storage fill:#0F766E,color:#fff,stroke:#5EEAD4,stroke-width:2px;
    classDef output fill:#581C87,color:#fff,stroke:#E879F9,stroke-width:2px;
    class R input;
    class N,P,E,H,S process;
    class L,V storage;
    class CLI,MCP output;
```

### Pros

- El SDK MCP de TypeScript está en el nivel principal de soporte oficial.
- Buen encaje con herramientas de agentes, editores y extensiones web.
- LanceDB es embebido y dispone de APIs JavaScript para búsqueda vectorial.
- Una misma base de lenguaje puede sostener CLI, MCP y una futura interfaz web.

### Contras

- Distribuir Node y dependencias nativas pesa más que un binario único.
- La búsqueda léxica y el ajuste fino de ranking requieren validar la madurez
  concreta del camino elegido en LanceDB.
- El ecosistema npm amplía la superficie de mantenimiento y supply chain.

**Elegirla si:** Gerard y Yoel quieren priorizar integración con agentes y web.

## 3. Rust + Tantivy + Qdrant Edge

**Componentes:** Rust, Tantivy para índice invertido, Qdrant Edge para vectores,
SDK MCP de Rust, Clap para CLI.

```mermaid
flowchart LR
    R["Repositorio local"] --> W["Rust · scanner paralelo"]
    W --> T["Tantivy · índice invertido"]
    W --> E["Runtime de embeddings"]
    E --> Q["Qdrant Edge · vectores"]
    T --> F["Fusión y reranking"]
    Q --> F
    F --> B["Binario Project Trucha"]
    B --> CLI["Clap CLI"]
    B --> MCP["Servidor MCP Rust"]

    classDef input fill:#431407,color:#fff,stroke:#FB923C,stroke-width:2px;
    classDef process fill:#7C2D12,color:#fff,stroke:#FDBA74,stroke-width:2px;
    classDef storage fill:#3F6212,color:#fff,stroke:#A3E635,stroke-width:2px;
    classDef output fill:#312E81,color:#fff,stroke:#A5B4FC,stroke-width:2px;
    class R input;
    class W,E,F,B process;
    class T,Q storage;
    class CLI,MCP output;
```

### Pros

- Binario portable, rápido y con bajo consumo en ejecución.
- Tantivy está diseñado como motor de búsqueda full-text inspirado en Lucene.
- Qdrant Edge apunta a búsqueda vectorial embebida y offline.
- Buen control de memoria, concurrencia y formatos de almacenamiento.

### Contras

- Mayor curva de aprendizaje y más tiempo hasta el primer MVP.
- El SDK MCP de Rust tiene menor nivel de madurez que Python y TypeScript.
- Integrar dos índices exige diseñar sincronización, recuperación y fusión.

**Elegirla si:** el artefacto final debe ser un binario veloz y autosuficiente.

## 4. Kotlin/JVM + Apache Lucene

**Componentes:** Kotlin, JVM 21+, Apache Lucene para texto y vectores, SDK MCP
de Kotlin o implementación del protocolo, Clikt para CLI.

```mermaid
flowchart LR
    R["Repositorio local"] --> K["Kotlin · JVM 21+"]
    K --> P["Parser y chunker"]
    P --> TXT["Lucene · BM25"]
    P --> E["Modelo de embeddings"]
    E --> KNN["Lucene · KNN vectors"]
    TXT --> H["Consulta híbrida Lucene"]
    KNN --> H
    H --> D["Capa de dominio Kotlin"]
    D --> CLI["Clikt CLI"]
    D --> MCP["Adaptador MCP"]

    classDef input fill:#4C1D95,color:#fff,stroke:#C4B5FD,stroke-width:2px;
    classDef process fill:#831843,color:#fff,stroke:#F9A8D4,stroke-width:2px;
    classDef storage fill:#1E3A8A,color:#fff,stroke:#93C5FD,stroke-width:2px;
    classDef output fill:#134E4A,color:#fff,stroke:#5EEAD4,stroke-width:2px;
    class R input;
    class K,P,E,H,D process;
    class TXT,KNN storage;
    class CLI,MCP output;
```

### Pros

- Lucene es un motor full-text maduro con soporte de búsqueda vectorial.
- Excelente observabilidad, profiling, concurrencia y tooling del ecosistema JVM.
- Cercano a la experiencia Java/Spring del equipo.
- Un único motor puede reducir la duplicación entre ranking léxico y vectorial.

### Contras

- La JVM aumenta tamaño de distribución y tiempo de arranque frente a Go/Rust.
- La API de Lucene es de bajo nivel y requiere una capa de dominio cuidada.
- El SDK MCP de Kotlin figura con madurez todavía por definir.

**Elegirla si:** se prioriza experiencia JVM y control profundo del buscador.

## 5. Go + Bleve + Qdrant

**Componentes:** Go, Bleve para full-text, Qdrant local o remoto para vectores,
implementación MCP compatible, Cobra para CLI.

```mermaid
flowchart LR
    R["Repositorio local"] --> G["Go · scanner concurrente"]
    G --> B["Bleve · full-text"]
    G --> E["Cliente de embeddings"]
    E --> Q["Qdrant · vectores"]
    B --> F["Rank fusion"]
    Q --> F
    F --> S["Servicio Go"]
    S --> CLI["Cobra CLI"]
    S --> MCP["Servidor MCP compatible"]

    classDef input fill:#0C4A6E,color:#fff,stroke:#38BDF8,stroke-width:2px;
    classDef process fill:#115E59,color:#fff,stroke:#2DD4BF,stroke-width:2px;
    classDef storage fill:#365314,color:#fff,stroke:#A3E635,stroke-width:2px;
    classDef output fill:#5B21B6,color:#fff,stroke:#C4B5FD,stroke-width:2px;
    class R input;
    class G,E,F,S process;
    class B,Q storage;
    class CLI,MCP output;
```

### Pros

- Compilación rápida y distribución sencilla como binario.
- Bleve ofrece indexado y búsqueda full-text nativos en Go.
- Buen modelo de concurrencia para indexar muchos archivos.
- Qdrant permite comenzar localmente y evolucionar hacia un servicio dedicado.

### Contras

- No hay un SDK oficial de MCP Tier 1 para Go en la matriz consultada.
- Dos motores implican consistencia, backups y fusión de rankings.
- Menos librerías de embeddings locales que Python.

**Elegirla si:** se busca operación sencilla y un servicio pequeño y concurrente.

## 6. Python + FastAPI + PostgreSQL + pgvector

**Componentes:** Python, FastAPI, PostgreSQL full-text, pgvector, SDK MCP de
Python, Alembic para migraciones.

```mermaid
flowchart LR
    R["Repositorios del equipo"] --> API["FastAPI · API de ingestión"]
    API --> W["Workers de indexado"]
    W --> TXT["PostgreSQL · full-text"]
    W --> E["Servicio de embeddings"]
    E --> V["pgvector · HNSW / IVFFlat"]
    TXT --> SQL["Consulta híbrida SQL"]
    V --> SQL
    SQL --> CORE["Servicio Project Trucha"]
    CORE --> MCP["Servidor MCP"]
    CORE --> CLI["CLI remota"]
    CORE --> TEAM["Gerard y Yoel"]

    classDef input fill:#172554,color:#fff,stroke:#60A5FA,stroke-width:2px;
    classDef process fill:#312E81,color:#fff,stroke:#A5B4FC,stroke-width:2px;
    classDef storage fill:#581C87,color:#fff,stroke:#E879F9,stroke-width:2px;
    classDef output fill:#064E3B,color:#fff,stroke:#34D399,stroke-width:2px;
    class R input;
    class API,W,E,SQL,CORE process;
    class TXT,V storage;
    class MCP,CLI,TEAM output;
```

### Pros

- Datos, metadatos y vectores bajo transacciones ACID.
- pgvector soporta búsqueda exacta y aproximada con índices HNSW e IVFFlat.
- Adecuado para equipos, permisos, auditoría y múltiples repositorios.
- Camino claro hacia despliegue centralizado y copias de seguridad maduras.

### Contras

- Contradice el objetivo de cero infraestructura para el usuario individual.
- Requiere servidor, migraciones, credenciales y operación continua.
- Mayor latencia y más piezas que diagnosticar que una solución embebida.

**Elegirla si:** el producto nace como memoria compartida o multiusuario.

## Recomendación para el primer corte

> [!TIP]
> Para validar el producto, comenzar con **Alternativa 1: Python + SQLite**.
> Mantener `store` detrás de una interfaz y preparar pruebas contractuales. Si
> los benchmarks muestran límites reales, comparar primero LanceDB y Lucene; si
> aparece colaboración multiusuario, evaluar PostgreSQL/pgvector.

## Preguntas que debe responder el ADR

1. ¿El índice debe poder copiarse como un único archivo?
2. ¿Cuántos repositorios y fragmentos debe soportar el MVP?
3. ¿Habrá más de un proceso escribiendo al mismo tiempo?
4. ¿Los embeddings deben generarse completamente offline?
5. ¿Qué pesa más: recall, latencia, tamaño o simplicidad operativa?
6. ¿El servidor MCP será siempre local o también remoto?
7. ¿Qué stack pueden mantener Gerard y Yoel durante los próximos doce meses?

## Fuentes técnicas

- [SQLite FTS5](https://www.sqlite.org/fts5.html)
- [SDK oficiales de MCP](https://modelcontextprotocol.io/docs/sdk)
- [LanceDB](https://docs.lancedb.com/faq/faq-oss)
- [Tantivy](https://docs.rs/tantivy/latest/tantivy/)
- [Qdrant](https://qdrant.tech/documentation/)
- [Apache Lucene](https://lucene.apache.org/)
- [Bleve](https://blevesearch.com/)
- [pgvector](https://github.com/pgvector/pgvector)
