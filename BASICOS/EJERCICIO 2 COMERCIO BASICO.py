# EJERCICIO 2 SOLUCION BASICA
# La tienda usa datos fijos y listas globales para mostrar un flujo secuencial
# que completa una compra sin comprobar permisos, existencias o confirmación externa.

productos = [[1, 'Cuaderno', 'Papelería', 3.5, 1]]
usuarios = [['cliente_demo', 'clave_de_ejemplo']]
carrito = []
pedidos = []


# Filtra nombre o categoría en la lista global y devuelve sus filas directamente,
# sin separar las consultas de la representación interna de los productos.
def buscar_productos(texto):
    return [p for p in productos if texto.lower() in p[1].lower() or texto.lower() in p[2].lower()]


# Mezcla carrito, descuento de stock y pago supuesto dentro de una función para
# contrastar cómo una compra puede terminar con existencias negativas y sin pasarela.
def comprar(usuario, producto_id, cantidad):
    producto = next(p for p in productos if p[0] == producto_id)
    carrito.append([usuario, producto_id, cantidad])
    producto[4] -= cantidad
    pedidos.append([usuario, producto_id, cantidad, producto[3] * cantidad, 'pagado'])
    carrito.clear()
    return pedidos[-1]


# Presenta una compra superior al stock para evidenciar que devolver un pedido
# no significa conservar la integridad de las existencias ni verificar un pago.
def demostracion():
    print('COMERCIO BASICO')
    print('Catálogo', buscar_productos('Papelería'))
    print('Perfil de ejemplo', usuarios[0][0])
    print('Pedido', comprar('cliente_demo', 1, 2))
    print('Stock resultante', productos[0][4])
    print('El pago se da por hecho y la contraseña está en texto, esta versión es sólo comparativa')


if __name__ == '__main__':
    demostracion()
