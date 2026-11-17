import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import openpyxl

from database.conexion import inicializar_base_datos
from services import import_export
from services.inventario import obtener_todos_productos


class ImportExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "inventory.db"
        inicializar_base_datos(self.database_path)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_importa_json_y_asigna_id_de_base(self) -> None:
        content = json.dumps(
            {
                "productos": [
                    {
                        "id": 900,
                        "nombre": "Teclado",
                        "descripcion": "Mecánico",
                        "cantidad": 4,
                        "precio": 29.5,
                        "categoria": "Periféricos",
                    }
                ]
            }
        ).encode("utf-8")

        result = import_export.importar_archivo(
            content, "productos.json", self.database_path
        )

        self.assertEqual(result.imported, 1)
        self.assertEqual(result.errors, [])
        producto = obtener_todos_productos(self.database_path)[0]
        self.assertEqual(producto[0], 1)
        self.assertEqual(producto[1], "Teclado")

    def test_valida_todo_el_lote_antes_de_guardar(self) -> None:
        content = json.dumps(
            [
                {"nombre": "Mouse", "cantidad": 1, "precio": 10},
                {"nombre": "Monitor", "cantidad": -1, "precio": 100},
            ]
        ).encode("utf-8")

        result = import_export.importar_archivo(
            content, "productos.json", self.database_path
        )

        self.assertEqual(result.imported, 0)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.errors[0].row, 2)
        self.assertEqual(obtener_todos_productos(self.database_path), [])
        report = import_export.generar_informe_errores(result.errors).decode(
            "utf-8-sig"
        )
        self.assertIn("2,cantidad", report)

    def test_importa_excel_con_encabezados_acentuados(self) -> None:
        workbook = openpyxl.Workbook()
        worksheet = workbook.active
        worksheet.append(("Nombre", "Descripción", "Cantidad", "Precio", "Categoría"))
        worksheet.append(("Mouse", "USB", 2, 12.5, "Accesorios"))
        output = io.BytesIO()
        workbook.save(output)

        result = import_export.importar_archivo(
            output.getvalue(), "productos.xlsx", self.database_path
        )

        self.assertEqual(result.imported, 1)
        self.assertEqual(result.errors, [])
        self.assertEqual(obtener_todos_productos(self.database_path)[0][1], "Mouse")

    def test_exporta_json_excel_y_respaldo_sqlite(self) -> None:
        import_export.importar_archivo(
            b'[{"nombre":"Mouse","cantidad":2,"precio":12.5}]',
            "productos.json",
            self.database_path,
        )

        json_data = json.loads(import_export.exportar_json(self.database_path))
        self.assertEqual(json_data["productos"][0]["nombre"], "Mouse")

        excel_data = import_export.exportar_excel(self.database_path)
        workbook = openpyxl.load_workbook(io.BytesIO(excel_data), data_only=True)
        self.assertEqual(workbook.active["B2"].value, "Mouse")
        workbook.close()

        backup_path = Path(self.temporary_directory.name) / "respaldo.db"
        backup_path.write_bytes(import_export.crear_respaldo(self.database_path))
        with closing(sqlite3.connect(str(backup_path))) as backup:
            row = backup.execute("SELECT nombre FROM productos").fetchone()
        self.assertEqual(row[0], "Mouse")


if __name__ == "__main__":
    unittest.main()
