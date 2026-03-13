# Actualización automática — qué hacer hoy y qué es automático

## ¿Es automático?

**Sí.** Después de que configuras todo **una vez**, no tienes que hacer nada cada día. Windows ejecuta solo los ETLs a las 6:00 y 8:00 y, si está configurado, sube la base a GitHub para que la web se actualice.

---

## Qué hacer HOY (solo una vez)

1. **Crear las tareas en Windows**  
   Abre PowerShell en la carpeta del proyecto y ejecuta:
   ```powershell
   .\programar_tareas_etl.ps1
   ```  
   Eso crea las dos tareas (6:00 y 8:00). No tienes que volver a hacerlo.

2. **Si quieres que la web se actualice sola**  
   Configura Git para que pueda hacer `git push` sin pedirte contraseña (token de GitHub o SSH). Solo se hace una vez.

3. **Dejar la PC encendida**  
   Para que a las 6:00 y 8:00 corra todo, la computadora tiene que estar encendida a esa hora (por ejemplo, no apagarla de noche).

---

## Qué pasa TODOS LOS DÍAS (automático)

- **Nada que hacer tú.**  
- A las **6:00** Windows ejecuta el programa: corre los ETLs y sube la base a GitHub (si lo configuraste).  
- A las **8:00** lo mismo.  
- La web (Streamlit) usa la base que está en GitHub, así que se actualiza con esos datos.

---

## En una frase

**Hoy:** ejecutas el script de programación (y opcionalmente configuras el push a GitHub). **Todos los días:** no haces nada; todo corre solo si la PC está encendida a las 6 y 8.
