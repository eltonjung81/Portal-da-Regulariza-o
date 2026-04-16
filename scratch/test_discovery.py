import asyncio
import sys
import os

# Add the project root to sys.path to import local modules
sys.path.append(os.getcwd())

from app.services.bot import search_cnpj_on_google

async def test():
    nome = "Elton Jung"
    cpf = "97683078034"
    expected = "28.600.483/0001-84"
    
    print(f"--- Iniciando teste de descoberta para: {nome} ---")
    results = await search_cnpj_on_google(nome, cpf)
    
    print(f"Resultados encontrados: {results}")
    
    if expected in results:
        print("OK: O CNPJ esperado foi encontrado!")
    elif any(expected.replace('.', '').replace('-', '').replace('/', '') in r.replace('.', '').replace('-', '').replace('/', '') for r in results):
         print("OK (aproximado): O CNPJ foi encontrado com formatação diferente.")
    else:
        print("FALHA: O CNPJ esperado não foi encontrado.")

if __name__ == "__main__":
    asyncio.run(test())
