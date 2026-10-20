## 🔌 Documentación de WebSocket (WSS)

El canal de monitoreo en tiempo real funciona a través de WebSocket. Swagger UI no soporta pruebas nativas de WSS, por lo que se detalla aquí su funcionamiento:

*   **URL de Conexión:** `ws://3.213.133.17:8000/ws` (o `ws://3.213.133.17:8000/ws` en producción).
*   **Comportamiento Inicial:** Al conectar, el servidor devuelve inmediatamente el último estado del vehículo guardado en RDS.

**Estructura de Mensajes JSON:**
1. **Evento de Estado (Movimiento Individual):**
   Se emite cuando un cliente realiza un POST a `/api/vehiculos/{id}/movimiento`.
   ```json
   { "vehiculo": 1, "status": 2, "comando_nombre": "AVANZANDO ADELANTE" }