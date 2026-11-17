import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional, Union

DB_NAME = Path(
    os.environ.get(
        "INVENTARIO_DB_PATH",
        str(Path(__file__).resolve().parent.parent / "inventario.db"),
    )
).expanduser().resolve()
DatabasePath = Union[str, Path]


@contextmanager
def obtener_conexion(
    db_name: Optional[DatabasePath] = None,
) -> Generator[sqlite3.Connection, None, None]:
    """Abre una conexión que se cierra incluso si falla la operación."""
    if db_name is None:
        database_path = DB_NAME
    else:
        database_path = Path(db_name).expanduser().resolve()
    conexion = sqlite3.connect(str(database_path))
    try:
        with conexion:
            yield conexion
    finally:
        conexion.close()


def inicializar_base_datos(db_name: Optional[DatabasePath] = None) -> None:
    """Crea la tabla de productos si todavía no existe."""
    try:
        with obtener_conexion(db_name) as conexion:
            conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS productos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL,
                    descripcion TEXT,
                    cantidad INTEGER NOT NULL,
                    precio REAL NOT NULL,
                    categoria TEXT
                )
                """
            )
    except sqlite3.Error:
        logging.exception("Error crítico al inicializar la base de datos.")
        raise
