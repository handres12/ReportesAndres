# Actualización en la nube: no depender de tu equipo

Hoy la **app en la web** (Streamlit Cloud) ya está en la nube; lo que sigue dependiendo de tu PC es **quién ejecuta los ETLs** (y el push a GitHub). Si tu equipo está apagado a las 6:30, 8:00 o 10:00, no hay actualización y la web muestra datos viejos.

Para que el servicio **no dependa de tu equipo**, hay que **ejecutar el pipeline (ETLs + push) en algún recurso que esté siempre disponible** (o se encienda a la hora indicada) y que pueda conectarse a SQL Server y a GitHub.

---

## 1. Dónde puede correr el pipeline

El pipeline necesita:
- **Conexión a SQL Server** (base principal + NEWACRVentas). Si hoy solo se conecta desde tu red (oficina/VPN), ese recurso debe estar en la misma red o tener acceso (VPN, regla de firewall, etc.).
- **Python** + dependencias (pandas, sqlalchemy, etc.) y el código del proyecto.
- **Variables de entorno** (`.env`): cadenas de conexión SQL, FTP, token de GitHub para push.
- **Git** para hacer push de `bi_local_data.db` al repo (para que Streamlit Cloud use datos nuevos).

---

## 2. Opciones (de más simple a más avanzada)

### A. Máquina virtual pequeña en Azure (u otro proveedor) – **recomendada**

- **Qué es:** Una VM barata (ej. **Azure B1s**: 1 vCPU, 1 GB RAM) que está encendida 24/7 (o solo en ventanas de tiempo si configuras encendido/apagado automático).
- **Qué hace:** En la VM instalas Python, clonas el repo, configuras `.env` (o usas Azure Key Vault para secretos). Programas las tres ejecuciones (6:30, 8:00, 10:00) con **cron** (Linux) o **Programador de tareas** (Windows). La VM ejecuta `run_pipeline_diario.py` a esas horas y hace push a GitHub.
- **Ventajas:** Misma lógica que hoy; no dependes de tu PC. Control total.
- **Coste aproximado:** ~10–15 USD/mes (B1s 24/7). Menos si apagas la VM fuera de las horas de actualización (ej. con Azure Automation start/stop).
- **Requisito:** Que la VM pueda conectarse a SQL Server (misma red, VPN o que el firewall de SQL permita la IP pública de la VM si SQL es accesible por internet).

### B. Azure Functions (timer trigger) o Azure Automation Runbook

- **Qué es:** Una función o runbook que se ejecuta en un horario (6:30, 8:00, 10:00) sin tener una VM encendida todo el rato.
- **Qué hace:** El código del ETL (o un script que llama a tu repo y ejecuta el pipeline) corre en Azure; al terminar, sube `bi_local_data.db` al repo (por ejemplo vía API de GitHub o Git desde el entorno de ejecución).
- **Ventajas:** No pagas por una VM 24/7; solo por las ejecuciones.
- **Desventajas:** Montar el entorno (Python, dependencias, acceso a SQL, push a GitHub) en Functions/Runbook es más técnico. Si SQL Server solo es accesible desde tu red, necesitas una red privada (VNet) o un hybrid worker en tu red.

### C. GitHub Actions (workflow programado)

- **Qué es:** Un workflow que se dispara por **cron** (ej. 6:30, 8:00, 10:00 en tu zona horaria) y en cada ejecución corre en un runner de GitHub (una máquina en la nube de GitHub).
- **Qué hace:** El workflow haría checkout del repo, instalaría Python y dependencias, ejecutaría `run_pipeline_diario.py` (o los ETLs + push).
- **Limitación importante:** El runner de GitHub está en internet. Si tu **SQL Server no es accesible desde internet** (solo desde tu oficina/VPN), el workflow **no podrá conectarse** y fallará. Solo sirve si SQL es público (con restricción por IP) o si usas un **self-hosted runner** (una máquina tuya, por ejemplo una VM en Azure) que sí tenga acceso a SQL; en ese caso es parecido a la opción A pero con el “programador” en GitHub.

### D. Otra VM de bajo costo (no Azure)

- Misma idea que A: una VM en AWS (EC2 pequeña), Google Cloud, DigitalOcean, etc., con Linux o Windows, Python, repo, `.env`, y cron o Programador de tareas. El coste y la complejidad son similares.

---

## 3. Recomendación práctica

- **Si quieres el menor esfuerzo y tener el servicio estable sin depender de tu PC:**  
  **VM pequeña en Azure (u otro proveedor)** que esté encendida en los horarios que necesites (o 24/7 si el coste es aceptable), con el mismo script que ya usas (`programar_tres_actualizaciones.ps1` o equivalente en cron) y las tres ejecuciones (6:30, 8:00, 10:00). Así el servicio es “más web”: la actualización ya no depende de tu equipo.

- **Si SQL Server solo es accesible desde tu red:**  
  Esa VM debe tener acceso (misma red, VPN o túnel). Opciones: VM en una red virtual que se conecte a tu red (VPN site-to-site o ExpressRoute), o una VM “dentro” de tu red que solo salga a internet para hacer push a GitHub.

- **Si quieres evitar mantener una VM:**  
  Se puede explorar Azure Functions / Automation o un runbook, asumiendo que resolverás el acceso a SQL (red/VNet o hybrid worker). Es el siguiente paso una vez tengas clara la conectividad.

---

## 4. Pasos mínimos para una VM en Azure (opción A)

1. Crear una VM (ej. Ubuntu o Windows Server) de tamaño mínimo (B1s o similar).
2. Abrir en el firewall de la VM (y en NSG de Azure) solo lo necesario (SSH o RDP; no exponer SQL desde internet si no hace falta).
3. En la VM: instalar Python 3.11, Git; clonar el repo; crear `.env` con las cadenas de conexión SQL, FTP y token de GitHub (o usar Key Vault y leer desde ahí).
4. Si la VM debe alcanzar SQL Server en tu red: configurar VPN (site-to-site o punto a sitio) o permitir la IP de la VM en el firewall de SQL (si aplica).
5. Programar las tres ejecuciones:
   - **Linux:** crontab con algo como `15 6 * * *`, `0 8 * * *`, `0 10 * * *` (ajustar zona horaria) ejecutando un script que active el venv y llame a `python run_pipeline_diario.py`.
   - **Windows:** usar el mismo `programar_tres_actualizaciones.ps1` o crear las tareas a mano en el Programador de tareas.
6. Comprobar una ejecución manual en la VM y luego revisar que a las 6:30, 8:00 y 10:00 se actualice el repo y la web en Streamlit Cloud.

Con eso, **cada actualización es menos local y más web**: el servicio ya no depende de que tu equipo esté encendido.
