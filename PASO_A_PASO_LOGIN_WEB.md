# Paso a paso: que el login con Microsoft funcione en la WEB (Streamlit Cloud)

En local ya te funciona. En la **nube** la app usa un flujo OAuth alternativo (Authlib) que no depende de la ruta `/oauth2callback`; el redirect es la **URL raíz** de la app. En Azure debes tener esa raíz como URI de redirección.

---

## 1. Formato de Secrets recomendado para la web (un solo bloque [auth])

En la documentación oficial, el deploy en Community Cloud usa **todo en un solo bloque `[auth]`**, sin `[auth.microsoft]`. En la nube prueba primero así.

En **Streamlit Cloud → Settings → Secrets** borra todo y pega **exactamente** este esquema (sustituye solo los valores que indico):

```toml
[auth]
redirect_uri = "https://reportesandresbi.streamlit.app/oauth2callback"
cookie_secret = "PEGA_AQUI_TU_COOKIE_SECRET"
client_id = "PEGA_AQUI_CLIENT_ID_DE_AZURE"
client_secret = "PEGA_AQUI_CLIENT_SECRET_DE_AZURE"
server_metadata_url = "https://login.microsoftonline.com/7585caec-e96f-4b86-926e-7e4462c93c2a/v2.0/.well-known/openid-configuration"
```

- **redirect_uri:** tiene que ser exactamente esa URL (con `oauth2callback` al final). No uses `https://reportesandresbi.streamlit.app/` sin la ruta.
- **cookie_secret:** el mismo que usas en local en `.streamlit/secrets.toml`, o una cadena larga aleatoria nueva.
- **client_id:** Id. de aplicación (cliente) de Azure (ReportesAndres).
- **client_secret:** Valor del secreto de cliente de Azure (Certificados y secretos).
- **server_metadata_url:** debe ser la URL del **documento de descubrimiento OIDC** (termina en `/.well-known/openid-configuration`). No uses la URL de “authorize” (`/oauth2/v2.0/authorize`).

Guarda con **Save changes** y espera ~1 minuto.

---

## 2. Azure: dos URIs de redirección (Web)

Para que el login en la web funcione, en Azure tienen que estar **las dos** URIs siguientes.

1. Entra a **https://portal.azure.com** → **Microsoft Entra ID** → **Registros de aplicaciones** → **ReportesAndres**.
2. Menú **Autenticación**.
3. En **Configuración de la plataforma** → **Web** deben aparecer **estas dos** (si falta una, **Agregar URI**):
   - `https://reportesandresbi.streamlit.app/oauth2callback`
   - **`https://reportesandresbi.streamlit.app/`**  ← necesaria para el flujo en la nube (URL raíz, con barra final).
4. Puedes tener además la de local: `http://localhost:8501/oauth2callback`.
5. **Guardar**.

---

## 3. Comprobar versión de Streamlit y Authlib (evitar error 400 en la nube)

Hay un bug conocido con Authlib 1.6.6 que provoca error 400 al usar Microsoft; se corrige con **Streamlit 1.52.2 o superior**.

En tu repositorio, en **requirements.txt** debe figurar:

```text
streamlit>=1.52.2
Authlib>=1.3.2
```

Si ya está así, no cambies nada. Si tenías `streamlit>=1.42.0`, sube a `1.52.2` o superior y haz commit y push para que la nube vuelva a hacer build.

---

## 4. Orden recomendado (resumen)

1. **Azure:** en **Autenticación → Web** tener las dos URIs: `.../oauth2callback` y **`https://reportesandresbi.streamlit.app/`** (raíz). Guardar.
2. **Secrets en la nube:** usar el bloque único `[auth]` de arriba (sin `[auth.microsoft]`), con `redirect_uri` de la web y el resto de valores reales. Save changes.
3. **requirements.txt:** `streamlit>=1.52.2` y `Authlib>=1.3.2`. Push al repo.
4. Esperar 1–2 minutos y abrir **https://reportesandresbi.streamlit.app** en una ventana de incógnito (para evitar caché de sesión). Probar “Iniciar sesión con Microsoft”.

---

## 5. Si sigue sin funcionar

- En la pantalla de login de la app en la web, abre **«¿No funciona el login? Ver diagnóstico»** y revisa:
  - **redirect_uri termina en oauth2callback:** debe decir **sí**.
  - **client_id / client_secret en secrets:** deben decir **sí**.
  - **st.user / st.login:** deben decir **sí** (si sale “no”, la versión de Streamlit en la nube puede ser antigua; asegura `streamlit>=1.52.2` y redeploy).
- En Azure, comprueba que la URI de redirección esté escrita **igual** que en Secrets (mismo dominio, misma ruta `/oauth2callback`, sin espacios).
- Prueba en otra red o en modo incógnito por si hay caché o bloqueos.

Referencia: [Streamlit – Use Microsoft Entra to authenticate users](https://docs.streamlit.io/develop/tutorials/authentication/microsoft), sección “Deploy your app on Community Cloud”.
