from fastapi import WebSocket

class WebSocketManager:
    def __init__(self):
        # Salas aisladas por id_vehiculo: { id_vehiculo: [ {ws, rol, id_usuario, jti} ] }
        self.clientes_web: dict[int, list[dict]] = {}
        self.dispositivos: dict[int, list[WebSocket]] = {}

    async def conectar_web(self, id_vehiculo: int, websocket: WebSocket, actor: dict):
        await websocket.accept()
        self.clientes_web.setdefault(id_vehiculo, []).append({
            "ws": websocket,
            "rol": actor.get("rol"),
            "id_usuario": actor.get("id_usuario"),
            "jti": actor.get("jti"),
        })

    def desconectar_web(self, id_vehiculo: int, websocket: WebSocket):
        if id_vehiculo in self.clientes_web:
            self.clientes_web[id_vehiculo] = [
                c for c in self.clientes_web[id_vehiculo] if c["ws"] != websocket
            ]

    async def conectar_dispositivo(self, id_vehiculo: int, websocket: WebSocket):
        await websocket.accept()
        self.dispositivos.setdefault(id_vehiculo, []).append(websocket)

    def desconectar_dispositivo(self, id_vehiculo: int, websocket: WebSocket):
        if id_vehiculo in self.dispositivos and websocket in self.dispositivos[id_vehiculo]:
            self.dispositivos[id_vehiculo].remove(websocket)

    def dispositivo_conectado(self, id_vehiculo: int) -> bool:
        return len(self.dispositivos.get(id_vehiculo, [])) > 0

    async def enviar_a_vehiculo(self, id_vehiculo: int, mensaje: dict):
        # 1. Enviar a los navegadores autorizados de ESE vehículo
        muertos_web = []
        for c in self.clientes_web.get(id_vehiculo, []):
            try:
                await c["ws"].send_json(mensaje)
            except Exception:
                muertos_web.append(c["ws"])
        for ws in muertos_web:
            self.desconectar_web(id_vehiculo, ws)

        # 2. Enviar al ESP8266 de ESE vehículo
        muertos_dev = []
        for ws in self.dispositivos.get(id_vehiculo, []):
            try:
                await ws.send_json(mensaje)
            except Exception:
                muertos_dev.append(ws)
        for ws in muertos_dev:
            self.desconectar_dispositivo(id_vehiculo, ws)

    async def revocar_web_vehiculo(self, id_vehiculo: int, motivo: str = "Permisos actualizados", solo_jti: str | None = None):
        restantes = []
        for c in self.clientes_web.get(id_vehiculo, []):
            if solo_jti is not None and c.get("jti") != solo_jti:
                restantes.append(c)
                continue
            try:
                await c["ws"].send_json({"type": "SESION_REVOCADA", "motivo": motivo})
                await c["ws"].close(code=4003)
            except Exception:
                pass
        self.clientes_web[id_vehiculo] = restantes