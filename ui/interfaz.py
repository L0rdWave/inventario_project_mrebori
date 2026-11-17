import sqlite3
from pathlib import Path
from typing import Callable, Dict

from colorama import init, Fore, Style
from database.conexion import inicializar_base_datos
from services import import_export, inventario

# Inicializamos colorama para asegurar el correcto funcionamiento multiplataforma de los colores
init(autoreset=True)

def mostrar_menu() -> None:
    """Imprime en consola el menú principal de opciones con formato visual."""
    print(f"\n{Fore.CYAN}========================================")
    print(f"{Fore.YELLOW}     SISTEMA DE GESTIÓN DE INVENTARIO   ")
    print(f"{Fore.CYAN}========================================")
    print(f"{Fore.GREEN}1.{Style.RESET_ALL} Registrar nuevo producto")
    print(f"{Fore.GREEN}2.{Style.RESET_ALL} Visualizar productos")
    print(f"{Fore.GREEN}3.{Style.RESET_ALL} Actualizar producto")
    print(f"{Fore.GREEN}4.{Style.RESET_ALL} Eliminar producto")
    print(f"{Fore.GREEN}5.{Style.RESET_ALL} Buscar producto")
    print(f"{Fore.GREEN}6.{Style.RESET_ALL} Reporte de bajo stock")
    print(f"{Fore.RED}7.{Style.RESET_ALL} Salir")
    print(f"{Fore.GREEN}8.{Style.RESET_ALL} Importar Excel o JSON")
    print(f"{Fore.GREEN}9.{Style.RESET_ALL} Exportar inventario a JSON")
    print(f"{Fore.GREEN}10.{Style.RESET_ALL} Exportar inventario a Excel")
    print(f"{Fore.GREEN}11.{Style.RESET_ALL} Crear respaldo de la base")
    print(f"{Fore.CYAN}----------------------------------------")

def interfaz_registrar() -> None:
    """Captura los datos por consola para dar de alta un nuevo producto."""
    print(f"\n{Fore.YELLOW}--- Registrar Nuevo Producto ---")
    nombre = input("Nombre del producto: ").strip()
    if not nombre:
        print(f"{Fore.RED}El nombre no puede quedar vacío.")
        return

    descripcion = input("Descripción (opcional): ").strip()

    try:
        cantidad = int(input("Cantidad disponible: "))
        precio = float(input("Precio unitario: "))
    except ValueError:
        print(f"{Fore.RED}Error: La cantidad debe ser un número entero y el precio un valor numérico.")
        return

    categoria = input("Categoría: ").strip()

    exito, mensaje = inventario.registrar_producto(nombre, descripcion, cantidad, precio, categoria)
    if exito:
        print(f"{Fore.GREEN}{mensaje}")
    else:
        print(f"{Fore.RED}{mensaje}")

def interfaz_visualizar() -> None:
    """Muestra en formato de tabla clara todos los productos cargados."""
    productos = inventario.obtener_todos_productos()
    if not productos:
        print(f"\n{Fore.YELLOW}No hay productos cargados en el inventario.")
        return

    print(f"\n{Fore.CYAN}--- Listado General de Inventario ---")
    print(f"{'ID':<4} | {'Nombre':<15} | {'Cant':<6} | {'Precio':<8} | {'Categoría'}")
    print("-" * 55)
    for p in productos:
        print(f"{p[0]:<4} | {p[1]:<15} | {p[3]:<6} | ${p[4]:<7.2f} | {p[5]}")

def interfaz_actualizar() -> None:
    """Permite modificar los atributos de un producto existente buscando por su ID."""
    interfaz_visualizar()
    try:
        id_prod = int(input(f"\n{Fore.YELLOW}Ingrese el ID del producto que desea actualizar: "))
    except ValueError:
        print(f"{Fore.RED}El ID ingresado no es válido.")
        return

    res = inventario.buscar_productos_db("id", id_prod)
    if not res:
        print(f"{Fore.RED}No se encontró ningún producto con ese ID.")
        return

    prod = res[0]
    print(f"Modificando producto: {prod[1]} (Presione Enter para conservar el valor actual)")

    nombre = input(f"Nuevo nombre [{prod[1]}]: ").strip() or prod[1]
    descripcion = input(f"Nueva descripción [{prod[2]}]: ").strip() or prod[2] or ""

    try:
        cant_str = input(f"Nueva cantidad [{prod[3]}]: ").strip()
        cantidad = int(cant_str) if cant_str else prod[3]

        precio_str = input(f"Nuevo precio [{prod[4]}]: ").strip()
        precio = float(precio_str) if precio_str else prod[4]
    except ValueError:
        print(f"{Fore.RED}La cantidad debe ser entera y el precio debe ser numérico.")
        return

    categoria = input(f"Nueva categoría [{prod[5]}]: ").strip() or prod[5] or ""

    exito, msg = inventario.actualizar_producto_db(id_prod, nombre, descripcion, cantidad, precio, categoria)
    print(f"{Fore.GREEN}{msg}" if exito else f"{Fore.RED}{msg}")

def interfaz_eliminar() -> None:
    """Procede a dar de baja un producto tras verificar su existencia y confirmación."""
    interfaz_visualizar()
    try:
        id_prod = int(input(f"\n{Fore.RED}Ingrese el ID del producto a eliminar: "))
    except ValueError:
        print(f"{Fore.RED}Debe ingresar un número de ID válido.")
        return

    confirmacion = input(f"¿Confirma que desea eliminar el producto con ID {id_prod}? (s/n): ").lower()
    if confirmacion == 's':
        exito, msg = inventario.eliminar_producto_db(id_prod)
        print(f"{Fore.GREEN}{msg}" if exito else f"{Fore.RED}{msg}")
    else:
        print("Operación cancelada por el usuario.")

def interfaz_buscar() -> None:
    """Gestiona las opciones de búsqueda avanzada según criterio seleccionado."""
    print(f"\n{Fore.CYAN}--- Criterios de Búsqueda ---")
    print("1. Buscar por ID")
    print("2. Buscar por Nombre")
    print("3. Buscar por Categoría")
    op = input("Seleccione una opción: ").strip()

    criterios = {"1": "id", "2": "nombre", "3": "categoria"}
    if op not in criterios:
        print(f"{Fore.RED}Opción de búsqueda no válida.")
        return

    val = input(f"Ingrese el valor a buscar: ").strip()
    resultados = inventario.buscar_productos_db(criterios[op], val)

    if not resultados:
        print(f"{Fore.YELLOW}No se encontraron registros coincidentes.")
        return

    print(f"\n{Fore.GREEN}--- Resultados de la Búsqueda ---")
    for p in resultados:
        print(f"ID: {p[0]} | Nombre: {p[1]} | Desc: {p[2]} | Cant: {p[3]} | Precio: ${p[4]:.2f} | Cat: {p[5]}")

def interfaz_reporte() -> None:
    """Solicita un límite numérico y despliega el reporte de productos con stock crítico."""
    try:
        limite = int(input(f"\n{Fore.YELLOW}Ingrese el límite máximo de stock para el reporte: "))
    except ValueError:
        print(f"{Fore.RED}Debe ingresar un número entero válido.")
        return

    productos = inventario.obtener_reporte_stock(limite)
    if not productos:
        print(f"{Fore.GREEN}No hay productos con stock menor o igual a {limite}.")
        return

    print(f"\n{Fore.RED}--- Reporte de Stock Crítico (<= {limite}) ---")
    for p in productos:
        print(f"ID: {p[0]} | Nombre: {p[1]} | Stock actual: {p[3]} | Categoría: {p[5]}")


def _guardar_archivo(prefijo: str, extension: str, content: bytes) -> None:
    path = Path.cwd() / import_export.nombre_con_fecha(prefijo, extension)
    try:
        path.write_bytes(content)
    except OSError:
        print(f"{Fore.RED}No se pudo guardar el archivo en {path}.")
        return
    print(f"{Fore.GREEN}Archivo guardado: {path}")


def interfaz_importar_archivo() -> None:
    ruta = input("Ruta del archivo .xls, .xlsx o .json: ").strip().strip('"')
    if not ruta:
        print(f"{Fore.RED}No se indicó una ruta.")
        return

    path = Path(ruta).expanduser()
    try:
        with path.open("rb") as input_file:
            content = input_file.read(import_export.MAX_IMPORT_BYTES + 1)
    except OSError:
        resultado = import_export.ImportResult(
            0,
            [
                import_export.ImportIssue(
                    0, "archivo", "No se pudo abrir la ruta indicada."
                )
            ],
        )
    else:
        resultado = import_export.importar_archivo(content, path.name)

    if resultado.errors:
        report = import_export.generar_informe_errores(resultado.errors)
        _guardar_archivo("errores_importacion", "csv", report)
        cantidad_errores = len(resultado.errors)
        etiqueta_errores = "error" if cantidad_errores == 1 else "errores"
        print(
            f"{Fore.RED}No se importó ningún producto. "
            f"Se encontraron {cantidad_errores} {etiqueta_errores}."
        )
        return
    etiqueta_producto = "producto" if resultado.imported == 1 else "productos"
    print(
        f"{Fore.GREEN}Se importaron {resultado.imported} "
        f"{etiqueta_producto}."
    )


def _exportar_archivo(prefijo: str, extension: str, generador: Callable[[], bytes]) -> None:
    try:
        content = generador()
    except (OSError, sqlite3.Error, ValueError):
        print(f"{Fore.RED}No se pudo generar el archivo de exportación.")
        return
    _guardar_archivo(prefijo, extension, content)


def interfaz_exportar_json() -> None:
    _exportar_archivo("inventario", "json", import_export.exportar_json)


def interfaz_exportar_excel() -> None:
    _exportar_archivo("inventario", "xlsx", import_export.exportar_excel)


def interfaz_crear_respaldo() -> None:
    _exportar_archivo("respaldo_inventario", "db", import_export.crear_respaldo)


def ejecutar_menu() -> None:
    """Inicializa la base compartida y ejecuta el menú interactivo de consola."""
    inicializar_base_datos()
    acciones: Dict[str, Callable[[], None]] = {
        "1": interfaz_registrar,
        "2": interfaz_visualizar,
        "3": interfaz_actualizar,
        "4": interfaz_eliminar,
        "5": interfaz_buscar,
        "6": interfaz_reporte,
        "8": interfaz_importar_archivo,
        "9": interfaz_exportar_json,
        "10": interfaz_exportar_excel,
        "11": interfaz_crear_respaldo,
    }

    while True:
        mostrar_menu()
        opcion = input("Seleccione una opción: ").strip()
        if opcion == "7":
            print("Hasta luego.")
            return

        accion = acciones.get(opcion)
        if accion is None:
            print(f"{Fore.RED}Opción no válida. Intente nuevamente.")
            continue
        accion()


if __name__ == "__main__":
    ejecutar_menu()
