# Las comprobaciones compartidas evitan repetir las mismas reglas en la clínica
# y la tienda y las contraseñas se guardan como resúmenes, nunca como texto original.

from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import secrets

from CALIDAD.COMUN.ERRORES import DatosInvalidos, AccesoDenegado


# Recibe un texto obligatorio y devuelve el contenido sin espacios externos,
# rechazando vacíos y caracteres nulos antes de enviarlo a la base de datos.
def texto(valor, nombre, maximo=200):
    if not isinstance(valor, str) or not valor.strip() or len(valor.strip()) > maximo or '\x00' in valor:
        raise DatosInvalidos(f'{nombre} debe contener entre 1 y {maximo} caracteres')
    return valor.strip()


# Recibe un importe y devuelve un Decimal positivo de dos decimales para mantener
# los centavos en facturas y pedidos sin aproximarlos con números de punto flotante.
def dinero(valor):
    try:
        importe = Decimal(str(valor))
        if not importe.is_finite() or not 0 < importe <= Decimal('9999999999.99'):
            raise DatosInvalidos('El importe debe ser positivo y estar dentro del límite')
        if importe != importe.quantize(Decimal('0.01')):
            raise DatosInvalidos('El importe debe tener como máximo dos decimales')
        return importe.quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        raise DatosInvalidos('Ingrese un importe numérico válido') from None


# Comprueba identificadores o cantidades enteras y devuelve el valor, permitiendo
# cero sólo cuando se quiere quitar un producto del carrito o actualizar el stock.
def entero(valor, permitir_cero=False):
    minimo = 0 if permitir_cero else 1
    if type(valor) is not int or not minimo <= valor <= 1000000:
        raise DatosInvalidos(f'Ingrese un entero entre {minimo} y 1000000')
    return valor


# Devuelve sal y resumen a partir de una contraseña, usando una sal distinta
# por cuenta para que claves iguales no produzcan registros iguales en la tabla.
def derivar_clave(clave, sal=None):
    if not isinstance(clave, str) or not 8 <= len(clave) <= 128:
        raise DatosInvalidos('La contraseña de la aplicación debe tener entre 8 y 128 caracteres')
    sal = sal or secrets.token_hex(16)
    # La biblioteca realiza la derivación de la clave y aquí se conserva sólo
    # su resultado para poder comprobar el acceso sin guardar la contraseña.
    resumen = hashlib.pbkdf2_hmac('sha256', clave.encode(), bytes.fromhex(sal), 600000).hex()
    return sal, resumen


# Recibe la contraseña y el registro y devuelve si coinciden sus resúmenes,
# evitando que el inicio de sesión necesite recuperar una contraseña en texto plano.
def comprobar_clave(clave, registro):
    try:
        _, resumen = derivar_clave(clave, registro['sal'])
        return hmac.compare_digest(resumen, registro['clave'])
    except DatosInvalidos:
        return False


# Recibe la cuenta devuelta por el inicio de sesión de esta interfaz local y
# comprueba su rol, sin añadir tokens ni sesiones de una aplicación web al ejercicio.
def exigir_rol(usuario, roles):
    if not isinstance(usuario, dict) or usuario.get('rol') not in roles:
        raise AccesoDenegado('Su cuenta no permite esta operación')
    return usuario['id']
