# ¿Qué estamos armando? (explicado fácil)

Imaginate que tenés un edificio de oficinas gigante (tu sistema) y cada
oficina (cada servicio: login, pagos, base de datos, etc.) va anotando
en un cuaderno todo lo que hace: "llegó una visita", "se cayó el
ascensor", "se aprobó el pago de la sala 4". Eso son los **logs**.

El problema: cuando pasa algo raro (un pago que falla, un usuario que
no puede entrar), tenés miles de cuadernos y no sabés en cuál buscar,
ni cómo conectar "lo que pasó en la oficina 3" con "lo que pasó
después en la oficina 7". Este proyecto resuelve eso.

---

## Parte 1 — Los dos generadores de logs

### `log_generator.py` (el prolijo)

Simula un sistema **bien hecho**, donde cada anotación en el cuaderno
tiene siempre los mismos campos, en el mismo formato, y además dice
"esto pasó *porque* pasó tal otra cosa antes" (eso es la
**causalidad**: `caused_by`).

Simula dos casos reales:
- Alguien pide ver los datos de un usuario (`GET /api/users/123`).
- Alguien hace un pago (`POST /api/payments`).

En cada caso, el log va contando la historia paso a paso: llegó el
pedido → se validó el usuario → se buscó en caché → no estaba → se
buscó en la base de datos → se encontró → se respondió. Y a veces algo
falla en el medio (timeout, usuario no existe, tarjeta rechazada), y
eso también queda anotado con la causa exacta.

### `messy_log_generator.py` (el desprolijo)

Simula la realidad de **la mayoría de los sistemas reales**: cada
oficina anota las cosas como quiere. Una anota en un formato, otra en
otro, algunas ni le ponen fecha, otras escriben mal la palabra "error"
("Err", "ERROR", "errr"), y a veces alguien anota solo un garabato
ilegible.

Genera la misma clase de eventos (usuarios, pagos) pero mezclando:
- **6 formatos distintos por línea** (como si mezclaras notas en
  papel, mensajes de WhatsApp y capturas de pantalla, todo junto).
- **Fechas escritas de formas distintas** (algunas sin año, algunas
  como número raro tipo `1786808830`).
- **Sin ningún hilo conductor**: no hay forma directa de saber qué
  anotación causó cuál otra, hay que adivinarlo.

**¿Por qué generar algo "malo" a propósito?** Porque si tu sistema de
búsqueda solo funciona con datos prolijos, en la vida real no te va a
servir. La mayoría de las empresas tienen los logs desprolijos, no los
prolijos.

---

## Parte 2 — Qué significa "ingerir" esos logs

"Ingerir" quiere decir: tomar todos esos cuadernos desordenados y
convertirlos en algo que se pueda **preguntar en lenguaje natural**,
tipo "¿qué pasó con los pagos que fallaron esta tarde?" y que te
conteste con la explicación completa, no solo una lista de líneas
sueltas.

Para lograr eso hacen falta dos herramientas trabajando juntas:

- **Una base de datos vectorial**: convierte cada log (o resumen de
  una transacción) en una lista de números que representa su
  *significado*. Así podés buscar por parecido de sentido, no por
  palabra exacta. Es como poder decir "buscame algo parecido a esto"
  en vez de tener que saber la palabra exacta que se usó.
- **Un grafo**: guarda las conexiones entre eventos ("esto pasó
  *después de* esto otro", "este pago pertenece a este usuario"). Es
  como un mapa de causa y efecto. Sirve para responder "¿qué generó
  este error?" en vez de solo "¿qué se parece a este error?".

Usar las dos juntas (**híbrido**) es lo mejor: la vectorial encuentra
"por dónde buscar" y el grafo te da "la película completa de lo que
pasó".

---

## Parte 3 — El paso a paso, explicado como una receta

**Paso 0 — Ordenar el quilombo (solo logs desprolijos)**
Antes de nada, hay que "traducir" cada formato raro a un formato único
y prolijo. Es como si alguien tuviera que leer todas las notas
garabateadas y volver a escribirlas prolijas en un mismo cuaderno
nuevo. Los logs que ya venían prolijos (`logs.jsonl`) se saltan este
paso, ya están listos.

**Paso 1 — Reconstruir "quién causó qué"**
En los logs prolijos esto ya está anotado. En los desprolijos hay que
adivinarlo con pistas: "estos dos eventos son del mismo usuario y
pasaron con 2 segundos de diferencia, probablemente están conectados".

**Paso 2 — Armar el resumen de cada historia**
En vez de guardar cada anotación suelta, se arma un resumen tipo "el
usuario 1788 quiso pagar $1098, pasó los controles, pero el banco no
respondió a tiempo". Ese resumen es mucho más útil que 10 líneas
sueltas.

**Paso 3 — Guardar el "significado" (vectorial)**
Cada resumen se convierte en números (embedding) y se guarda para
poder buscar por parecido de sentido más adelante.

**Paso 4 — Guardar las conexiones (grafo)**
Se arma el mapa: qué evento generó cuál, a qué usuario/pago pertenece
cada cosa, en qué servicio pasó.

**Paso 5 — Buscar de las dos formas a la vez**
Cuando alguien pregunta algo, primero se busca por significado (Paso
3) para encontrar por dónde empezar, y después se usa el grafo (Paso
4) para traer toda la cadena de causa y efecto de esa historia.

**Paso 6 — Armar la respuesta final**
Con todo lo encontrado, se arma una respuesta en lenguaje natural que
explica qué pasó y por qué, no solo "acá hay unos logs parecidos".

---

## Por qué esto importa

El desafío real de este proyecto **no es la parte linda** (vectorizar
logs prolijos). El desafío real es el **Paso 0**: poder tomar
información desordenada, como la de casi cualquier empresa real, y
convertirla en algo confiable para buscar y razonar. Por eso conviene
practicar con las dos fuentes desde el principio.
