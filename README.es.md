# callsheet

**Dejá en cada repo sólo lo que sirve, sin desinstalar nada.**

[English](README.md)

En un rodaje, la *call sheet* dice quién tiene que estar hoy en el set. El resto sigue en el elenco, listo para otro día.

Cada plugin, servidor MCP, conector de claude.ai y skill que instalás globalmente se carga en **todas** las sesiones de Claude Code, en todos los repos. Una app web no necesita tu servidor de Proxmox, tu plugin de pagos ni la skill de releases de otro cliente. Igual cuestan tokens y atención en cada sesión, y le tapan al modelo las skills que sí sirven.

`/callsheet` los apaga **sólo para el repo actual**. Cada cambio se revierte con un comando, y los demás repos quedan como estaban.

## Instalación

```bash
npx skills add PapiScholz/callsheet
```

Necesita Python 3.9 o superior (sólo librería estándar) y Claude Code.

## Uso

| Escribís | Hace |
|---|---|
| `/callsheet` | Hace el inventario de todo lo que se carga acá y arma el perfil del repo. Propone qué apagar, con una razón para cada elemento. Espera tu OK y lo aplica con backup |
| `/callsheet status` | Muestra qué está apagado acá y detecta si Claude Code reescribió su configuración |
| `/callsheet enable <nombre>` | Vuelve a prender un elemento, acá |
| `/callsheet restore` | Deshace todo lo que callsheet hizo en este repo |

Los cambios rigen desde la **próxima** sesión. Corré `/context` ahí para ver la diferencia.

## Qué cambia y dónde

Nada global. Todo usa interruptores por proyecto que Claude Code ya soporta:

| Elemento | Se apaga en |
|---|---|
| Plugins (incluidos los sincronizados desde claude.ai) | `<repo>/.claude/settings.local.json` → `enabledPlugins: false` |
| Servidores MCP de archivos `.mcp.json` (también los heredados de carpetas padre) | el mismo archivo → `disabledMcpjsonServers` |
| Tus skills | el mismo archivo → `skillOverrides: "user-invocable-only"`: el modelo no las ve y vos las seguís teniendo en el menú `/` |
| Servidores MCP de usuario y conectores de claude.ai | `~/.claude.json` → `disabledMcpServers` de este repo, la misma lista que escribe `/mcp` |

`settings.local.json` y el registro `callsheet.local.json` se agregan al `.gitignore`, porque describen tu máquina, no el proyecto. Antes de cada escritura se hace un backup verificado de los dos archivos.

Los hooks se listan pero no se tocan: Claude Code no tiene forma de apagar un hook suelto por repo.

## Por qué pregunta antes de apagar

El error barato es dejar una herramienta que no necesitás: unos cientos de tokens. El caro es sacar una que sí necesitás: el modelo no puede usar lo que no ve, y no te avisa.

callsheet está escrita contra ese segundo error. Antes de juzgar cada elemento, el modelo tiene que:
- leer la descripción completa del elemento;
- leer el punto de entrada del repo, el roadmap y el handoff, no sólo `package.json`;
- leer tus instrucciones globales, que pueden volver obligatorio un plugin.

Ante la duda, se mantiene y te pregunta. Razones como "no hace falta" o "se usa poco" están prohibidas.

## Combina con

[greenroom](https://github.com/PapiScholz/greenroom) oculta skills globalmente detrás de puertas; callsheet recorta por repo. callsheet nunca apaga una puerta de greenroom, y oculta las skills de la misma forma que greenroom.

## Desarrollo

```bash
python -m unittest discover tests
```

Los tests corren contra una carpeta de inicio falsa: tu `~/.claude.json` real nunca se toca.

## Licencia

MIT
