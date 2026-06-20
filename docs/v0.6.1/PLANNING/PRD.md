# PRD — ouroborOS v0.6.1: Gestor de Dotfiles `our-dots`

**Versión:** 1.1  
**Fecha:** 2026-06-07  
**Autor:** ouroborOS dev team  
**Estado:** Aprobado  

> **Revisión 1.1:** Aplicados 4 CRITICAL + 13 IMPORTANT + 8 MINOR del Ciclo de Review 1.  
> Cambios principales: política `--noconfirm`/CRITICAL unificada (`OUROBOROS_ALLOW_CRITICAL=1`), CU-23/24/25 añadidos, schema de manifest (§6.8), glosario (§14), terminología de canales estandarizada (`git`), protección de concurrencia en `system.yaml`, validación de schema para repos externos.

---

## Tabla de Contenidos

1. [Resumen Ejecutivo](#1-resumen-ejecutivo)
2. [Objetivos](#2-objetivos)
3. [Stakeholders](#3-stakeholders)
4. [User Stories](#4-user-stories)
5. [Casos de Uso](#5-casos-de-uso)
6. [Catálogo de Packs](#6-catálogo-de-packs)
7. [Agradecimientos](#7-agradecimientos)
8. [Métricas de Éxito](#8-métricas-de-éxito)
9. [Stack Tecnológico](#9-stack-tecnológico)
10. [Riesgos y Mitigaciones](#10-riesgos-y-mitigaciones)
11. [Scope y No-Scope](#11-scope-y-no-scope)
12. [Criterios de Aceptación Global](#12-criterios-de-aceptación-global)
13. [Dependencias y Restricciones](#13-dependencias-y-restricciones)
14. [Glosario](#14-glosario)

---

## 1. Resumen Ejecutivo

ouroborOS v0.6.1 introduce **`our-dots`**: un gestor de packs de dotfiles y configuración de escritorio que permite a los usuarios instalar entornos de ricing curados con un único comando, respetando la inmutabilidad del sistema de archivos raíz (Btrfs read-only).

El sistema Linux en general, y la comunidad Arch Linux en particular, cuenta con proyectos de ricing de alta calidad mantenidos activamente — desde shells de escritorio hasta configuraciones completas de entorno — que son utilizados por cientos de miles de usuarios. Sin embargo, ninguno de estos proyectos ofrece integración automatizada con instaladores de sistemas inmutables.

`our-dots` cierra esa brecha. Siguiendo la filosofía de la familia `our-*` (interfaz consistente, integración con `system.yaml` como fuente de verdad, soporte de canales stable/git), el gestor expone 7 packs curados con metadatos de compatibilidad explícitos, flujos de confirmación diferenciados por nivel de riesgo, y un sistema de repositorios externos extensible.

La feature es la primera de la Fase 6 y actúa como puente entre la infraestructura inmutable de v0.6.0 y el instalador con selección de packs que llegará en v0.7.0.

---

## 2. Objetivos

### 2.1 Objetivos Primarios

- Implementar `our-dots` como herramienta CLI completa, integrada en la familia `our-*`.
- Proveer un catálogo de 7 packs curados con manifests YAML estructurados.
- Integrar `our-dots` con `system.yaml` para persistencia declarativa del estado.
- Garantizar que todos los packs puedan instalarse sin violar la política de inmutabilidad, o bien informar explícitamente cuando se requieren excepciones temporales.
- Incluir flujos de confirmación diferenciados: `low/medium` silencioso, `high` con aviso, `critical` con panel de advertencia y confirmación textual.

### 2.2 Objetivos Secundarios

- Exponer el catálogo en el instalador Textual TUI como paso opcional post-instalación.
- Proveer un sistema de repositorios externos (`repo-add/remove/list/update`) para packs de la comunidad.
- Documentar los créditos y licencias de cada pack de forma formal.
- Mantener ≥ 93 % de cobertura de tests en `dots_profiles.py` y casos relacionados.

### 2.3 No-Objetivos

- **No** se implementa un gestor de temas gráfico con GUI propia en v0.6.1.
- **No** se automatizan actualizaciones OTA de packs sin intervención del usuario.
- **No** se provee rollback automático de packs (la restauración usa `our-rollback` sobre snapshots Btrfs existentes).
- **No** se soporta instalación simultánea de múltiples packs CRITICAL en una sola invocación.
- **No** se modifica la estructura de `system.yaml` más allá de agregar la clave `dots_packs`.

---

## 3. Stakeholders

| Rol | Descripción | Interés Principal |
|-----|-------------|-------------------|
| **Usuario final — entusiasta** | Usuario técnico que conoce ricing y quiere un flujo estructurado | Instalar su pack favorito sin seguir 5 guías distintas |
| **Usuario final — principiante** | Usuario nuevo que quiere un escritorio hermoso sin investigación | Catálogo curado, instrucciones claras, sin sorpresas |
| **Mantenedor del proyecto** | dev team ouroborOS | Mantener integridad del sistema inmutable, deuda técnica baja |
| **Creadores de packs** | Stephan Raabe, noctalia-dev, soramane, end-4, DHH/37signals, Axenide, AvengeMedia | Visibilidad, atribución correcta, feedback de usuarios |
| **Comunidad de ricing** | Usuarios de Hyprland/Niri en Arch Linux | Adopción del estándar de manifests YAML |
| **CI/CD** | GitHub Actions | Tests pasando, cobertura mantenida, ISO construible |

---

## 4. User Stories

### US-01 — Descubrir packs disponibles
**Rol:** Usuario entusiasta  
**Historia:** Como usuario, quiero listar todos los packs disponibles con su compatibilidad y estado de instalación, para decidir cuál instalar.  
**Criterios de aceptación:**
- `our-dots list` muestra tabla con nombre, DE compatible, nivel de compatibilidad, canal y estado instalado.
- La tabla incluye packs de repositorios externos si están configurados; estos se marcan con `[EXTERN]`.
- Los packs instalados muestran su versión, no un guión.
**Prioridad:** Must  
**Dependencias:** —

### US-02 — Ver información detallada de un pack
**Rol:** Usuario entusiasta  
**Historia:** Como usuario, quiero ver la descripción completa, créditos, homepage y canales de un pack antes de instalarlo, para tomar una decisión informada.  
**Criterios de aceptación:**
- `our-dots -Si <id>` muestra nombre, descripción completa, autor, homepage, docs, nivel de inmutabilidad y canales disponibles.
- Si está instalado, muestra versión instalada y fecha.
- Muestra la nota de compatibilidad si existe.
**Prioridad:** Must  
**Dependencias:** US-01

### US-03 — Instalar un pack en canal stable
**Rol:** Usuario entusiasta  
**Historia:** Como usuario, quiero instalar un pack con un solo comando y que el sistema me guíe por el proceso, para no tener que seguir instrucciones manuales.  
**Criterios de aceptación:**
- `our-dots -S <id>` muestra info del pack, solicita confirmación, instala dependencias y ejecuta post_deploy.
- Si el pack tiene canal git además de stable, el flujo ofrece selección interactiva.
- El estado queda registrado en `system.yaml` tras instalación exitosa.
- Se genera log en `/var/log/our-dots/<id>-<timestamp>.log`.
**Prioridad:** Must  
**Dependencias:** US-02

### US-04 — Instalar un pack en canal git
**Rol:** Usuario avanzado  
**Historia:** Como usuario que quiere la última versión, quiero poder elegir el canal git de un pack, para tener las features más recientes aunque sean menos estables.  
**Criterios de aceptación:**
- `our-dots -S <id> --git` fuerza canal git sin menú de selección.
- Se registra `channel: git` en `system.yaml`.
- El canal git solo está disponible si el manifest define `variants.git`.
**Prioridad:** Should  
**Dependencias:** US-03

### US-05 — Instalar un pack CRITICAL con confirmación explícita
**Rol:** Usuario avanzado  
**Historia:** Como usuario, quiero que el sistema me advierta claramente cuando un pack va a modificar el sistema de forma invasiva, para no ser sorprendido por cambios irreversibles.  
**Criterios de aceptación:**
- Los packs `critical` muestran panel rojo con lista de acciones antes de proceder.
- El usuario debe tipear exactamente "yes" (no "y") para confirmar.
- Si el usuario no confirma, la instalación se cancela sin efectos secundarios.
- El flag `--noconfirm` es **ignorado** para packs `critical`. La única forma de automatizar la instalación de packs CRITICAL es mediante `OUROBOROS_ALLOW_CRITICAL=1`.
**Prioridad:** Must  
**Dependencias:** US-03

### US-06 — Eliminar un pack instalado
**Rol:** Usuario entusiasta  
**Historia:** Como usuario, quiero poder desinstalar un pack cuando ya no lo necesite, para mantener mi sistema limpio.  
**Criterios de aceptación:**
- `our-dots -R <id>` solicita confirmación, elimina paquetes y ejecuta `post_remove`.
- El registro es eliminado de `system.yaml`.
- Si el manifest no existe pero el pack está en `system.yaml`, muestra mensaje de eliminación manual.
**Prioridad:** Must  
**Dependencias:** US-03

### US-07 — Consultar packs instalados
**Rol:** Usuario entusiasta  
**Historia:** Como usuario, quiero ver qué packs tengo instalados actualmente con su canal y fecha de instalación, para mantener un inventario de mis personalizaciones.  
**Criterios de aceptación:**
- `our-dots -Q` lista todos los packs en `system.yaml.dots_packs`.
- Muestra ID, canal, y fecha de instalación.
- Si no hay packs instalados, muestra mensaje informativo.
**Prioridad:** Must  
**Dependencias:** US-03

### US-08 — Buscar packs por patrón
**Rol:** Usuario entusiasta  
**Historia:** Como usuario, quiero buscar packs por nombre o descripción, para encontrar opciones relacionadas con mis preferencias.  
**Criterios de aceptación:**
- `our-dots -Qs <patrón>` filtra el listado de forma case-insensitive sobre ID, nombre y descripción.
- Si no hay coincidencias, no muestra error sino resultado vacío.
- Sin argumento, `our-dots -Qs` muestra el catálogo completo.
**Prioridad:** Should  
**Dependencias:** US-01

### US-09 — Actualizar packs instalados
**Rol:** Usuario entusiasta  
**Historia:** Como usuario, quiero poder actualizar todos mis packs a las últimas versiones disponibles, para mantenerlos al día.  
**Criterios de aceptación:**
- `our-dots -Su` itera sobre packs instalados y compara versión actual con disponible.
- Packs basados en AUR usan la API de AUR para detección de actualizaciones.
- Packs sin mecanismo de actualización automática muestran mensaje de reinstalación manual.
- El log de actualización se guarda correctamente.
**Prioridad:** Should  
**Dependencias:** US-07

### US-10 — Agregar repositorio externo
**Rol:** Usuario avanzado  
**Historia:** Como usuario, quiero poder agregar repositorios externos de manifests, para acceder a packs de la comunidad no incluidos en el catálogo oficial.  
**Criterios de aceptación:**
- `our-dots repo-add <nombre> <url>` clona o descarga manifests desde repositorios Git o HTTP.
- La URL debe usar HTTPS obligatoriamente.
- El repositorio queda registrado en `/etc/ouroboros/dots-repos.yaml`.
- Requiere root.
**Prioridad:** Should  
**Dependencias:** —

### US-11 — Eliminar repositorio externo
**Rol:** Usuario avanzado  
**Historia:** Como usuario, quiero poder eliminar un repositorio externo que ya no necesito.  
**Criterios de aceptación:**
- `our-dots repo-remove <nombre>` elimina los archivos del repositorio y su registro.
- El directorio `REPOS_DIR/<nombre>` es eliminado completamente.
- Requiere root.
**Prioridad:** Should  
**Dependencias:** US-10

### US-12 — Listar repositorios configurados
**Rol:** Usuario avanzado  
**Historia:** Como usuario, quiero ver todos los repositorios configurados con su URL y cantidad de packs.  
**Criterios de aceptación:**
- `our-dots repo-list` muestra tabla con nombre, URL y cantidad de packs.
- El repositorio built-in siempre aparece como primera fila.
- Si no hay repositorios externos, solo aparece built-in.
**Prioridad:** Should  
**Dependencias:** US-10

### US-13 — Actualizar manifests de repositorios externos
**Rol:** Usuario avanzado  
**Historia:** Como usuario, quiero poder refrescar los manifests de todos los repositorios externos para ver nuevos packs disponibles.  
**Criterios de aceptación:**
- `our-dots repo-update` actualiza repositorios Git con `git pull --ff-only`.
- Para repositorios HTTP, re-descarga `index.yaml` y los manifests referenciados.
- Si un repositorio falla, muestra warning pero continúa con los demás.
**Prioridad:** Should  
**Dependencias:** US-10

### US-14 — Instalar pack sin interacción (unattended)
**Rol:** Script de automatización / CI  
**Historia:** Como script de automatización, quiero poder instalar un pack sin input interactivo usando `--noconfirm`, para soporte de instalaciones desatendidas.  
**Criterios de aceptación:**
- `our-dots -S <id> --noconfirm` omite todos los prompts interactivos.
- El flag `--noconfirm` **nunca** aplica a packs `critical`. Para automatización de CRITICAL, usar `OUROBOROS_ALLOW_CRITICAL=1`.
- Compatible con el instalador TUI en modo unattended.
**Prioridad:** Should  
**Dependencias:** US-03

### US-15 — Ver versión de our-dots
**Rol:** Cualquier usuario  
**Historia:** Como usuario, quiero poder ver la versión actual de `our-dots`, para saber qué features están disponibles.  
**Criterios de aceptación:**
- `our-dots --version` imprime `our-dots X.Y.Z`.
- La versión es consistente con la versión de ouroborOS donde se distribuye.
- La cadena de versión incluye al menos major.minor.patch.
**Prioridad:** Must  
**Dependencias:** —

### US-16 — Ver ayuda del comando
**Rol:** Cualquier usuario  
**Historia:** Como usuario nuevo, quiero poder ver la ayuda del comando con todos los subcomandos disponibles.  
**Criterios de aceptación:**
- `our-dots --help` o `our-dots help` imprime descripción de todos los subcomandos.
- La ayuda menciona ambos grupos: gestión de packs y gestión de repositorios.
- Si se pasa un subcomando desconocido, la ayuda se imprime con exit code 1.
**Prioridad:** Must  
**Dependencias:** —

### US-17 — Ver estado de instalación en info de pack
**Rol:** Usuario entusiasta  
**Historia:** Como usuario, quiero saber si un pack específico ya está instalado cuando lo consulto con `-Si`, para no reinstalar accidentalmente.  
**Criterios de aceptación:**
- `our-dots -Si <id>` indica claramente "installed: yes (versión, fecha)" o "not installed".
- La información de instalación se lee de `system.yaml` en tiempo real.
**Prioridad:** Must  
**Dependencias:** US-02, US-07

### US-18 — Pack con compatibilidad HIGH muestra aviso simple
**Rol:** Usuario entusiasta  
**Historia:** Como usuario, quiero un aviso visible pero no bloqueante para packs de compatibilidad HIGH, para estar informado sin fricción excesiva.  
**Criterios de aceptación:**
- Packs `high` muestran aviso en amarillo con la nota de compatibilidad.
- Solicitan confirmación con `[y/N]` (una sola tecla, no "yes").
- El aviso aparece antes del panel de info del pack.
**Prioridad:** Must  
**Dependencias:** US-03

### US-19 — Seleccionar pack de dots durante instalación del sistema
**Rol:** Usuario instalando ouroborOS  
**Historia:** Como usuario que instala ouroborOS, quiero poder seleccionar un pack de dots durante el proceso de instalación, para tener un entorno visual configurado desde el primer arranque.  
**Criterios de aceptación:**
- El instalador Textual TUI muestra el catálogo filtrado por el perfil desktop seleccionado.
- La selección es opcional (puede omitirse).
- El pack seleccionado se instala como parte del estado `DOTS_PACK` de la FSM.
**Prioridad:** Must  
**Dependencias:** US-03, instalador TUI v0.6.1

### US-20 — Instalar pack desde repositorio externo
**Rol:** Usuario avanzado  
**Historia:** Como usuario, quiero poder instalar packs de repositorios externos exactamente igual que los packs built-in, para tener una experiencia unificada.  
**Criterios de aceptación:**
- `our-dots -S <id>` busca el manifest en built-in primero, luego en repositorios externos.
- Los packs de repositorios externos se marcan con prefijo `[EXTERN]` en `list` y `-Si`.
- Se muestra aviso explícito previo a la instalación: "This pack is from an external repository not audited by the ouroborOS project."
- El ID del pack aparece en `system.yaml` independientemente de su origen.
**Prioridad:** Should  
**Dependencias:** US-10, US-03

### US-21 — Log de instalación accesible
**Rol:** Usuario técnico / soporte  
**Historia:** Como usuario técnico, quiero que todas las operaciones de instalación generen un log, para diagnosticar problemas cuando algo falla.  
**Criterios de aceptación:**
- Cada instalación crea `/var/log/our-dots/<id>-<timestamp>.log`.
- El log captura stdout/stderr de `our-pac`, `our-aur` y `post_deploy`.
- El path del log se indica al usuario al inicio de la instalación.
**Prioridad:** Must  
**Dependencias:** US-03

### US-22 — Catálogo filtrado por perfil desktop
**Rol:** Usuario entusiasta  
**Historia:** Como usuario con un perfil desktop específico, quiero ver solo los packs compatibles con mi setup, para no ver opciones irrelevantes.  
**Criterios de aceptación:**
- `dots_profiles.py::packs_for_profile(profile)` retorna solo packs donde `profile` está en `compatibility.profiles`.
- El instalador TUI usa esta función para filtrar el catálogo.
- Los packs sin perfil compatible se omiten silenciosamente.
**Prioridad:** Must  
**Dependencias:** US-01

---

## 5. Casos de Uso

### CU-01 — Exploración del catálogo
**Actor:** Usuario entusiasta  
**Precondiciones:** `our-dots` instalado en el sistema.  
**Flujo Principal:**
1. Usuario ejecuta `our-dots list`.
2. El sistema busca manifests en `MANIFEST_DIR` y `REPOS_DIR`.
3. Para cada manifest, extrae ID, nombre, perfiles, compatibilidad, canal y estado instalado.
4. Los packs de repos externos se marcan con `[EXTERN]`.
5. Presenta tabla formateada en stdout.
**Postcondiciones:** Usuario tiene visión completa del catálogo.  
**Flujos Alternativos:** Sin manifests → tabla vacía con encabezado.  
**Excepciones:** `MANIFEST_DIR` inexistente → lista vacía sin error.

### CU-02 — Consulta de información de pack
**Actor:** Usuario entusiasta  
**Precondiciones:** Pack existe en catálogo.  
**Flujo Principal:**
1. Usuario ejecuta `our-dots -Si <id>`.
2. Sistema llama a `find_manifest(id)` — busca en built-in y repos externos.
3. Extrae campos: nombre, descripción, autor, homepage, docs, compatibilidad, canales.
4. Verifica si está instalado en `system.yaml`.
5. Si el pack es de repo externo, muestra prefijo `[EXTERN]` y nota de origen.
6. Imprime panel informativo formateado.
**Postcondiciones:** Usuario tiene info completa del pack.  
**Flujos Alternativos:** Pack instalado → muestra versión y fecha de instalación.  
**Excepciones:** Pack no encontrado → `die "Pack not found: <id>"`.

### CU-03 — Instalación de pack low/medium (happy path)
**Actor:** Usuario entusiasta  
**Precondiciones:** Pack existe, usuario tiene `sudo`, `our-pac` disponible.  
**Flujo Principal:**
1. Usuario ejecuta `sudo our-dots -S <id>`.
2. Sistema verifica compatibilidad — `low` o `medium`, sin aviso especial.
3. Muestra panel de info del pack (créditos, descripción, canales).
4. Si el pack tiene stable y git, ofrece selección de canal.
5. Solicita confirmación `[y/N]`.
6. Instala paquetes pacman via `our-pac -S`.
7. Instala paquetes AUR via `our-aur -S` (si aplica).
8. Ejecuta `post_deploy` como el usuario original (`SUDO_USER`).
9. Registra en `system.yaml` via `sysyaml_add_pack`.
10. Genera log en `/var/log/our-dots/`.
**Postcondiciones:** Pack instalado y registrado en `system.yaml`.  
**Flujos Alternativos:** Usuario cancela en paso 5 → salida limpia.  
**Excepciones:** Fallo en `our-pac` → exit 1. Fallo en `post_deploy` → exit 4. Usuario intenta instalar un pack CRITICAL mientras `OUROBOROS_ALLOW_CRITICAL` no está definido y el nivel del pack es `critical` → error con mensaje explicativo.

### CU-04 — Instalación de pack HIGH con aviso
**Actor:** Usuario entusiasta  
**Precondiciones:** Pack con `compatibility.immutable: high`.  
**Flujo Principal:**
1. Pasos 1-2 de CU-03.
2. Sistema detecta `high` → imprime aviso en amarillo con `compatibility_note`.
3. Solicita confirmación `[y/N]`.
4. Si usuario confirma → continúa con CU-03 desde paso 3.
5. Si cancela → salida limpia.
**Postcondiciones:** Igual que CU-03 o sin cambios si cancelado.  
**Excepciones:** Las mismas que CU-03.

### CU-05 — Instalación de pack CRITICAL con panel completo
**Actor:** Usuario avanzado  
**Precondiciones:** Pack con `compatibility.immutable: critical`.  
**Flujo Principal:**
1. Pasos 1-2 de CU-03.
2. Sistema detecta `critical` → muestra panel rojo con título, `compatibility_warning` y lista numerada de `critical_actions`.
3. Solicita que el usuario tipe exactamente "yes".
4. Si no es "yes" → cancela sin efectos secundarios.
5. Sistema instala trap de cleanup (CU-23): si cualquier paso posterior falla, el trap revierte remount y edits de `/etc` antes de salir.
6. Si confirma → continúa con CU-03 desde paso 3.
**Postcondiciones:** Igual que CU-03 o sin cambios si cancelado.  
**Flujos Alternativos:** `OUROBOROS_ALLOW_CRITICAL=1` en environment → omite el panel y procede directamente (solo para CI/automatización). El flag `--noconfirm` es IGNORADO para packs CRITICAL.  
**Excepciones:** Las mismas que CU-03. Fallo durante instalación → trap de cleanup activado (ver CU-23).

### CU-06 — Desinstalación de pack
**Actor:** Usuario entusiasta  
**Precondiciones:** Pack instalado en `system.yaml`.  
**Flujo Principal:**
1. Usuario ejecuta `sudo our-dots -R <id>`.
2. Sistema verifica que el pack está en `system.yaml`.
3. Busca manifest para obtener listas de desinstalación.
4. Solicita confirmación `[y/N]`.
5. Elimina paquetes AUR primero, luego pacman.
6. Ejecuta `post_remove` si existe.
7. Elimina entrada de `system.yaml`.
**Postcondiciones:** Pack eliminado del sistema y de `system.yaml`.  
**Flujos Alternativos:** Manifest no encontrado → indica eliminación manual de `system.yaml`.  
**Excepciones:** Fallo en desinstalación de paquetes → warning, pero sigue intentando el resto.

### CU-07 — Consulta de packs instalados
**Actor:** Cualquier usuario  
**Precondiciones:** —  
**Flujo Principal:**
1. Usuario ejecuta `our-dots -Q`.
2. Sistema lee `system.yaml.dots_packs`.
3. Imprime tabla con ID, canal y fecha de instalación.
**Postcondiciones:** Usuario conoce su inventario de packs.  
**Flujos Alternativos:** Sin packs instalados → imprime "(no packs installed)". `system.yaml` inexistente → imprime "(no packs installed)" sin error.  
**Excepciones:** —

### CU-08 — Búsqueda por patrón
**Actor:** Usuario entusiasta  
**Precondiciones:** —  
**Flujo Principal:**
1. Usuario ejecuta `our-dots -Qs <patrón>`.
2. Sistema carga el catálogo y filtra case-insensitive por ID, nombre y descripción.
3. Muestra resultados filtrados.
**Postcondiciones:** Usuario ve packs que coinciden.  
**Flujos Alternativos:** Sin patrón → muestra catálogo completo.  
**Excepciones:** Sin coincidencias → resultado vacío, sin error.

### CU-09 — Actualización de packs instalados
**Actor:** Usuario entusiasta  
**Precondiciones:** Al menos un pack instalado.  
**Flujo Principal:**
1. Usuario ejecuta `sudo our-dots -Su`.
2. Sistema itera sobre `system.yaml.dots_packs`.
3. Para cada pack CRITICAL: lo omite de la actualización automática e imprime "CRITICAL packs require manual update: sudo our-dots -S <id>".
4. Para cada pack con paquetes AUR, consulta API de AUR. Si hay versión nueva disponible → llama a `cmd_install` con `--noconfirm`.
5. Para packs con `channel: git` sin AUR, ejecuta `git pull --ff-only` en el directorio clonado del pack.
6. Reporta resumen de packs actualizados, omitidos y fallidos.
**Postcondiciones:** Packs actualizados a última versión disponible; packs CRITICAL omitidos con aviso.  
**Flujos Alternativos:** Pack sin mecanismo de actualización (ni AUR ni git) → mensaje de reinstalación manual (`our-dots -S <id>`).  
**Excepciones:** API de AUR no disponible → warning por pack, continúa con el siguiente. `git pull` falla → warning con sugerencia de `git pull --rebase`.

### CU-10 — Alta de repositorio externo (Git)
**Actor:** Usuario avanzado  
**Precondiciones:** URL Git accesible vía HTTPS, usuario con root.  
**Flujo Principal:**
1. Usuario ejecuta `sudo our-dots repo-add <nombre> <url.git>`.
2. Sistema verifica que la URL usa HTTPS.
3. Detecta que es repositorio Git (`git ls-remote` o extensión `.git`).
4. Clona con `git clone --depth=1`.
5. Valida el schema de cada manifest descargado antes de registrar el repositorio.
6. Registra en `dots-repos.yaml`.
**Postcondiciones:** Packs del repositorio disponibles en el catálogo.  
**Flujos Alternativos:** URL HTTP → rechaza con error. Manifest con schema inválido → warning por manifest, el repositorio se registra pero el manifest inválido se ignora.  
**Excepciones:** Clone falla → `die "Failed to clone"`. Ningún manifest válido encontrado → warning al usuario.

> **Nota de seguridad:** Los repositorios externos no están auditados por el proyecto ouroborOS. El usuario es responsable de verificar los manifests antes de agregar el repositorio.

### CU-11 — Alta de repositorio externo (HTTP)
**Actor:** Usuario avanzado  
**Precondiciones:** URL HTTPS con `index.yaml` válido, usuario con root.  
**Flujo Principal:**
1. Usuario ejecuta `sudo our-dots repo-add <nombre> <url>`.
2. Sistema verifica HTTPS.
3. Descarga `index.yaml` del repositorio.
4. Itera sobre lista de packs en `index.yaml` y descarga cada `<id>.yaml`.
5. Valida el schema de cada manifest descargado.
6. Registra en `dots-repos.yaml`.
**Postcondiciones:** Manifests disponibles en `REPOS_DIR/<nombre>/`.  
**Flujos Alternativos:** Manifest con schema inválido → warning por manifest, continúa con los demás.  
**Excepciones:** `index.yaml` no disponible → `die "Failed to fetch index.yaml"`.

### CU-12 — Baja de repositorio externo
**Actor:** Usuario avanzado  
**Precondiciones:** Repositorio registrado en `dots-repos.yaml`.  
**Flujo Principal:**
1. Usuario ejecuta `sudo our-dots repo-remove <nombre>`.
2. Sistema verifica si hay packs del repositorio actualmente instalados en `system.yaml`.
3. Si hay packs instalados → lista los packs afectados y pregunta `[y/N]` para confirmar eliminación de todos modos.
4. Si el usuario confirma (o no había packs instalados): elimina directorio `REPOS_DIR/<nombre>`.
5. Actualiza `dots-repos.yaml` removiendo la entrada.
**Postcondiciones:** Repositorio y sus manifests eliminados.  
**Flujos Alternativos:** Repositorio no registrado → operación silenciosa (noop). Usuario cancela en paso 3 → operación cancelada sin cambios.  
**Excepciones:** Fallo al eliminar directorio → warning con path para eliminación manual.

### CU-13 — Listado de repositorios
**Actor:** Usuario avanzado  
**Precondiciones:** —  
**Flujo Principal:**
1. Usuario ejecuta `our-dots repo-list`.
2. Sistema muestra repositorio built-in con count de manifests.
3. Lee `dots-repos.yaml` y muestra repos externos con nombre, URL y count.
**Postcondiciones:** Usuario conoce sus fuentes de packs.  
**Flujos Alternativos:** Sin repos externos → solo aparece built-in. `dots-repos.yaml` no existe → muestra solo built-in sin error.  
**Excepciones:** Error de lectura de `dots-repos.yaml` → warning, muestra solo built-in.

### CU-14 — Actualización de repositorios externos
**Actor:** Usuario avanzado  
**Precondiciones:** Al menos un repositorio externo configurado.  
**Flujo Principal:**
1. Usuario ejecuta `sudo our-dots repo-update`.
2. Sistema lee `dots-repos.yaml`.
3. Para repos Git: `git pull --ff-only`.
4. Para repos HTTP: re-ejecuta lógica de descarga de CU-11.
5. Reporta resultado por repositorio.
**Postcondiciones:** Manifests actualizados.  
**Flujos Alternativos:** Sin repositorios externos → mensaje informativo, sin error.  
**Excepciones:** Fallo en repo individual → warning, continúa con siguientes.

### CU-15 — Selección de dots en instalador TUI
**Actor:** Usuario instalando ouroborOS  
**Precondiciones:** Estado `DOTS_PACK` alcanzado en la FSM del instalador.  
**Flujo Principal:**
1. Instalador llama a `dots_profiles.packs_for_profile(profile)`.
2. Presenta lista de packs compatibles en Select widget de Textual.
3. Usuario selecciona pack (o "Ninguno").
4. La selección se guarda en `InstallerConfig.dots_pack`.
5. La FSM ejecuta `cmd_install` en el estado `DOTS_PACK`.
**Postcondiciones:** Pack instalado como parte del sistema base.  
**Flujos Alternativos:** Sin packs para el perfil → estado se omite silenciosamente. Usuario selecciona "Ninguno" → estado se omite, FSM avanza al siguiente estado.  
**Excepciones:** `cmd_install` falla → instalador registra el error en log y muestra opción de continuar sin el pack o abortar la instalación.

### CU-16 — Instalación en modo unattended
**Actor:** Script de CI / automatización  
**Precondiciones:** Pack no tiene `compatibility.immutable: critical`, o bien `OUROBOROS_ALLOW_CRITICAL=1` está definido en el environment.  
**Flujo Principal:**
1. Script llama `our-dots -S <id> --noconfirm`.
2. Sistema omite todos los prompts interactivos.
3. Procede directamente a instalación de dependencias y `post_deploy`.
4. Registra en `system.yaml`.
**Postcondiciones:** Pack instalado sin input del usuario.  
**Flujos Alternativos:** Pack CRITICAL con `OUROBOROS_ALLOW_CRITICAL=1` → omite panel de confirmación y procede directamente.  
**Excepciones:** Pack `critical` sin `OUROBOROS_ALLOW_CRITICAL=1` → sale con error: "CRITICAL pack requires OUROBOROS_ALLOW_CRITICAL=1 for unattended installation."

### CU-17 — Fallo de post_deploy
**Actor:** Usuario entusiasta  
**Precondiciones:** Pack con `post_deploy` definido, el script falla.  
**Flujo Principal:**
1. Instalación de paquetes completa.
2. `post_deploy` retorna exit code ≠ 0.
3. Sistema imprime error con path al log.
4. Retorna exit code 4.
**Postcondiciones:** Paquetes instalados pero pack NO registrado en `system.yaml`.  
**Flujos Alternativos:** Paquetes pacman/AUR quedaron instalados tras el fallo → `our-dots -R --force <id>` permite limpiar paquetes huérfanos sin requerir registro previo en `system.yaml`.  
**Excepciones:** Usuario debe revisar log y resolver manualmente.

### CU-18 — Pack ya instalado — reinstalación
**Actor:** Usuario entusiasta  
**Precondiciones:** Pack ya registrado en `system.yaml`.  
**Flujo Principal:**
1. Usuario ejecuta `our-dots -S <id>` nuevamente.
2. Sistema detecta el pack en `system.yaml` → muestra aviso: "Pack already installed. Reinstalling will overwrite the existing entry."
3. Solicita confirmación `[y/N]`.
4. Si el usuario confirma → procede con instalación completa.
5. `sysyaml_add_pack` actualiza la entrada existente (upsert).
**Postcondiciones:** Pack reinstalado con versión y fecha actualizadas.  
**Flujos Alternativos:** Usuario cancela en paso 3 → salida limpia sin cambios.  
**Excepciones:** Las mismas que CU-03.

### CU-19 — Carga de catálogo desde Python (dots_profiles)
**Actor:** Módulo Python del instalador  
**Precondiciones:** `MANIFEST_DIR` existe con archivos `.yaml`.  
**Flujo Principal:**
1. `load_catalog()` enumera `*.yaml` en `MANIFEST_DIR` (orden alfabético).
2. Para cada archivo: `yaml.safe_load` → construye `DotsPack` dataclass.
3. Retorna lista de instancias `DotsPack`.
**Postcondiciones:** Catálogo disponible para el instalador.  
**Flujos Alternativos:** `MANIFEST_DIR` inexistente → retorna lista vacía.  
**Excepciones:** Manifest inválido → se ignora con `continue` (sin crash).

### CU-20 — Filtrado de packs por perfil desktop
**Actor:** Módulo Python del instalador  
**Precondiciones:** Catálogo cargado, perfil desktop conocido.  
**Flujo Principal:**
1. `packs_for_profile(profile)` llama a `load_catalog()`.
2. Filtra packs donde `profile in pack.profiles`.
3. Retorna sublista compatible.
**Postcondiciones:** Solo packs relevantes para el perfil seleccionado.  
**Flujos Alternativos:** Perfil sin packs compatibles → lista vacía. Perfil desconocido → retorna lista vacía sin error.  
**Excepciones:** Error al cargar catálogo → propaga excepción al llamador.

### CU-21 — Verificación de estado de instalación en system.yaml
**Actor:** Cualquier subcomando de our-dots  
**Precondiciones:** `system.yaml` existe en `/etc/ouroboros/`.  
**Flujo Principal:**
1. `sysyaml_is_installed(id)` abre `system.yaml`.
2. Lee `dots_packs` y verifica si el ID está presente.
3. Retorna 0 (instalado) o 1 (no instalado).
**Postcondiciones:** El llamador conoce el estado de instalación del pack.  
**Flujos Alternativos:** `system.yaml` inexistente → el pack se considera no instalado (retorna 1 sin error; no puede estar instalado sin el archivo).  
**Excepciones:** —

### CU-22 — Escritura atómica en system.yaml
**Actor:** Operaciones de instalación/desinstalación  
**Precondiciones:** Escritura en `system.yaml` requerida.  
**Flujo Principal:**
1. Adquiere advisory lock sobre `system.yaml.lock` con `flock`. Si el lock está tomado → espera hasta 5 segundos, luego aborta con error: "system.yaml is locked by another our-dots process."
2. Lee `system.yaml` actual.
3. Modifica la estructura en memoria.
4. Escribe a `system.yaml.tmp`.
5. `os.replace(tmp, path)` — operación atómica en mismo filesystem.
6. Libera el lock.
**Postcondiciones:** `system.yaml` actualizado sin riesgo de corrupción parcial.  
**Flujos Alternativos:** Lock liberado tras salida limpia, incluso con excepción (via context manager).  
**Excepciones:** Fallo de permisos → Python exception (requiere root). Timeout de lock → aborta con mensaje de proceso bloqueante.

### CU-23 — Cleanup de instalación fallida de pack CRITICAL
**Actor:** Mecanismo interno de our-dots  
**Precondiciones:** Pack CRITICAL falló durante instalación después de remount o edición de `/etc`.  
**Flujo Principal:**
1. Trap `ERR` o `EXIT` activado durante instalación CRITICAL.
2. Si `/` fue remontado como lectura-escritura: ejecuta `mount -o remount,ro /`.
3. Si `/etc/pacman.conf` fue modificado: restaura desde backup creado en paso pre-edit (`/etc/pacman.conf.our-dots-bak`).
4. Si se instalaron paquetes antes del fallo: intenta revertirlos via `our-pac -R` (best-effort, no fatal).
5. Graba log de cleanup en `/var/log/our-dots/<id>-cleanup-<timestamp>.log`.
6. Sale con exit code 5 (instalación fallida + cleanup ejecutado).
**Postcondiciones:** Sistema restaurado a estado inmutable previo.  
**Flujos Alternativos:** Cleanup completa exitosamente → exit 5 con mensaje de estado restaurado.  
**Excepciones:** Remount fallido → advertencia crítica al usuario con instrucciones manuales (`mount -o remount,ro /`). Restauración de `pacman.conf` fallida → advertencia crítica con path del backup.

### CU-24 — Instalación de pack en canal git
**Actor:** Usuario avanzado  
**Precondiciones:** Pack con `variants.git` definido en manifest, flag `--git` presente.  
**Flujo Principal:**
1. Usuario ejecuta `sudo our-dots -S <id> --git`.
2. Sistema verifica que el manifest define `variants.git`.
3. Continúa con CU-03/CU-04/CU-05 según nivel de compatibilidad, usando URL y dependencias del canal `git`.
4. Registra `channel: git` en `system.yaml`.
**Postcondiciones:** Pack instalado en canal git y registrado en `system.yaml`.  
**Flujos Alternativos:** Pack sin canal git → error: "Canal git no disponible para <id>. Instalar sin --git para usar canal stable."  
**Excepciones:** Las mismas que CU-03.

### CU-25 — Instalación de pack desde repositorio externo
**Actor:** Usuario avanzado  
**Precondiciones:** Repositorio externo registrado, pack disponible en él.  
**Flujo Principal:**
1. Usuario ejecuta `sudo our-dots -S <id>`.
2. Sistema busca manifest en built-in; no encontrado.
3. Busca en repositorios externos registrados en `dots-repos.yaml`.
4. Encontrado en repo externo: marca pack con prefijo `[EXTERN]` en output.
5. Muestra aviso: "This pack is from an external repository not audited by the ouroborOS project."
6. Continúa con flujo de confirmación según nivel de compatibilidad del pack (CU-03/CU-04/CU-05).
**Postcondiciones:** Pack instalado y registrado en `system.yaml` con metadato de origen.  
**Flujos Alternativos:** Mismo ID en built-in y externo → built-in tiene prioridad sin aviso.  
**Excepciones:** Schema del manifest externo inválido → error con ruta al manifest y campos faltantes. Pack no encontrado en ninguna fuente → `die "Pack not found: <id>"`.

---

## 6. Catálogo de Packs

> **Nota sobre terminología de canales:** El término canónico para el canal de última versión es **`git`** en toda la documentación, manifests y CLI. Los términos "rolling" y "bleeding edge" no son vocabulario normativo — `git` es el valor usado en manifests y outputs de herramientas.

### 6.1 ML4W Dotfiles

| Campo | Valor |
|-------|-------|
| **ID** | `ml4w` |
| **Autor** | Stephan Raabe |
| **Homepage** | https://ml4w.com |
| **Licencia** | GPL-2.0 |
| **WM** | Hyprland |
| **Compatibilidad** | MEDIUM |
| **Canales** | stable (v0.2.3) |

Framework de dotfiles orientado a Hyprland, ampliamente reconocido en la comunidad por los tutoriales en YouTube de su autor. ML4W no impone una apariencia única sino que provee un instalador estructurado (`make install`) que gestiona el despliegue de perfiles de forma modular. Las dependencias se instalan via `our-pac` y `our-aur` como ciudadanos de primera clase.

**Proceso de instalación:** `git clone` + `make install` ejecutado como el usuario original. Los paquetes base (`git`, `make`) se instalan primero via `our-pac`.

---

### 6.2 Noctalia v4

| Campo | Valor |
|-------|-------|
| **ID** | `noctalia` |
| **Autor** | noctalia-dev team |
| **Homepage** | https://github.com/noctalia-dev/noctalia-shell |
| **Docs** | https://docs.noctalia.dev/v4/getting-started/installation/#arch |
| **WM** | Niri, Hyprland |
| **Compatibilidad** | LOW |
| **Canales** | stable (v4), git |

Shell de escritorio basada en Quickshell con diseño modular: barra, notificaciones, historial de portapapeles, luz nocturna y calendario. Tiene el soporte de distribuciones más amplio del catálogo (Fedora, openSUSE, Void, AUR para Arch). La separación explícita stable/git la convierte en una de las opciones más seguras para sistemas inmutables. La compatibilidad `low` refleja que solo requiere instalación desde AUR y config en user-space — sin escrituras root en directorios del sistema.

---

### 6.3 Caelestia Shell

| Campo | Valor |
|-------|-------|
| **ID** | `caelestia` |
| **Autor** | soramane |
| **Homepage** | https://github.com/caelestia-dots/shell |
| **WM** | Hyprland |
| **Compatibilidad** | MEDIUM |
| **Canales** | stable (AUR), git |

Shell de escritorio de alto perfil (9.800+ GitHub stars), diseñada como reemplazo completo de Waybar para Hyprland. Implementada en QML y C++, provee barra, dashboard, lanzador de aplicaciones, pantalla de bloqueo y utilidades del sistema. Se distribuye como paquete AUR compilado (`cmake build`), lo que significa que se instala en paths del sistema — de ahí la compatibilidad `medium`. Más de 20 releases versionadas con separación clara de canales.

---

### 6.4 illogical-impulse

| Campo | Valor |
|-------|-------|
| **ID** | `illogical-impulse` |
| **Autor** | end-4 |
| **Homepage** | https://ii.clsty.link |
| **Repo** | https://github.com/end-4/dots-hyprland |
| **WM** | Hyprland |
| **Compatibilidad** | CRITICAL |
| **Canales** | git |

Rice de Hyprland construido sobre Quickshell, reconocido por su estética pulida y comunidad activa. Requiere modificación de `/etc/pacman.conf` (agregar `IgnoreGroup=illogical-impulse`) en el sistema en vivo — operación incompatible con raíz read-only. ouroborOS gestiona esto remontando temporalmente `/` como lectura-escritura, realizando el edit, y restaurando read-only inmediatamente. Esta acción se lista explícitamente en el panel CRITICAL antes de confirmar.

**Acciones críticas:**
1. Remontar `/` como lectura-escritura (temporal).
2. Agregar `IgnoreGroup=illogical-impulse` a `/etc/pacman.conf`.
3. Restaurar `/` a solo-lectura.
4. Instalar dependencias via `our-pac` y `our-aur`.
5. Clonar `dots-hyprland` y ejecutar `./setup install` como el usuario original.

---

### 6.5 Omarchy

| Campo | Valor |
|-------|-------|
| **ID** | `omarchy` |
| **Autor** | DHH (David Heinemeier Hansson) / 37signals |
| **Homepage** | https://omarchy.org |
| **Docs** | https://learn.omacom.io/2/the-omarchy-manual/96/manual-installation |
| **Repo** | https://github.com/basecamp/omarchy |
| **Licencia** | MIT |
| **WM** | Hyprland |
| **Compatibilidad** | CRITICAL |
| **Canales** | git |

Configuración "omakase" opinionada de Arch Linux por DHH. Funciona más como una distribución que como un pack de dotfiles: configura el sistema completo desde preferencias de bootloader hasta setup del editor. Incluye Hyprland, Neovim, Tmux, Alacritty/Ghostty, Lazygit, Lazydocker, Btop, Obsidian, 19 temas integrados, y Claude Code/OpenCode AI. Respaldado por 37signals (Basecamp, Ruby on Rails). Es el pack más invasivo del catálogo — requiere múltiples escrituras en `/etc` y configuración global del sistema.

**Acciones críticas:**
1. Instalar ~40 paquetes pacman (neovim, tmux, alacritty, lazygit, etc.).
2. Instalar paquetes AUR (obsidian, btop, y otros).
3. Desplegar configuración Hyprland en `~/.config/hypr/`.
4. Desplegar configuración Neovim en `~/.config/nvim/`.
5. Desplegar configuración Tmux en `~/.config/tmux/`.
6. Establecer preferencias de fuente y tema a nivel sistema.
7. Configurar locale y teclado en `/etc`.

---

### 6.6 Ambxst

| Campo | Valor |
|-------|-------|
| **ID** | `ambxst` |
| **Autor** | Axenide |
| **Homepage** | https://axeni.de/es/ambxst/ |
| **Repo** | https://github.com/Axenide/Ambxst |
| **Licencia** | AGPL-3.0 |
| **WM** | Hyprland |
| **Compatibilidad** | MEDIUM |
| **Canales** | git |

Shell Quickshell para Hyprland con diseño explícitamente no-intrusivo: se integra en la configuración existente de Hyprland en lugar de reemplazarla. Todo el runtime vive en user-space (`~/.local/share/ambxst`, `~/.config/ambxst`). El conjunto de features es el más amplio de los proyectos shell del catálogo: lanzador de apps, portapapeles, notas, gestor de fondos, selector de emoji, gestor de sesiones Tmux, monitor del sistema, control de media, notificaciones, WiFi, Bluetooth, mixer de audio, EasyEffects, captura de pantalla, grabación, selector de color, OCR, escáner QR, cámara, modo juego, modo nocturno, perfiles de energía, asistente AI, clima, calendario, menú de energía y gestión de espacios de trabajo.

---

### 6.7 DankMaterialShell

| Campo | Valor |
|-------|-------|
| **ID** | `danklinux` |
| **Autor** | AvengeMedia |
| **Homepage** | https://danklinux.com |
| **Repo** | https://github.com/AvengeMedia/DankMaterialShell |
| **WM** | Niri, Hyprland |
| **Compatibilidad** | HIGH |
| **Canales** | stable (v1.4) |

> **Nota sobre el ID:** El ID `danklinux` (en lugar de `danklinuxmaterialshell`) es intencionalmente corto, coherente con la convención de IDs monosílabos o de una palabra del catálogo. El nombre completo `DankMaterialShell` se muestra en el display name del manifest y en los outputs de `list` e `-Si`.

Shell Wayland temática Material You con soporte de primera clase para Niri e Hyprland. Genera paletas de color automáticamente desde el fondo de pantalla via `matugen`. Incluye terminal Ghostty, framework Quickshell, `dgop` (monitor del sistema), `dsearch` (búsqueda de archivos) y `cliphist` (historial de portapapeles). Uno de los pocos proyectos del catálogo con soporte explícito para Niri junto a Hyprland. La compatibilidad `high` refleja que requiere construcción desde AUR con toolchains Go, CMake y Rust, con tiempo de build aproximado de 10 minutos.

---

### 6.8 Schema de Manifest

> ⚠️ **Referencia histórica.** El schema autoritativo de manifests está en **TRD §2.3**. Ante cualquier discrepancia entre esta sección y el TRD, prevalece el TRD. Esta sección refleja el diseño original de producto y se mantiene por contexto.

Cada pack del catálogo (built-in o externo) se describe en un archivo YAML con el siguiente schema. Los manifests externos son validados antes de ejecutar cualquier hook.

#### Tabla de campos

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `id` | string | **Sí** | Identificador único del pack (kebab-case, minúsculas) |
| `name` | string | **Sí** | Nombre de display del pack |
| `description` | string | **Sí** | Descripción breve (1-2 oraciones) |
| `author` | string | **Sí** | Nombre del autor u organización |
| `homepage` | url | **Sí** | URL del proyecto (HTTPS) |
| `docs` | url | No | URL de documentación |
| `repo` | url | No | URL del repositorio de código |
| `license` | string | No | Identificador SPDX (e.g., `MIT`, `GPL-2.0`) |
| `compatibility.immutable` | enum | **Sí** | `low` \| `medium` \| `high` \| `critical` |
| `compatibility.profiles` | list | **Sí** | Perfiles desktop compatibles (`hyprland`, `niri`, etc.) |
| `compatibility.note` | string | No | Nota breve para packs `high` (aparece en aviso amarillo) |
| `compatibility.warning` | string | Sí si `critical` | Texto del panel rojo de confirmación CRITICAL |
| `compatibility.critical_actions` | list | Sí si `critical` | Lista numerada de acciones críticas |
| `variants.stable` | objeto | No | Definición del canal stable |
| `variants.stable.url` | url | No | URL del archivo o repo stable |
| `variants.stable.version` | string | No | Versión del canal stable |
| `variants.git` | objeto | No | Definición del canal git |
| `variants.git.url` | url | No | URL del repositorio git |
| `packages.pacman` | list | No | Paquetes pacman a instalar |
| `packages.aur` | list | No | Paquetes AUR a instalar |
| `packages.remove.pacman` | list | No | Paquetes pacman a desinstalar en `-R` |
| `packages.remove.aur` | list | No | Paquetes AUR a desinstalar en `-R` |
| `hooks.post_deploy` | path | No | Script ejecutado tras instalación (como `$SUDO_USER`) |
| `hooks.post_remove` | path | No | Script ejecutado tras desinstalación (como `$SUDO_USER`) |
| `signature` | null | No | **Reservado.** Campo para firma criptográfica futura. Siempre `null` en v0.6.1. Requerido en versiones futuras para repositorios externos. |

#### Ejemplo completo

```yaml
id: noctalia
name: Noctalia v4
description: Modular Quickshell desktop shell for Niri and Hyprland.
author: noctalia-dev team
homepage: https://github.com/noctalia-dev/noctalia-shell
docs: https://docs.noctalia.dev/v4/getting-started/installation/#arch
license: ~

compatibility:
  immutable: low
  profiles:
    - niri
    - hyprland
  note: ~
  warning: ~
  critical_actions: []

variants:
  stable:
    url: https://aur.archlinux.org/packages/noctalia
    version: "4.0"
  git:
    url: https://github.com/noctalia-dev/noctalia-shell

packages:
  pacman: []
  aur:
    - noctalia
  remove:
    pacman: []
    aur:
      - noctalia

hooks:
  post_deploy: hooks/noctalia-post-deploy.sh
  post_remove: ~

signature: null
```

---

## 7. Agradecimientos

ouroborOS v0.6.1 no sería posible sin el trabajo extraordinario de los siguientes creadores. Sus proyectos representan miles de horas de desarrollo open source y han definido el estándar de calidad del escritorio Linux moderno.

---

**Stephan Raabe** — ML4W Dotfiles  
Proyecto: [ML4W Dotfiles Installer](https://ml4w.com/dotfiles-installer/getting-started/install)  
Repositorio: https://github.com/mylinuxforwork/ml4w-dotfiles-installer  
Contribución: Framework de instalación modular para Hyprland, con soporte explícito para Arch Linux como objetivo de primera clase. Su trabajo educativo en YouTube ha introducido a miles de usuarios al ricing de Linux.

---

**noctalia-dev team** — Noctalia v4  
Proyecto: [Noctalia Shell](https://github.com/noctalia-dev/noctalia-shell)  
Documentación: https://docs.noctalia.dev/v4/getting-started/installation/#arch  
Contribución: Shell Quickshell con el soporte de distribuciones más amplio del catálogo, y uno de los pocos proyectos que explicita canales stable/git con semántica clara — un modelo a seguir para la comunidad.

---

**soramane** — Caelestia Shell  
Proyecto: [Caelestia Shell](https://github.com/caelestia-dots/shell)  
Apoyo: https://ko-fi.com/soramane  
Contribución: Shell de escritorio implementada en QML/C++ con más de 9.800 estrellas en GitHub, 20+ releases versionadas, y una separación de canales estable/git que la hace segura para integraciones como ouroborOS.

---

**end-4** — illogical-impulse  
Proyecto: [dots-hyprland](https://github.com/end-4/dots-hyprland)  
Web: https://ii.clsty.link  
Contribución: Rice de Hyprland con estética pulida y comunidad activa. Su documentación bilingüe (EN/CN) y sistema de instalación modular por categorías son un ejemplo de cómo hacer accesible un proyecto complejo.

---

**David Heinemeier Hansson (DHH) / 37signals** — Omarchy  
Proyecto: [Omarchy](https://omarchy.org)  
Repositorio: https://github.com/basecamp/omarchy  
Documentación: https://learn.omacom.io/2/the-omarchy-manual/96/manual-installation  
Contribución: Configuración "omakase" completa de Arch Linux que eleva el concepto de dotfiles a herramienta de productividad empresarial. Su filosofía de ofrecer un entorno curado sin elecciones paralela la de ouroborOS en inmutabilidad.

---

**Axenide** — Ambxst  
Proyecto: [Ambxst](https://axeni.de/es/ambxst/)  
Repositorio: https://github.com/Axenide/Ambxst  
Créditos adicionales: outfoxxed (Quickshell), end-4, soramane  
Contribución: Shell Hyprland de diseño no-intrusivo y el conjunto de features más amplio del catálogo. Su enfoque de integrarse en lugar de reemplazar configuraciones existentes es un modelo para la compatibilidad en sistemas inmutables.

---

**AvengeMedia** — DankMaterialShell  
Proyecto: [DankMaterialShell](https://danklinux.com)  
Repositorio: https://github.com/AvengeMedia/DankMaterialShell  
Contribución: Una de las pocas shells Wayland con soporte explícito y de primera clase para Niri además de Hyprland. Su implementación de Material You con generación automática de paletas via `matugen` define el estándar de personalización dinámica.

---

## 8. Métricas de Éxito

| Métrica | Objetivo | Medición |
|---------|----------|----------|
| Cobertura de tests `dots_profiles.py` | ≥ 93 % | `pytest --cov` en CI |
| Tiempo de instalación pack medium | < 5 min (sin compilación) | Medido en QEMU E2E |
| Tiempo de instalación pack high (DankLinux) | < 15 min (con builds AUR) | Medido en QEMU E2E |
| Tests E2E pasando | 100 % (72/72 + nuevos) | Suite QEMU |
| ISO construible con `our-dots` incluido | Build verde en CI | GitHub Actions |
| `system.yaml` actualizado tras instalación | 100 % de los casos | Test de integración |
| Escritura atómica de `system.yaml` | 0 corrupciones | Test con fallo simulado |
| Flujo CRITICAL rechazado sin "yes" | 100 % de los casos | Test unitario |
| Cleanup CU-23 revierte remount tras fallo | 100 % de los casos | Test con fallo inyectado |

---

## 9. Stack Tecnológico

| Componente | Tecnología | Justificación |
|------------|-----------|---------------|
| `our-dots` binary | Bash (set -euo pipefail) | Consistente con toda la familia `our-*` |
| Parsing de manifests | Python 3.11+ (yaml.safe_load) | Mismo intérprete del instalador |
| Módulo Python | `dots_profiles.py` (dataclasses) | Integración directa con TUI Textual |
| Formato de manifests | YAML | Legible, tipado, compatible con system.yaml |
| Persistencia de estado | `system.yaml` (key: dots_packs) | Source of truth declarativo existente |
| Concurrencia `system.yaml` | `flock` (advisory lock) | Previene corrupción por escrituras concurrentes |
| Repositorios externos | Git (clone --depth=1) + HTTP (curl) | Flexibilidad para tipos de fuente |
| Logs | `/var/log/our-dots/` | Estándar FHS para logs del sistema |
| Index de repos | `/etc/ouroboros/dots-repos.yaml` | Consistente con convenciones ouroboros |
| Instalación de paquetes | `our-pac` + `our-aur` | Sin dependencia directa de pacman |

---

## 10. Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| Pack CRITICAL daña sistema inmutable | Media | Alto | Panel de confirmación explícito, lista de acciones, "yes" requerido; trap de cleanup CU-23 |
| `post_deploy` falla a mitad de instalación | Media | Medio | Exit code 4 diferenciado, log completo, NO se registra en system.yaml; `our-dots -R --force` para huérfanos |
| Manifest externo malicioso | Baja | Alto | Solo HTTPS; validación de schema antes de ejecutar hooks; marca EXTERN; aviso explícito al usuario |
| Ejecución arbitraria de `post_deploy` externo | Media | Alto | Validación de schema obligatoria pre-ejecución; usuario debe auditar repos externos; `signature: null` reservado para firma futura |
| Incompatibilidad futura de pack upstream | Alta | Bajo | Packs sin `post_remove` completo → usuario usa Btrfs snapshot |
| AUR build time excede timeout de sesión | Baja | Medio | Log guardado, reinstalación idempotente via upsert |
| `system.yaml` corrupto tras write parcial | Muy baja | Alto | Escritura atómica via `os.replace` con archivo `.tmp` + `flock` |
| Pack git inestable rompe el entorno | Media | Medio | Canal git requiere selección explícita del usuario (`--git`) |
| Escritura concurrente de `system.yaml` | Muy baja | Alto | Advisory lock con `flock`; timeout de 5 segundos; aborta con error claro |

---

## 11. Scope y No-Scope

### En Scope (v0.6.1)

- Binary `our-dots` con **11 subcomandos funcionales**: `list`, `-Si`, `-S`, `-R`, `-Q`, `-Qs`, `-Su`, `repo-add`, `repo-remove`, `repo-list`, `repo-update`. Flags adicionales: `--git`, `--noconfirm`, `--version`, `--help`.
- 7 manifests YAML curados en `MANIFEST_DIR`.
- Módulo `dots_profiles.py` con `DotsPack`, `load_catalog()`, `packs_for_profile()`.
- Integración con `system.yaml` (clave `dots_packs`).
- Flujos de confirmación por nivel: low/medium/high/critical.
- Mecanismo CRITICAL: panel de advertencia + trap de cleanup (CU-23).
- Sistema de repositorios externos (Git + HTTP) con validación de schema.
- Estado `DOTS_PACK` en la FSM del instalador.
- Logs en `/var/log/our-dots/`.
- Tests unitarios para `dots_profiles.py`.

### Fuera de Scope (v0.6.1)

- GUI para gestión de packs (v0.7.0+).
- Rollback automático de packs (se usa `our-rollback` + snapshot Btrfs manual).
- Actualización OTA de packs sin intervención del usuario.
- Firma criptográfica de manifests (campo `signature: null` reservado para versión futura).
- Soporte para packs GNOME, KDE o Cosmic (solo Hyprland y Niri en v0.6.1).
- Preview visual de packs (capturas de pantalla en TUI).
- Sistema de ratings o reviews de packs.

---

## 12. Criterios de Aceptación Global

1. `our-dots list` muestra los 7 packs built-in con información correcta de compatibilidad.
2. `our-dots -Si ml4w` muestra información completa incluyendo créditos y canales.
3. `our-dots -S noctalia` completa instalación, registra en `system.yaml`, genera log.
4. `our-dots -S illogical-impulse` muestra panel CRITICAL; cancelar con "no" → sin efectos.
5. `our-dots -R noctalia` (instalado) → desinstala y elimina de `system.yaml`.
6. `our-dots -Q` lista packs instalados con canal y fecha.
7. `our-dots -Qs hypr` filtra packs relacionados.
8. `our-dots repo-add test https://example.com/dots` → requiere root, registra en index.
9. `dots_profiles.packs_for_profile("hyprland")` retorna todos los packs Hyprland.
10. `dots_profiles.packs_for_profile("niri")` retorna noctalia y danklinux únicamente.
11. `load_catalog()` con `MANIFEST_DIR` inexistente retorna lista vacía sin excepción.
12. Manifest inválido en directorio → ignorado, catálogo continúa cargando.
13. `system.yaml` actualizado de forma atómica (`.tmp` + `os.replace` + `flock`).
14. ISO construible con todos los manifests incluidos en `MANIFEST_DIR`.
15. CI verde: lint Python, shellcheck, pytest ≥ 93 % cobertura.
16. `our-dots -S <id> --noconfirm` con pack CRITICAL → error, sin instalación.
17. `OUROBOROS_ALLOW_CRITICAL=1 our-dots -S <id> --noconfirm` con pack CRITICAL → procede sin panel.
18. Fallo inyectado en instalación CRITICAL → trap de cleanup restaura `/` a read-only.

---

## 13. Dependencias y Restricciones

### Dependencias del Sistema

| Dependencia | Versión Mínima | Rol |
|-------------|---------------|-----|
| Python | 3.11+ | Runtime de manifests y escritura atómica |
| PyYAML | 6.0+ | Parsing de manifests y system.yaml |
| Bash | 5.0+ | Binary `our-dots` |
| `our-pac` | v0.6.0+ | Instalación de paquetes pacman |
| `our-aur` | v0.6.0+ | Instalación de paquetes AUR |
| git | 2.30+ | Clonar repos externos y post_deploy de packs git |
| curl | 7.80+ | Descargar repos HTTP y verificar actualizaciones AUR |
| util-linux (`flock`) | 2.37+ | Advisory lock para escritura concurrente de system.yaml |

### Restricciones Técnicas

- `our-dots` requiere `sudo` para operaciones de escritura en `/etc/` y `/var/`.
- `post_deploy` se ejecuta como `$SUDO_USER` (no como root) para respetar el entorno del usuario.
- Los manifests en `MANIFEST_DIR` son read-only (parte del ISO); solo los repos externos son mutables.
- `system.yaml` es la única fuente de verdad para el estado de instalación — no hay base de datos propia.
- `our-dots` usa `flock` sobre `system.yaml.lock` para prevenir escrituras concurrentes. El lock tiene timeout de 5 segundos.
- Los packs CRITICAL requieren análisis manual de compatibilidad antes de cada release de ouroborOS.
- Todos los scripts `.sh` deben pasar `shellcheck -S style` y comenzar con `set -euo pipefail`.
- Los manifests externos deben servirse exclusivamente por HTTPS.
- Los manifests de repositorios externos son validados contra el schema (§6.8) antes de ejecutar cualquier hook.

### Restricciones de Compatibilidad

- Packs con perfil `hyprland` solo están disponibles si el sistema tiene Hyprland instalado.
- Packs con perfil `niri` solo están disponibles si el sistema tiene Niri instalado.
- El instalador TUI filtra el catálogo por `compatibility.profiles` — un pack fuera de perfil nunca aparece en la UI aunque esté instalable via CLI.

---

## 14. Glosario

| Término | Definición |
|---------|-----------|
| **built-in** | Pack incluido en el catálogo oficial de ouroborOS, distribuido dentro del ISO. Read-only. |
| **canal git** | Canal de distribución que apunta al último commit del repositorio del pack. Término canónico — anteriormente llamado "rolling" o "bleeding edge" informalmente. |
| **canal stable** | Canal de distribución que apunta a una versión etiquetada del pack. |
| **compatibility level** | Nivel de impacto de un pack sobre el sistema inmutable. Valores: `low`, `medium`, `high`, `critical`. Ver tabla en §6.8. |
| **CRITICAL** | Pack cuya instalación requiere acciones que modifican el sistema raíz de forma temporal (remount rw, edición de `/etc`). Requiere confirmación explícita "yes" o `OUROBOROS_ALLOW_CRITICAL=1`. |
| **EXTERN** | Prefijo visual (`[EXTERN]`) que indica que un pack proviene de un repositorio externo no auditado por el proyecto ouroborOS. |
| **manifest** | Archivo YAML que describe un pack de dotfiles: ID, dependencias, compatibilidad, canales y hooks. Schema definido en §6.8. |
| **MANIFEST_DIR** | Directorio de manifests built-in incluido en el ISO (read-only). |
| **OUROBOROS_ALLOW_CRITICAL=1** | Variable de entorno que habilita la instalación de packs CRITICAL en modo no-interactivo. Solo para CI y automatización. |
| **pack** | Conjunto de dotfiles, configuraciones y dependencias que definen un entorno de escritorio Linux, gestionado por `our-dots`. |
| **post_deploy** | Hook ejecutado tras la instalación de paquetes de un pack. Corre como `$SUDO_USER` (no como root). |
| **post_remove** | Hook ejecutado tras la desinstalación de paquetes de un pack. Corre como `$SUDO_USER`. |
| **REPOS_DIR** | Directorio donde se almacenan los manifests de repositorios externos (mutable). |
| **SUDO_USER** | Variable de entorno con el nombre del usuario original cuando se ejecuta un comando con `sudo`. |
| **system.yaml** | Archivo de configuración declarativa de ouroborOS en `/etc/ouroboros/system.yaml`. Fuente de verdad del estado del sistema. |
| **dots_packs** | Clave en `system.yaml` que registra los packs instalados por `our-dots`, con canal, versión y fecha de instalación. |
