from contextlib import redirect_stdout
from contextlib import closing
from io import BytesIO
from io import StringIO
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Dict
from unittest.mock import patch

from flask.testing import FlaskClient

from main import create_app
from services import inventario
from ui import interfaz


class InventarioWebTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "test-inventario.db"
        app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "DATABASE_PATH": str(self.database_path),
            }
        )
        self.client: FlaskClient = app.test_client()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    @staticmethod
    def _datos_producto(**cambios: str) -> Dict[str, str]:
        datos = {
            "nombre": "Teclado",
            "descripcion": "Teclado mecánico",
            "cantidad": "5",
            "precio": "25.50",
            "categoria": "Periféricos",
        }
        datos.update(cambios)
        return datos

    def test_registra_producto_y_muestra_edicion_en_listado(self) -> None:
        respuesta = self.client.post("/registrar", data=self._datos_producto())

        self.assertEqual(respuesta.status_code, 302)
        productos = inventario.obtener_todos_productos(self.database_path)
        self.assertEqual(len(productos), 1)
        self.assertEqual(productos[0][1], "Teclado")

        listado = self.client.get("/")
        self.assertEqual(listado.status_code, 200)
        self.assertIn(b"Guardar cambios", listado.data)
        self.assertIn(b'data-dialog-open="edit-dialog-1"', listado.data)
        self.assertIn(b"<dialog", listado.data)
        self.assertNotIn(b"<details", listado.data)
        self.assertIn(b"$25.50", listado.data)

    def test_rechaza_datos_invalidos_en_backend(self) -> None:
        for datos in (
            self._datos_producto(cantidad="-1"),
            self._datos_producto(precio="-0.01"),
            self._datos_producto(precio="nan"),
            self._datos_producto(nombre="   "),
        ):
            with self.subTest(datos=datos):
                respuesta = self.client.post("/registrar", data=datos)
                self.assertEqual(respuesta.status_code, 302)

        self.assertEqual(inventario.obtener_todos_productos(self.database_path), [])

    def test_actualiza_y_elimina_producto(self) -> None:
        inventario.registrar_producto(
            "Teclado", "", 5, 25.5, "Periféricos", self.database_path
        )

        actualizacion = self.client.post(
            "/actualizar/1", data=self._datos_producto(nombre="Teclado nuevo")
        )
        self.assertEqual(actualizacion.status_code, 302)
        producto = inventario.buscar_productos_db("id", "1", self.database_path)[0]
        self.assertEqual(producto[1], "Teclado nuevo")

        eliminacion = self.client.post("/eliminar/1")
        self.assertEqual(eliminacion.status_code, 302)
        self.assertEqual(inventario.obtener_todos_productos(self.database_path), [])

    def test_informa_id_de_busqueda_no_numerico(self) -> None:
        respuesta = self.client.get("/?criterio=id&valor=abc")

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("debe ser un número entero".encode(), respuesta.data)

    def test_informa_id_inexistente_al_actualizar(self) -> None:
        respuesta = self.client.post(
            "/actualizar/999", data=self._datos_producto()
        )

        self.assertEqual(respuesta.status_code, 302)
        listado = self.client.get("/")
        self.assertIn("No se encontró el producto".encode(), listado.data)

    def test_terminal_guarda_en_la_misma_base_de_datos(self) -> None:
        entradas = ["1", "Mouse", "USB", "2", "10.25", "Accesorios", "7"]
        salida = StringIO()

        with patch("database.conexion.DB_NAME", self.database_path):
            with patch("builtins.input", side_effect=entradas):
                with redirect_stdout(salida):
                    interfaz.ejecutar_menu()

        productos = inventario.obtener_todos_productos(self.database_path)
        self.assertEqual(productos[0][1], "Mouse")
        self.assertIn("Hasta luego.", salida.getvalue())
        respuesta_web = self.client.get("/")
        self.assertIn(b"Mouse", respuesta_web.data)

    def test_terminal_importa_json(self) -> None:
        source_path = self.database_path.parent / "terminal-products.json"
        source_path.write_text(
            '[{"nombre":"Importado","cantidad":2,"precio":3.5}]',
            encoding="utf-8",
        )
        entradas = ["8", str(source_path), "7"]
        salida = StringIO()

        with patch("database.conexion.DB_NAME", self.database_path):
            with patch("builtins.input", side_effect=entradas):
                with redirect_stdout(salida):
                    interfaz.ejecutar_menu()

        productos = inventario.obtener_todos_productos(self.database_path)
        self.assertEqual(productos[0][1], "Importado")
        self.assertIn("Se importaron 1 producto.", salida.getvalue())

    def test_importa_json_desde_la_web(self) -> None:
        content = json.dumps(
            [{"nombre": "Web JSON", "cantidad": 3, "precio": 8.5}]
        ).encode("utf-8")
        respuesta = self.client.post(
            "/importar",
            data={"archivo": (BytesIO(content), "productos.json")},
            content_type="multipart/form-data",
        )

        self.assertEqual(respuesta.status_code, 302)
        productos = inventario.obtener_todos_productos(self.database_path)
        self.assertEqual(productos[0][1], "Web JSON")

    def test_entrega_informe_descargable_si_falla_importacion_web(self) -> None:
        content = b'[{"nombre":"Mouse","cantidad":-1,"precio":5}]'
        respuesta = self.client.post(
            "/importar",
            data={"archivo": (BytesIO(content), "productos.json")},
            content_type="multipart/form-data",
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.mimetype, "text/csv")
        self.assertIn("Content-Disposition", respuesta.headers)
        self.assertIn(b"1,cantidad", respuesta.data)
        self.assertEqual(inventario.obtener_todos_productos(self.database_path), [])

    def test_descarga_exportaciones_y_respaldo_web(self) -> None:
        inventario.registrar_producto(
            "Descarga", "", 1, 4.5, "Prueba", self.database_path
        )

        exportacion_json = self.client.get("/exportar/json")
        exportacion_excel = self.client.get("/exportar/xlsx")
        respaldo = self.client.get("/exportar/respaldo")

        self.assertEqual(exportacion_json.status_code, 200)
        self.assertEqual(
            json.loads(exportacion_json.data)["productos"][0]["nombre"], "Descarga"
        )
        self.assertEqual(exportacion_excel.status_code, 200)
        self.assertIn(b"PK", exportacion_excel.data[:2])
        self.assertEqual(respaldo.status_code, 200)

        backup_path = self.database_path.parent / "downloaded-backup.db"
        backup_path.write_bytes(respaldo.data)
        with closing(sqlite3.connect(str(backup_path))) as backup:
            row = backup.execute("SELECT nombre FROM productos").fetchone()
        self.assertEqual(row[0], "Descarga")


if __name__ == "__main__":
    unittest.main()
