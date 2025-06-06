import asyncio
import os
from dotenv import load_dotenv
from browser_use import Agent
# Cambio 1: Importamos el modelo de Chat de Google en lugar del de OpenAI
from langchain_google_genai import ChatGoogleGenerativeAI

# Carga las variables de entorno (ahora buscará GOOGLE_API_KEY)
load_dotenv()

# Cambio 2: Actualizamos la línea de debug para verificar la clave de Google
print(f"Clave de Google API cargada: {os.getenv('GOOGLE_API_KEY')}")


async def main():
    # Creamos la instancia del agente
    agent = Agent(
        # La tarea puede ser la misma
        task="Compare the price of gpt-4o and DeepSeek-V3",

        # Cambio 3: Usamos ChatGoogleGenerativeAI con un modelo de Gemini
        llm=ChatGoogleGenerativeAI(model="gemini-1.5-flash"),
    )

    # Le decimos al agente que comience a trabajar
    print("🤖 Agente iniciando... La ventana del navegador debería abrirse pronto.")
    await agent.run()
    print("✅ ¡Tarea completada!")

# Ejecutamos la función principal
if __name__ == "__main__":
    asyncio.run(main())