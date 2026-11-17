import logging
import math
import sqlite3
from typing import List, Optional, Tuple, Union

from database.conexion import DatabasePath, obtener_conexion

Producto = Tuple[int, str, Optional[str], int, float, Optional[str]]
Resultado = Tuple[bool, str]


def _validar_producto(nombre: str, cantidad: int, precio: float) -> Optional[str]:
    if not nombre.strip():
        return "El nombre del producto no puede estar vacío."
    if not isinstance(cantidad, int) or isinstance(cantidad, bool) or cantidad < 0:
        return "La cantidad debe ser un entero mayor o igual a cero."
    if (
        not isinstance(precio, (int, float))
        or isinstance(precio, bool)
        or precio < 0
    ):
        return "El precio debe ser un número válido mayor o igual a cero."
    try:
        if not math.isfinite(float(precio)):
            return "El precio debe ser un número válido mayor o igual a cero."
    except (OverflowError, ValueError):
        return "El precio debe ser un número válido mayor o igual a cero."
    return None


def registrar_producto(
    nombre: str,
    descripcion: str,
    cantidad: int,
    precio: float,
    categoria: str,
    db_path: Optional[DatabasePath] = None,
) -> Resultado:
    """Valida e inserta un producto en la base de datos."""
    error = _validar_producto(nombre, cantidad, precio)
    if error:
        return False, error

    try:
        with obtener_conexion(db_path) as conexion:
            conexion.execute(
                """
                INSERT INTO productos (nombre, descripcion, cantidad, precio, categoria)
                VALUES (?, ?, ?, ?, ?)
                """,
                (nombre.strip(), descripcion, cantidad, precio, categoria),
            )
        return True, "El producto se registró correctamente en el sistema."
    except sqlite3.Error:
        logging.exception("Ocurrió un error al guardar el producto.")
        return False, "Ocurrió un error al intentar guardar en la base de datos."


def obtener_todos_productos(
    db_path: Optional[DatabasePath] = None,
) -> List[Producto]:
    """Recupera todos los productos almacenados."""
    try:
        with obtener_conexion(db_path) as conexion:
            return conexion.execute("SELECT * FROM productos").fetchall()
    except sqlite3.Error:
        logging.exception("Error al consultar los productos.")
        return []


def actualizar_producto_db(
    id_prod: int,
    nombre: str,
    descripcion: str,
    cantidad: int,
    precio: float,
    categoria: str,
    db_path: Optional[DatabasePath] = None,
) -> Resultado:
    """Valida y actualiza un producto identificado por su ID."""
    error = _validar_producto(nombre, cantidad, precio)
    if error:
        return False, error

    try:
        with obtener_conexion(db_path) as conexion:
            cursor = conexion.execute(
                """
                UPDATE productos
                SET nombre = ?, descripcion = ?, cantidad = ?, precio = ?, categoria = ?
                WHERE id = ?
                """,
                (nombre.strip(), descripcion, cantidad, precio, categoria, id_prod),
            )
            if cursor.rowcount == 0:
                return False, "No se encontró el producto que desea actualizar."
        return True, "Los datos del producto fueron actualizados con éxito."
    except sqlite3.Error:
        logging.exception("No se pudo actualizar el producto %s.", id_prod)
        return False, "No se pudo actualizar el registro por un error de base de datos."


def eliminar_producto_db(
    id_prod: int,
    db_path: Optional[DatabasePath] = None,
) -> Resultado:
    """Elimina un producto identificado por su ID."""
    try:
        with obtener_conexion(db_path) as conexion:
            cursor = conexion.execute("DELETE FROM productos WHERE id = ?", (id_prod,))
            if cursor.rowcount == 0:
                return False, "No se encontró el producto que desea eliminar."
        return True, "El producto fue eliminado del inventario."
    except sqlite3.Error:
        logging.exception("No se pudo eliminar el producto %s.", id_prod)
        return False, "No se pudo eliminar el producto por un error de base de datos."


def buscar_productos_db(
    criterio: str,
    valor: Union[str, int],
    db_path: Optional[DatabasePath] = None,
) -> List[Producto]:
    """Busca productos por ID, nombre o categoría."""
    if criterio == "id":
        try:
            id_prod = int(valor)
        except (TypeError, ValueError):
            return []
        query = "SELECT * FROM productos WHERE id = ?"
        parametros: Tuple[Union[str, int], ...] = (id_prod,)
    elif criterio == "nombre":
        query = "SELECT * FROM productos WHERE nombre LIKE ?"
        parametros = (f"%{valor}%",)
    elif criterio == "categoria":
        query = "SELECT * FROM productos WHERE categoria LIKE ?"
        parametros = (f"%{valor}%",)
    else:
        return []

    try:
        with obtener_conexion(db_path) as conexion:
            return conexion.execute(query, parametros).fetchall()
    except sqlite3.Error:
        logging.exception("Error durante la búsqueda de productos.")
        return []


def obtener_reporte_stock(
    limite: int,
    db_path: Optional[DatabasePath] = None,
) -> List[Producto]:
    """Devuelve productos cuya cantidad es menor o igual al límite indicado."""
    try:
        with obtener_conexion(db_path) as conexion:
            return conexion.execute(
                "SELECT * FROM productos WHERE cantidad <= ?", (limite,)
            ).fetchall()
    except sqlite3.Error:
        logging.exception("Error al generar el reporte de stock.")
        return []
