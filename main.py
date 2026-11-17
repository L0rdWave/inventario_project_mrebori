import os
import secrets
import sqlite3
from io import BytesIO
from pathlib import Path
from typing import List, Mapping, Optional, Tuple, Union

from flask import (
    Flask,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from database.conexion import inicializar_base_datos
from services import import_export, inventario

PROJECT_ROOT = Path(__file__).resolve().parent
DatosProducto = Tuple[str, str, int, float, str]


def _datos_producto_del_formulario() -> Optional[DatosProducto]:
    nombre = request.form.get("nombre", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    categoria = request.form.get("categoria", "").strip()

    try:
        cantidad = int(request.form.get("cantidad", ""))
        precio = float(request.form.get("precio", ""))
    except ValueError:
        flash("La cantidad debe ser entera y el precio debe ser numérico.", "danger")
        return None

    return nombre, descripcion, cantidad, precio, categoria


def _descargar_informe_errores(
    errors: List[import_export.ImportIssue],
) -> Response:
    return send_file(
        BytesIO(import_export.generar_informe_errores(errors)),
        mimetype="text/csv; charset=utf-8",
        as_attachment=True,
        download_name=import_export.nombre_con_fecha(
            "errores_importacion", "csv"
        ),
    )


def create_app(test_config: Optional[Mapping[str, object]] = None) -> Flask:
    """Construye la aplicación con configuración aislable para pruebas."""
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32),
        DATABASE_PATH=os.environ.get(
            "INVENTARIO_DB_PATH", str(PROJECT_ROOT / "inventario.db")
        ),
        DEBUG=os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes"},
        MAX_CONTENT_LENGTH=import_export.MAX_IMPORT_BYTES + 64 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    db_path: Union[str, Path] = app.config["DATABASE_PATH"]
    if not isinstance(db_path, (str, Path)):
        raise TypeError("DATABASE_PATH debe ser una ruta de texto o Path.")
    inicializar_base_datos(db_path)

    @app.errorhandler(413)
    def archivo_demasiado_grande(error):
        app.logger.warning("Se rechazó una carga superior al límite: %s", error)
        response = _descargar_informe_errores(
            [
                import_export.ImportIssue(
                    0,
                    "archivo",
                    "El archivo supera el límite permitido de 10 MB.",
                )
            ]
        )
        response.status_code = 413
        return response

    @app.route("/")
    def index():
        criterio = request.args.get("criterio", "").strip()
        valor = request.args.get("valor", "").strip()
        stock_limite = request.args.get("stock_limite", "").strip()

        if criterio and valor:
            if criterio == "id":
                try:
                    int(valor)
                except ValueError:
                    flash("El ID de búsqueda debe ser un número entero.", "danger")
                    productos = []
                else:
                    productos = inventario.buscar_productos_db(
                        criterio, valor, db_path
                    )
            else:
                productos = inventario.buscar_productos_db(criterio, valor, db_path)
        elif stock_limite:
            try:
                limite = int(stock_limite)
            except ValueError:
                flash("El límite de stock debe ser un número entero.", "danger")
                productos = inventario.obtener_todos_productos(db_path)
            else:
                productos = inventario.obtener_reporte_stock(limite, db_path)
        else:
            productos = inventario.obtener_todos_productos(db_path)

        return render_template("index.html", productos=productos)

    @app.route("/registrar", methods=["POST"])
    def registrar():
        datos = _datos_producto_del_formulario()
        if datos is None:
            return redirect(url_for("index"))

        exito, mensaje = inventario.registrar_producto(*datos, db_path=db_path)
        flash(mensaje, "success" if exito else "danger")
        return redirect(url_for("index"))

    @app.route("/actualizar/<int:id_prod>", methods=["POST"])
    def actualizar(id_prod: int):
        datos = _datos_producto_del_formulario()
        if datos is None:
            return redirect(url_for("index"))

        exito, mensaje = inventario.actualizar_producto_db(
            id_prod, *datos, db_path=db_path
        )
        flash(mensaje, "success" if exito else "danger")
        return redirect(url_for("index"))

    @app.route("/eliminar/<int:id_prod>", methods=["POST"])
    def eliminar(id_prod: int):
        exito, mensaje = inventario.eliminar_producto_db(id_prod, db_path)
        flash(mensaje, "info" if exito else "danger")
        return redirect(url_for("index"))

    @app.route("/importar", methods=["POST"])
    def importar():
        archivo = request.files.get("archivo")
        if archivo is None or not archivo.filename:
            return _descargar_informe_errores(
                [
                    import_export.ImportIssue(
                        0, "archivo", "Seleccioná un archivo para importar."
                    )
                ]
            )

        resultado = import_export.importar_archivo(
            archivo.read(), archivo.filename, db_path
        )
        if resultado.errors:
            return _descargar_informe_errores(resultado.errors)

        etiqueta_producto = "producto" if resultado.imported == 1 else "productos"
        flash(f"Se importaron {resultado.imported} {etiqueta_producto}.", "success")
        return redirect(url_for("index"))

    @app.route("/exportar/<string:tipo>")
    def exportar(tipo: str):
        if tipo == "json":
            generar = import_export.exportar_json
            extension = "json"
            mimetype = "application/json"
            prefijo = "inventario"
        elif tipo == "xlsx":
            generar = import_export.exportar_excel
            extension = "xlsx"
            mimetype = (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            )
            prefijo = "inventario"
        elif tipo == "respaldo":
            generar = import_export.crear_respaldo
            extension = "db"
            mimetype = "application/vnd.sqlite3"
            prefijo = "respaldo_inventario"
        else:
            abort(404)

        try:
            contenido = generar(db_path)
        except (OSError, sqlite3.Error, ValueError):
            app.logger.exception("No se pudo generar la descarga solicitada.")
            flash("No se pudo generar el archivo solicitado.", "danger")
            return redirect(url_for("index"))

        return send_file(
            BytesIO(contenido),
            mimetype=mimetype,
            as_attachment=True,
            download_name=import_export.nombre_con_fecha(prefijo, extension),
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=app.config["DEBUG"], port=5000)
