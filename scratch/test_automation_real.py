import asyncio
import sys
import os

# Add root to path so we can import app.services
sys.path.append(os.getcwd())

from app.services.bot import MEIAutomator

async def test_bot():
    cnpj = "28600483000184"
    cpf = "97683078034"
    password = "@kasarao1981"
    
    print(f"--- INICIANDO TESTE DE AUTOMAÇÃO ---")
    print(f"CNPJ: {cnpj}")
    print(f"CPF: {cpf}")
    
    # We run with headed=True so I can see what's happening if I were a human, 
    # but since I'm an AI I'll run headless and print status.
    automator = MEIAutomator(cnpj, cpf, password, headed=False)
    
    async def callback(progress, message):
        print(f"[{progress}%] {message}")

    try:
        await automator.start()
        print("Navegador iniciado.")
        
        await automator.login_gov_br(callback)
        print("Login Gov.br concluído com sucesso!")
        
        results = await automator.consultar_debitos(callback)
        print("Resultados obtidos:", results)
        
    except Exception as e:
        print(f"ERRO NO TESTE: {e}")
    finally:
        await automator.stop()
        print("Navegador fechado.")

if __name__ == "__main__":
    asyncio.run(test_bot())
