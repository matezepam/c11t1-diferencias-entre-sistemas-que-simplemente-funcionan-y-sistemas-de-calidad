# Las cuentas se comparten entre ambos ejemplos para no hacer depender la tienda
# de los usuarios de la clínica y el inicio de sesión devuelve sólo id, nombre y rol.

import re
from CALIDAD.INFRAESTRUCTURA import DATOS
from CALIDAD.COMUN.SEGURIDAD import texto, derivar_clave, comprobar_clave, exigir_rol
from CALIDAD.COMUN.ERRORES import DatosInvalidos, AccesoDenegado
from CALIDAD.INFRAESTRUCTURA.REGISTRO import registrar_evento


# Recibe los campos de una cuenta y devuelve su id, validando el correo y
# guardando el resumen de la contraseña antes de permitir su uso en los menús.
def registrar_usuario(nombre, correo, clave, rol='cliente', administrador=None):
    if rol != 'cliente':
        exigir_rol(administrador, ('administracion',))
    if rol not in ('administracion', 'recepcion', 'doctor', 'cliente'):
        raise DatosInvalidos('Rol no reconocido')
    nombre = texto(nombre, 'Nombre', 120)
    correo = texto(correo, 'Correo', 200).lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', correo):
        raise DatosInvalidos('Ingrese un correo válido')
    sal, resumen = derivar_clave(clave)
    with DATOS.transaccion() as conexion:
        identificador = DATOS.guardar_usuario(conexion, nombre, correo, sal, resumen, rol)
    registrar_evento(identificador, 'registro_usuario', identificador)
    return identificador


# Recibe correo y contraseña y devuelve la cuenta de esta sesión local sin
# claves ni resúmenes, dejando que cada servicio compruebe su rol antes de actuar.
def iniciar_sesion(correo, clave):
    with DATOS.transaccion() as conexion:
        registro = DATOS.buscar_usuario(conexion, texto(correo, 'Correo', 200).lower())
        if not registro or not comprobar_clave(clave, registro):
            raise AccesoDenegado('Correo o contraseña incorrectos')
    usuario = {campo: registro[campo] for campo in ('id', 'nombre', 'rol')}
    registrar_evento(usuario['id'], 'inicio_sesion', usuario['id'])
    return usuario


# Devuelve el perfil de la cuenta autenticada y opcionalmente cambia su nombre,
# sin recibir un id ajeno para consultar perfiles de otras personas.
def consultar_perfil(usuario, nuevo_nombre=None):
    exigir_rol(usuario, ('administracion', 'doctor', 'recepcion', 'cliente'))
    nombre = texto(nuevo_nombre, 'Nombre', 120) if nuevo_nombre is not None else None
    with DATOS.transaccion() as conexion:
        perfil = DATOS.perfil(conexion, usuario['id'], nombre)
    if nombre is not None:
        usuario['nombre'] = nombre
        registrar_evento(usuario['id'], 'cambio_nombre', usuario['id'])
    return perfil
