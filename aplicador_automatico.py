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
        logging.FileHandler('aplicador_automatico.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- 1. CONFIGURACIÓN ---
CSV_FILENAME = "aplicaciones_enviadas.csv"
SEARCH_QUERY = "Data Scientist"
LOCATION = "América Latina"
TARGET_APPLICATIONS = 5

# Rutas de los CVs
CV_ESPAÑOL = "Hugo Canaval - Cientifico de datos.pdf"
CV_INGLÉS = "Hugo Canaval - Data Scientist.pdf"

# --- 2. ESTRUCTURA DE DATOS ---
class AplicacionEnviada(BaseModel):
    nombre_vacante: str = Field(description="El título exacto del puesto de trabajo.")
    empresa: str = Field(description="El nombre de la empresa.")
    idioma_detectado: str = Field(description="'español' o 'inglés' según el idioma de la vacante.")
    cv_utilizado: str = Field(description="Nombre del CV que se utilizó para aplicar.")
    estado_aplicacion: str = Field(description="'exitosa' o 'fallida' según el resultado.")
    enlace: str = Field(description="El enlace URL directo a la vacante.")
    notas: str = Field(description="Observaciones adicionales sobre la aplicación.")

# --- 3. ACCIONES PERSONALIZADAS ---
controller = Controller()

@controller.action("Detectar el idioma de una vacante analizando el texto del panel derecho")
async def detectar_idioma_vacante(browser_session: BrowserSession) -> ActionResult:
    try:
        page = await browser_session.get_current_page()
        
        # Extraer texto del panel de detalles de la vacante
        content = await page.locator('[data-job-id], .job-details, .jobs-description').first.text_content()
        
        if not content:
            content = await page.locator('.jobs-search__job-details--container').text_content()
        
        # Palabras clave para detectar idioma
        palabras_español = [
            'requisitos', 'experiencia', 'conocimientos', 'habilidades', 'responsabilidades',
            'funciones', 'empresa', 'trabajo', 'equipo', 'desarrollar', 'años', 'título',
            'licenciatura', 'universidad', 'postgrado', 'maestría', 'estudiante'
        ]
        
        palabras_ingles = [
            'requirements', 'experience', 'skills', 'responsibilities', 'qualifications',
            'bachelor', 'degree', 'university', 'graduate', 'team', 'develop', 'years',
            'knowledge', 'ability', 'working', 'company', 'role', 'position'
        ]
        
        content_lower = content.lower()
        
        # Contar ocurrencias
        count_español = sum(1 for palabra in palabras_español if palabra in content_lower)
        count_ingles = sum(1 for palabra in palabras_ingles if palabra in content_lower)
        
        idioma = "español" if count_español > count_ingles else "inglés"
        
        logger.info(f"Idioma detectado: {idioma} (ES: {count_español}, EN: {count_ingles})")
        return ActionResult(extracted_content=idioma)
        
    except Exception as e:
        logger.error(f"Error al detectar idioma: {e}")
        return ActionResult(extracted_content="inglés")  # Default a inglés en caso de error

@controller.action("Aplicar a una vacante con el CV correspondiente según el idioma")
async def aplicar_a_vacante(idioma: str, browser_session: BrowserSession) -> ActionResult:
    try:
        page = await browser_session.get_current_page()
        
        # Seleccionar CV según idioma
        cv_path = CV_ESPAÑOL if idioma == "español" else CV_INGLÉS
        
        logger.info(f"Aplicando con CV: {cv_path}")
        
        # Buscar y hacer clic en el botón "Solicitud sencilla" o "Easy Apply"
        botones_aplicar = [
            "Solicitud sencilla",
            "Easy Apply", 
            "Aplicar ahora",
            "Apply now",
            "Postularme"
        ]
        
        boton_encontrado = False
        for texto_boton in botones_aplicar:
            try:
                boton = page.locator(f"button:has-text('{texto_boton}')").first
                await boton.wait_for(state="visible", timeout=3000)
                await boton.click()
                boton_encontrado = True
                logger.info(f"Clic en botón: {texto_boton}")
                break
            except:
                continue
        
        if not boton_encontrado:
            return ActionResult(error="No se encontró botón de solicitud sencilla")
        
        await page.wait_for_timeout(2000)
        
        # Manejar el proceso de aplicación paso a paso
        max_steps = 5
        for step in range(max_steps):
            try:
                # Buscar campo de subida de CV
                file_input = page.locator('input[type="file"]').first
                if await file_input.is_visible():
                    await file_input.set_input_files(cv_path)
                    logger.info(f"CV subido: {cv_path}")
                    await page.wait_for_timeout(2000)
                
                # Buscar botón "Siguiente" o "Next"
                botones_siguiente = ["Siguiente", "Next", "Continuar", "Continue"]
                siguiente_encontrado = False
                
                for texto in botones_siguiente:
                    try:
                        siguiente = page.locator(f"button:has-text('{texto}')").first
                        if await siguiente.is_visible():
                            await siguiente.click()
                            siguiente_encontrado = True
                            logger.info(f"Clic en: {texto}")
                            await page.wait_for_timeout(2000)
                            break
                    except:
                        continue
                
                # Buscar botón "Enviar solicitud" o "Submit application"
                botones_enviar = [
                    "Enviar solicitud", 
                    "Submit application", 
                    "Enviar", 
                    "Submit",
                    "Postularme"
                ]
                
                for texto in botones_enviar:
                    try:
                        enviar = page.locator(f"button:has-text('{texto}')").first
                        if await enviar.is_visible():
                            await enviar.click()
                            logger.info(f"Aplicación enviada con: {texto}")
                            await page.wait_for_timeout(3000)
                            return ActionResult(
                                extracted_content=f"Aplicación exitosa con {cv_path}",
                                include_in_memory=True
                            )
                    except:
                        continue
                
                if not siguiente_encontrado:
                    break
                    
            except Exception as e:
                logger.warning(f"Error en paso {step}: {e}")
                continue
        
        return ActionResult(error="No se pudo completar la aplicación")
        
    except Exception as e:
        logger.error(f"Error al aplicar a vacante: {e}")
        return ActionResult(error=f"Error en aplicación: {e}")

@controller.action("Obtener información básica de la vacante actual")
async def obtener_info_vacante(browser_session: BrowserSession) -> ActionResult:
    try:
        page = await browser_session.get_current_page()
        
        # Extraer nombre de la vacante
        nombre_vacante = ""
        selectors_titulo = [
            "h1.job-title",
            ".job-details-jobs-unified-top-card__job-title",
            "h1[data-test-job-title]",
            ".jobs-unified-top-card__job-title"
        ]
        
        for selector in selectors_titulo:
            try:
                elemento = page.locator(selector).first
                if await elemento.is_visible():
                    nombre_vacante = await elemento.text_content()
                    break
            except:
                continue
        
        # Extraer nombre de la empresa
        empresa = ""
        selectors_empresa = [
            ".job-details-jobs-unified-top-card__company-name",
            "a[data-test-job-company-name]",
            ".jobs-unified-top-card__company-name"
        ]
        
        for selector in selectors_empresa:
            try:
                elemento = page.locator(selector).first
                if await elemento.is_visible():
                    empresa = await elemento.text_content()
                    break
            except:
                continue
        
        # Obtener URL actual
        enlace = page.url
        
        info = f"Vacante: {nombre_vacante.strip()} | Empresa: {empresa.strip()} | URL: {enlace}"
        logger.info(f"Info extraída: {info}")
        
        return ActionResult(extracted_content=info)
        
    except Exception as e:
        logger.error(f"Error al obtener info de vacante: {e}")
        return ActionResult(error=f"Error al extraer información: {e}")

@controller.action("Contar cuántas aplicaciones ya se han enviado")
def contar_aplicaciones_enviadas() -> ActionResult:
    try:
        if not os.path.exists(CSV_FILENAME):
            return ActionResult(extracted_content="0")
        
        with open(CSV_FILENAME, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader, None)  # Saltar encabezado
            count = sum(1 for _ in reader)
        
        logger.info(f"Aplicaciones enviadas hasta ahora: {count}")
        return ActionResult(extracted_content=str(count))
    except Exception as e:
        logger.error(f"Error al contar aplicaciones: {e}")
        return ActionResult(error=f"Error al contar aplicaciones: {e}")

@controller.action("Guardar el registro de una aplicación enviada", param_model=AplicacionEnviada)
def guardar_aplicacion_csv(params: AplicacionEnviada):
    fecha_actual = date.today().isoformat()
    escribir_encabezado = not os.path.exists(CSV_FILENAME)
    try:
        with open(CSV_FILENAME, 'a', newline='', encoding='utf-8') as f:
            nombres_campos = ["fecha_aplicacion"] + list(AplicacionEnviada.model_fields.keys())
            writer = csv.writer(f)
            if escribir_encabezado: 
                writer.writerow(nombres_campos)
            
            fila = [fecha_actual] + list(params.model_dump().values())
            writer.writerow(fila)
        
        logger.info(f"Aplicación guardada: {params.nombre_vacante} - {params.empresa}")
        return ActionResult(extracted_content=f"Aplicación registrada: '{params.nombre_vacante}'")
    except Exception as e: 
        logger.error(f"Error al guardar aplicación: {e}")
        return ActionResult(error=f"Error al guardar: {e}")

@controller.action("Solicitar al usuario humano el código de verificación por SMS")
def obtener_codigo_sms() -> ActionResult:
    print("\n" + "="*50)
    print("--- 🙋 ACCIÓN HUMANA REQUERIDA 🙋 ---")
    code = input("Por favor, introduce el código de verificación de LinkedIn que recibiste por SMS: ")
    print("="*50 + "\n")
    if code and code.strip(): 
        logger.info("Código de verificación SMS recibido")
        return ActionResult(extracted_content=code.strip(), include_in_memory=True)
    else: 
        logger.warning("No se recibió código de verificación")
        return ActionResult(error="No se recibió código.")

async def main():
    # Verificar que los CVs existen
    if not os.path.exists(CV_ESPAÑOL):
        logger.error(f"No se encuentra el CV en español: {CV_ESPAÑOL}")
        print(f"❌ Error: No se encuentra el archivo {CV_ESPAÑOL}")
        return
    
    if not os.path.exists(CV_INGLÉS):
        logger.error(f"No se encuentra el CV en inglés: {CV_INGLÉS}")
        print(f"❌ Error: No se encuentra el archivo {CV_INGLÉS}")
        return
    
    logger.info(f"CVs encontrados: {CV_ESPAÑOL}, {CV_INGLÉS}")
    
    # --- TAREA ESPECIALIZADA PARA APLICACIÓN AUTOMÁTICA ---
    tarea_aplicacion = f"""
    Eres un robot aplicador de empleos altamente especializado. Tu misión es aplicar automáticamente a {TARGET_APPLICATIONS} vacantes de {SEARCH_QUERY} en {LOCATION}.

    **INSTRUCCIONES CRÍTICAS:**
    - Solo aplica a vacantes con "Solicitud sencilla" / "Easy Apply" habilitado
    - Detecta el idioma de cada vacante antes de aplicar
    - Usa el CV correcto según el idioma detectado
    - Registra cada aplicación inmediatamente después de enviarla
    - Si LinkedIn te pide verificación, usa `obtener_codigo_sms`

    **CHECKLIST DE OPERACIONES:**

    1.  **VERIFICACIÓN INICIAL**: 
        - Usa `contar_aplicaciones_enviadas` para ver cuántas aplicaciones ya has enviado
        - Si ya tienes {TARGET_APPLICATIONS} o más, termina con `done`

    2.  **INICIO**: Ve a linkedin.com. Si necesitas iniciar sesión, hazlo.
    
    3.  **IR A EMPLEOS**: Busca y haz clic en "Empleos" en la barra de navegación superior.
    
    4.  **BÚSQUEDA INICIAL**:
        a. En el campo "Cargo, aptitud o empresa", escribe "{SEARCH_QUERY}"
        b. En el campo "Ubicación", escribe "{LOCATION}" 
        c. Presiona Enter para buscar y espera a que carguen los resultados

    5.  **APLICAR FILTROS CRÍTICOS**:
        a. Busca el filtro "Fecha de publicación" → clic → selecciona "Últimas 24 horas"
        b. Busca el filtro "Modalidad de trabajo" → clic → selecciona "En remoto"
        c. Busca el filtro "Solicitud sencilla" o "Easy Apply" → clic para activarlo
        d. Espera 3 segundos después de cada filtro para que se actualicen los resultados

    6.  **CICLO DE APLICACIÓN** (Repetir hasta tener {TARGET_APPLICATIONS} aplicaciones):
        
        **ANTES DE CADA APLICACIÓN:**
        - Usa `contar_aplicaciones_enviadas` para verificar tu progreso
        - Si ya tienes {TARGET_APPLICATIONS}, termina con `done`
        
        **PROCESAMIENTO:**
        a. Haz clic en el primer título de trabajo no procesado del panel izquierdo
        b. Espera a que se cargue el detalle en el panel derecho
        c. **VERIFICAR SOLICITUD SENCILLA**: Confirma que tiene botón "Solicitud sencilla" o "Easy Apply"
        d. **OBTENER INFO**: Usa `obtener_info_vacante` para extraer nombre y empresa
        e. **DETECTAR IDIOMA**: Usa `detectar_idioma_vacante` para determinar español/inglés
        f. **APLICAR**: Usa `aplicar_a_vacante` con el idioma detectado
        g. **REGISTRAR**: Usa `guardar_aplicacion_csv` con toda la información:
           - nombre_vacante, empresa (de `obtener_info_vacante`)
           - idioma_detectado (de `detectar_idioma_vacante`)
           - cv_utilizado ("{CV_ESPAÑOL}" si español, "{CV_INGLÉS}" si inglés)
           - estado_aplicacion ("exitosa" o "fallida")
           - enlace (URL actual)
           - notas (cualquier observación)
        
        h. **CONTINUAR**: Después de registrar, ve al siguiente trabajo de la lista

    7.  **PAGINACIÓN**: Si terminas la página actual y necesitas más aplicaciones, busca "Siguiente" y continúa.

    8.  **FINALIZACIÓN**: 
        - Usa `contar_aplicaciones_enviadas` una vez más
        - Si tienes {TARGET_APPLICATIONS} o más, o no hay más resultados, termina con `done`

    **RECORDATORIOS IMPORTANTES:**
    - Solo procesa vacantes con "Solicitud sencilla" habilitado
    - Cada aplicación se registra automáticamente en el CSV
    - Las credenciales están en datos_sensibles, úsalas si necesitas login
    - Si una aplicación falla, regístrala como "fallida" y continúa
    - PRIORIDAD: Aplicaciones exitosas, no solo intentos
    """
    
    datos_sensibles = {
        "linkedin_email": os.getenv("LINKEDIN_EMAIL"),
        "linkedin_password": os.getenv("LINKEDIN_PASSWORD")
    }

    logger.info("Iniciando robot aplicador de empleos...")
    
    agent = Agent(
        task=tarea_aplicacion,
        llm=ChatGoogleGenerativeAI(model="gemini-1.5-pro"),
        controller=controller,
        sensitive_data=datos_sensibles,
        tool_calling_method="function_calling",
        browser_session=BrowserSession(
            headless=False,
            allowed_domains=["*.linkedin.com", "*.google.com"],
            browser_type="chromium"
        )
    )

    try:
        resultado = await agent.run(max_steps=250)
        logger.info("Robot aplicador terminó exitosamente")
    except Exception as e:
        logger.error(f"Error durante la ejecución del robot: {e}")
    finally:
        # Mostrar resumen final
        if os.path.exists(CSV_FILENAME):
            with open(CSV_FILENAME, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None)  # Saltar encabezado
                total_aplicaciones = sum(1 for _ in reader)
            logger.info(f"✅ Aplicaciones completadas. Total enviadas: {total_aplicaciones}")
            print(f"\n🎉 ¡Proceso finalizado! Se enviaron {total_aplicaciones} aplicaciones registradas en '{CSV_FILENAME}'")
        else:
            logger.warning("No se encontró el archivo CSV al finalizar")
            print("\n⚠️  No se enviaron aplicaciones")


if __name__ == "__main__":
    asyncio.run(main()) 