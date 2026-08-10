# Conectar project-trucha con agentes de terminal

Esta guía deja a Yoel y Gerardo Lopez con una instalación mínima funcional para usar
project-trucha desde la terminal o como servidor MCP local. No requiere Docker,
servicios remotos ni claves de API.

## 1. Instalar el proyecto

Desde la raíz del repositorio, con Python 3.11 o superior:

```bash
python -m venv .venv
```

Activar el entorno:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
source .venv/bin/activate
```

Instalar en modo editable:

```bash
python -m pip install -e .
```

Comprobar la capa CLI:

```bash
trucha hello Joel --agent terminal
trucha --json info
```

La primera orden debe responder que la memoria de project-trucha está despierta.

También se puede probar la bienvenida compartida:

```bash
trucha hola-mundo
```

## 2. Conectar Codex

Codex acepta servidores MCP locales por `stdio`:

```bash
codex mcp add project-trucha -- trucha-mcp
codex mcp list
```

Dentro de Codex, ejecutar `/mcp` y pedir:

```text
Usá trucha_hello para saludar a Joel desde Codex.
```

O ejecutar `/hola-mundo` y seleccionar el prompt MCP `hola-mundo` de
`project-trucha`. La respuesta esperada es:

```text
Hola truchos, bienvenidos a project-trucha
```

Codex CLI, la aplicación de escritorio y la extensión comparten la misma
configuración del host. Si se prefiere alcance por proyecto, también puede
declararse el servidor en `.codex/config.toml` dentro de un proyecto confiable.

## 3. Conectar Claude Code

El repositorio ya incluye `.mcp.json` con alcance de proyecto. Después de
instalar `trucha-mcp`, abrir Claude Code desde la raíz:

```bash
claude
```

Claude pedirá aprobar el servidor compartido la primera vez. Verificar con:

```text
/mcp
```

Alternativamente, registrarlo por comando:

```bash
claude mcp add --transport stdio --scope project project-trucha -- trucha-mcp
claude mcp list
```

Luego pedir:

```text
Usá trucha_hello para saludar a Gerardo Lopez desde Claude.
```

## 4. Conectar OpenCode

El archivo `opencode.json` ya declara el servidor local. Abrir OpenCode desde la
raíz del repositorio y comprobarlo:

```bash
opencode mcp list
opencode
```

Luego pedir:

```text
Usá la herramienta trucha_hello y saludá a Joel desde OpenCode.
```

## 5. Herramientas MCP disponibles

| Herramienta | Uso |
|---|---|
| `trucha_hello` | Comprueba la conexión y devuelve un saludo estructurado. |
| `trucha_project_info` | Devuelve versión, interfaces y capacidades actuales. |

El servidor también publica el prompt MCP `hola-mundo`, pensado como bienvenida
rápida para verificar la importación del proyecto.

La implementación está en `src/trucha/interface/mcp.py`. Usa JSON-RPC por
entrada/salida estándar y no accede a la red ni ejecuta comandos recibidos del
modelo.

## 6. Desarrollo y pruebas

```bash
python -m unittest discover -s tests -v
```

También se puede iniciar el servidor manualmente con `trucha mcp` o
`trucha-mcp`. En una terminal quedará esperando mensajes por `stdin`; eso es el
comportamiento normal de un servidor MCP `stdio`.

## Fuentes oficiales

- Codex MCP: https://developers.openai.com/codex/mcp
- Claude Code MCP: https://code.claude.com/docs/en/mcp
- OpenCode MCP: https://dev.opencode.ai/docs/mcp-servers/
