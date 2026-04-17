import asyncio
import sys
import selectors
import uvicorn

# Configuração definitiva para Windows + psycopg3
async def start_server():
    from main import app
    config = uvicorn.Config(app, host="0.0.0.0", port=5000, log_level="info", loop="asyncio")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    if sys.platform == 'win32':
        # Força o uso do SelectorEventLoop no asyncio.run (Disponível em Python 3.12+)
        selector = selectors.SelectSelector()
        loop_factory = lambda: asyncio.SelectorEventLoop(selector)
        try:
            asyncio.run(start_server(), loop_factory=loop_factory)
        except TypeError:
            # Fallback para versões anteriores do Python
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            asyncio.run(start_server())
    else:
        asyncio.run(start_server())
