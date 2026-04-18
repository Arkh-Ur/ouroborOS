- El error está en el diagrama unificado — al hacer `checkout pub-origin-main` y luego `merge main`, Mermaid se confunde porque `pub-origin-main` nació de `main`. La solución es representar los mirrors como commits directos en `pub-origin-main`, que es más fiel a la realidad (es un push, no un merge).

  Acá va todo el documento corregido:

  ---

  # Plan: Alinear CI a estrategia dev-first (v2)

  ## Flujo completo entre repos

  ```mermaid
  flowchart LR
      subgraph LOCAL["💻 Local"]
          direction TB
          L_DEV["dev"]
      end
  
      subgraph PRIVATE["🔒 ouroborOS-dev (privado)"]
          direction TB
          P_DEV["origin/dev"]
          P_CI{"CI: lint\ntest + build"}
          P_TAG["🏷️ Tag v0.5.X"]
          P_MAIN["origin/main"]
          P_PRE["📦 Prerelease ISO"]
      end
  
      subgraph PUBLIC["🌍 ouroborOS (público)"]
          direction TB
          PU_MAIN["origin/main"]
          PU_REL["🚀 GitHub Release"]
      end
  
      L_DEV -->|"git push"| P_DEV
      P_DEV -->|"trigger"| P_CI
  
      P_CI -->|"❌ Falla"| L_DEV
  
      P_CI -->|"✅ Verde"| P_TAG
      P_TAG -->|"trigger release job"| P_PRE
      P_PRE -->|"merge tag → main"| P_MAIN
      P_MAIN -->|"mirror push"| PU_MAIN
      P_MAIN -->|"mirror push"| PU_REL
  
      style L_DEV fill:#4CAF50,color:white
      style P_DEV fill:#4CAF50,color:white
      style P_CI fill:#FFC107,color:black
      style P_TAG fill:#FF9800,color:white
      style P_PRE fill:#9C27B0,color:white
      style P_MAIN fill:#9E9E9E,color:white
      style PU_MAIN fill:#2196F3,color:white
      style PU_REL fill:#2196F3,color:white
  ```

  ---

  ## Detalle del flujo paso a paso

  ```mermaid
  flowchart TD
      subgraph STEP1["① Local → Private origin/dev"]
          S1A["💻 git push origin dev"] --> S1B["🔒 origin/dev actualizado"]
      end
  
      subgraph STEP2["② CI se dispara en privado"]
          S2A["🔒 origin/dev"] --> S2B["Lint"]
          S2B --> S2C["Test"]
          S2C --> S2D["Build"]
          S2D --> S2E{"¿Todo verde?"}
          S2E -->|"No"| S2F["❌ Arreglar en local\nvolver a ①"]
          S2E -->|"Sí"| S2G["✅ Habilitado para tag"]
      end
  
      subgraph STEP3["③ Tag en private origin/dev"]
          S3A["🔒 git tag v0.5.X origin/dev"] --> S3B["🏷️ Release job se dispara"]
      end
  
      subgraph STEP4["④ Prerelease en privado"]
          S4A["🔒 Build ISO"] --> S4B["🔒 Prerelease en\nouroborOS-dev"]
          S4B --> S4C["🔒 Merge tag → origin/main\n(ouroborOS-dev)"]
      end
  
      subgraph STEP5["⑤ Mirror a público"]
          S5A["🔒 origin/main\n(privado)"] --> S5B["🌍 Push a origin/main\n(ouroborOS público)"]
          S5A --> S5C["🌍 GitHub Release\n(ouroborOS público)"]
      end
  
      STEP1 --> STEP2
      STEP2 --> STEP3
      STEP3 --> STEP4
      STEP4 --> STEP5
  
      style STEP1 fill:#E8F5E9,color:black
      style STEP2 fill:#FFF8E1,color:black
      style STEP3 fill:#FFF3E0,color:black
      style STEP4 fill:#F3E5F5,color:black
      style STEP5 fill:#E3F2FD,color:black
  ```

  ---

  ## Reglas estrictas del flujo

  ```mermaid
  flowchart TD
      START["Developer push"] --> Q1{"¿Branch?"}
  
      Q1 -->|"dev"| CI_RUN["CI: lint + test + build"]
      Q1 -->|"cualquier otra"| BLOCK1["❌ BLOQUEADO\nSolo dev"]
  
      CI_RUN --> Q2{"¿Todo verde?"}
      Q2 -->|"No"| FIX["❌ Arreglar en dev\nNo se puede taggear"]
      Q2 -->|"Sí"| CAN_TAG["✅ Habilitado para taggear"]
  
      CAN_TAG --> Q3{"¿Se creó tag v*?"}
      Q3 -->|"No"| WAIT["⏳ Seguir desarrollando en dev"]
      Q3 -->|"Sí"| RELEASE["🚀 Release job se dispara"]
  
      RELEASE --> BUILD["Build ISO + Prerelease\nen repo privado"]
      BUILD --> MERGE["Merge tag → origin/main\nrepo privado"]
      MERGE --> MIRROR["Mirror origin/main →\nrepo público + GitHub Release"]
  
      Q1 -->|"directo a main"| BLOCK2["❌ BLOQUEADO\nNadie pushea a main\nSolo CI via tag"]
  
      style BLOCK1 fill:#F44336,color:white
      style BLOCK2 fill:#F44336,color:white
      style FIX fill:#F44336,color:white
      style CAN_TAG fill:#4CAF50,color:white
      style RELEASE fill:#FF9800,color:white
      style BUILD fill:#9C27B0,color:white
      style MERGE fill:#9E9E9E,color:white
      style MIRROR fill:#2196F3,color:white
  ```

  ---

  ## Gate de protección: tag solo con CI verde

  ```mermaid
  flowchart LR
      subgraph GATE["🚧 Gate de protección"]
          direction TB
          PUSH["Push a dev"] --> LINT["Lint"]
          LINT --> TEST["Test"]
          TEST --> BUILD["Build"]
          BUILD --> CHECK{"¿Los 3 pasaron?"}
          CHECK -->|"No"| RED["🔴 Tag BLOQUEADO"]
          CHECK -->|"Sí"| UNLOCK["🟢 Tag DESBLOQUEADO"]
      end
  
      UNLOCK -->|"git tag v0.5.X"| RELEASE_PIPELINE["Release Pipeline"]
  
      style RED fill:#F44336,color:white
      style UNLOCK fill:#4CAF50,color:white
      style GATE fill:#FFF3E0,color:black
  ```

  ---

  ## Estrategia de branches — Vista por repo

  ### ① Local (💻)

  ```mermaid
  gitGraph
      commit id: "init"
      branch dev
      checkout dev
      commit id: "work"
      commit id: "work"
      commit id: "work"
      commit id: "CI fix"
      commit id: "work"
      commit id: "CI verde" tag: "v0.5.0"
      commit id: "work"
      commit id: "work"
      commit id: "CI verde" tag: "v0.5.1"
  ```

  > El developer trabaja siempre en `dev`. Cuando CI está verde, crea el tag localmente y lo pushea.

  ---

  ### ② Private origin — ouroborOS-dev (🔒)

  ```mermaid
  gitGraph
      commit id: "init"
      branch dev
      checkout dev
      commit id: "push"
      commit id: "push"
      commit id: "push"
      commit id: "push"
      commit id: "push"
      commit id: "push" tag: "v0.5.0"
      checkout main
      merge dev
      checkout dev
      commit id: "push"
      commit id: "push"
      commit id: "push" tag: "v0.5.1"
      checkout main
      merge dev
  ```

  > `origin/dev` recibe todos los pushes. Cuando llega un tag `v*`, el release job hace merge a `origin/main`. **Nadie toca main directamente.**

  ---

  ### ③ Public origin — ouroborOS (🌍)

  ```mermaid
  gitGraph
      commit id: "mirror v0.5.0"
      commit id: "mirror v0.5.1"
  ```

  > El repo público solo recibe mirrors desde `private origin/main`. Cada commit en público corresponde a un merge post-tag del privado.

  ---

  ### Vista unificada — Simulación con nombres descriptivos

  ```mermaid
  gitGraph
      commit id: "init commit"
  
      
      branch priv-origin-main
      branch priv-origin-dev
  
      checkout priv-origin-dev
      commit id: "dev work #1"
      commit id: "dev work #2"
      commit id: "dev work #3"
      commit id: "CI Fix"
      commit id: "CI Verde"
  
      checkout priv-origin-main
      merge priv-origin-dev tag: "v0.5.0"
  
      checkout main
      merge priv-origin-main tag: "v0.5.0 (mirror)"
  
      checkout priv-origin-dev
      commit id: "dev work #5"
      commit id: "dev work #6"
      commit id: "CI verde"
  
      checkout priv-origin-main
      merge priv-origin-dev tag: "v0.5.1"
  
      checkout main
      merge priv-origin-main tag: "v0.5.1 (mirror)"
  
      checkout priv-origin-dev
      commit id: "dev work #7"
  
  ```

  **Leyenda de branches:**

  | Branch en diagrama | Representa            | Quién escribe                      |
  | ------------------ | --------------------- | ---------------------------------- |
  | `priv-origin-dev`  | 🔒 private origin/dev  | Developer via push                 |
  | `priv-origin-main` | 🔒 private origin/main | Solo CI via release job (post-tag) |
  | `main`             | 🌍 public origin/main  | Solo mirror desde privado          |

  ---

  ## Cambios por archivo

  | Archivo                   | Cambio                                  | Razón                             |
  | ------------------------- | --------------------------------------- | --------------------------------- |
  | **build.yml** triggers    | `branches: [dev]` (sacar main)          | CI solo corre desde dev           |
  | **build.yml** PRs         | `branches: [dev]` (sacar main)          | PRs van contra dev                |
  | **build.yml** release job | Se dispara solo con tag v* en dev       | No hay release sin CI verde       |
  | **build.yml** release job | Genera prerelease en privado primero    | Validar antes de publicar         |
  | **build.yml** release job | Luego merge tag → origin/main (privado) | main solo recibe via tag          |
  | **build.yml** release job | Finalmente mirror a repo público        | Público siempre detrás de privado |
  | **lint.yml** triggers     | `branches: [dev]` en vez de `["**"]`    | Evitar lint en branches basura    |
  | **lint.yml** PRs          | `branches: [dev]` (sacar master)        | master no existe                  |
  | **test.yml** PRs          | `branches: [dev]` (sacar master)        | master no existe                  |
  | **code-review.yml** PRs   | `branches: [dev]` (sacar master)        | master no existe                  |
  | **CLAUDE.md** line 30     | v0.4.0 → v0.5.0 Phase 5                 | Desactualizado                    |
  | **CLAUDE.md** line 97-100 | Tags desde dev, no main                 | Alinear con realidad              |
  | **branch protection**     | Proteger main — nadie pushea directo    | Solo CI via tag puede tocar main  |

  ---

  ## Resumen del flujo en 5 pasos

  ```
  1. PUSH a dev        →  Solo dev, nada más
  2. CI corre          →  lint + test + build
  3. Si todo verde ✅   →  Se puede taggear
  4. Tag v* en dev     →  Release job: ISO + prerelease (privado) + merge a origin/main (privado)
  5. origin/main       →  Mirror automático a repo público + GitHub Release
  ```

  **Nada se mueve sin verde. Nada toca main sin tag. Nada es público sin pasar por privado primero.**

  ---

  ## Orden de ejecución

  1. **Fix workflows (5 archivos)** — sacar main de triggers, master de PRs
  2. **Fix CLAUDE.md** — actualizar versión, estrategia de branches
  3. **Proteger branch main** — branch protection rules en GitHub
  4. **Push a dev** — un solo commit con todo
  5. **Verificar CI** — lint + test + build corren solo desde dev
  6. **Probar release** — tag v0.5.X desde dev → prerelease privado → mirror público

  ---

  ### Qué causaba el error

  ```
  ❌ checkout pub-origin-main
  ❌ merge main                    → "Cannot merge branch 'main' into itself"
  ```

  `pub-origin-main` fue creado con `branch pub-origin-main` estando parado en `main`. Para Mermaid, ambos comparten la misma raíz y al intentar `merge main` lo interpreta como mergearse consigo mismo.

  **Solución:** En lugar de `merge main`, usar `commit id: "mirror v0.5.X"` directamente en `pub-origin-main`. Esto es además más fiel a la realidad: el repo público recibe un **push/mirror**, no un merge.
