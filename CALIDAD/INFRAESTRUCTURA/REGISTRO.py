# El registro conserva acciones e identificadores sin copiar contraseñas,
# teléfonos u observaciones médicas dentro de los archivos de auditoría.

from concurrent.futures import ThreadPoolExecutor
import logging
from CALIDAD.INFRAESTRUCTURA.DATOS import RAIZ

_avisos = ThreadPoolExecutor(max_workers=1)


# Recibe actor, acción y registro afectado y escribe el evento con fecha y hora,
# usando logging para compartir el mismo formato entre clínica, tienda y errores.
def registrar_evento(actor, accion, entidad):
    logger = logging.getLogger('c11t1')
    if not logger.handlers:
        carpeta = RAIZ / '.local'
        try:
            carpeta.mkdir(exist_ok=True)
            archivo = logging.FileHandler(carpeta / 'operaciones.log', encoding='utf-8')
        except OSError:
            # Si no se puede crear el archivo, el aviso queda en consola para que
            # una compra ya confirmada no aparezca como fallida por el registro.
            archivo = logging.StreamHandler()
        archivo.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logger.addHandler(archivo)
        logger.setLevel(logging.INFO)
    logger.info('actor=%s accion=%s entidad=%s', actor, accion, entidad)


# Envía un aviso simulado a un único trabajador y devuelve su tarea para poder
# comprobarla en las pruebas, evitando que el comprador espere una tarea no crítica.
def avisar_pedido(usuario_id, pedido_id):
    return _avisos.submit(registrar_evento, usuario_id, 'aviso_pedido_simulado', pedido_id)


# Espera los avisos pendientes al cerrar normalmente el programa, sin afirmar
# que estos avisos en memoria sobreviven a un cierre forzado de la aplicación.
def cerrar_avisos():
    _avisos.shutdown(wait=True)
