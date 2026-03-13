# Login con Microsoft (Outlook / cuenta corporativa)

**Guía paso a paso para configurar el tenant y el correo:** ver **`CONFIGURAR_TENANT_OUTLOOK.md`**.

Si configuras la autenticación con Microsoft, **solo** quienes tengan una cuenta de Outlook/Microsoft 365 (o la cuenta que definas en Azure) podrán entrar al informe. No habrá registro público: nadie puede “crear cuenta” sin tener esa identidad.

## Cómo funciona

- **Sin configurar Microsoft:** la app usa el sistema actual (usuario/contraseña y registro libre).
- **Con Microsoft configurado:** la app muestra solo el botón “Iniciar sesión con Microsoft”. Solo entran quienes inicien sesión con esa cuenta (Outlook corporativo o la que definas en Azure).

## Pasos en Azure (Microsoft Entra ID)

1. Entra a [portal.azure.com](https://portal.azure.com) e inicia sesión.
2. **Microsoft Entra ID** (o Azure Active Directory) → **Registros de aplicaciones** → **Nuevo registro**.
3. **Nombre:** por ejemplo “Informe Ventas Andrés”.
4. **Tipos de cuenta soportados:**
   - **Solo tu organización** (recomendado para Outlook corporativo): “Cuentas solo de este directorio organizativo”. Solo usuarios de tu empresa.
   - Cualquier organización: “Cuentas de cualquier directorio organizativo”.
   - Personales: “Cuentas personales de Microsoft”.
5. **URI de redirección:** plataforma **Web** y una de estas URLs:
   - Local: `http://localhost:8501/oauth2callback`
   - En la nube: `https://reportesandresbi.streamlit.app/oauth2callback` (usa la URL real de tu app).
6. **Registrar**. En la página de la app:
   - Copia **Id. de aplicación (cliente)** → será `client_id`.
   - **Certificados y secretos** → **Nuevo secreto de cliente** → copia el **Valor** → será `client_secret` (solo se muestra una vez).
   - **Puntos de conexión** → copia **Documento de metadatos de OpenID Connect** → será `server_metadata_url`.

## URL de metadatos según el tipo de cuenta

- **Solo tu organización (un tenant):**  
  `https://login.microsoftonline.com/<TU_TENANT_ID>/v2.0/.well-known/openid-configuration`  
  (El Tenant ID está en Entra ID → Información general del directorio.)

- **Cualquier cuenta laboral:**  
  `https://login.microsoftonline.com/organizations/v2.0/.well-known/openid-configuration`

- **Solo cuentas personales (Hotmail/Outlook personal):**  
  `https://login.microsoftonline.com/consumers/v2.0/.well-known/openid-configuration`

## Configuración en la app

Crea el archivo **`.streamlit/secrets.toml`** (no lo subas a Git; ya está en `.gitignore`):

```toml
[auth]
redirect_uri = "http://localhost:8501/oauth2callback"
cookie_secret = "una-cadena-aleatoria-muy-larga-y-segura"
client_id = "tu-application-client-id"
client_secret = "tu-client-secret"
server_metadata_url = "https://login.microsoftonline.com/TU_TENANT_ID/v2.0/.well-known/openid-configuration"
```

- **En local:** `redirect_uri` con `http://localhost:8501/oauth2callback`.
- **En Streamlit Cloud:** en la configuración de la app → **Secrets**, pega el mismo bloque pero con:
  - `redirect_uri = "https://reportesandresbi.streamlit.app/oauth2callback"` (tu URL real).
- **Importante:** la URI debe terminar en **`/oauth2callback`**; si usas solo la raíz (`/`) el login no funcionará.
- **cookie_secret:** genera una cadena aleatoria larga (por ejemplo con un generador de contraseñas).
- En Azure, en **Autenticación** de la app, añade también la URI de redirección de producción (`https://...streamlit.app/oauth2callback`).

### Si no funciona: formato nombrado (Microsoft)

En **Secrets** (local o Cloud) puedes usar el formato con proveedor nombrado. La app lo detecta y usará `st.login("microsoft")`:

```toml
[auth]
redirect_uri = "https://reportesandresbi.streamlit.app/oauth2callback"
cookie_secret = "tu-cookie-secret"

[auth.microsoft]
client_id = "tu-client-id"
client_secret = "tu-client-secret"
server_metadata_url = "https://login.microsoftonline.com/TU_TENANT_ID/v2.0/.well-known/openid-configuration"
```

En la pantalla de login, abre **«¿No funciona el login? Ver diagnóstico»** para ver si `st.user`/`st.login` están disponibles y si `redirect_uri` termina en `oauth2callback`.

## Resumen

| Objetivo                         | Acción |
|----------------------------------|--------|
| Solo correo corporativo (Outlook) | Tipo “Solo este directorio” y usa `server_metadata_url` con tu `<TU_TENANT_ID>`. |
| Cualquiera puede registrarse     | No configures `[auth]`; la app seguirá con usuario/contraseña y registro. |
| No subir secretos                | `.streamlit/secrets.toml` está en `.gitignore`. En Cloud usas Secrets de la app. |
