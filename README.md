🚜 Excavadora IoT - API & WebSocket

Este repositorio contiene el backend de la evaluación (Tema 2) desarrollado con Python, FastAPI, WebSockets y conexión a MySQL (Amazon RDS).

📚 Documentación HTTP (Swagger UI)

La documentación completa de los 21 Stored Procedures integrados en la API (GET, POST, PUT, DELETE), organizados por categorías y listos para pruebas, está disponible y expuesta de forma pública en:
👉 Swagger UI - API IoT

🔌 Documentación de WebSocket (WSS)

El canal de monitoreo y control en tiempo real opera a través de un WebSocket seguro. Debido a que Swagger UI no documenta conexiones WSS de forma nativa, la especificación de los eventos se describe a continuación:

URL de Conexión WSS: wss://mutual-spearhead-factoid.ngrok-free.dev/ws

Comportamiento Inicial: Al establecer la conexión, el servidor extrae y devuelve inmediatamente el último estado del vehículo guardado en RDS.

Estructura de Mensajes JSON (Eventos)

1. Evento de Estado (Movimiento Individual)

Se emite automáticamente a todas las interfaces conectadas tras recibir un POST válido en /api/vehiculos/{id}/movimiento. Se registra en el historial.

{
  "vehiculo": 1,
  "status": 2,
  "comando_nombre": "AVANZANDO"
}


2. Eventos de DEMO en tiempo real

Se emiten en cascada al iniciar una rutina automática (POST a /api/vehiculos/{id}/demo/{id_demo}/iniciar). Estos movimientos modifican el estado visual y del motor, pero NO ensucian la tabla del historial en la base de datos.

Inicio de DEMO:

{ "type": "DEMO_INICIO", "vehiculo": 1 }


Ejecución de un Paso (Comando activo):

{ "status": 10, "duracion": 1500 }


Pausa programada entre Pasos:

{ "status": 13, "pausa": 300 }


Finalización exitosa:

{ "status": 13, "type": "DEMO_FIN" }


3. Cancelación / Interrupción

Si se lanza un POST al endpoint de cancelación de DEMO, el ciclo se rompe inmediatamente y el vehículo transmite un estado 13 (Detenido).

🚀 Despliegue

La API se ejecuta de manera persistente en Amazon EC2 (Windows Server 2025) y se comunica de manera segura con Amazon RDS. Los puertos locales están expuestos mediante túneles seguros para cumplir con los requerimientos de HTTPS y WSS públicos.