# Cómo publicar el reporte a la web (link sin dominio)

Puedes obtener un **link público** para que otros vean el reporte sin tener dominio. Dos opciones:

---

## Opción A: Link temporal desde tu PC (ngrok)

**Ventaja:** Rápido, sin subir código a internet. El link funciona mientras la app corre en tu computador.

### Pasos

1. **Instalar ngrok**  
   - Entra en [ngrok.com](https://ngrok.com), regístrate (gratis) y descarga ngrok.  
   - O con Chocolatey: `choco install ngrok`

2. **Iniciar Streamlit en tu PC**
   ```bash
   cd c:\Users\Andres Reyes\proyecto_bi_streamlit
   streamlit run app.py
   ```
   (Streamlit suele quedar en `http://localhost:8501`)

3. **Exponer ese puerto con ngrok**
   ```bash
   ngrok http 8501
   ```
   ngrok te mostrará una URL pública, por ejemplo:
   ```text
   Forwarding   https://abc123.ngrok-free.app -> http://localhost:8501
   ```
   Esa URL **https://...ngrok-free.app** es el link que puedes compartir. Cualquiera que la abra verá tu reporte (mientras la app y ngrok sigan corriendo).

4. **Importante**
   - La app usa la base SQLite y los datos de tu PC.  
   - Si apagas el PC o cierras Streamlit/ngrok, el link deja de funcionar.  
   - En la versión gratuita de ngrok la URL puede cambiar cada vez que reinicias ngrok.

---

## Opción B: Link fijo 24/7 (Streamlit Community Cloud)

**Ventaja:** Un link fijo (ej. `https://tu-proyecto.streamlit.app`) que funciona siempre, sin tener tu PC encendida.

**Limitación:** La app en la nube no tiene acceso a tu SQLite ni a tus SQL Server. Tienes que:
- **O bien** subir una copia de `bi_local_data.db` al repositorio (solo si el tamaño y la confidencialidad lo permiten),  
- **O bien** cambiar la app para que en la nube use otra fuente de datos (por ejemplo una base en la nube).

### Pasos

1. **Crear un repositorio en GitHub**  
   - [github.com/new](https://github.com/new)  
   - Sube tu proyecto (código). **No subas** el archivo `.env` (tiene contraseñas).  
   - Crea un `.gitignore` en la raíz del proyecto con algo como:
     ```gitignore
     .env
     venv/
     __pycache__/
     *.pyc
     bi_local_data.db
     ```
     Si quieres que la app en la nube use datos, puedes no ignorar `bi_local_data.db` y subir una versión “de ejemplo” o actualizada (ten en cuenta tamaño y sensibilidad de los datos).

2. **Streamlit Community Cloud**  
   - Entra en [share.streamlit.io](https://share.streamlit.io) e inicia sesión con GitHub.  
   - “New app” → elige tu repo, rama `main`, y como archivo de entrada: `app.py`.  
   - Deja el directorio en blanco si `app.py` está en la raíz.  
   - En “Advanced settings” puedes añadir variables de entorno si más adelante usas BD en la nube (nunca pongas contraseñas en el repo).

3. **Deploy**  
   - Clic en “Deploy”. Streamlit construye y publica la app.  
   - Te dará una URL tipo: `https://nombre-repo-nombre-usuario.streamlit.app`  
   - Ese es tu **link fijo** para compartir.

4. **Si la app espera `bi_local_data.db`**  
   - Si dejaste `bi_local_data.db` en el `.gitignore`, la app en la nube no tendrá datos hasta que:  
     - incluyas el `.db` en el repo (quítalo del `.gitignore` y haz commit), o  
     - modifiques la app para leer de otra fuente en la nube.

---

## Resumen

| Qué quieres | Opción | Link |
|-------------|--------|------|
| Compartir “desde acá” un rato, sin tocar GitHub | **A – ngrok** | URL que te da ngrok (cambia si reinicias ngrok) |
| Un link fijo que funcione 24/7 | **B – Streamlit Cloud** | `https://....streamlit.app` |

Para “publicar desde acá el reporte a la web sin dominio solo un link”, la opción más directa es **Opción A (ngrok)**. Si quieres un link permanente, usa **Opción B** y ten en cuenta lo de la base de datos.
