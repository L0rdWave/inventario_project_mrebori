# Sistema de Gestión de Inventario

Proyecto final de curso: sistema de gestión de inventario desarrollado en
Python, Flask y SQLite. Cumple los requisitos de la evaluación e incorpora una
interfaz web integrada con la terminal, carga masiva desde Excel y JSON,
exportación de datos, respaldos de la base e informes de errores.

La lógica de inventario, las conexiones y las interfaces están separadas en
módulos. Ambas interfaces trabajan con la misma base de datos.

## Requisitos

- Python 3.9 o superior
- Dependencias de `requirements.txt`

## Ejecutar

```powershell
python -m pip install -r requirements.txt
python main.py
```

Abrir `http://127.0.0.1:5000`. La base `inventario.db` se crea en la carpeta
del proyecto si todavía no existe.

## Usar desde la terminal

En otra terminal, desde la carpeta del proyecto, ejecutá:

```powershell
python -m ui.interfaz
```

La interfaz web y la terminal usan la misma base SQLite por defecto. Los
cambios hechos en una aparecen en la otra al volver a consultar; en el
navegador, actualizá la página para ver los cambios hechos desde la terminal.
Si configurás `INVENTARIO_DB_PATH`, usá la misma ruta para ambos procesos.

En el menú de consola, las opciones 8 a 11 permiten importar archivos, exportar
el inventario a JSON o Excel, y crear un respaldo de SQLite.

## Importar, exportar y respaldar

La web y la terminal pueden importar `.xls`, `.xlsx` y `.json`. Las planillas
deben tener las columnas `nombre`, `cantidad` y `precio`; `descripcion` y
`categoria` son opcionales. También se aceptan encabezados con tilde.

El JSON puede ser una lista de productos o un objeto con una propiedad
`productos`:

```json
{
  "productos": [
    {
      "nombre": "Teclado",
      "descripcion": "Mecánico",
      "cantidad": 5,
      "precio": 29.5,
      "categoria": "Periféricos"
    }
  ]
}
```

La importación valida el lote completo antes de guardarlo. Si hay errores, no
se importa ningún producto: la web descarga un CSV con fila, campo y motivo; la
terminal guarda ese informe en la carpeta actual. Los productos existentes no
se sobrescriben; los productos repetidos se agregan como registros nuevos y la
base asigna los IDs. Se admiten archivos de hasta 10 MB y lotes de hasta 10.000
productos.

Para probar la carga masiva, está disponible la planilla de ejemplo
[Ejemplo_inventario_50_articulos.xlsx](./Ejemplo_inventario_50_articulos.xlsx),
que contiene 50 productos y los encabezados aceptados por el importador. La
columna `id`, si está presente, se ignora al importar.

Las opciones de exportación descargan el inventario como `.xlsx` o `.json`.
**Descargar respaldo de la base** genera una copia completa `.db`, independiente
de esas exportaciones. Conviene guardar los respaldos en otro lugar seguro.

## Configuración

- `INVENTARIO_DB_PATH`: ruta opcional de la base SQLite. Por defecto es
  `inventario.db` junto a `main.py`.
- `FLASK_SECRET_KEY`: clave de sesión. Si no se define, se genera una clave
  aleatoria al iniciar (las sesiones anteriores no persisten entre reinicios).
- `FLASK_DEBUG`: activa el modo de depuración solo con `1`, `true` o `yes`.
  Mantenelo desactivado en producción y configurá `FLASK_SECRET_KEY`.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

Las pruebas usan bases temporales y no modifican el inventario real.
