// Importamos funciones del módulo API
import { enviarComando, obtenerDemos, checkApiHealth } from './api.js';

const VEHICULO_ID = 1;
const WS_URL = "ws://3.213.133.17:8000/ws";

// Referencias a los indicadores
const indWs = document.getElementById('ind-ws');
const indApi = document.getElementById('ind-api');
const indRds = document.getElementById('ind-rds');

// ==========================================
// 1. GESTIÓN DEL WEBSOCKET (Indicador 1)
// ==========================================
let ws = null;
function conectarWebSocket() {
    indWs.className = "badge bg-warning text-dark";
    indWs.innerText = "Conectando...";
    
    ws = new WebSocket(WS_URL);
    
    ws.onopen = () => {
        indWs.className = "badge bg-success";
        indWs.innerText = "En línea";
    };
    
    ws.onclose = () => {
        indWs.className = "badge bg-danger";
        indWs.innerText = "Desconectado";
        setTimeout(conectarWebSocket, 5000); // Intento de reconexión
    };
    
    ws.onmessage = (event) => {
        console.log("Evento WS recibido:", event.data);
    };
}
conectarWebSocket();

// ==========================================
// 2. MONITOREO DE SALUD API Y RDS (Indicadores 2 y 3)
// ==========================================
async function monitorearSalud() {
    const apiViva = await checkApiHealth(VEHICULO_ID);
    
    if (apiViva) {
        indApi.className = "badge bg-success"; indApi.innerText = "Disponible";
        // Si la API responde, asumimos RDS disponible por ahora según reglas
        indRds.className = "badge bg-success"; indRds.innerText = "Disponible"; 
    } else {
        indApi.className = "badge bg-danger"; indApi.innerText = "No disponible";
        indRds.className = "badge bg-secondary"; indRds.innerText = "Sin verificar";
    }
}
setInterval(monitorearSalud, 10000); // Chequea cada 10 segundos
monitorearSalud();

// ==========================================
// 3. CARGAR CATÁLOGO DE DEMOS
// ==========================================
async function cargarDemos() {
    const select = document.getElementById('demoSelect');
    const demos = await obtenerDemos(VEHICULO_ID);
    
    select.innerHTML = '<option value="">Seleccione una DEMO...</option>';
    demos.forEach(d => {
        select.innerHTML += `<option value="${d.id_demo}">${d.nombre}</option>`;
    });
}
cargarDemos();

// ==========================================
// 4. LÓGICA DE BOTONES Y JOYSTICKS
// ==========================================
document.getElementById('btn-13').addEventListener('click', () => enviarComando(VEHICULO_ID, 13));
document.getElementById('btn-7').addEventListener('click', () => enviarComando(VEHICULO_ID, 7));
document.getElementById('btn-5').addEventListener('click', () => enviarComando(VEHICULO_ID, 5));
document.getElementById('btn-8').addEventListener('click', () => enviarComando(VEHICULO_ID, 8));

// Lógica base para joysticks táctiles/mouse
function configurarJoystick(elementId, mapeoComandos) {
    const stick = document.getElementById(elementId);
    let active = false;
    let currentCmd = 13; // Detenido

    const startDrag = () => active = true;
    const endDrag = () => {
        active = false;
        stick.style.transform = `translate(-50%, -50%)`;
        if (currentCmd !== 13) {
            currentCmd = 13;
            enviarComando(VEHICULO_ID, 13); // Comando prioritario al soltar
        }
    };

    const drag = (e) => {
        if (!active) return;
        e.preventDefault();
        
        const rect = stick.parentElement.getBoundingClientRect();
        const clientX = e.touches ? e.touches[0].clientX : e.clientX;
        const clientY = e.touches ? e.touches[0].clientY : e.clientY;
        
        let x = clientX - rect.left - (rect.width/2);
        let y = clientY - rect.top - (rect.height/2);
        
        // Limitar radio del joystick
        const r = 50; 
        const dist = Math.sqrt(x*x + y*y);
        if (dist > r) { x = (x/dist)*r; y = (y/dist)*r; }
        
        stick.style.transform = `translate(calc(-50% + ${x}px), calc(-50% + ${y}px))`;

        // Determinar cuadrante para enviar comando
        let newCmd = 13;
        if (y < -20) newCmd = mapeoComandos.up;
        else if (y > 20) newCmd = mapeoComandos.down;
        else if (x < -20) newCmd = mapeoComandos.left;
        else if (x > 20) newCmd = mapeoComandos.right;

        if (newCmd !== currentCmd && newCmd !== 13) {
            currentCmd = newCmd;
            enviarComando(VEHICULO_ID, currentCmd);
        }
    };

    stick.addEventListener('mousedown', startDrag);
    window.addEventListener('mouseup', endDrag);
    window.addEventListener('mousemove', drag);
    
    stick.addEventListener('touchstart', startDrag, {passive: false});
    window.addEventListener('touchend', endDrag);
    window.addEventListener('touchmove', drag, {passive: false});
}

// Inicializar joysticks con tus reglas invertidas/corregidas
configurarJoystick('joyLeft', { up: 2, down: 3, left: 4, right: 1 });
configurarJoystick('joyRight', { up: 10, down: 11, left: 9, right: 12 });

// ==========================================
// CONTROL DEL CATÁLOGO DE DEMOS
// ==========================================

// 1. Función para descargar las demos de la base de datos y llenar el Select
async function cargarDemos() {
    try {
        const resp = await fetch(`${CONFIG.API_BASE}/vehiculos/${CONFIG.VEHICULO_ID}/demos`, {
            // ¡El header de ngrok es obligatorio aquí también!
            headers: { 'ngrok-skip-browser-warning': 'true' } 
        });
        
        if (!resp.ok) throw new Error("Error en red");
        const demos = await resp.json();
        
        const select = document.querySelector('.demo-select');
        select.innerHTML = '<option value="">Seleccione una DEMO...</option>'; // Limpia la lista
        
        // Inserta cada demo en la lista desplegable
        demos.forEach(demo => {
            let opt = document.createElement('option');
            opt.value = demo.id_demo;
            opt.text = `${demo.id_demo} - ${demo.nombre}`;
            select.appendChild(opt);
        });
    } catch (error) {
        console.error("Fallo al cargar las demos:", error);
    }
}

// 2. Ejecutar la función apenas cargue la página
document.addEventListener('DOMContentLoaded', () => {
    cargarDemos();
});

// 3. Darle vida al botón verde (EJECUTAR)
document.querySelector('.btn-play').addEventListener('click', async () => {
    const idDemo = document.querySelector('.demo-select').value;
    
    if (!idDemo) {
        alert("Selecciona una demo de la lista primero.");
        return;
    }

    try {
        await fetch(`${CONFIG.API_BASE}/vehiculos/${CONFIG.VEHICULO_ID}/demo/${idDemo}/iniciar`, {
            method: 'POST',
            headers: { 'ngrok-skip-browser-warning': 'true' }
        });
        console.log(`Demo ${idDemo} iniciada`);
    } catch (e) {
        console.error("Error al iniciar demo", e);
    }
});

// 4. Darle vida al botón rojo (CANCELAR)
document.querySelector('.btn-clear').addEventListener('click', async () => {
    try {
        await fetch(`${CONFIG.API_BASE}/vehiculos/${CONFIG.VEHICULO_ID}/demo/cancelar`, {
            method: 'POST',
            headers: { 'ngrok-skip-browser-warning': 'true' }
        });
        console.log("Demo cancelada");
    } catch (e) {
        console.error("Error al cancelar demo", e);
    }
});