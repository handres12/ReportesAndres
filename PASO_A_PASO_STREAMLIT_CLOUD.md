# Paso a paso (para dummies): Publicar el informe en Streamlit Cloud

Ya tienes cuenta en GitHub y abriste el link de Streamlit. Sigue estos pasos en orden.

---

## PARTE 1: Subir tu proyecto a GitHub

### Paso 1.1 – Crear un repositorio nuevo en GitHub

1. Entra a **https://github.com** e inicia sesión.
2. Arriba a la derecha haz clic en el **+** y elige **"New repository"**.
3. En **"Repository name"** escribe por ejemplo: `informe-ventas-andres`.
4. Elige **"Private"** si no quieres que el código sea público, o **"Public"** si no te importa.
5. **No** marques "Add a README file".
6. Clic en **"Create repository"**.

---

### Paso 1.2 – Preparar la carpeta del proyecto (no subir contraseñas)

En la carpeta de tu proyecto ya hay un archivo **`.gitignore`**. Ese archivo hace que **no** se suban cosas como `.env` (donde están las contraseñas de las bases de datos) ni la carpeta `venv`.  
No borres ese archivo y no subas nunca el archivo **`.env`**.

---

### Paso 1.3 – Subir el código desde tu PC a GitHub

1. Abre **PowerShell** o **Símbolo del sistema**.
2. Ve a la carpeta del proyecto:
   ```bash
   cd "c:\Users\Andres Reyes\proyecto_bi_streamlit"
   ```
3. Inicializa Git (solo la primera vez):
   ```bash
   git init
   ```
4. Añade todos los archivos (el .gitignore evita .env y venv):
   ```bash
   git add .
   ```
5. Primer commit:
   ```bash
   git commit -m "Primera subida del informe"
   ```
6. Conecta con tu repositorio de GitHub (cambia `TU_USUARIO` por tu usuario de GitHub y `informe-ventas-andres` por el nombre del repo que creaste):
   ```bash
   git remote add origin https://github.com/TU_USUARIO/informe-ventas-andres.git
   ```
7. Sube el código (si te pide usuario/contraseña, en GitHub ahora se usa un "Personal Access Token" en lugar de la contraseña; puedes crearlo en GitHub → Settings → Developer settings → Personal access tokens):
   ```bash
   git branch -M main
   git push -u origin main
   ```

**Importante para que el informe muestre datos:**  
La app usa la base **`bi_local_data.db`**. Si ese archivo está en la carpeta y **no** está en el `.gitignore`, se subirá y el informe en la nube tendrá datos. Si prefieres no subir la base (por tamaño o privacidad), el informe en la nube se abrirá pero sin datos hasta que configures otra fuente.

---

## PARTE 2: Crear el informe en Streamlit Cloud

### Paso 2.1 – Entrar a Streamlit Cloud

1. Abre **https://share.streamlit.io**.
2. Clic en **"Sign in with GitHub"** e inicia sesión con tu cuenta de GitHub si no lo has hecho.
3. Autoriza a Streamlit cuando GitHub lo pida.

---

### Paso 2.2 – Crear una app nueva

1. Clic en **"New app"** (o "Create new app").
2. En **"Repository"** elige tu repositorio (ej. `TU_USUARIO/informe-ventas-andres`).
3. En **"Branch"** deja **`main`**.
4. En **"Main file path"** escribe: **`app.py`** (es el archivo que arranca el informe).
5. **"App URL"** (opcional): puedes dejar el que te propone o poner algo como `informe-ventas-andres` para que el link sea `https://informe-ventas-andres.streamlit.app`.
6. Clic en **"Deploy"** o **"Create"**.

---

### Paso 2.3 – Esperar a que construya

1. Streamlit va a instalar lo que pone en `requirements.txt` y luego ejecutar `app.py`.
2. Puede tardar 1–3 minutos. Verás un log en pantalla.
3. Si todo va bien, al final verás **"Your app is live!"** y un link tipo:
   **`https://informe-ventas-andres.streamlit.app`**
4. Ese es **tu link**: ábrelo y compártelo. El informe ya está en la web.

---

### Si algo falla (errores en el log)

- **Error de módulo no encontrado:** falta algo en `requirements.txt`. Dime el mensaje y lo añadimos.
- **Error de base de datos:** la app busca `bi_local_data.db`. Si no lo subiste, en la nube no hay datos; sube ese archivo al repo (y quita `bi_local_data.db` del `.gitignore` si lo tenías) y vuelve a desplegar (re-run o "Reboot app").
- **Error de conexión a SQL Server:** en la nube la app no puede llegar a tu SQL Server de la oficina; por eso la app está pensada para usar solo el SQLite local (`bi_local_data.db`). Sube ese `.db` al repo para que el informe en la nube tenga datos.

---

## Resumen rápido

| Dónde | Qué hacer |
|-------|-----------|
| **GitHub** | Crear repo → en tu PC: `git init`, `git add .`, `git commit`, `git remote add origin ...`, `git push`. |
| **share.streamlit.io** | New app → elegir repo, branch `main`, Main file `app.py` → Deploy. |
| **Link final** | Te lo da Streamlit: `https://algo.streamlit.app` |

Cuando quieras actualizar el informe (código o datos), haz cambios en tu PC, luego:

```bash
git add .
git commit -m "Actualización"
git push
```

En Streamlit Cloud, si está configurado para redeploy automático, se actualizará solo; si no, en la app haz clic en "Reboot app" o "Redeploy".
