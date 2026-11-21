from app.services.db_service import DBService
from app.services.auth_service import hash_password

db = DBService()

def crear_o_asegurar_usuario(username, nombre, correo, password, rol):
    existe = db.ejecutar_consulta("SELECT id_usuario FROM usuarios WHERE username = %s LIMIT 1", (username,))
    if existe:
        print(f"[OK] Usuario '{username}' ya existe (ID {existe[0]['id_usuario']}).")
        return existe[0]["id_usuario"]
    res = db.ejecutar_escritura(
        "INSERT INTO usuarios (username, nombre, correo, password_hash, rol, activo) "
        "VALUES (%s, %s, %s, %s, %s, TRUE)",
        (username, nombre, correo, hash_password(password), rol),
    )
    print(f"[CREADO] Usuario '{username}' ({rol}) -> ID {res['last_id']}")
    return res["last_id"]

if __name__ == "__main__":
    id_admin = crear_o_asegurar_usuario("admin", "Administrador Empresa", "admin@iot.com", "admin1234", "ADMIN")
    id_brach = crear_o_asegurar_usuario("brach", "Erick Brachiel", "brach@iot.com", "brach1234", "USUARIO")

    # Asignar tu Excavadora IoT (ID 1) a brach como VENDIDO
    db.ejecutar_escritura(
        "UPDATE vehiculos SET id_propietario = %s, estado_comercial = 'VENDIDO' WHERE id_vehiculo = 1",
        (id_brach,),
    )
    print("[OK] Vehículo ID 1 asignado a 'brach' (estado: VENDIDO).")

    # Preparar vehículo ID 6 como unidad de EXHIBICION para probar Modo Invitado
    v6 = db.ejecutar_consulta("SELECT id_vehiculo FROM vehiculos WHERE id_vehiculo = 6")
    if v6:
        db.ejecutar_escritura(
            "UPDATE vehiculos SET nombre = 'Excavadora Exhibición Demo', "
            "descripcion = 'Unidad de demostración para invitados (5 min)', "
            "microcontrolador = 'ESP8266', estado_comercial = 'EXHIBICION', id_propietario = NULL "
            "WHERE id_vehiculo = 6"
        )
        db.clonar_comandos_base(6)
        print("[OK] Vehículo ID 6 configurado en EXHIBICION con sus 13 comandos base.")