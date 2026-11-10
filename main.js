// Importamos funciones del módulo API
import { CONFIG } from './config.js';
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
    try {
        const resp = await fetch('https://mutual-spearhead-factoid.ngrok-free.dev/api/vehiculos/1/demos', {
            method: 'GET',
            headers: {
                'ngrok-skip-browser-warning': '69420',
                'Accept': 'application/json'
            }
        });
        
        if (!resp.ok) throw new Error("Error en red");
        const demos = await resp.json();
        
        const select = document.querySelector('.demo-select');
        select.innerHTML = '<option value="">Seleccione una DEMO...</option>';
        
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

document.addEventListener('DOMContentLoaded', () => {
    cargarDemos();
});

// ==========================================
// 4. LÓGICA DE BOTONES Y JOYSTICKS
// ==========================================
document.getElementById('btn-13').addEventListener('click', () => enviarComando(VEHICULO_ID, 13));
document.getElementById('btn-7').addEventListener('click', () => enviarComando(VEHICULO_ID, 7));
document.getElementById('btn-5').addEventListener('click', () => enviarComando(VEHICULO_ID, 5));
document.getElementById('btn-8').addEventListener('click', () => enviarComando(VEHICULO_ID, 8));

function configurarJoystick(elementId, mapeoComandos) {
    const stick = document.getElementById(elementId);
    let active = false;
    let currentCmd = 13; 

    const startDrag = () => active = true;
    const endDrag = () => {
        active = false;
        stick.style.transform = `translate(-50%, -50%)`;
        if (currentCmd !== 13) {
            currentCmd = 13;
            enviarComando(VEHICULO_ID, 13); 
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
        
        const r = 50; 
        const dist = Math.sqrt(x*x + y*y);
        if (dist > r) { x = (x/dist)*r; y = (y/dist)*r; }
        
        stick.style.transform = `translate(calc(-50% + ${x}px), calc(-50% + ${y}px))`;

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

configurarJoystick('joyLeft', { up: 2, down: 3, left: 4, right: 1 });
configurarJoystick('joyRight', { up: 10, down: 11, left: 9, right: 12 });

// ==========================================
// 5. BOTONES DE EJECUCIÓN DE DEMOS
// ==========================================
document.querySelector('.btn-play').addEventListener('click', async () => {
    const idDemo = document.querySelector('.demo-select').value;
    
    if (!idDemo) {
        alert("Selecciona una demo de la lista primero.");
        return;
    }

    try {
        await fetch(`https://mutual-spearhead-factoid.ngrok-free.dev/api/vehiculos/1/demo/${idDemo}/iniciar`, {
            method: 'POST',
            headers: { 
                'ngrok-skip-browser-warning': '69420',
                'Accept': 'application/json' 
            }
        });
        console.log(`Demo ${idDemo} iniciada`);
    } catch (e) {
        console.error("Error al iniciar demo", e);
    }
});

document.querySelector('.btn-clear').addEventListener('click', async () => {
    try {
        await fetch(`https://mutual-spearhead-factoid.ngrok-free.dev/api/vehiculos/1/demo/cancelar`, {
            method: 'POST',
            headers: { 
                'ngrok-skip-browser-warning': '69420',
                'Accept': 'application/json' 
            }
        });
        console.log("Demo cancelada");
    } catch (e) {
        console.error("Error al cancelar demo", e);
    }
});