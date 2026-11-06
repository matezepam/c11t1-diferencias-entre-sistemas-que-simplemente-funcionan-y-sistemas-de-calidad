# Aquí se concentran las consultas para que los menús no contengan SQL y las
# reglas de negocio puedan trabajar con registros sin abrir conexiones por su cuenta.

from contextlib import contextmanager
from pathlib import Path
import os
import re
import json

from CALIDAD.COMUN.ERRORES import Conflicto, DatosInvalidos

RAIZ = Path(__file__).resolve().parents[2]


# Lee las credenciales locales sin sobrescribir variables ya definidas y conserva
# la contraseña fuera de los archivos que se suben al repositorio.
def cargar_configuracion():
    ruta = RAIZ / '.env'
    if ruta.exists():
        for linea in ruta.read_text(encoding='utf-8').splitlines():
            if linea and not linea.startswith('#') and '=' in linea:
                clave, valor = linea.split('=', 1)
                valor = valor.strip()
                if valor.startswith('"'):
                    valor = json.loads(valor)
                os.environ.setdefault(clave.strip(), valor)


# Devuelve una conexión nueva a PostgreSQL y selecciona el esquema del trabajo
# para que las consultas utilicen las tablas de la clínica y la tienda.
def conectar():
    import psycopg
    from psycopg.rows import dict_row

    cargar_configuracion()
    usuario = os.environ.get('PGUSER')
    clave = os.environ.get('PGPASSWORD')
    if not usuario or not clave:
        raise DatosInvalidos('Ejecute PREPARAR.py para configurar sus credenciales locales')
    esquema = os.environ.get('C11_ESQUEMA', 'c11_clase')
    if not re.fullmatch(r'[a-z][a-z0-9_]*', esquema):
        raise ValueError('Nombre de esquema inválido')
    return psycopg.connect(host=os.environ.get('PGHOST', '127.0.0.1'),
                          port=os.environ.get('PGPORT', '55432'),
                          dbname=os.environ.get('PGDATABASE', 'c11t1'),
                          user=usuario, password=clave,
                          options=f'-c search_path={esquema}', connect_timeout=5, row_factory=dict_row)


# Confirma el bloque completo o revierte sus cambios ante un fallo, convirtiendo
# conflictos de restricciones y bloqueos en un mensaje comprensible para la interfaz.
@contextmanager
def transaccion():
    import psycopg

    try:
        # El contexto de la conexión confirma al terminar y revierte si una
        # excepción sale del bloque, evitando guardar sólo parte de la operación.
        with conectar() as conexion:
            yield conexion
    except (psycopg.IntegrityError, psycopg.errors.SerializationFailure, psycopg.errors.DeadlockDetected) as error:
        raise Conflicto('La operación entra en conflicto con los datos existentes') from error


# Las consultas reciben valores aparte del SQL y devuelven una fila o una lista,
# evitando interpretar nombres o búsquedas del usuario como instrucciones de la base.
def uno(conexion, consulta, valores=()):
    return conexion.execute(consulta, valores).fetchone()


# Devuelve todas las filas cuando la consulta necesita una lista de resultados.
def varios(conexion, consulta, valores=()):
    return conexion.execute(consulta, valores).fetchall()


# Recibe datos ya validados y guarda una cuenta, devolviendo su identificador.
def guardar_usuario(conexion, nombre, correo, sal, clave, rol):
    return uno(conexion, 'INSERT INTO usuarios(nombre,correo,sal,clave,rol) VALUES (%s,%s,%s,%s,%s) RETURNING id',
               (nombre, correo, sal, clave, rol))['id']


# Devuelve la cuenta por correo para que seguridad compruebe la contraseña.
def buscar_usuario(conexion, correo):
    return uno(conexion, 'SELECT * FROM usuarios WHERE correo=%s', (correo,))


# Guarda los datos de un paciente y devuelve su id sin copiarlo a las citas.
def guardar_paciente(conexion, valores):
    return uno(conexion, '''INSERT INTO pacientes(documento,nombre,nacimiento,telefono,antecedentes)
               VALUES (%s,%s,%s,%s,%s) RETURNING id''', valores)['id']


# Devuelve la identificación necesaria para agendar sin incluir antecedentes médicos.
def pacientes(conexion):
    return varios(conexion, 'SELECT id,documento,nombre FROM pacientes ORDER BY id')


# Devuelve doctores con sus especialidades para mostrar opciones de la agenda.
def doctores(conexion):
    return varios(conexion, '''SELECT d.id,u.nombre,e.nombre AS especialidad FROM doctores d
                  JOIN usuarios u ON u.id=d.usuario_id JOIN especialidades e ON e.id=d.especialidad_id ORDER BY d.id''')


# Bloquea doctor y paciente y devuelve si existen antes de comprobar sus horarios.
def bloquear_agenda(conexion, paciente_id, doctor_id):
    # Las reservas del mismo doctor o paciente esperan este bloqueo antes de
    # consultar horarios, evitando que ambas acepten un intervalo todavía libre.
    doctor = uno(conexion, 'SELECT id FROM doctores WHERE id=%s FOR UPDATE', (doctor_id,))
    paciente = uno(conexion, 'SELECT id FROM pacientes WHERE id=%s FOR UPDATE', (paciente_id,))
    return bool(doctor and paciente)


# Detecta solapamientos y devuelve la cita encontrada o None si el intervalo está libre.
def buscar_cruce(conexion, paciente_id, doctor_id, inicio, fin):
    return uno(conexion, '''SELECT id FROM citas WHERE (paciente_id=%s OR doctor_id=%s)
               AND inicio<%s AND fin>%s LIMIT 1''', (paciente_id, doctor_id, fin, inicio))


# Inserta la cita validada dentro de la misma transacción que bloqueó los horarios.
def guardar_cita(conexion, paciente_id, doctor_id, inicio, fin):
    return uno(conexion, 'INSERT INTO citas(paciente_id,doctor_id,inicio,fin) VALUES (%s,%s,%s,%s) RETURNING id',
               (paciente_id, doctor_id, inicio, fin))['id']


# Devuelve agenda y facturas sin mostrar el texto del historial en recepción.
def agenda(conexion, usuario):
    return varios(conexion, '''SELECT c.id,p.nombre AS paciente,u.nombre AS doctor,c.inicio,c.fin,c.atendida
                  FROM citas c JOIN pacientes p ON p.id=c.paciente_id JOIN doctores d ON d.id=c.doctor_id
                  JOIN usuarios u ON u.id=d.usuario_id WHERE (%s<>'doctor' OR d.usuario_id=%s)
                  ORDER BY c.inicio''', (usuario['rol'], usuario['id']))


# Devuelve los importes de atención que forman la facturación básica.
def facturas(conexion):
    return varios(conexion, 'SELECT id,cita_id,importe,fecha FROM atenciones ORDER BY id')


# Bloquea la cita y devuelve su doctor para impedir atenciones repetidas.
def cita_para_atender(conexion, cita_id):
    return uno(conexion, '''SELECT c.*,d.usuario_id FROM citas c JOIN doctores d ON d.id=c.doctor_id
               WHERE c.id=%s FOR UPDATE OF c''', (cita_id,))


# Guarda historial y monto facturado y marca la atención, devolviendo su número.
def guardar_atencion(conexion, cita_id, observacion, importe):
    identificador = uno(conexion, 'INSERT INTO atenciones(cita_id,observacion,importe) VALUES (%s,%s,%s) RETURNING id',
                        (cita_id, observacion, importe))['id']
    conexion.execute('UPDATE citas SET atendida=true WHERE id=%s', (cita_id,))
    return identificador


# Devuelve si el doctor atiende al paciente para comprobar acceso a su historial.
def doctor_asignado(conexion, paciente_id, usuario_id):
    return uno(conexion, '''SELECT c.id FROM citas c JOIN doctores d ON d.id=c.doctor_id
               WHERE c.paciente_id=%s AND d.usuario_id=%s LIMIT 1''', (paciente_id, usuario_id))


# Devuelve antecedentes y observaciones sólo después de comprobar el permiso.
def historial(conexion, paciente_id):
    paciente = uno(conexion, 'SELECT nombre,antecedentes FROM pacientes WHERE id=%s', (paciente_id,))
    registros = varios(conexion, '''SELECT a.fecha,a.observacion,a.importe FROM atenciones a
                       JOIN citas c ON c.id=a.cita_id WHERE c.paciente_id=%s ORDER BY a.fecha''', (paciente_id,))
    return paciente, registros


# Agrega especialidad y doctor sin condiciones fijas sobre los nombres admitidos.
def guardar_especialidad(conexion, nombre):
    return uno(conexion, 'INSERT INTO especialidades(nombre) VALUES (%s) RETURNING id', (nombre,))['id']


# Devuelve el id de la asociación entre una cuenta médica y su especialidad.
def guardar_doctor(conexion, usuario_id, especialidad_id):
    return uno(conexion, 'INSERT INTO doctores(usuario_id,especialidad_id) VALUES (%s,%s) RETURNING id',
               (usuario_id, especialidad_id))['id']


# Devuelve un perfil sin contraseña y permite cambiar únicamente su nombre.
def perfil(conexion, usuario_id, nombre=None):
    if nombre is not None:
        conexion.execute('UPDATE usuarios SET nombre=%s WHERE id=%s', (nombre, usuario_id))
    return uno(conexion, 'SELECT id,nombre,correo,rol FROM usuarios WHERE id=%s', (usuario_id,))


# Consulta el catálogo por nombre y categoría con búsquedas parametrizadas.
def catalogo(conexion, busqueda, categoria):
    return varios(conexion, '''SELECT * FROM productos WHERE strpos(lower(nombre),%s)>0
                  AND (%s='' OR lower(categoria)=%s) ORDER BY id''', (busqueda, categoria, categoria))


# Guarda un producto nuevo y devuelve el identificador generado.
def guardar_producto(conexion, nombre, categoria, precio, stock):
    return uno(conexion, 'INSERT INTO productos(nombre,categoria,precio,stock) VALUES (%s,%s,%s,%s) RETURNING id',
               (nombre, categoria, precio, stock))['id']


# Cambia existencias disponibles sin permitir valores negativos en la tabla.
def cambiar_stock(conexion, producto_id, stock):
    return uno(conexion, 'UPDATE productos SET stock=%s WHERE id=%s RETURNING id', (stock, producto_id))


# Bloquea la fila del comprador para ordenar los cambios de su carrito y compra.
def bloquear_usuario(conexion, usuario_id):
    return uno(conexion, 'SELECT id FROM usuarios WHERE id=%s FOR UPDATE', (usuario_id,))


# Devuelve un producto para comprobar existencia y cantidad antes de añadirlo.
def producto(conexion, producto_id):
    return uno(conexion, 'SELECT * FROM productos WHERE id=%s', (producto_id,))


# Guarda la cantidad total del carrito o quita la fila cuando se recibe cero.
def guardar_carrito(conexion, usuario_id, producto_id, cantidad):
    if cantidad == 0:
        conexion.execute('DELETE FROM carrito WHERE usuario_id=%s AND producto_id=%s', (usuario_id, producto_id))
    else:
        conexion.execute('''INSERT INTO carrito VALUES (%s,%s,%s) ON CONFLICT(usuario_id,producto_id)
                          DO UPDATE SET cantidad=excluded.cantidad''', (usuario_id, producto_id, cantidad))


# Devuelve el carrito y opcionalmente bloquea los productos en un orden común
# para proteger la última unidad cuando dos compradores intentan reservarla.
def carrito(conexion, usuario_id, bloquear=False):
    consulta = '''SELECT p.*,c.cantidad FROM carrito c JOIN productos p ON p.id=c.producto_id
                  WHERE c.usuario_id=%s ORDER BY p.id'''
    if bloquear:
        consulta += ' FOR UPDATE OF p'
    return varios(conexion, consulta, (usuario_id,))


# Guarda pedido y detalles y descuenta stock dentro de la transacción recibida.
def guardar_pedido(conexion, usuario_id, clave, total, filas):
    pedido_id = uno(conexion, "INSERT INTO pedidos(usuario_id,clave,total,estado) VALUES (%s,%s,%s,'pendiente') RETURNING id",
                    (usuario_id, clave, total))['id']
    for fila in filas:
        conexion.execute('UPDATE productos SET stock=stock-%s WHERE id=%s', (fila['cantidad'], fila['id']))
        conexion.execute('INSERT INTO detalles VALUES (%s,%s,%s,%s)',
                          (pedido_id, fila['id'], fila['cantidad'], fila['precio']))
    conexion.execute('DELETE FROM carrito WHERE usuario_id=%s', (usuario_id,))
    return pedido_id


# Devuelve un pedido por id o clave y permite bloquearlo al cambiar su estado.
def pedido(conexion, pedido_id=None, clave=None, bloquear=False):
    consulta = 'SELECT * FROM pedidos WHERE id=%s' if pedido_id is not None else 'SELECT * FROM pedidos WHERE clave=%s'
    if bloquear:
        consulta += ' FOR UPDATE'
    return uno(conexion, consulta, (pedido_id if pedido_id is not None else clave,))


# Cambia el estado del pedido dentro de una transacción ya validada.
def cambiar_estado(conexion, pedido_id, estado):
    conexion.execute('UPDATE pedidos SET estado=%s WHERE id=%s', (estado, pedido_id))


# Devuelve las unidades reservadas después de bloquear el pedido, evitando
# que reintentar una cancelación devuelva dos veces las mismas existencias.
def devolver_stock(conexion, pedido_id):
    filas = varios(conexion, '''SELECT p.id,d.cantidad FROM productos p JOIN detalles d ON d.producto_id=p.id
                    WHERE d.pedido_id=%s ORDER BY p.id FOR UPDATE OF p''', (pedido_id,))
    for fila in filas:
        conexion.execute('UPDATE productos SET stock=stock+%s WHERE id=%s', (fila['cantidad'], fila['id']))


# Recupera los pedidos del comprador después de cerrar la aplicación para que
# pueda reintentar un pago o terminar una cancelación pendiente con el mismo id.
def pedidos_usuario(conexion, usuario_id):
    return varios(conexion, 'SELECT id,total,estado FROM pedidos WHERE usuario_id=%s ORDER BY id', (usuario_id,))
