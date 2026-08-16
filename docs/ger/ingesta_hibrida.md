# Ingesta híbrida de logs (vector + grafo) — paso a paso

Este documento cubre cómo ingerir **ambas fuentes**: `logs.jsonl` (bien
estructurado, con causalidad explícita) y `messy_logs.log` (desprolijo,
sin estándar). La diferencia entre ambas define en qué punto del
pipeline entra cada una.

```
logs.jsonl  ────────────────────────────┐
                                          ├──▶ [normalización] ──▶ [enriquecimiento] ──▶ [vector DB + grafo] ──▶ [recuperación híbrida]
messy_logs.log ──▶ [parseo/reparación] ──┘
```

---

## Paso 0 — Parseo y reparación (SOLO para logs desprolijos)

Los logs limpios ya vienen en JSON con schema fijo, así que este paso
se salta para ellos. Para los desprolijos:

1. **Detección de formato por línea**: usar una cascada de parsers
   (regex para syslog, `logfmt` parser, `json.loads` con fallback).
   Si ninguno matchea, la línea va a una cola de "no parseable".
2. **Reparación de JSON casi válido**: comillas simples → dobles,
   comas colgantes, `null`/`None` — librerías como `json5` o un
   regex de limpieza antes de reintentar `json.loads`.
3. **Extracción asistida por LLM para el resto**: para las líneas que
   ningún parser estructurado puede resolver (stack traces pegados,
   prosa libre en español/inglés, ruido), usar un LLM barato con
   function calling para extraer: `timestamp`, `level`, `service`,
   `user_id`, `message`. Si el LLM no encuentra suficiente señal, la
   línea se descarta o se marca como `low_confidence`.
4. **Normalización de timestamps**: todos a UTC ISO 8601. Los formatos
   sin año o sin fecha se completan con la fecha de ingesta como
   fallback (y se marca `timestamp_inferred=true`).
5. **Normalización de niveles**: mapear `Info/info/INFOO/LOG` → `INFO`,
   `Warn/warning/WARNING` → `WARN`, etc., con un diccionario de
   sinónimos.

Salida de este paso: un JSON con el mismo shape que ya usa
`logs.jsonl` (`timestamp`, `service`, `level`, `message`, `metadata`),
más un campo `source_quality: "clean" | "repaired" | "low_confidence"`
para no perder el rastro de qué tan confiable es cada registro.

---

## Paso 1 — Reconstrucción de causalidad

- **Logs limpios**: ya traen `trace_id` / `caused_by`, no hay nada que
  hacer.
- **Logs desprolijos**: toda línea trae al menos un trace_id (siempre,
  aunque con nombre de campo y formato distintos por línea), compartido
  por las líneas de la misma transacción. Se agrupa directamente por
  `trace_id` una vez extraído en el Paso 0. La heurística de antes
  (mismo `user_id` + mismo `service` + ventana de tiempo corta) queda
  solo como fallback para líneas cuyo id no se logre parsear.

---

## Paso 2 — Chunking por traza

Agrupar los logs (ya normalizados) por `trace_id` (real o inferido) y
generar un resumen narrativo de la transacción completa en lenguaje
natural. Ejemplo: *"Usuario 1788 intentó un pago de $1098.36, pasó
validación y fraude, pero el gateway externo dio timeout tras un
reintento."*

Este resumen es lo que se vectoriza — da muchísimo mejor contexto
semántico que vectorizar cada línea suelta.

---

## Paso 3 — Embeddings + Vector DB

- Generar embedding del resumen narrativo (y opcionalmente de cada
  mensaje individual para búsquedas más finas).
- Guardar en Chroma/Qdrant con metadata: `trace_id`, `service`,
  `level`, `timestamp`, `status_code`, `source_quality`.
- El campo `source_quality` permite luego filtrar o ponderar resultados
  ("dame solo evidencia confiable" vs "dame todo lo que haya").

---

## Paso 4 — Construcción del grafo

Nodos: `Trace`, `LogEvent`, `Service`, `User`, `PaymentID`.
Relaciones: `CAUSED_BY` (explícita en logs limpios, inferida en los
desprolijos), `PART_OF` (log → trace), `EMITTED_BY` (log → service),
`INVOLVES` (trace → user/payment).

Para los logs desprolijos, cada relación `CAUSED_BY` inferida debería
guardar un peso/confianza (ej. `confidence: 0.6`), para que después la
recuperación pueda decidir si confiar en esa cadena causal o no.

---

## Paso 5 — Índice híbrido de recuperación

Ante una pregunta en lenguaje natural:

1. Búsqueda semántica en el vector store → top-k trazas relevantes.
2. Con esos `trace_id`, entrar al grafo y traer la cadena causal
   completa (qué pasó antes/después, en qué servicio).
3. Si hay trazas de `source_quality: low_confidence` en el resultado,
   marcarlas visualmente distinto en la respuesta final (no ocultarlas,
   pero sí avisar que son inferidas).

---

## Paso 6 — Capa de respuesta ("el rack")

Un LLM recibe: la pregunta + los resúmenes narrativos recuperados + el
subgrafo causal, y arma la respuesta explicando causa-raíz, citando
de qué fuente salió cada dato (limpia vs. reparada vs. inferida).

---

## Por qué importa tener las dos fuentes

Este es el punto central del ejercicio: un pipeline de ingesta que solo
funciona con `logs.jsonl` es un pipeline de laboratorio. El valor real
está en el Paso 0 — ahí es donde se juega si el sistema sirve en
producción real, porque en la vida real casi nadie tiene logs tan
prolijos como los del primer generador.
