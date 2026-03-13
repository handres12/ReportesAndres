# Paso a paso: Login con Microsoft (local y web)

Guía por casos. Elige **solo local** o **local + web**.

---

## Caso 1: Login con Microsoft solo en LOCAL (tu PC)

### 1.1 Azure: registrar la aplicación (una sola vez)

1. Abre **https://portal.azure.com** e inicia sesión con tu **cuenta corporativa** (Outlook / Microsoft 365).
2. Busca **Microsoft Entra ID** → **Registros de aplicaciones** → **+ Nuevo registro**.
3. **Nombre:** por ejemplo `Informe Ventas Andrés`.
4. **Tipos de cuenta:** **Solo cuentas de este directorio organizativo** (solo tu organización).
5. **URI de redirección:** plataforma **Web**, URL:
   ```text
   http://localhost:8501/oauth2callback
   ```
6. Clic en **Registrar**.

### 1.2 Azure: copiar datos de la app

7. En la página de la app, copia **Id. de aplicación (cliente)** → lo usarás como `client_id`.
8. Menú **Certificados y secretos** → **+ Nuevo secreto de cliente** → copia el **Valor** (solo se muestra una vez) → es tu `client_secret`.
9. Menú **Puntos de conexión** → copia **Documento de metadatos de OpenID Connect** → es tu `server_metadata_url` (o usa la URL con tu Tenant ID: `https://login.microsoftonline.com/<TU_TENANT_ID>/v2.0/.well-known/openid-configuration`).

### 1.3 Azure: confirmar URI de redirección

10. Menú **Autenticación** → en **Web** debe estar `http://localhost:8501/oauth2callback`. Si no, **Agregar URI**, pegar esa URL y **Guardar**.

### 1.4 En tu PC: archivo de secrets

11. En la carpeta del proyecto, crea (o edita) el archivo **`.streamlit/secrets.toml`** (no lo subas a Git).
12. Pega este bloque y reemplaza los valores por los de Azure y un `cookie_secret` aleatorio:

```toml
[auth]
redirect_uri = "http://localhost:8501/oauth2callback"
cookie_secret = "una-cadena-aleatoria-muy-larga-y-segura"
client_id = "pega-aqui-el-application-client-id"
client_secret = "pega-aqui-el-valor-del-secreto"
server_metadata_url = "https://login.microsoftonline.com/TU_TENANT_ID/v2.0/.well-known/openid-configuration"
```

13. **cookie_secret:** inventa una cadena larga (o usa un generador de contraseñas). No puede estar vacía.
14. Guarda el archivo.

### 1.5 Probar en local

15. En la terminal: `streamlit run app.py`.
16. Abre **http://localhost:8501**.
17. Deberías ver **"Iniciar sesión con Microsoft"**. Al hacer clic, te lleva a Microsoft, inicias sesión y vuelves al informe.

---

## Caso 2: Login con Microsoft en la WEB (Streamlit Cloud)

Haz primero **Caso 1** (local). Luego añade los pasos siguientes para que funcione también en la URL de la nube (ej. `https://reportesandresbi.streamlit.app`).

### 2.1 Azure: añadir URI de redirección de la nube

1. Entra a **https://portal.azure.com** → **Microsoft Entra ID** → **Registros de aplicaciones** → tu app (la misma del Caso 1).
2. Menú **Autenticación**.
3. En **Configuración de la plataforma** → **Web**, clic en **Agregar URI**.
4. Pega (con la URL real de tu app en Streamlit Cloud):
   ```text
   https://reportesandresbi.streamlit.app/oauth2callback
   ```
   Si tu app tiene otra URL, cambia solo la parte del nombre: `https://TU-NOMBRE-APP.streamlit.app/oauth2callback`.
5. **Guardar**.

### 2.2 Streamlit Cloud: pegar Secrets

6. Entra a **https://share.streamlit.io** e inicia sesión.
7. Abre tu app (**reportesandresbi** o el nombre que tenga).
8. Menú **Settings** (o configuración) → **Secrets**.
9. En el cuadro de texto, pega el bloque **completo** `[auth]` con la URI de la **nube** (no la de local):

```toml
[auth]
redirect_uri = "https://reportesandresbi.streamlit.app/oauth2callback"
cookie_secret = "la-misma-cadena-aleatoria-que-en-local"
client_id = "el-mismo-client-id-de-azure"
client_secret = "el-mismo-client-secret-de-azure"
server_metadata_url = "https://login.microsoftonline.com/TU_TENANT_ID/v2.0/.well-known/openid-configuration"
```

10. **Importante:** `redirect_uri` debe terminar en **`/oauth2callback`**. No uses solo `https://...streamlit.app/`.
11. Clic en **Save changes**.

### 2.3 Esperar redeploy y probar

12. La app en la nube se reiniciará en unos segundos.
13. Abre **https://reportesandresbi.streamlit.app** (tu URL real).
14. Deberías ver **"Iniciar sesión con Microsoft"**. Al hacer clic, Microsoft te redirige y, tras iniciar sesión, vuelves al informe en la nube.

### 2.4 Si en la web no funciona

15. En la pantalla de login de la app en la nube, abre el desplegable **«¿No funciona el login? Ver diagnóstico»**.
16. Revisa:
    - **st.user / st.login:** deben decir **sí**. Si dicen **no**, la versión de Streamlit en la nube puede no soportar auth.
    - **client_id / client_secret en secrets:** **sí**.
    - **redirect_uri termina en oauth2callback:** **sí**. Si sale **no**, corrige en Secrets y en Azure la URI a `.../oauth2callback`.
17. Comprueba en Azure que en **Autenticación** → **Web** figure exactamente la misma URL que pusiste en `redirect_uri` en Streamlit Secrets.

---

## Resumen rápido

| Dónde        | redirect_uri |
|-------------|---------------|
| **Solo local** | `http://localhost:8501/oauth2callback` |
| **Web (Cloud)**| `https://reportesandresbi.streamlit.app/oauth2callback` |

- **Local:** todo va en `.streamlit/secrets.toml` (no subir a Git).
- **Web:** todo va en **Streamlit Cloud → Settings → Secrets** (mismo bloque, con `redirect_uri` de la nube).
- **Azure:** en la misma app puedes tener las **dos** URIs de redirección (local y nube) a la vez.
