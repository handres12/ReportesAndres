"""
Opcional: después de ejecutar los ETLs, sube bi_local_data.db a GitHub
para que la app en la web (Streamlit Cloud) use los datos actualizados.

Requisitos:
- Git en el PATH.
- Repositorio con remote 'origin' apuntando a GitHub.
- Poder hacer push sin prompt: token (PAT) en la URL o credenciales guardadas, o SSH.

Para desactivar el push automático: variable de entorno PUSH_DB_TO_GITHUB=0
"""
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

DB = "bi_local_data.db"
if not os.path.isfile(DB):
    print("[push_db] No existe bi_local_data.db; no se sube nada.")
    sys.exit(0)

if os.getenv("PUSH_DB_TO_GITHUB", "1").strip().lower() in ("0", "false", "no"):
    print("[push_db] PUSH_DB_TO_GITHUB=0; no se sube a GitHub.")
    sys.exit(0)

def run(cmd, check=True):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=SCRIPT_DIR)
    if check and r.returncode != 0:
        print(f"[push_db] Error: {cmd}\n{r.stderr or r.stdout}")
        return False
    return r.returncode == 0

if not run("git rev-parse --is-inside-work-tree", check=False):
    print("[push_db] No es un repositorio git; no se sube.")
    sys.exit(0)

run("git add " + DB, check=False)
run('git commit -m "Actualización automática ETL: bi_local_data.db"', check=False)
if not run("git push origin HEAD", check=False):
    print("[push_db] Falló el push. Revisa: Git en PATH, remote origin, y permisos (PAT o SSH).")
    sys.exit(1)
print("[push_db] bi_local_data.db subido a GitHub. La web se actualizará en el próximo deploy.")
