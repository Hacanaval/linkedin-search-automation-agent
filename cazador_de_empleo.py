import asyncio
import os
import csv
import logging
from pathlib import Path
from datetime import date
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from browser_use import Agent, Controller, BrowserSession, ActionResult
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('cazador_empleo.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- 1. CONFIGURACIÓN ---
CSV_FILENAME = "vacantes_remotas.csv"
SEARCH_QUERY = "Data Scientist"
LOCATIONS = ["Colombia", "Latinoamérica"]
TARGET_JOB_COUNT = 10

# --- 2. ESTRUCTURA DE DATOS ---
class Vacante(BaseModel):
    nombre_vacante: str = Field(description="El título exacto del puesto de trabajo.")
    empresa: str = Field(description="El nombre de la empresa.")
    descripcion: str = Field(description="Un resumen conciso de los requisitos del trabajo.")
    salario_y_beneficios: str = Field(description="El salario y beneficios, si se mencionan. Si no, 'No especificado'.")
    enlace: str = Field(description="El enlace URL directo y completo a la vacante.")

# --- 3. ACCIONES PERSONALIZADAS ---
controller = Controller()

@controller.action("Aplica un filtro haciendo clic en un elemento que contiene un texto específico")
async def aplicar_filtro_por_texto(texto_del_filtro: str, browser_session: BrowserSession) -> ActionResult:
    page = await browser_session.get_current_page()
    try:
        logger.info(f"Aplicando filtro: {texto_del_filtro}")
        locator = page.locator(f"*:text-is('{texto_del_filtro}')").first
        await locator.wait_for(state="visible", timeout=5000)
        await locator.locator('xpath=./ancestor-or-self::*[self::button or self::label or @role="button" or contains(@class, "filter")]').first.click()
        await page.wait_for_timeout(2000)  # Esperar a que se aplique el filtro
        return ActionResult(extracted_content=f"Filtro '{texto_del_filtro}' aplicado.")
    except Exception as e:
        logger.error(f"Error al aplicar filtro '{texto_del_filtro}': {e}")
        return ActionResult(error=f"No se pudo aplicar el filtro para '{texto_del_filtro}': {e}")

@controller.action("Obtiene el enlace (URL) de un elemento de la lista de trabajos")
async def obtener_enlace_de_vacante(index: int, browser_session: BrowserSession) -> ActionResult:
    try:
        selector_map = await browser_session.get_selector_map()
        if index not in selector_map:
            return ActionResult(error=f"No se encontró el elemento con el índice {index}.")
        element_node = selector_map[index]
        
        enlace = None
        temp_node = element_node
        for _ in range(3):
            if temp_node:
                enlace = temp_node.attributes.get('href')
                if enlace: break
                temp_node = temp_node.parent
            else: break
                
        if enlace:
            if enlace.startswith('/'): enlace = "https://www.linkedin.com" + enlace
            logger.info(f"Enlace obtenido: {enlace}")
            return ActionResult(extracted_content=enlace)
        else:
            return ActionResult(error=f"El elemento con índice {index} no contiene un enlace 'href'.")
    except Exception as e:
        logger.error(f"Error al obtener enlace del índice {index}: {e}")
        return ActionResult(error=f"Error al obtener enlace: {e}")

@controller.action("Contar cuántas vacantes ya se han guardado en el CSV")
def contar_vacantes_guardadas() -> ActionResult:
    try:
        if not os.path.exists(CSV_FILENAME):
            return ActionResult(extracted_content="0")
        
        with open(CSV_FILENAME, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader, None)  # Saltar encabezado
            count = sum(1 for _ in reader)
        
        logger.info(f"Vacantes guardadas hasta ahora: {count}")
        return ActionResult(extracted_content=str(count))
    except Exception as e:
        logger.error(f"Error al contar vacantes: {e}")
        return ActionResult(error=f"Error al contar vacantes: {e}")

@controller.action("Guardar la información de UNA vacante en un archivo CSV", param_model=Vacante)
def guardar_vacante_csv(params: Vacante):
    fecha_actual = date.today().isoformat()
    escribir_encabezado = not os.path.exists(CSV_FILENAME)
    try:
        with open(CSV_FILENAME, 'a', newline='', encoding='utf-8') as f:
            nombres_campos = ["fecha_busqueda"] + list(Vacante.model_fields.keys())
            writer = csv.writer(f)
            if escribir_encabezado: writer.writerow(nombres_campos)
            fila = [fecha_actual] + list(params.model_dump().values())
            writer.writerow(fila)
        
        logger.info(f"Vacante guardada: {params.nombre_vacante} - {params.empresa}")
        return ActionResult(extracted_content=f"Guardada la vacante '{params.nombre_vacante}'.")
    except Exception as e: 
        logger.error(f"Error al guardar vacante: {e}")
        return ActionResult(error=f"Error al guardar: {e}")

@controller.action("Solicitar al usuario humano el código de verificación por SMS")
def obtener_codigo_sms() -> ActionResult:
    print("\n" + "="*50); print("--- 🙋 ACCIÓN HUMANA REQUERIDA 🙋 ---")
    code = input("Por favor, introduce el código de verificación de LinkedIn que recibiste por SMS: ")
    print("="*50 + "\n")
    if code and code.strip(): 
        logger.info("Código de verificación SMS recibido")
        return ActionResult(extracted_content=code.strip(), include_in_memory=True)
    else: 
        logger.warning("No se recibió código de verificación")
        return ActionResult(error="No se recibió código.")

async def main():
    # --- 4. EL CHECKLIST MAESTRO (BASADO EN TUS IMÁGENES Y LOGS) ---
    tarea_especifica = f"""
    Eres un robot de búsqueda de empleo altamente especializado. Tu misión es encontrar {TARGET_JOB_COUNT} vacantes remotas para {SEARCH_QUERY}. 

    **INSTRUCCIONES CRÍTICAS:**
    - Antes de procesar cualquier vacante, usa `contar_vacantes_guardadas` para saber cuántas ya tienes
    - Solo procesa vacantes que sean 100% remotas/trabajo remoto
    - Guarda cada vacante inmediatamente después de extraer sus datos
    - Si LinkedIn te pide verificación, usa `obtener_codigo_sms`

    **CHECKLIST DE OPERACIONES:**

    1.  **VERIFICACIÓN INICIAL**: 
        - Usa `contar_vacantes_guardadas` para ver cuántas vacantes ya tienes guardadas
        - Si ya tienes {TARGET_JOB_COUNT} o más, termina con `done`

    2.  **INICIO**: Ve a linkedin.com. Si necesitas iniciar sesión, hazlo.
    
    3.  **IR A EMPLEOS**: Busca y haz clic en "Empleos" en la barra de navegación superior.
    
    4.  **BÚSQUEDA INICIAL**:
        a. En el campo "Cargo, aptitud o empresa", escribe "{SEARCH_QUERY}"
        b. En el campo "Ubicación", escribe "Colombia" 
        c. Presiona Enter para buscar y espera a que carguen los resultados

    5.  **APLICAR FILTROS CRÍTICOS**:
        a. Busca el filtro "Fecha de publicación" → clic → selecciona "Últimas 24 horas"
        b. Busca el filtro "Modalidad de trabajo" → clic → selecciona "En remoto"
        c. Espera 3 segundos después de cada filtro para que se actualicen los resultados

    6.  **CICLO DE EXTRACCIÓN** (Repetir hasta tener {TARGET_JOB_COUNT} vacantes):
        
        **ANTES DE CADA VACANTE:**
        - Usa `contar_vacantes_guardadas` para verificar tu progreso
        - Si ya tienes {TARGET_JOB_COUNT}, termina con `done`
        
        **PROCESAMIENTO:**
        a. Haz clic en el primer título de trabajo no procesado del panel izquierdo
        b. Espera a que se cargue el detalle en el panel derecho
        c. **VERIFICACIÓN REMOTO**: Lee la descripción del panel derecho. Busca palabras como:
           - ✅ "remoto", "remote", "desde casa", "home office", "trabajo remoto"
           - ❌ Si ves "híbrido", "presencial", "oficina", DESCARTA esta vacante
        
        d. **SI ES REMOTO:**
           - Usa `obtener_enlace_de_vacante` con el índice del título clickeado
           - Usa `extract_content` para obtener: nombre_vacante, empresa, descripción, salario_y_beneficios
           - **GUARDAR INMEDIATAMENTE**: Llama a `guardar_vacante_csv` con todos los datos
        
        e. **CONTINUAR**: Después de guardar (o descartar), ve al siguiente trabajo de la lista

    7.  **PAGINACIÓN**: Si terminas la página actual y necesitas más vacantes, busca "Siguiente" y continúa.

    8.  **FINALIZACIÓN**: 
        - Usa `contar_vacantes_guardadas` una vez más
        - Si tienes {TARGET_JOB_COUNT} o más, o no hay más resultados, termina con `done`

    **RECORDATORIOS IMPORTANTES:**
    - Cada vez que guardes una vacante, el archivo CSV se actualiza automáticamente
    - Las credenciales de LinkedIn están en datos_sensibles, úsalas si necesitas login
    - Si algo falla, registra el error y continúa con la siguiente vacante
    - PRIORIDAD: Calidad sobre cantidad - solo vacantes 100% remotas
    """
    
    datos_sensibles = {
        "linkedin_email": os.getenv("LINKEDIN_EMAIL"),
        "linkedin_password": os.getenv("LINKEDIN_PASSWORD")
    }

    logger.info("Iniciando agente de búsqueda de empleo...")
    
    agent = Agent(
        task=tarea_especifica,
        llm=ChatGoogleGenerativeAI(model="gemini-1.5-pro"),
        controller=controller,
        sensitive_data=datos_sensibles,
        tool_calling_method="function_calling",
        browser_session=BrowserSession(
            headless=False,
            allowed_domains=["*.linkedin.com", "*.google.com"],
            browser_type="chromium"  # Especificar tipo de browser
        )
    )

    try:
        resultado = await agent.run(max_steps=200)  # Aumentar pasos máximos
        logger.info("Agente terminó exitosamente")
    except Exception as e:
        logger.error(f"Error durante la ejecución del agente: {e}")
    finally:
        # Mostrar resumen final
        if os.path.exists(CSV_FILENAME):
            with open(CSV_FILENAME, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None)  # Saltar encabezado
                total_vacantes = sum(1 for _ in reader)
            logger.info(f"✅ Búsqueda completada. Total de vacantes guardadas: {total_vacantes}")
            print(f"\n🎉 ¡Proceso finalizado! Se guardaron {total_vacantes} vacantes en '{CSV_FILENAME}'")
        else:
            logger.warning("No se encontró el archivo CSV al finalizar")
            print("\n⚠️  No se encontraron vacantes para guardar")


if __name__ == "__main__":
    asyncio.run(main())