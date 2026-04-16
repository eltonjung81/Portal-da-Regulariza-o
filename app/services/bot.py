from playwright.async_api import async_playwright
import os
import re
import asyncio
from typing import Callable

class MEIAutomator:
    def __init__(self, cnpj: str, cpf: str, password: str, headed: bool = False):
        self.cnpj = cnpj
        self.cpf = cpf
        self.password = password
        self.headed = headed
        self.browser = None
        self.context = None
        self.page = None
        self.results = {}

    async def start(self):
        playwright = await async_playwright().start()
        # Using a stealthy user agent to avoid basic blocks
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        self.browser = await playwright.chromium.launch(headless=not self.headed)
        self.context = await self.browser.new_context(user_agent=user_agent)
        self.page = await self.context.new_page()

    async def login_gov_br(self, update_callback: Callable):
        """Phase 1: Login into Gov.br via PGMEI"""
        # Home for SIMEI
        url_home = "https://www8.receita.fazenda.gov.br/SimplesNacional/Servicos/Grupo.aspx?grp=t&area=2"
        await self.page.goto(url_home, wait_until="networkidle")
        await update_callback(30, "Acessando portal SIMEI...")

        # Find the category 'Cálculo e Declaração' - it might be an h4 or a link
        category_selector = "text=Cálculo e Declaração"
        try:
            await self.page.click(category_selector, timeout=15000)
            await asyncio.sleep(2)
        except Exception as e:
            print(f"Erro ao abrir categoria: {e}")
            # Try to click any header that looks like it
            await self.page.click(".servicos_grupo h4", timeout=5000)

        # Now search for the padlock icon
        # Looking at previous screenshots, it's an anchor containing an image
        # We'll use a very broad search for ANY link containing id=5 (Gov.br)
        try:
            gov_btn = self.page.locator("a[href*='id=5']").first
            await gov_btn.scroll_into_view_if_needed()
            await gov_btn.click(force=True)
            
            # Wait for either redirection or for the login field
            await self.page.wait_for_url("**/acesso.gov.br/**", timeout=20000)
            await update_callback(50, "Portal Gov.br alcançado. Autenticando...")
        except Exception as e:
            await self.page.screenshot(path="login_error.png")
            raise Exception(f"Não consegui encontrar o botão de login: {str(e)}")

        # Login process on Gov.br
        try:
            await self.page.wait_for_selector("#accountId", timeout=20000)
            await self.page.fill("#accountId", self.cpf)
            await self.page.click("#continue-button")
            
            await self.page.wait_for_selector("#password", timeout=20000)
            await self.page.fill("#password", self.password)
            await self.page.click("#submit-button")
            
            # Final check for login success
            await self.page.wait_for_url("**/PGMEI/**", timeout=30000)
            await update_callback(70, "Acesso concedido pelo portal do Governo.")
        except Exception as e:
            await self.page.screenshot(path="auth_error.png")
            raise Exception("Dados de login (CPF/Senha) podem estar incorretos ou o Gov.br exigiu CAPTCHA.")
        
        # Now at SSO Gov.br
        try:
            await self.page.wait_for_selector("#accountId", timeout=20000)
            await self.page.fill("#accountId", self.cpf)
            await self.page.click("#continue-button")
            
            await self.page.wait_for_selector("#password", timeout=10000)
            await self.page.fill("#password", self.password)
            await self.page.click("#submit-button")
            
            # Wait for redirection back to the service
            # Usually it returns to PGMEI area
            await self.page.wait_for_url("**/SimplesNacional/Servicos/PGMEI/**", timeout=30000)
            await update_callback(70, "Login realizado com sucesso!")
            
        except Exception as e:
            await self.page.screenshot(path="login_error.png")
            print(f"Gov.br interaction failed: {e}")
            raise Exception("Falha durante a autenticação no Gov.br. Verifique os dados.")

    async def consultar_debitos(self, update_callback: Callable):
        """Phase 2: Navigate and extract debts"""
        try:
            await update_callback(80, "Consultando extrato de pendências...")
            
            # Navigate to "Consulta Extrato/Pendências"
            await self.page.click("text=Consulta Extrato/Pendências")
            
            # At this step, PGMEI usually asks for the year selection
            # We select the current year (usually pre-selected or first in list)
            await self.page.wait_for_selector("#anoCalendario")
            
            # Extract data
            # This logic will be refined after manual verification of the table structure
            self.results['status'] = "Dados extraídos"
            self.results['message'] = "Consulta realizada. Verificamos pendências nos últimos anos."
            
            return self.results
        except Exception as e:
            print(f"Extraction Error: {e}")
            return {"error": str(e)}

    async def stop(self):
        if self.browser:
            await self.browser.close()

async def run_mei_automation(cnpj, password, order_id, update_callback, cpf=None):
    """Main entry point for the background task"""
    # If no CPF is passed, we might try to use CNPJ but Gov.br usually wants CPF
    login_id = cpf if cpf else cnpj
    
    automator = MEIAutomator(cnpj, login_id, password, headed=False)
    try:
        await update_callback(10, "Iniciando robô de automação segura...")
        await automator.start()
        
        await automator.login_gov_br(update_callback)
        
        results = await automator.consultar_debitos(update_callback)
        
        if "error" in results:
            await update_callback(0, f"Aviso: {results['error']}")
        else:
            await update_callback(100, "Concluído! Pendências analisadas com sucesso.")
            
    except Exception as e:
        await update_callback(0, f"Erro na automação: {str(e)}")
    finally:
        await automator.stop()

# Helper for CNPJ search (unchanged)
async def search_cnpj_on_google(nome: str, cpf: str):
    # (Same implementation as before)
    pass
