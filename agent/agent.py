import os
import json
import platform
import time
import requests
import psutil
import schedule

# --- CONFIGURACIÓN ---
# URL completa del endpoint de la API donde se enviarán los datos.
# ¡Asegúrate de cambiar 'TU_IP_DE_EC2' por la IP pública de tu instancia de AWS!
API_URL = "http://44.211.226.254/collect"

# Token de autenticación. Debe ser el mismo que está configurado en la API.
API_TOKEN = "micompania_secret_token_12345"

# Intervalo en minutos para la recolección y envío de datos.
COLLECTION_INTERVAL_MINUTES = 5

# --- FUNCIONES DE RECOLECCIÓN ---

def get_system_info() -> dict:
    """
    Recolecta información clave del sistema operativo, procesador, procesos y usuarios.
    Utiliza bloques try-except para evitar que el script falle si alguna información no está disponible.
    """
    print("Iniciando recolección de información del sistema...")
    
    # Información del Procesador
    try:
        cpu_info = {
            "physical_cores": psutil.cpu_count(logical=False),
            "total_cores": psutil.cpu_count(logical=True),
            "frequency": psutil.cpu_freq().current if psutil.cpu_freq() else "N/A",
            "usage_percent": psutil.cpu_percent(interval=1)
        }
    except Exception as e:
        cpu_info = {"error": str(e)}

    # Listado de Procesos
    try:
        processes = [
            {"pid": p.info['pid'], "name": p.info['name'], "username": p.info['username']}
            for p in psutil.process_iter(['pid', 'name', 'username'])
        ]
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
        processes = [{"error": f"No se pudo acceder a todos los procesos: {e}"}]

    # Usuarios con sesión abierta
    try:
        active_users = [{"user": u.name, "terminal": u.terminal} for u in psutil.users()]
    except Exception as e:
        active_users = {"error": str(e)}

    # Consolidar toda la información en un único diccionario
    system_data = {
        "os_name": platform.system(),
        "os_version": platform.version(),
        "cpu_info": cpu_info,
        "running_processes": processes,
        "logged_in_users": active_users,
    }
    
    print("Recolección finalizada.")
    return system_data

def send_data_to_api(data: dict):
    """
    Envía los datos recolectados a la API mediante una solicitud POST.
    Incluye el token de autorización en las cabeceras.
    """
    print(f"Enviando datos a {API_URL}...")
    try:
        headers = {
            "Authorization": f"Bearer {API_TOKEN}",
            "Content-Type": "application/json"
        }
        response = requests.post(API_URL, json=data, headers=headers, timeout=15)
        
        # Lanza una excepción para códigos de error HTTP (4xx o 5xx)
        response.raise_for_status()
        
        print(f"Datos enviados con éxito. Respuesta del servidor: {response.json()}")
    
    except requests.exceptions.RequestException as e:
        print(f"Error al conectar con la API: {e}")
    except Exception as e:
        print(f"Ocurrió un error inesperado al enviar los datos: {e}")

def job():
    """Función principal que encapsula la lógica de recolección y envío."""
    system_data = get_system_info()
    send_data_to_api(system_data)

# --- BUCLE PRINCIPAL DE EJECUCIÓN ---

if __name__ == "__main__":
    print("Iniciando agente de monitoreo...")
    print(f"Los datos se enviarán cada {COLLECTION_INTERVAL_MINUTES} minutos.")
    
    # Ejecuta el trabajo una vez al inicio para no esperar el primer intervalo
    job()
    
    # Configura la ejecución periódica
    schedule.every(COLLECTION_INTERVAL_MINUTES).minutes.do(job)
    
    # Bucle infinito para mantener el script corriendo y ejecutar las tareas programadas
    while True:
        schedule.run_pending()
        time.sleep(1)