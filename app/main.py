import asyncio
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from app.models.schemas import *
from app.services.db_service import DBService
from app.websocket.websocket_manager import WebSocketManager

app = FastAPI(title="API Excavadora IoT (21 SPs)", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

db = DBService()
ws_manager = WebSocketManager()
active_demos = {}

# ==========================================
# 1. VEHÍCULOS (5 SPs)
# ==========================================
@app.post("/api/vehiculos", tags=["1. Vehículos"])
def crear_vehiculo(req: VehiculoRequest):
    db.llamar_sp_escritura('sp_crear_vehiculo', [req.nombre, req.modelo, req.descripcion, req.microcontrolador])
    return {"mensaje": "Vehículo creado"}

@app.get("/api/vehiculos", tags=["1. Vehículos"])
def obtener_vehiculos():
    return db.llamar_sp_lectura('sp_obtener_vehiculos')

@app.get("/api/vehiculos/{id_vehiculo}", tags=["1. Vehículos"])
def obtener_vehiculo(id_vehiculo: int):
    res = db.llamar_sp_lectura('sp_obtener_vehiculo', [id_vehiculo])
    if not res: raise HTTPException(404, "Vehículo no encontrado")
    return res[0]

@app.put("/api/vehiculos/{id_vehiculo}", tags=["1. Vehículos"])
def actualizar_vehiculo(id_vehiculo: int, req: VehiculoRequest):
    db.llamar_sp_escritura('sp_actualizar_vehiculo', [id_vehiculo, req.nombre, req.modelo, req.descripcion, req.microcontrolador, req.activo])
    return {"mensaje": "Vehículo actualizado"}

@app.delete("/api/vehiculos/{id_vehiculo}", tags=["1. Vehículos"])
def eliminar_vehiculo(id_vehiculo: int):
    db.llamar_sp_escritura('sp_eliminar_vehiculo', [id_vehiculo])
    return {"mensaje": "Vehículo eliminado"}

# ==========================================
# 2. COMANDOS (4 SPs)
# ==========================================
@app.post("/api/vehiculos/{id_vehiculo}/comandos", tags=["2. Comandos"])
def crear_comando(id_vehiculo: int, req: ComandoRequest):
    db.llamar_sp_escritura('sp_crear_comando', [id_vehiculo, req.nombre, req.codigo, req.descripcion])
    return {"mensaje": "Comando creado"}

@app.get("/api/vehiculos/{id_vehiculo}/comandos", tags=["2. Comandos"])
def obtener_comandos(id_vehiculo: int):
    return db.llamar_sp_lectura('sp_obtener_comandos_vehiculo', [id_vehiculo])

@app.put("/api/comandos/{id_comando}", tags=["2. Comandos"])
def actualizar_comando(id_comando: int, req: ComandoRequest):
    db.llamar_sp_escritura('sp_actualizar_comando', [id_comando, req.nombre, req.codigo, req.descripcion, req.activo])
    return {"mensaje": "Comando actualizado"}

@app.delete("/api/comandos/{id_comando}", tags=["2. Comandos"])
def eliminar_comando(id_comando: int):
    db.llamar_sp_escritura('sp_eliminar_comando', [id_comando])
    return {"mensaje": "Comando eliminado"}

# ==========================================
# 3. ESTADO E HISTORIAL Y CONTROL MANUAL (4 SPs)
# ==========================================
@app.get("/api/vehiculos/{id_vehiculo}/estado", tags=["3. Estado e Historial"])
def obtener_estado(id_vehiculo: int):
    return db.llamar_sp_lectura('sp_obtener_estado', [id_vehiculo])

@app.get("/api/vehiculos/{id_vehiculo}/historial", tags=["3. Estado e Historial"])
def obtener_historial(id_vehiculo: int):
    """Punto 6 y 15: Muestra solo los 10 registros más recientes."""
    historial = db.llamar_sp_lectura('sp_obtener_historial', [id_vehiculo])
    return historial[:10]

@app.post("/api/vehiculos/{id_vehiculo}/movimiento", status_code=201, tags=["3. Estado e Historial"])
async def ejecutar_movimiento(id_vehiculo: int, req: MovimientoRequest):
    """Punto 5 y 14: Transacción atómica de movimiento."""
    vehiculo = db.llamar_sp_lectura('sp_obtener_vehiculo', [id_vehiculo])
    if not vehiculo or not vehiculo[0]['activo']:
        raise HTTPException(404, "Vehículo inexistente o inactivo")

    if id_vehiculo in active_demos:
        active_demos[id_vehiculo]["cancel_event"].set()

    comandos = db.llamar_sp_lectura('sp_obtener_comandos_vehiculo', [id_vehiculo])
    comando_valido = next((c for c in comandos if c['id_comando'] == req.id_comando and c['activo']), None)
    
    if not comando_valido:
        raise HTTPException(400, "Comando inválido")

    db.registrar_movimiento(id_vehiculo, req.id_comando, req.origen)
    await ws_manager.enviar_a_todos({
        "vehiculo": id_vehiculo,
        "status": req.id_comando,
        "comando_nombre": comando_valido['nombre']
    })
    return {"mensaje": "Movimiento registrado", "comando": req.id_comando}

# ==========================================
# 4. DEMOS (4 SPs)
# ==========================================
@app.post("/api/vehiculos/{id_vehiculo}/demos", tags=["4. Demos"])
def crear_demo(id_vehiculo: int, req: DemoRequest):
    db.llamar_sp_escritura('sp_crear_demo', [id_vehiculo, req.nombre, req.descripcion])
    return {"mensaje": "Demo creada"}

@app.get("/api/vehiculos/{id_vehiculo}/demos", tags=["4. Demos"])
def obtener_demos(id_vehiculo: int):
    return db.llamar_sp_lectura('sp_obtener_demos', [id_vehiculo])

@app.put("/api/demos/{id_demo}", tags=["4. Demos"])
def actualizar_demo(id_demo: int, req: DemoRequest):
    db.llamar_sp_escritura('sp_actualizar_demo', [id_demo, req.nombre, req.descripcion, req.activo])
    return {"mensaje": "Demo actualizada"}

@app.delete("/api/demos/{id_demo}", tags=["4. Demos"])
def eliminar_demo(id_demo: int):
    db.llamar_sp_escritura('sp_eliminar_demo', [id_demo])
    return {"mensaje": "Demo eliminada"}

# ==========================================
# 5. MOVIMIENTOS DEMO Y EJECUCIÓN (4 SPs)
# ==========================================
@app.post("/api/demos/{id_demo}/movimientos", tags=["5. Movimientos Demo"])
def agregar_movimiento_demo(id_demo: int, req: DemoMovimientoRequest):
    db.llamar_sp_escritura('sp_agregar_movimiento_demo', [id_demo, req.id_comando, req.orden, req.duracion_ms, req.pausa_ms])
    return {"mensaje": "Movimiento agregado a la demo"}

@app.get("/api/demos/{id_demo}/movimientos", tags=["5. Movimientos Demo"])
def obtener_movimientos_demo(id_demo: int):
    return db.llamar_sp_lectura('sp_obtener_movimientos_demo', [id_demo])

@app.put("/api/movimientos_demo/{id_demo_movimiento}", tags=["5. Movimientos Demo"])
def actualizar_movimiento_demo(id_demo_movimiento: int, req: DemoMovimientoRequest):
    db.llamar_sp_escritura('sp_actualizar_movimiento_demo', [id_demo_movimiento, req.id_comando, req.orden, req.duracion_ms, req.pausa_ms])
    return {"mensaje": "Movimiento de demo actualizado"}

@app.delete("/api/movimientos_demo/{id_demo_movimiento}", tags=["5. Movimientos Demo"])
def eliminar_movimiento_demo(id_demo_movimiento: int):
    db.llamar_sp_escritura('sp_eliminar_movimiento_demo', [id_demo_movimiento])
    return {"mensaje": "Movimiento de demo eliminado"}

# ==========================================
# EJECUCIÓN DE DEMOS (Punto 8 y 16)
# ==========================================
@app.post("/api/vehiculos/{id_vehiculo}/demo/{id_demo}/iniciar", status_code=202, tags=["5. Movimientos Demo"])
async def iniciar_demo(id_vehiculo: int, id_demo: int):
    if id_vehiculo in active_demos and not active_demos[id_vehiculo]["task"].done():
        raise HTTPException(409, "DEMO en ejecución.")
    movimientos = db.llamar_sp_lectura('sp_obtener_movimientos_demo', [id_demo])
    if not movimientos: raise HTTPException(404, "DEMO vacía o no existe.")

    cancel_event = asyncio.Event()
    task = asyncio.create_task(motor_ejecucion_demo(id_vehiculo, id_demo, movimientos, cancel_event))
    active_demos[id_vehiculo] = {"task": task, "cancel_event": cancel_event}
    return {"mensaje": "DEMO iniciada"}

@app.post("/api/vehiculos/{id_vehiculo}/demo/cancelar", tags=["5. Movimientos Demo"])
async def cancelar_demo(id_vehiculo: int):
    if id_vehiculo in active_demos and not active_demos[id_vehiculo]["task"].done():
        active_demos[id_vehiculo]["cancel_event"].set()
        return {"mensaje": "Señal de cancelación enviada."}
    raise HTTPException(400, "No hay DEMO activa.")

async def motor_ejecucion_demo(id_vehiculo: int, id_demo: int, movimientos: list, cancel_event: asyncio.Event):
    try:
        await ws_manager.enviar_a_todos({"type": "DEMO_INICIO", "vehiculo": id_vehiculo})
        for mov in movimientos:
            if cancel_event.is_set(): break
            db.actualizar_estado_solo(id_vehiculo, mov['id_comando'], True)
            await ws_manager.enviar_a_todos({"status": mov['id_comando'], "duracion": mov['duracion_ms']})
            try:
                await asyncio.wait_for(cancel_event.wait(), timeout=mov['duracion_ms']/1000.0)
                break
            except asyncio.TimeoutError: pass
            
            if mov['pausa_ms'] > 0 and not cancel_event.is_set():
                db.actualizar_estado_solo(id_vehiculo, 13, True) # 13 = Detenido
                await ws_manager.enviar_a_todos({"status": 13, "pausa": mov['pausa_ms']})
                try:
                    await asyncio.wait_for(cancel_event.wait(), timeout=mov['pausa_ms']/1000.0)
                    break
                except asyncio.TimeoutError: pass
                
        db.actualizar_estado_solo(id_vehiculo, 13, True)
        await ws_manager.enviar_a_todos({"status": 13, "type": "DEMO_FIN"})
    finally:
        if id_vehiculo in active_demos: del active_demos[id_vehiculo]

# ==========================================
# WEBSOCKET (Punto 7)
# ==========================================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.conectar(websocket)
    try:
        estado_actual = db.llamar_sp_lectura('sp_obtener_estado', [1])
        ultimo_comando = estado_actual[0]['id_comando'] if estado_actual and estado_actual[0]['id_comando'] else 13
        await websocket.send_json({"status": ultimo_comando})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.desconectar(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)