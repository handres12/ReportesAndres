# Configurar el tenant para login con correo Outlook (Microsoft 365)

Esta guía te lleva paso a paso a obtener el **Tenant ID** de tu organización y dejar la app lista para que solo usuarios con correo Outlook corporativo puedan entrar.

---

## Si ves "Application was not found in the directory 'Divina Providencia'"

Ese error (AADSTS700016) significa: **la app está registrada en otro tenant** (otra “organización” en Azure), no en el tenant de tu correo (Divina Providencia). Para que el login funcione con tu correo corporativo:

1. Entra a **portal.azure.com** con una cuenta del **mismo dominio** que usas en Outlook (ej. @tudominio.com de Divina Providencia), no con cuenta personal ni de otra organización.
2. En ese tenant (Divina Providencia), crea un **nuevo** registro de aplicación: Microsoft Entra ID → Registros de aplicaciones → Nuevo registro.
3. Usa el **nuevo** client_id, client_secret y el **Tenant ID de Divina Providencia** en `.streamlit/secrets.toml` (y en `server_metadata_url` usa ese tenant ID).

Si no tienes permisos para crear aplicaciones en el tenant de Divina Providencia, pide a tu área de TI que registre la app allí o que te den permisos (ej. “Registro de aplicaciones”).

---

## 1. Entrar a Azure y abrir Microsoft Entra ID

1. Abre el navegador y ve a: **https://portal.azure.com**
2. Inicia sesión con tu **cuenta corporativa** (la misma con la que usas Outlook en el trabajo; debe ser del tenant donde quieres que entren los usuarios).
3. En el buscador superior (o en “Todos los servicios”) escribe: **Microsoft Entra ID** (antes se llamaba “Azure Active Directory”).
4. Entra a **Microsoft Entra ID**.

---

## 2. Obtener el Tenant ID (Id. del directorio)

1. En el menú izquierdo de **Microsoft Entra ID** haz clic en **Información general** (Overview).
2. En la página verás un bloque con datos del directorio. Busca:
   - **Id. del inquilino** (o **Tenant ID** / **Directory ID**).
3. **Cópialo** y guárdalo en un lugar seguro. Es un valor tipo:  
   `a1b2c3d4-e5f6-7890-abcd-ef1234567890`

Si no ves “Microsoft Entra ID” o “Información general”, es posible que tu cuenta no tenga permisos de administrador. En ese caso pide a tu área de TI el **Tenant ID** del directorio de la organización y di que es para registrar una aplicación que usará login con Microsoft (OpenID Connect).

---

## 3. Registrar la aplicación en Azure

1. En el menú izquierdo de **Microsoft Entra ID** → **Aplicaciones** → **Registros de aplicaciones**.
2. Clic en **+ Nuevo registro**.
3. Completa:
   - **Nombre:** por ejemplo `Informe Ventas Andrés` (lo verán los usuarios al iniciar sesión).
   - **Tipos de cuenta soportados:** selecciona **“Cuentas solo de este directorio organizativo (solo [tu organización])”**. Así solo correos de tu empresa podrán entrar.
   - **URI de redirección:**  
     - Tipo: **Web**.  
     - URL:  
       - Para probar en tu PC: `http://localhost:8501/oauth2callback`  
       - Para la app en la nube: `https://reportesandres.streamlit.app/oauth2callback`  
     Puedes añadir las dos (local y nube) en el mismo registro.
4. Clic en **Registrar**.

---

## 4. Copiar Client ID y crear el Client Secret

1. En la página de tu aplicación:
   - Copia **Id. de aplicación (cliente)** → ese es tu **client_id**.
2. Menú izquierdo → **Certificados y secretos**:
   - Clic en **+ Nuevo secreto de cliente**.
   - Descripción: por ejemplo `Streamlit informe`.
   - Vencimiento: 24 meses (o lo que permita tu política).
   - **Agregar**.
   - **Copia el Valor** del secreto de inmediato (solo se muestra una vez) → ese es tu **client_secret**.

---

## 5. Añadir la URI de redirección en Autenticación (si no la pusiste antes)

1. Menú izquierdo → **Autenticación**.
2. En **Configuración de la plataforma** → **Web** debe aparecer la URI. Si no:
   - **Agregar URI** y pega:
     - `http://localhost:8501/oauth2callback` (local)
     - `https://reportesandres.streamlit.app/oauth2callback` (nube)
3. En **Configuración avanzada** suele estar bien dejar “Sí” en **Permitir flujo de cliente público** según la plantilla de Streamlit (si Azure te lo pide).
4. **Guardar**.

---

## 6. Armar la URL de metadatos con tu Tenant ID

La URL debe ser **exactamente** (sustituye `TU_TENANT_ID` por el Id. del inquilino que copiaste):

```
https://login.microsoftonline.com/TU_TENANT_ID/v2.0/.well-known/openid-configuration
```

Ejemplo si tu Tenant ID es `a1b2c3d4-e5f6-7890-abcd-ef1234567890`:

```
https://login.microsoftonline.com/a1b2c3d4-e5f6-7890-abcd-ef1234567890/v2.0/.well-known/openid-configuration
```

Esa URL es tu **server_metadata_url**.

(Opcional: abre esa URL en el navegador; debe devolver un JSON. Si ves el JSON, el Tenant ID es correcto.)

---

## 7. Configurar la app (secrets)

Crea el archivo **`.streamlit/secrets.toml`** en la raíz del proyecto (no lo subas a Git). Contenido de ejemplo:

```toml
[auth]
redirect_uri = "http://localhost:8501/oauth2callback"
cookie_secret = "GENERA_UNA_CADENA_ALEATORIA_LARGA_32_O_MAS_CARACTERES"
client_id = "el-client-id-que-copiaste-del-paso-4"
client_secret = "el-client-secret-que-copiaste-del-paso-4"
server_metadata_url = "https://login.microsoftonline.com/TU_TENANT_ID/v2.0/.well-known/openid-configuration"
```

- Sustituye **TU_TENANT_ID** en `server_metadata_url` por tu Id. del inquilino (sin corchetes).
- Sustituye **client_id** y **client_secret** por los valores reales.
- **cookie_secret:** genera una cadena aleatoria larga (por ejemplo: https://passwordsgenerator.net/ con 32+ caracteres).

Para **probar en local:** deja `redirect_uri = "http://localhost:8501/oauth2callback"`.

Para **usar en la nube (reportesandres.streamlit.app):**
- En Streamlit Cloud → tu app → **Settings** → **Secrets**, pega el mismo bloque pero con:
  - `redirect_uri = "https://reportesandres.streamlit.app/oauth2callback"`
- Y en Azure → **Autenticación** debe estar añadida esa misma URI en “Web”.

---

## 8. Probar

1. Guarda `secrets.toml` y reinicia la app: `streamlit run app.py`.
2. Deberías ver solo el botón **“Iniciar sesión con Microsoft”**.
3. Al hacer clic, te redirige a Microsoft; inicia sesión con tu **correo corporativo** (Outlook).
4. Si todo está bien, vuelves al informe y en el sidebar verás “Conectado como [tu nombre]”.

---

## Resumen rápido

| Qué necesitas        | Dónde lo obtienes |
|----------------------|-------------------|
| **Tenant ID**        | Microsoft Entra ID → Información general → Id. del inquilino (o pedirlo a TI). |
| **client_id**        | Registros de aplicaciones → tu app → Id. de aplicación (cliente). |
| **client_secret**    | Tu app → Certificados y secretos → Nuevo secreto → copiar Valor. |
| **server_metadata_url** | `https://login.microsoftonline.com/<TENANT_ID>/v2.0/.well-known/openid-configuration` |
| **redirect_uri**     | Local: `http://localhost:8501/oauth2callback`. Nube: `https://reportesandres.streamlit.app/oauth2callback`. |

Si algo falla (por ejemplo “redirect_uri no coincide”), revisa que la URI en `.streamlit/secrets.toml` sea **exactamente** la misma que en Azure → Autenticación → Web.
