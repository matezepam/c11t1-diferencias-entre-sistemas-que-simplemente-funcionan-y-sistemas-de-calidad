# Estas excepciones permiten distinguir una entrada incorrecta de una operación
# que no puede completarse, sin mostrar al usuario detalles internos de PostgreSQL.

class ErrorAplicacion(Exception):
    pass


class DatosInvalidos(ErrorAplicacion):
    pass


class Conflicto(ErrorAplicacion):
    pass


class AccesoDenegado(ErrorAplicacion):
    pass


class PagoNoDisponible(ErrorAplicacion):
    pass
