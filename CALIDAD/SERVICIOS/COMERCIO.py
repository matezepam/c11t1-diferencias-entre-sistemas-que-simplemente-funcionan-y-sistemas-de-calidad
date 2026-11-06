# EJERCICIO 2 COMERCIO DE CALIDAD
# Las reglas reciben la cuenta local y trabajan con DATOS, separando catálogo,
# carrito, compra y seguimiento en funciones que se pueden probar por separado.

from decimal import Decimal
import time
from CALIDAD.INFRAESTRUCTURA import DATOS
from CALIDAD.COMUN.SEGURIDAD import texto, dinero, entero, exigir_rol
from CALIDAD.COMUN.ERRORES import DatosInvalidos, Conflicto, AccesoDenegado, PagoNoDisponible
from CALIDAD.INFRAESTRUCTURA.REGISTRO import registrar_evento, avisar_pedido

IMPUESTO = Decimal('0.15')
ENVIOS = {'normal': Decimal('2.50'), 'rapido': Decimal('5.00')}
_catalogo = None
_vencimiento = 0.0


# Recibe subtotal y método y devuelve el total con impuesto y envío, dejando
# esas reglas juntas para modificarlas sin cambiar la reserva ni las consultas.
def calcular_total(subtotal, envio):
    if envio not in ENVIOS:
        raise DatosInvalidos('Seleccione envío normal o rapido')
    subtotal = dinero(subtotal)
    impuesto = (subtotal * IMPUESTO).quantize(Decimal('0.01'))
    return dinero(subtotal + impuesto + ENVIOS[envio])


# Descarta el catálogo después de un cambio de productos o stock de esta aplicación.
def invalidar_catalogo():
    global _catalogo
    _catalogo = None


# Devuelve coincidencias de nombre y categoría desde una copia temporal del
# catálogo, evitando consultar toda la tabla en cada búsqueda durante quince segundos.
def buscar_catalogo(busqueda='', categoria=''):
    global _catalogo, _vencimiento
    if not isinstance(busqueda, str) or not isinstance(categoria, str) or len(busqueda)>120 or len(categoria)>100:
        raise DatosInvalidos('Búsqueda o categoría inválida')
    if '\x00' in busqueda or '\x00' in categoria:
        raise DatosInvalidos('La búsqueda contiene caracteres inválidos')
    if _catalogo is None or time.monotonic() >= _vencimiento:
        with DATOS.transaccion() as conexion:
            _catalogo = DATOS.catalogo(conexion, '', '')
        _vencimiento = time.monotonic() + 15
    busqueda, categoria = busqueda.strip().lower(), categoria.strip().lower()
    # Cada resultado es una copia para que cambiarlo desde el menú no altere
    # el catálogo que se reutiliza en la siguiente búsqueda.
    return [dict(p) for p in _catalogo if busqueda in p['nombre'].lower()
            and (not categoria or p['categoria'].lower() == categoria)]


# Agrega un producto y devuelve su id sólo a administración, validando precio
# y stock antes de confirmar la escritura e invalidar la copia del catálogo.
def registrar_producto(usuario, nombre, categoria, precio, stock):
    exigir_rol(usuario, ('administracion',))
    nombre, categoria = texto(nombre, 'Nombre', 120), texto(categoria, 'Categoría', 100)
    precio, stock = dinero(precio), entero(stock, True)
    with DATOS.transaccion() as conexion:
        producto_id = DATOS.guardar_producto(conexion, nombre, categoria, precio, stock)
    invalidar_catalogo()
    registrar_evento(usuario['id'], 'registro_producto', producto_id)
    return producto_id


# Actualiza existencias disponibles con permiso administrativo y descarta la caché,
# manteniendo los pedidos ya reservados separados del stock que todavía se puede vender.
def actualizar_stock(usuario, producto_id, stock):
    exigir_rol(usuario, ('administracion',))
    entero(producto_id)
    entero(stock, True)
    with DATOS.transaccion() as conexion:
        if not DATOS.cambiar_stock(conexion, producto_id, stock):
            raise DatosInvalidos('El producto no existe')
    invalidar_catalogo()
    registrar_evento(usuario['id'], 'actualizacion_stock', producto_id)


# Devuelve el carrito de la cuenta del comprador sin aceptar un id de otra cuenta.
def consultar_carrito(usuario):
    exigir_rol(usuario, ('cliente',))
    with DATOS.transaccion() as conexion:
        return DATOS.carrito(conexion, usuario['id'])


# Cambia la cantidad total y devuelve el carrito, interpretando cero como quitar
# el producto y comprobando el stock otra vez al comprar porque añadir no lo reserva.
def cambiar_carrito(usuario, producto_id, cantidad):
    exigir_rol(usuario, ('cliente',))
    entero(producto_id)
    entero(cantidad, True)
    with DATOS.transaccion() as conexion:
        DATOS.bloquear_usuario(conexion, usuario['id'])
        producto = DATOS.producto(conexion, producto_id)
        if not producto or cantidad > producto['stock']:
            raise Conflicto('Producto inexistente o stock insuficiente')
        DATOS.guardar_carrito(conexion, usuario['id'], producto_id, cantidad)
        return DATOS.carrito(conexion, usuario['id'])


# Reserva stock y devuelve un pedido pendiente en una única transacción, usando
# bloqueos para proteger la última unidad y una clave para recuperar el mismo intento.
def reservar_pedido(usuario, clave, envio='normal'):
    exigir_rol(usuario, ('cliente',))
    clave = texto(clave, 'Clave de compra', 80)
    with DATOS.transaccion() as conexion:
        DATOS.bloquear_usuario(conexion, usuario['id'])
        previo = DATOS.pedido(conexion, clave=clave)
        # La misma clave identifica el mismo intento de compra y permite
        # recuperar su pedido después de un fallo sin descontar stock otra vez.
        if previo:
            if previo['usuario_id'] != usuario['id']:
                raise AccesoDenegado('La clave pertenece a otra cuenta')
            return previo['id']
        filas = DATOS.carrito(conexion, usuario['id'], bloquear=True)
        if not filas:
            raise Conflicto('El carrito está vacío')
        subtotal = Decimal('0.00')
        for producto in filas:
            if producto['cantidad'] > producto['stock']:
                raise Conflicto('Ya no quedan unidades suficientes para completar la compra')
            subtotal += producto['cantidad'] * producto['precio']
        total = calcular_total(subtotal, envio)
        pedido_id = DATOS.guardar_pedido(conexion, usuario['id'], clave, total, filas)
    invalidar_catalogo()
    registrar_evento(usuario['id'], 'reserva_pedido', pedido_id)
    return pedido_id


# Devuelve un pedido únicamente a su comprador, comprobando la propiedad dentro
# del servicio y no sólo en la pantalla que solicita el identificador.
def consultar_pedido(usuario, pedido_id):
    exigir_rol(usuario, ('cliente',))
    entero(pedido_id)
    with DATOS.transaccion() as conexion:
        pedido = DATOS.pedido(conexion, pedido_id)
        if not pedido or pedido['usuario_id'] != usuario['id']:
            raise AccesoDenegado('Ese pedido no pertenece a su cuenta')
        return pedido


# Devuelve únicamente los pedidos de esta cuenta para recuperar sus ids y
# continuar los pagos o cancelaciones pendientes después de reiniciar el menú.
def listar_pedidos(usuario):
    exigir_rol(usuario, ('cliente',))
    with DATOS.transaccion() as conexion:
        return DATOS.pedidos_usuario(conexion, usuario['id'])


# Solicita el pago fuera del bloqueo del inventario y devuelve el estado final,
# conservando pendiente una respuesta desconocida para reintentar sin otro cobro.
def confirmar_pago(usuario, pedido_id, pasarela, rechazar=False):
    pedido = consultar_pedido(usuario, pedido_id)
    if pedido['estado'] != 'pendiente':
        return pedido['estado']
    estado_pago = pasarela.cobrar(pedido['clave'], pedido['total'], rechazar)
    with DATOS.transaccion() as conexion:
        actual = DATOS.pedido(conexion, pedido_id, bloquear=True)
        # El estado pudo cambiar mientras respondía la pasarela, por eso se
        # consulta de nuevo antes de confirmar el pago o devolver existencias.
        if actual['estado'] != 'pendiente':
            return actual['estado']
        if estado_pago == 'cobrado':
            nuevo = 'pagado'
        elif estado_pago in ('rechazado', 'reembolsado', 'anulado'):
            DATOS.devolver_stock(conexion, pedido_id)
            nuevo = 'cancelado'
        else:
            raise PagoNoDisponible('La respuesta de pago no es válida, reintente')
        DATOS.cambiar_estado(conexion, pedido_id, nuevo)
    invalidar_catalogo()
    registrar_evento(usuario['id'], nuevo, pedido_id)
    if nuevo == 'pagado':
        avisar_pedido(usuario['id'], pedido_id)
    return nuevo


# Cancela y devuelve el stock sólo después de confirmar la compensación del pago,
# dejando reembolso pendiente si falla la pasarela para recuperarlo desde el menú.
def cancelar_pedido(usuario, pedido_id, pasarela):
    pedido = consultar_pedido(usuario, pedido_id)
    with DATOS.transaccion() as conexion:
        actual = DATOS.pedido(conexion, pedido_id, bloquear=True)
        if actual['estado'] == 'cancelado':
            return 'cancelado'
        if actual['estado'] in ('enviado', 'entregado'):
            raise Conflicto('Un pedido enviado ya no puede cancelarse en este ejemplo')
        DATOS.cambiar_estado(conexion, pedido_id, 'reembolso_pendiente')
    respuesta = pasarela.reembolsar(pedido['clave'], pedido['total'])
    if respuesta not in ('anulado', 'rechazado', 'reembolsado'):
        raise PagoNoDisponible('No se confirmó el reembolso')
    with DATOS.transaccion() as conexion:
        actual = DATOS.pedido(conexion, pedido_id, bloquear=True)
        if actual['estado'] != 'cancelado':
            DATOS.devolver_stock(conexion, pedido_id)
            DATOS.cambiar_estado(conexion, pedido_id, 'cancelado')
    invalidar_catalogo()
    registrar_evento(usuario['id'], 'cancelacion', pedido_id)
    return 'cancelado'


# Avanza un pedido de pagado a enviado o de enviado a entregado con permiso
# administrativo, evitando saltar directamente de una compra pendiente a una entrega.
def avanzar_pedido(usuario, pedido_id, estado):
    exigir_rol(usuario, ('administracion',))
    entero(pedido_id)
    with DATOS.transaccion() as conexion:
        actual = DATOS.pedido(conexion, pedido_id, bloquear=True)
        if not actual or (actual['estado'], estado) not in (('pagado','enviado'), ('enviado','entregado')):
            raise Conflicto('Cambio de estado no permitido')
        DATOS.cambiar_estado(conexion, pedido_id, estado)
    registrar_evento(usuario['id'], estado, pedido_id)
