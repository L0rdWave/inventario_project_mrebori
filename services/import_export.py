import csv
import io
import json
import logging
import math
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from xml.etree.ElementTree import ParseError

import openpyxl
import xlrd
from openpyxl.utils.exceptions import InvalidFileException

from database.conexion import DatabasePath, obtener_conexion

MAX_IMPORT_BYTES = 10 * 1024 * 1024
MAX_IMPORT_RECORDS = 10000
MAX_SQLITE_INTEGER = 2**63 - 1
PRODUCT_FIELDS = ("nombre", "descripcion", "cantidad", "precio", "categoria")
REQUIRED_FIELDS = ("nombre", "cantidad", "precio")
HEADER_ALIASES = {
    "descripción": "descripcion",
    "categoría": "categoria",
}


@dataclass(frozen=True)
class ImportIssue:
    row: int
    field: str
    message: str


@dataclass(frozen=True)
class ImportResult:
    imported: int
    errors: List[ImportIssue]


def nombre_con_fecha(prefijo: str, extension: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return f"{prefijo}_{timestamp}.{extension.lstrip('.')}"


def _normalizar_campo(value: object) -> str:
    field = str(value).strip().lower()
    return HEADER_ALIASES.get(field, field)


def _es_fila_vacia(values: List[object]) -> bool:
    return all(
        value is None or (isinstance(value, str) and not value.strip())
        for value in values
    )


def _leer_json(content: bytes) -> Tuple[List[Tuple[int, object]], List[ImportIssue]]:
    try:
        decoded: object = json.loads(content.decode("utf-8-sig"))
    except UnicodeDecodeError:
        return [], [ImportIssue(1, "JSON", "El archivo debe estar codificado en UTF-8.")]
    except json.JSONDecodeError as error:
        return [], [
            ImportIssue(
                error.lineno,
                "JSON",
                f"JSON inválido en la línea {error.lineno}, columna {error.colno}.",
            )
        ]
    except RecursionError:
        return [], [ImportIssue(1, "JSON", "La estructura del JSON es demasiado profunda.")]

    records: object = decoded
    if isinstance(decoded, dict):
        records = decoded.get("productos")
    if not isinstance(records, list):
        return [], [
            ImportIssue(
                1,
                "estructura",
                "Se esperaba una lista de productos o un objeto con una lista 'productos'.",
            )
        ]
    if len(records) > MAX_IMPORT_RECORDS:
        return [], [
            ImportIssue(
                0,
                "productos",
                f"El archivo supera el máximo de {MAX_IMPORT_RECORDS} productos.",
            )
        ]
    return list(enumerate(records, start=1)), []


def _encabezados_excel(
    values: List[object],
) -> Tuple[Dict[int, str], List[ImportIssue]]:
    headers: Dict[int, str] = {}
    seen: Dict[str, int] = {}
    errors: List[ImportIssue] = []
    for column, value in enumerate(values):
        field = _normalizar_campo(value) if value is not None else ""
        if not field:
            continue
        if field in seen:
            errors.append(
                ImportIssue(
                    1,
                    field,
                    f"El encabezado '{field}' está repetido en las columnas "
                    f"{seen[field]} y {column + 1}.",
                )
            )
            continue
        headers[column] = field
        seen[field] = column + 1

    for field in REQUIRED_FIELDS:
        if field not in seen:
            errors.append(
                ImportIssue(1, field, f"Falta la columna obligatoria '{field}'.")
            )
    return headers, errors


def _leer_xlsx(content: bytes) -> Tuple[List[Tuple[int, object]], List[ImportIssue]]:
    try:
        workbook = openpyxl.load_workbook(
            io.BytesIO(content), read_only=True, data_only=True
        )
    except (
        InvalidFileException,
        OSError,
        zipfile.BadZipFile,
        KeyError,
        ParseError,
        ValueError,
    ):
        return [], [
            ImportIssue(
                1,
                "archivo",
                "No se pudo leer el XLSX. Verificá que el archivo sea válido.",
            )
        ]

    records: List[Tuple[int, object]] = []
    try:
        worksheet = workbook.active
        iterator = worksheet.iter_rows(values_only=True)
        first_row = next(iterator, None)
        if first_row is None:
            return [], [ImportIssue(1, "encabezados", "La hoja está vacía.")]
        headers, header_errors = _encabezados_excel(list(first_row))
        if header_errors:
            return [], header_errors

        for row_number, values in enumerate(iterator, start=2):
            cells = list(values)
            if _es_fila_vacia(cells):
                continue
            record = {
                field: cells[column] if column < len(cells) else None
                for column, field in headers.items()
            }
            records.append((row_number, record))
            if len(records) > MAX_IMPORT_RECORDS:
                return [], [
                    ImportIssue(
                        row_number,
                        "productos",
                        f"El archivo supera el máximo de {MAX_IMPORT_RECORDS} productos.",
                    )
                ]
    except (
        InvalidFileException,
        OSError,
        zipfile.BadZipFile,
        KeyError,
        ParseError,
        ValueError,
    ):
        return [], [
            ImportIssue(
                1,
                "archivo",
                "No se pudo leer el XLSX. Verificá que el archivo sea válido.",
            )
        ]
    finally:
        workbook.close()
    return records, []


def _leer_xls(content: bytes) -> Tuple[List[Tuple[int, object]], List[ImportIssue]]:
    try:
        workbook = xlrd.open_workbook(file_contents=content, on_demand=True)
    except (xlrd.XLRDError, OSError):
        return [], [
            ImportIssue(
                1,
                "archivo",
                "No se pudo leer el XLS. Verificá que el archivo sea válido.",
            )
        ]

    try:
        if workbook.nsheets == 0:
            return [], [ImportIssue(1, "encabezados", "El libro no contiene hojas.")]
        worksheet = workbook.sheet_by_index(0)
        if worksheet.nrows == 0:
            return [], [ImportIssue(1, "encabezados", "La hoja está vacía.")]

        headers, header_errors = _encabezados_excel(worksheet.row_values(0))
        if header_errors:
            return [], header_errors

        records: List[Tuple[int, object]] = []
        for row_index in range(1, worksheet.nrows):
            values = worksheet.row_values(row_index)
            if _es_fila_vacia(values):
                continue
            for column, value in enumerate(values):
                if worksheet.cell(row_index, column).ctype == xlrd.XL_CELL_DATE:
                    values[column] = xlrd.xldate_as_datetime(
                        value, workbook.datemode
                    )
            record = {
                field: values[column] if column < len(values) else None
                for column, field in headers.items()
            }
            records.append((row_index + 1, record))
            if len(records) > MAX_IMPORT_RECORDS:
                return [], [
                    ImportIssue(
                        row_index + 1,
                        "productos",
                        f"El archivo supera el máximo de {MAX_IMPORT_RECORDS} productos.",
                    )
                ]
        return records, []
    finally:
        workbook.release_resources()


def _cantidad_entera(value: object) -> Optional[int]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value <= MAX_SQLITE_INTEGER else None
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        integer = int(value)
        return integer if integer <= MAX_SQLITE_INTEGER else None
    if isinstance(value, str):
        try:
            integer = int(value.strip())
        except ValueError:
            try:
                parsed = float(value.strip())
            except ValueError:
                return None
            if not math.isfinite(parsed) or not parsed.is_integer():
                return None
            integer = int(parsed)
        return integer if integer <= MAX_SQLITE_INTEGER else None
    return None


def _precio_valido(value: object) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    if not isinstance(value, (int, float, str)):
        return None
    try:
        parsed = float(value.strip()) if isinstance(value, str) else float(value)
    except (OverflowError, ValueError):
        return None
    if math.isfinite(parsed) and parsed >= 0:
        return parsed
    return None


def _validar_registro(
    row_number: int, record: object
) -> Tuple[Optional[Tuple[str, str, int, float, str]], List[ImportIssue]]:
    if not isinstance(record, dict):
        return None, [
            ImportIssue(row_number, "registro", "El registro debe ser un objeto.")
        ]

    fields = {
        _normalizar_campo(key): value
        for key, value in record.items()
        if isinstance(key, str)
    }
    errors: List[ImportIssue] = []

    name = fields.get("nombre")
    if not isinstance(name, str) or not name.strip():
        errors.append(
            ImportIssue(row_number, "nombre", "El nombre es obligatorio y debe ser texto.")
        )
        name = ""
    else:
        name = name.strip()

    quantity = _cantidad_entera(fields.get("cantidad"))
    if quantity is None or quantity < 0:
        errors.append(
            ImportIssue(
                row_number,
                "cantidad",
                "La cantidad debe ser un entero mayor o igual a cero.",
            )
        )
        quantity = 0

    price = _precio_valido(fields.get("precio"))
    if price is None:
        errors.append(
            ImportIssue(
                row_number,
                "precio",
                "El precio debe ser un número válido mayor o igual a cero.",
            )
        )
        price = 0.0

    description = fields.get("descripcion")
    category = fields.get("categoria")
    description = "" if description is None else str(description).strip()
    category = "" if category is None else str(category).strip()

    if errors:
        return None, errors
    return (name, description, quantity, price, category), []


def importar_archivo(
    content: bytes,
    filename: str,
    db_path: Optional[DatabasePath] = None,
) -> ImportResult:
    """Valida e importa un XLS, XLSX o JSON completo en una sola transacción."""
    if len(content) > MAX_IMPORT_BYTES:
        return ImportResult(
            0,
            [
                ImportIssue(
                    0,
                    "archivo",
                    f"El archivo supera el máximo de {MAX_IMPORT_BYTES // (1024 * 1024)} MB.",
                )
            ],
        )

    extension = Path(filename).suffix.lower()
    if extension == ".json":
        rows, errors = _leer_json(content)
    elif extension == ".xlsx":
        rows, errors = _leer_xlsx(content)
    elif extension == ".xls":
        rows, errors = _leer_xls(content)
    else:
        return ImportResult(
            0,
            [
                ImportIssue(
                    0,
                    "archivo",
                    "Formato no admitido. Usá .xls, .xlsx o .json.",
                )
            ],
        )

    if errors:
        return ImportResult(0, errors)
    if not rows:
        return ImportResult(
            0, [ImportIssue(0, "productos", "El archivo no contiene productos.")]
        )

    products: List[Tuple[str, str, int, float, str]] = []
    for row_number, record in rows:
        product, record_errors = _validar_registro(row_number, record)
        errors.extend(record_errors)
        if product is not None:
            products.append(product)
    if errors:
        return ImportResult(0, errors)

    try:
        with obtener_conexion(db_path) as conexion:
            conexion.executemany(
                """
                INSERT INTO productos (nombre, descripcion, cantidad, precio, categoria)
                VALUES (?, ?, ?, ?, ?)
                """,
                products,
            )
    except sqlite3.Error:
        logging.exception("Falló la importación masiva desde %s.", extension)
        return ImportResult(
            0,
            [
                ImportIssue(
                    0,
                    "base de datos",
                    "No se pudo guardar el lote. No se importó ningún producto.",
                )
            ],
        )
    return ImportResult(len(products), [])


def generar_informe_errores(errors: List[ImportIssue]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("fila", "campo", "error"))
    for error in errors:
        writer.writerow((error.row, error.field, error.message))
    return output.getvalue().encode("utf-8-sig")


def _obtener_productos(
    db_path: Optional[DatabasePath] = None,
) -> List[Tuple[int, str, Optional[str], int, float, Optional[str]]]:
    try:
        with obtener_conexion(db_path) as conexion:
            return conexion.execute(
                """
                SELECT id, nombre, descripcion, cantidad, precio, categoria
                FROM productos
                ORDER BY id
                """
            ).fetchall()
    except sqlite3.Error:
        logging.exception("No se pudieron leer los productos para exportar.")
        raise


def exportar_json(db_path: Optional[DatabasePath] = None) -> bytes:
    products = [
        {
            "id": product[0],
            "nombre": product[1],
            "descripcion": product[2] or "",
            "cantidad": product[3],
            "precio": product[4],
            "categoria": product[5] or "",
        }
        for product in _obtener_productos(db_path)
    ]
    content = json.dumps(
        {"productos": products}, ensure_ascii=False, indent=2, allow_nan=False
    )
    return content.encode("utf-8")


def exportar_excel(db_path: Optional[DatabasePath] = None) -> bytes:
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "Productos"
    worksheet.append(("id", *PRODUCT_FIELDS))
    for product in _obtener_productos(db_path):
        worksheet.append(
            tuple(
                _valor_excel_seguro(value)
                for value in (
                    product[0],
                    product[1],
                    product[2] or "",
                    product[3],
                    product[4],
                    product[5] or "",
                )
            )
        )
    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions
    for column, width in zip(
        ("A", "B", "C", "D", "E", "F"), (10, 28, 38, 14, 14, 24)
    ):
        worksheet.column_dimensions[column].width = width

    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def _valor_excel_seguro(value: object) -> object:
    if isinstance(value, str) and value.lstrip(" \t\r\n")[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def crear_respaldo(db_path: Optional[DatabasePath] = None) -> bytes:
    """Genera una copia SQLite consistente usando la API de respaldo."""
    backup_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temporary_file:
            backup_path = Path(temporary_file.name)
        with obtener_conexion(db_path) as source:
            destination = sqlite3.connect(str(backup_path))
            try:
                source.backup(destination)
            finally:
                destination.close()
        return backup_path.read_bytes()
    except (OSError, sqlite3.Error):
        logging.exception("No se pudo generar el respaldo de la base.")
        raise
    finally:
        if backup_path is not None:
            try:
                backup_path.unlink()
            except FileNotFoundError:
                pass
