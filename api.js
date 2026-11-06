// Configuración de IPs (Ajustaremos esto para HTTPS después)
const HOST = "3.213.133.17:8000";
const API_BASE = `http://${HOST}/api`;

// 1. Módulo para ejecutar movimientos individuales
export async function enviarComando(vehiculoId, comandoId) {
    try {
        const resp = await fetch(`${API_BASE}/vehiculos/${vehiculoId}/movimiento`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id_comando: comandoId, origen: 'WEB' })
        });
        return resp.ok;
    } catch (e) {
        console.error("Error enviando comando REST:", e);
        return false;
    }
}

// 2. Módulo para consultar las Demos
export async function obtenerDemos(vehiculoId) {
    try {
        const resp = await fetch(`${API_BASE}/vehiculos/${vehiculoId}/demos`);
        if (!resp.ok) throw new Error("Fallo al obtener demos");
        return await resp.json();
    } catch (e) {
        console.error("Error Demos:", e);
        return [];
    }
}

// 3. Módulo para comprobar salud de la API (Indicador AWS)
export async function checkApiHealth(vehiculoId) {
    try {
        // Hacemos un ping ligero obteniendo el estado para verificar que AWS está vivo
        const resp = await fetch(`${API_BASE}/vehiculos/${vehiculoId}/estado`);
        return resp.ok;
    } catch (e) {
        return false;
    }
}