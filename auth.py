"""
Sistema de registro e inicio de sesión para el informe BI.
Usa la misma base SQLite (bi_local_data.db). Contraseñas con bcrypt.
"""
from datetime import datetime
from sqlalchemy import text

def init_auth_table(engine):
    """Crea la tabla usuarios si no existe."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                creado TEXT NOT NULL
            )
        """))
        conn.commit()

def register(engine, usuario, password):
    """
    Registra un usuario. Devuelve True si se creó, False si ya existe o error.
    """
    from passlib.hash import bcrypt
    usuario = (usuario or "").strip()
    if not usuario or not password:
        return False
    init_auth_table(engine)
    password_hash = bcrypt.hash(password)
    try:
        with engine.connect() as conn:
            conn.execute(
                text("INSERT INTO usuarios (usuario, password_hash, creado) VALUES (:u, :h, :c)"),
                {"u": usuario, "h": password_hash, "c": datetime.utcnow().isoformat()}
            )
            conn.commit()
        return True
    except Exception:
        return False

def verify(engine, usuario, password):
    """
    Verifica usuario y contraseña. Devuelve True si son correctos.
    """
    from passlib.hash import bcrypt
    usuario = (usuario or "").strip()
    if not usuario or not password:
        return False
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT password_hash FROM usuarios WHERE usuario = :u"),
                {"u": usuario}
            ).fetchone()
        if not row:
            return False
        return bcrypt.verify(password, row[0])
    except Exception:
        return False
