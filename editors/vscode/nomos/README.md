# Nomos para VS Code

Soporte del lenguaje **Nomos** (archivos `.game`) de [GameHub](../../../README.md):

- **Resaltado** de sintaxis (gramática TextMate): palabras clave, tipos de nodo, nombres de nodos,
  acciones y funciones, anotaciones (`@visible`…), comentarios de documentación (`///`).
- **Diagnósticos** de `gamehub check` al abrir y al guardar: errores y avisos con su posición,
  nota y ayuda, también los de los módulos importados.
- **Formato** con `gamehub fmt` (*Dar formato al documento*, o al guardar si tienes
  `editor.formatOnSave`).
- Comentarios, corchetes, sangría automática y continuación de `///` al pulsar Intro.

## Instalación

Hace falta `gamehub` (el paquete Python de este repositorio). Para probar la extensión sin
empaquetarla:

```bash
ln -s "$PWD" ~/.vscode/extensions/gamehub.nomos-0.1.0
```

(desde este directorio) y reinicia VS Code. Para empaquetarla: `npx @vscode/vsce package` y
`code --install-extension nomos-0.1.0.vsix`.

## Ajustes

| Ajuste | Por defecto | Qué hace |
|---|---|---|
| `nomos.command` | `["gamehub"]` | Cómo ejecutar gamehub. En el repositorio de GameHub: `["uv", "run", "--project", "python", "gamehub"]`. |
| `nomos.checkOnSave` | `true` | Comprueba el archivo al abrirlo y al guardarlo. |

El comando **Nomos: comprobar el juego** lo comprueba en cualquier momento.
