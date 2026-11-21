import os
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

load_dotenv(override=True)

COMANDOS_BASE_EXCAVADORA = [
    (1,  "GIRANDO IZQUIERDA", "Gira a la izquierda"),
    (2,  "AVANZANDO",         "Adelante"),
    (3,  "RETROCEDIENDO",     "Atrás"),
    (4,  "GIRANDO DERECHA",   "Gira a la derecha"),
    (5,  "SONIDO",            "Claxon"),
    (6,  "ON/OFF",            "Encendido"),
    (7,  "LUZ",               "Luces"),
    (8,  "MODO DEMO",         "Demo"),
    (9,  "BRAZO IZQUIERDA",   "Brazo izq"),
    (10, "GARRA ARRIBA",      "Sube garra"),
    (11, "GARRA ABAJO",       "Baja garra"),
    (12, "BRAZO DERECHA",     "Brazo der"),
    (13, "DETENIDO",          "Detener"),
]

class DBService:
    def __init__(self):
        self.config = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", "3306")),
            "user": os.getenv("DB_USER", "admin"),
            "password": os.getenv("DB_PASSWORD", ""),
            "database": os.getenv("DB_NAME", "vehiculo_iot"),
            "connection_timeout": 5,
        }

    def get_connection(self):
        return mysql.connector.connect(**self.config)

    def ping_rds(self) -> bool:
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            conn.close()
            return True
        except Exception:
            return False

    def llamar_sp_lectura(self, sp_name, args=()):
        conn = self.get_connection()
        cursor = conn.cursor(dictionary=True)
        resultados = []
        try:
            cursor.callproc(sp_name, args)
            for result in cursor.stored_results():
                resultados = result.fetchall()
        finally:
            cursor.close()
            conn.close()
        return resultados

    def llamar_sp_escritura(self, sp_name, args=()):
        conn = self.get_connection()
        cursor = conn.cursor(dictionary=True)
        resultado = None
        try:
            cursor.callproc(sp_name, args)
            for res in cursor.stored_results():
                rows = res.fetchall()
                if rows:
                    resultado = rows[0]
            conn.commit()
            return resultado if resultado is not None else True
        except Error as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    def ejecutar_consulta(self, query: str, params=()):
        conn = self.get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(query, params)
            return cursor.fetchall()
        finally:
            cursor.close()
            conn.close()

    def ejecutar_escritura(self, query: str, params=()):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            last_id = cursor.lastrowid
            affected = cursor.rowcount
            conn.commit()
            return {"last_id": last_id, "affected": affected}
        except Error as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    def registrar_movimiento(self, id_vehiculo, id_comando, origen):
        """Transacción atómica: actualiza estado y registra historial."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            conn.start_transaction()
            cursor.callproc("sp_actualizar_estado", [id_vehiculo, id_comando, True])
            cursor.callproc("sp_registrar_historial", [id_vehiculo, id_comando, origen])
            conn.commit()
            return True
        except Error as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    def actualizar_estado_solo(self, id_vehiculo, id_comando, conectado=True):
        """Uso exclusivo para DEMO: actualiza estado sin duplicar en historial."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.callproc("sp_actualizar_estado", [id_vehiculo, id_comando, conectado])
            conn.commit()
            return True
        except Error as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    def clonar_comandos_base(self, id_vehiculo: int):
        """Inserta los 13 comandos estándar si el vehículo no tiene comandos aún."""
        existentes = self.ejecutar_consulta(
            "SELECT COUNT(*) AS total FROM comandos WHERE id_vehiculo = %s", (id_vehiculo,)
        )
        if existentes and existentes[0]["total"] > 0:
            return
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            for codigo, nombre, desc in COMANDOS_BASE_EXCAVADORA:
                cursor.execute(
                    "INSERT IGNORE INTO comandos (id_vehiculo, nombre, codigo, descripcion, activo) "
                    "VALUES (%s, %s, %s, %s, TRUE)",
                    (id_vehiculo, nombre, codigo, desc),
                )
            cursor.execute(
                "SELECT id_comando FROM comandos WHERE id_vehiculo = %s AND codigo = 13 LIMIT 1",
                (id_vehiculo,),
            )
            row = cursor.fetchone()
            if row:
                cursor.execute(
                    "INSERT INTO estado_vehiculo (id_vehiculo, id_comando, conectado) "
                    "VALUES (%s, %s, FALSE) ON DUPLICATE KEY UPDATE id_comando = VALUES(id_comando)",
                    (id_vehiculo, row[0]),
                )
            conn.commit()
        except Error as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    def registrar_auditoria(
        self,
        accion: str,
        entidad: str,
        id_entidad: int | None,
        detalles: str,
        actor: dict | None = None,
    ):
        try:
            id_usuario = actor.get("id_usuario") if actor and actor.get("rol") != "INVITADO" else None
            username = actor.get("username", "SISTEMA") if actor else "SISTEMA"
            correo = actor.get("correo") if actor else None
            self.ejecutar_escritura(
                "INSERT INTO bitacora_auditoria "
                "(id_usuario, username_actor, correo_actor, accion, entidad, id_entidad, detalles) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (id_usuario, username, correo, accion, entidad, id_entidad, detalles[:500]),
            )
        except Exception:
            pass