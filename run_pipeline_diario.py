"""
Pipeline diario: ETLs + (opcional) FTP 2025 + subida a GitHub.
Una sola sentencia para cargar todo a pasos:

  python run_pipeline_diario.py

Uso:
  python run_pipeline_diario.py

Para programar cada día (Programador de tareas de Windows):
  - Acción: Iniciar un programa
  - Programa: python (o ruta completa a python.exe)
  - Argumentos: run_pipeline_diario.py
  - Iniciar en: carpeta del proyecto (donde está .env y bi_local_data.db)

Opciones (variables de entorno):
  RUN_FTP=0           -> no ejecutar listar_ftp_ventas_2025.py --cargar (por defecto sí se ejecuta)
  PUSH_DB_TO_GITHUB=0  -> no subir la base a GitHub (por defecto sí se sube)
"""
import os
import sys
import subprocess
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("America/Bogota")
except Exception:
    TZ = None


def _ahora():
    if TZ:
        return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def run_paso(nombre, comando, obligatorio=True):
    """Ejecuta un comando (lista: [python, script.py, ...]) y retorna True si salió bien."""
    print()
    print("=" * 60)
    print(f"  {nombre}")
    print("=" * 60)
    r = subprocess.run(comando, cwd=SCRIPT_DIR)
    ok = r.returncode == 0
    if ok:
        print(f"[OK] {nombre} terminó correctamente.")
    else:
        print(f"[ERROR] {nombre} terminó con código {r.returncode}.")
    return ok


def main():
    print()
    print("=" * 60)
    print(f"  PIPELINE DIARIO - INICIO {_ahora()}")
    print("=" * 60)

    # Paso 1: ETLs (maestros, ventas SQL, Excel)
    if not run_paso("Paso 1: ETLs (maestros, ventas, Excel)", [sys.executable, "ejecutar_etls.py"], obligatorio=True):
        print()
        print("[PIPELINE] Se detuvo por error en ETLs. Revisa conexión SQL y archivos Excel.")
        sys.exit(1)

    # Paso 2: FTP 2025 (opcional)
    run_ftp = os.getenv("RUN_FTP", "1").strip().lower() not in ("0", "false", "no")
    if run_ftp:
        run_paso("Paso 2: Histórico 2025 desde FTP", [sys.executable, "listar_ftp_ventas_2025.py", "--cargar"], obligatorio=False)
    else:
        print()
        print("[PIPELINE] Paso 2 omitido (RUN_FTP=0).")

    # Paso 3: Subir base a GitHub para la web
    push = os.getenv("PUSH_DB_TO_GITHUB", "1").strip().lower() not in ("0", "false", "no")
    if push:
        if not run_paso("Paso 3: Subir bi_local_data.db a GitHub", [sys.executable, "push_db_to_github.py"], obligatorio=False):
            print("[PIPELINE] No se pudo subir a GitHub. Revisa Git y remote origin.")
    else:
        print()
        print("[PIPELINE] Paso 3 omitido (PUSH_DB_TO_GITHUB=0).")

    print()
    print("=" * 60)
    print(f"  PIPELINE DIARIO - FIN {_ahora()}")
    print("=" * 60)
    print()
    sys.exit(0)


if __name__ == "__main__":
    main()
