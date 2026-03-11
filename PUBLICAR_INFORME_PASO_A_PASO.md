# Publicar el informe en la web — Paso a paso (para dummies)

Sigue los pasos en orden. No te saltes ninguno.

---

## PARTE A: Crear el repositorio en GitHub

**Paso 1.** Abre el navegador y entra a: **https://github.com**  
Inicia sesión con tu cuenta (ej. handres12).

**Paso 2.** Arriba a la derecha verás un botón **"+"** o **"New"**. Haz clic y elige **"New repository"**.

**Paso 3.** En la página "Create a new repository":
- **Owner:** deja tu usuario (ej. handres12).
- **Repository name:** escribe un nombre, por ejemplo **ReporteAndres** (sin espacios).
- **Description:** opcional, puedes dejarlo en blanco.
- **Visibility:** elige **Public**.
- **NO** marques "Add a README file".
- **NO** agregues .gitignore ni licencia (tu proyecto ya los tiene).
- Haz clic en el botón verde **"Create repository"**.

**Paso 4.** GitHub te mostrará una página con instrucciones. **No cierres esa pestaña.** La necesitas para saber que el repo ya existe. La URL será algo como: `https://github.com/handres12/ReporteAndres`

---

## PARTE B: Subir el código de tu PC a GitHub

**Paso 5.** Abre **PowerShell** (clic derecho en Inicio → Windows PowerShell, o búscalo en el menú).

**Paso 6.** Escribe o pega este comando y pulsa Enter (sirve para ir a la carpeta del proyecto):
```bash
cd "c:\Users\Andres Reyes\proyecto_bi_streamlit"
```

**Paso 7.** Comprueba si ya usas Git en esta carpeta. Escribe:
```bash
git status
```
y pulsa Enter.

- Si dice **"not a git repository"** → sigue al **Paso 8**.
- Si muestra archivos o "On branch main" → sigue al **Paso 10**.

**Paso 8.** (Solo si en el Paso 7 dijo "not a git repository") Inicializa Git:
```bash
git init
```
Pulsa Enter.

**Paso 9.** Añade todos los archivos y haz el primer guardado (commit):
```bash
git add .
```
Pulsa Enter. Luego:
```bash
git commit -m "Primera subida del informe"
```
Pulsa Enter.

**Paso 10.** Conecta tu carpeta con el repositorio de GitHub. **Cambia handres12 y ReporteAndres** si usaste otro usuario o nombre de repo:
```bash
git remote add origin https://github.com/handres12/ReporteAndres.git
```
Pulsa Enter.

Si te dice que "origin already exists", usa en su lugar:
```bash
git remote set-url origin https://github.com/handres12/ReporteAndres.git
```
Pulsa Enter.

**Paso 11.** Sube el código a GitHub:
```bash
git branch -M main
```
Pulsa Enter. Luego:
```bash
git push -u origin main
```
Pulsa Enter.

**Paso 12.** Si te pide **usuario y contraseña**:
- Usuario: tu usuario de GitHub (ej. handres12).
- Contraseña: **no** uses la contraseña de tu cuenta. GitHub ya no la acepta. Debes usar un **Personal access token**:
  1. En GitHub: clic en tu foto (arriba derecha) → **Settings**.
  2. Abajo a la izquierda: **Developer settings** → **Personal access tokens** → **Tokens (classic)**.
  3. **Generate new token (classic)**. Ponle un nombre (ej. "Streamlit") y marca **repo**.
  4. **Generate token**. Copia el token (solo se muestra una vez).
  5. En PowerShell, donde pide contraseña, pega ese token.

Cuando termine sin errores, tu código ya está en GitHub. Puedes comprobarlo entrando a `https://github.com/handres12/ReporteAndres` y viendo la lista de archivos (app.py, etc.).

---

## PARTE C: Publicar el informe en Streamlit Cloud

**Paso 13.** Abre una nueva pestaña y entra a: **https://share.streamlit.io**

**Paso 14.** Si no has entrado antes, haz clic en **"Sign in with GitHub"** e inicia sesión. Autoriza a Streamlit cuando GitHub lo pida.

**Paso 15.** En la página principal de Streamlit Cloud, haz clic en **"New app"** (o "Deploy an app").

**Paso 16.** Rellena el formulario:
- **Repository:** escribe exactamente **handres12/ReporteAndres** (tu usuario, una barra, nombre del repo). Si ves "Switch to interactive picker", puedes usarlo y elegir el repo desde la lista.
- **Branch:** escribe **main**.
- **Main file path:** escribe **app.py**.
- **App URL (optional):** escribe un nombre corto para tu link, por ejemplo **biandres** o **reporte-andres** (solo letras, números y guiones). Tu informe quedará en: `https://biandres.streamlit.app` (o el nombre que pongas).

**Paso 17.** Haz clic en el botón **"Deploy"** (o "Create").

**Paso 18.** Espera 1 a 3 minutos. Streamlit instalará lo necesario y arrancará la app. Cuando termine verás **"Your app is live!"** y un link (ej. https://biandres.streamlit.app). Ese es el link de tu informe; puedes compartirlo con quien quieras.

---

## Resumen rápido

| Parte | Qué haces |
|-------|-----------|
| **A** | GitHub → + → New repository → nombre ReporteAndres → Public → Create repository |
| **B** | PowerShell: cd a la carpeta → git init (si aplica) → git add . → git commit → git remote add origin → git push |
| **C** | share.streamlit.io → Sign in with GitHub → New app → repo handres12/ReporteAndres, main, app.py → Deploy |

Cuando quieras actualizar el informe en la web: haz tus cambios en el PC, luego en PowerShell ejecuta `git add .`, `git commit -m "Actualización"` y `git push`. Streamlit actualizará la app solo.
