import mysql.connector
from mysql.connector import Error

class DBService:
    def __init__(self):
        self.config = {
            'host': 'instancia-rds-iot.cz33dhruuc3n.us-east-1.rds.amazonaws.com',
            'user': 'admin',
            'password': 'Admin1234#',
            'database': 'vehiculo_iot'
        }

    def get_connection(self):
        return mysql.connector.connect(**self.config)

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
        cursor = conn.cursor()
        try:
            cursor.callproc(sp_name, args)
            conn.commit()
            return True
        except Error as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    def registrar_movimiento(self, id_vehiculo, id_comando, origen):
        """Transacción atómica: actualiza estado y registra historial (Punto 5)."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            conn.start_transaction()
            cursor.callproc('sp_actualizar_estado', [id_vehiculo, id_comando, True])
            cursor.callproc('sp_registrar_historial', [id_vehiculo, id_comando, origen])
            conn.commit()
            return True
        except Error as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    def actualizar_estado_solo(self, id_vehiculo, id_comando, conectado=True):
        """Uso exclusivo para la DEMO: actualiza estado sin ensuciar el historial (Punto 8)."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.callproc('sp_actualizar_estado', [id_vehiculo, id_comando, conectado])
            conn.commit()
            return True
        except Error as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()