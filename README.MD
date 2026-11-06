# C11T1 Diferencias entre sistemas que simplemente funcionan y sistemas de calidad

El proyecto compara dos formas de resolver una clínica y una tienda, comenzando con versiones básicas que mezclan tareas y aceptan datos sin comprobar y pasando a versiones de calidad que separan funciones, validan entradas y conservan la información en PostgreSQL, con una pasarela local para estudiar pagos y reembolsos sin dinero real.

## Instalación y ejecución

Necesitas Linux, Git, Python y PostgreSQL con `initdb` y `pg_ctl` disponibles en la terminal.

### 1. Clonar el proyecto

Clona el repositorio y entra en la carpeta del proyecto.

```bash
git clone "https://github.com/matezepam/c11t1-diferencias-entre-sistemas-que--simplemente-funcionan--y-sistemas-de-calidad.git" c11t1
cd c11t1
```

### 2. Crear el entorno y la configuración

```bash
python -m venv .venv
.venv/bin/python -m pip install -r REQUISITOS.txt
cp .env.example .env
```

La plantilla `.env.example` contiene los campos de conexión vacíos y se puede publicar, mientras `.env` guarda tus datos personales y está excluido de Git, por lo que si ya tienes una configuración local conserva ese archivo y omite la copia de la plantilla.

### 3. Preparar PostgreSQL y las cuentas

```bash
.venv/bin/python PREPARAR.py
```

El programa crea las tablas y los ejemplos y completa `.env` con tus datos, solicitando lo siguiente en este orden.

1. Usuario de PostgreSQL, con letras minúsculas, números o guiones bajos y comenzando con una letra, o Enter para aceptar tu usuario de Linux
2. Contraseña de PostgreSQL y su confirmación
3. Nombre y correo de la cuenta administrativa
4. Contraseña administrativa y su confirmación
5. Otra contraseña para las cuentas ficticias y su confirmación, distinta de la administrativa

Las contraseñas requieren entre ocho y 128 caracteres y se escriben sin mostrarse en pantalla, mientras `.env` queda con permisos privados y la aplicación conserva sólo los resúmenes de sus contraseñas en PostgreSQL.

Al terminar verás el correo administrativo y los comandos para iniciar la pasarela y la interfaz, con la conexión de DBeaver preparada si está instalado.

### 4. Iniciar la pasarela local

En la misma terminal ejecuta este comando y déjala abierta.

```bash
.venv/bin/python -m PASARELA.SERVIDOR
```

```text
PASARELA DE PRUEBA | http://127.0.0.1:55433
```

### 5. Abrir el programa

Abre otra terminal en la carpeta `c11t1` y ejecuta la interfaz.

```bash
.venv/bin/python INICIAR.py
```

En el menú principal, `1` y `3` muestran las versiones básicas, `2` abre la clínica de calidad y `4` el comercio de calidad, solicitando el correo y la contraseña de la cuenta que corresponda.

| Cuenta | Permisos principales |
|---|---|
| El correo administrativo que elegiste | Administración de especialidades, doctores, productos, stock y envíos |
| `recepcion@example.test` | Registro de pacientes, agenda y facturas |
| `doctor@example.test` | Atención e historial de pacientes asignados |
| `cliente@example.test` | Perfil, carrito, compras y pedidos propios |

La cuenta administrativa utiliza su propia contraseña y doctor, recepción y cliente comparten la contraseña de ejemplos elegida por quien prepara el proyecto, con `0` para volver al menú principal y cambiar de cuenta, mientras repetir `PREPARAR.py` conserva los registros y actualiza las claves de las cuentas indicadas, manteniendo el usuario propietario de la base existente en ese equipo.

Las versiones básicas también pueden ejecutarse por separado.

```bash
.venv/bin/python "BASICOS/EJERCICIO 1 CLINICA BASICA.py"
.venv/bin/python "BASICOS/EJERCICIO 2 COMERCIO BASICO.py"
```

## Organización del código

```text
.
├── INICIAR.py
├── PREPARAR.py
├── README.MD
├── REQUISITOS.txt
├── .gitignore
├── .env.example
├── BASICOS/
│   ├── EJERCICIO 1 CLINICA BASICA.py
│   └── EJERCICIO 2 COMERCIO BASICO.py
├── BASE DE DATOS/
│   ├── ESQUEMA.sql
│   └── CONSULTAS.sql
├── CALIDAD/
│   ├── __init__.py
│   ├── SERVICIOS/
│   │   ├── __init__.py
│   │   ├── CLINICA.py
│   │   ├── COMERCIO.py
│   │   └── CUENTAS.py
│   ├── INFRAESTRUCTURA/
│   │   ├── __init__.py
│   │   ├── DATOS.py
│   │   ├── PAGOS.py
│   │   └── REGISTRO.py
│   └── COMUN/
│       ├── __init__.py
│       ├── ERRORES.py
│       └── SEGURIDAD.py
├── PASARELA/
│   ├── __init__.py
│   └── SERVIDOR.py
└── PRUEBAS/
    ├── __init__.py
    └── EJECUTAR.py
```

| Archivo o módulo | Para qué se utiliza |
|---|---|
| `INICIAR.py` | Solicita entradas, presenta los menús y muestra resultados sin incluir consultas SQL |
| `PREPARAR.py` | Configura PostgreSQL, la conexión, las cuentas y los productos iniciales |
| `.env.example` | Sirve de plantilla sin contraseñas para crear la configuración privada `.env` |
| `BASICOS/` | Contiene las soluciones con listas globales y responsabilidades mezcladas para comparar sus limitaciones |
| `SERVICIOS/CLINICA.py` | Separa registro de pacientes, agenda, atención, historial y facturación |
| `SERVICIOS/COMERCIO.py` | Organiza catálogo, carrito, reservas, pagos, cancelaciones y seguimiento |
| `SERVICIOS/CUENTAS.py` | Registra usuarios, comprueba el acceso y permite consultar o modificar el perfil |
| `INFRAESTRUCTURA/DATOS.py` | Concentra las consultas parametrizadas y las transacciones de PostgreSQL |
| `INFRAESTRUCTURA/PAGOS.py` | Comunica la tienda con el servicio de pagos mediante solicitudes HTTP |
| `INFRAESTRUCTURA/REGISTRO.py` | Guarda eventos de auditoría y procesa avisos de pedidos en segundo plano |
| `COMUN/SEGURIDAD.py` y `ERRORES.py` | Reutilizan validaciones, comprobaciones de permisos y excepciones con mensajes comprensibles |
| `PASARELA/SERVIDOR.py` | Confirma cobros y reembolsos de prueba en un proceso con almacenamiento independiente |
| `ESQUEMA.sql` y `CONSULTAS.sql` | Definen las tablas y permiten revisar sus registros desde PostgreSQL o DBeaver |
| `PRUEBAS/EJECUTAR.py` | Comprueba reglas, operaciones simultáneas y recuperación de transacciones |

Los módulos de servicios, infraestructura y validación pertenecen a `CALIDAD`, utilizando funciones con parámetros y resultados definidos para que una regla pueda cambiar sin modificar los menús ni duplicar consultas.

## Ejercicio 1 Clínica

La versión básica registra pacientes en listas y reúne cita, historial y factura en `gestionar_cita`, permitiendo repetir un horario porque no comprueba la agenda, mientras la versión de calidad utiliza `registrar_paciente`, `programar_cita`, `registrar_atencion` y `consultar_historial` para resolver cada tarea por separado.

`programar_cita` comprueba el intervalo después de bloquear los registros del doctor y del paciente para impedir reservas simultáneas incompatibles, mientras `registrar_atencion` guarda la observación, el importe y el estado de la cita en una transacción que revierte todos esos cambios si falla una escritura.

Para probarlo, entra desde la opción `2` del menú principal como recepción, registra un paciente con documento `DEMO001`, nacimiento `2000-01-01`, teléfono `0999999999` y antecedentes `Ninguno`, consulta los identificadores mostrados y agenda treinta minutos con una fecha futura en formato `2030-11-06T10:00-05:00`, repitiendo el horario para comprobar el rechazo.

Para completar también la atención en la misma sesión, agenda una cita que comience dentro de unos minutos y entra como el doctor asignado cuando llegue esa hora, usando `6` para registrar una observación y un importe como `25.00`, `7` para consultar el historial y la cuenta de recepción con `8` para revisar la factura.

| Pregunta del ejercicio | Respuesta |
|---|---|
| ¿Se separaron pacientes, citas e historiales? | Cada operación tiene funciones propias en `CLINICA.py` y las consultas permanecen en `DATOS.py` |
| ¿Qué ocurre con un horario ocupado? | Se rechaza el solapamiento del doctor o paciente y se permiten citas consecutivas |
| ¿Se pueden añadir especialidades? | Administración puede crear especialidades, cuentas médicas y asociaciones desde las opciones `9`, `10` y `11` |
| ¿Los nombres describen su propósito? | Se emplean verbos y `snake_case`, como `programar_cita` y `consultar_historial` |
| ¿Se documentaron las operaciones críticas? | Los comentarios explican validaciones, permisos, bloqueos y el motivo de agrupar escrituras |
| ¿Las estructuras son apropiadas? | Las tablas relacionadas evitan duplicar pacientes y doctores y los índices apoyan la búsqueda de horarios |

## Ejercicio 2 Comercio

La versión básica descuenta stock y supone un pago dentro de `comprar`, dejando existencias negativas si se solicita más de lo disponible, mientras la versión de calidad separa esas decisiones y utiliza `Decimal` para los importes y enteros para las unidades.

`buscar_catalogo` conserva una copia durante quince segundos para reducir consultas repetidas y `reservar_pedido` comprueba las existencias dentro de una transacción antes de guardar el pedido y sus detalles, bloqueando los productos en un orden común para controlar compras simultáneas de la última unidad.

Con la pasarela abierta, entra desde la opción `4` del menú principal como cliente y utiliza `1` con nombre y categoría vacíos para ver el catálogo, `5` para agregar la cantidad de un producto, `4` para revisar el carrito y `6` para comprar con envío `normal` o `rapido`, respondiendo `n` para aprobar el pago de prueba o `s` para rechazarlo.

Una unidad del cuaderno inicial cuesta `3.50` y el total con impuesto del 15 % y envío normal de `2.50` resulta `6.52` después del redondeo, mostrando `pagado` al aprobar y `cancelado` al rechazar, con `7` para consultar un pedido y `13` para ver los pedidos de la cuenta.

Las opciones `2` y `3` consultan y modifican el perfil y `5` con cantidad cero quita un producto del carrito, mientras administración utiliza `10` y `11` para productos y stock y `12` para avanzar un pedido de `pagado` a `enviado` y después a `entregado`.

| Pregunta del ejercicio | Respuesta |
|---|---|
| ¿Cómo se protege la información sensible? | Se guardan resúmenes de contraseñas con sal, se parametriza el SQL y se comprueban roles y propiedad de pedidos sin incluir claves ni datos médicos en los logs |
| ¿Se conserva la integridad durante pagos? | Se reserva stock y pedido juntos y se confirma o compensa el pago mediante estados persistentes y una clave única |
| ¿Qué pasa con compras simultáneas? | El bloqueo y la comprobación del stock permiten que una sola reserva obtenga la última unidad |
| ¿Hay separación entre capas? | El menú llama a los servicios y éstos al acceso a datos o al cliente de la pasarela |
| ¿Cómo se cambian impuestos y envíos? | `IMPUESTO`, `ENVIOS` y `calcular_total` reúnen esas reglas y cada pedido conserva su precio y total |

## Funcionamiento de la pasarela local

La tienda envía solicitudes a `127.0.0.1:55433` y el servicio registra los pagos en SQLite, utilizando una clave privada creada durante la preparación y una clave por compra para recuperar el mismo resultado al reintentar, sin tarjetas ni cobros reales y con independencia de las transacciones de PostgreSQL.

La coordinación utiliza compensación, también llamada saga, reservando primero el stock, solicitando después el cobro y confirmando al final el pedido, mientras una respuesta desconocida conserva `pendiente` y permite recuperarlo con la opción `8` después de volver a iniciar el servicio.

`cancelar_pedido` guarda `reembolso_pendiente` y devuelve las unidades sólo después de confirmar la anulación o el reembolso, permitiendo repetir la opción `9` sin duplicar la devolución y conservando las anulaciones en la pasarela para impedir cobros atrasados, con el alcance de un servicio externo al proceso de la tienda creado para pruebas académicas.

## Rendimiento y mantenimiento

La separación de funciones permite cambiar las validaciones, las consultas o el cálculo de importes en su módulo correspondiente, mientras las tablas relacionadas evitan repetir información y la caché reduce consultas a cambio de memoria proporcional al catálogo, manteniendo siempre la comprobación del stock real al reservar aunque una edición desde DBeaver todavía no aparezca en la copia temporal.

Los pagos usan un tiempo de espera de cinco segundos por operación de red sin mantener bloqueado el inventario durante esa espera, mientras SQLite ordena las escrituras del servicio y las transacciones de PostgreSQL protegen los cambios de la tienda, permitiendo recuperar operaciones incompletas mediante sus estados persistentes.

Un único trabajador procesa avisos no críticos y guarda fecha, actor, acción e identificador en `.local/operaciones.log`, esperando los avisos pendientes al cerrar normalmente y sin garantizar su recuperación tras un cierre forzado, con los eventos en consola si el archivo no puede crearse.

## Datos, cierre y pruebas

DBeaver puede consultar la base `c11t1` en `127.0.0.1:55432`, con el usuario y contraseña de PostgreSQL que elegiste y esquema `c11_clase`, mostrando la preparación el nombre de usuario de la conexión y utilizando `BASE DE DATOS/CONSULTAS.sql` para revisar usuarios, pacientes, citas, facturas, productos y pedidos.

La conexión permanece en `.env`, PostgreSQL guarda sus datos en `~/.local/share/c11t1/postgres` y la pasarela en `~/.local/share/c11t1/PAGOS.sqlite3`, conservándolos entre sesiones y excluyendo del repositorio la configuración privada, el entorno virtual, los logs y las cachés.

Para cerrar utiliza `0` en el menú principal y `Ctrl+C` en la pasarela, pudiendo detener también PostgreSQL con el siguiente comando y volver a iniciarlo mediante `PREPARAR.py`.

```bash
pg_ctl -D "$HOME/.local/share/c11t1/postgres" stop
```

Para comprobar todo el trabajo después de la preparación, ejecuta la integración con el Python del entorno, que abre su propia pasarela temporal y verifica horarios, compras simultáneas, pagos, reembolsos y recuperación tras fallos sin borrar los registros del ejemplo ni necesitar la pasarela de demostración abierta.

```bash
.venv/bin/python -m PRUEBAS.EJECUTAR --integracion
```

El resumen esperado de la comprobación completa es el siguiente, con un tiempo que puede variar según el equipo.

```text
Ran 39 tests in ...s

OK
```

Para comprobar únicamente las reglas y las pruebas locales utiliza `.venv/bin/python -m PRUEBAS.EJECUTAR`, que omite expresamente las doce pruebas de integración.
