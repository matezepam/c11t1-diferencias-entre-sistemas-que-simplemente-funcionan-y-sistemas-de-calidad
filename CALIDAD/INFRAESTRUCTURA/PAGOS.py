# La tienda utiliza una pasarela de prueba en otro proceso y mantiene la
# comunicación separada de las funciones que gestionan el carrito y el stock.

from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import json
import os

from CALIDAD.INFRAESTRUCTURA.DATOS import cargar_configuracion
from CALIDAD.COMUN.SEGURIDAD import texto, dinero
from CALIDAD.COMUN.ERRORES import Conflicto, PagoNoDisponible


class PasarelaPrueba:
    # Permite elegir un puerto temporal en las pruebas y simular una caída
    # sin cambiar la forma en que la tienda solicita cobros o reembolsos.
    def __init__(self, disponible=True, url='http://127.0.0.1:55433', clave=None):
        cargar_configuracion()
        self.disponible, self.url = disponible, url
        self.clave = clave if clave is not None else os.environ.get('C11_CLAVE_PASARELA')

    # Envía sólo la clave de compra y el importe y conserva la clave al reintentar
    # para recuperar una respuesta que el servicio ya pudo haber confirmado.
    def solicitar(self, accion, clave, importe, rechazar=False):
        if not self.disponible or not self.clave:
            raise PagoNoDisponible('La pasarela no está disponible o no está configurada')
        datos = {'clave': texto(clave, 'Clave de compra', 80),
                 'importe': str(dinero(importe)), 'rechazar': rechazar}
        solicitud = Request(self.url + '/' + accion, data=json.dumps(datos).encode(),
            headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + self.clave}, method='POST')
        try:
            with urlopen(solicitud, timeout=5) as respuesta:
                resultado = json.load(respuesta)
            estado = resultado.get('estado') if isinstance(resultado, dict) else None
            if estado not in ('cobrado', 'rechazado', 'anulado', 'reembolsado'):
                raise PagoNoDisponible('La respuesta de la pasarela no es válida')
            return estado
        except HTTPError as error:
            error.close()
            if error.code == 409:
                raise Conflicto('La clave de compra ya tiene otro importe') from None
            raise PagoNoDisponible('La pasarela rechazó la solicitud, revise su configuración y reintente') from None
        except (URLError, TimeoutError, OSError, ValueError):
            # Un corte no permite saber si se confirmó el cobro y por eso no se
            # marca como rechazado ni se libera stock hasta recuperar la respuesta.
            raise PagoNoDisponible('Sin respuesta de la pasarela, conserve el pedido y reintente') from None

    # Devuelve el resultado del cobro sin modificar las tablas de la tienda.
    def cobrar(self, clave, importe, rechazar=False):
        return self.solicitar('cobrar', clave, importe, rechazar)

    # Solicita la compensación antes de que la tienda devuelva las existencias.
    def reembolsar(self, clave, importe):
        return self.solicitar('reembolsar', clave, importe)
