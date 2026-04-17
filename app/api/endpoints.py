from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from typing import Optional
import uuid
import httpx
from pydantic import BaseModel
import os
import mercadopago
from dotenv import load_dotenv
from app.services.bot import run_mei_automation, search_cnpj_on_google
from app.services.db import save_order, get_order, update_order_status, update_payment_paid, update_contact_phone, update_gov_password, get_all_leads

load_dotenv()

router = APIRouter()

# Initialize MP SDK
sdk = mercadopago.SDK(os.getenv("MERCADO_PAGO_ACCESS_TOKEN", "TEST-TOKEN-MISSING"))

class CheckoutRequest(BaseModel):
    cnpj: Optional[str] = None
    razao_social: Optional[str] = None
    plan_name: str
    price: float

class RegularizeRequest(BaseModel):
    order_id: str
    gov_password: str
    cpf: Optional[str] = None
    consent: bool

class ContactRequest(BaseModel):
    order_id: str
    phone: str
    name: Optional[str] = None

class AdminLoginRequest(BaseModel):
    password: str

class TrackingLoginRequest(BaseModel):
    cnpj: str
    phone_suffix: str

class SearchCNPJRequest(BaseModel):
    nome: str
    cpf: str

@router.post("/buscar-cnpj")
async def buscar_cnpj(request: SearchCNPJRequest):
    cnpjs = await search_cnpj_on_google(request.nome, request.cpf)
    return {"cnpjs": cnpjs}

@router.post("/checkout")
async def checkout(request_data: CheckoutRequest, request: Request):
    order_id = str(uuid.uuid4())
    
    # Obter a URL base dinamicamente (host atual)
    base_url = f"{request.url.scheme}://{request.url.netloc}"
    
    # Configuração da Preferência (Checkout Pro)
    preference_data = {
        "items": [
            {
                "title": f"MEI em Dia - {request_data.plan_name}",
                "description": f"Plano de regularização MEI: {request_data.plan_name}",
                "quantity": 1,
                "unit_price": float(request_data.price),
                "currency_id": "BRL"
            }
        ],
        "payment_methods": {
            "excluded_payment_types": [
                {"id": "ticket"}, # Boleto
                {"id": "debit_card"},
                {"id": "atm"}
            ],
            "installments": 12 # Permitir parcelamento no cartão
        },
        "back_urls": {
            "success": f"{base_url}/?order_id={order_id}&status=success",
            "failure": f"{base_url}/?order_id={order_id}&status=failure",
            "pending": f"{base_url}/?order_id={order_id}&status=pending"
        },
        "auto_return": "approved",
        "external_reference": order_id
    }
    
    result = sdk.preference().create(preference_data)
    
    if result["status"] >= 400:
        print(f"MP Preference Error: {result['response']}")
        # Fallback simulation
        init_point = f"{base_url}/?order_id={order_id}&simulated=true"
    else:
        # Usar init_point (Produção) ou sandbox_init_point (Teste)
        # Se o token começar com TEST-, usamos sandbox
        if os.getenv("MERCADO_PAGO_ACCESS_TOKEN", "").startswith("TEST-"):
            init_point = result["response"]["sandbox_init_point"]
        else:
            init_point = result["response"]["init_point"]

    order_data = {
        "id": order_id,
        "payment_id": f"PREF_{order_id}", # Placeholder até o pagamento real
        "cnpj": request_data.cnpj if request_data.cnpj else "",
        "razao_social": request_data.razao_social if request_data.razao_social else "",
        "plan": request_data.plan_name,
        "price": request_data.price,
        "status": "pending_payment",
        "progress": 0,
        "message": "Aguardando pagamento no Mercado Pago"
    }
    
    await save_order(order_data)
    
    return {
        "order_id": order_id, 
        "init_point": init_point
    }

# Helper functions are imported from app.services.db

@router.post("/regularizar")
async def regularizar(request: RegularizeRequest, background_tasks: BackgroundTasks):
    order = await get_order(request.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    
    if not request.consent:
        raise HTTPException(status_code=400, detail="Consentimento LGPD é obrigatório.")

    # Save password and update state
    await update_gov_password(request.order_id, request.gov_password)
    await update_order_status(request.order_id, "starting", 5, "Iniciando robô de automação...")
    
    # Trigger REAL background task
    background_tasks.add_task(
        run_mei_automation, 
        order["cnpj"], 
        request.gov_password, 
        request.order_id, 
        lambda p, m: update_order_status(request.order_id, "processing", p, m),
        cpf=request.cpf
    )
    
    return {"message": "Processo iniciado com sucesso.", "status": "processing"}

@router.get("/status-processo/{order_id}")
async def get_status(order_id: str):
    order = await get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Processo não encontrado.")
    
    # If still waiting for payment, check real status in MP using external_reference
    if order["status"] == "pending_payment":
        try:
            # Buscar pagamentos associados a esta external_reference (order_id)
            search_results = sdk.payment().search({'external_reference': order_id})
            if search_results["status"] == 200:
                payments = search_results["response"].get("results", [])
                for p in payments:
                    if p["status"] == "approved":
                        await update_payment_paid(order_id)
                        order = await get_order(order_id) # Refresh
                        break
        except Exception as e:
            print(f"Status check error: {e}")
            pass

    return order

@router.post("/atualizar-contato")
async def atualizar_contato(request: ContactRequest):
    from app.services.db import update_lead_contact
    await update_lead_contact(request.order_id, request.phone, request.name)
    return {"status": "ok"}

@router.post("/simular-pagamento/{order_id}")
async def simular_pagamento(order_id: str):
    await update_payment_paid(order_id)
    return {"status": "paid"}

@router.post("/admin/login")
async def admin_login(request: AdminLoginRequest):
    if request.password == "kasarao1981":
        return {"status": "authorized"}
    raise HTTPException(status_code=401, detail="Senha incorreta")

@router.get("/admin/leads")
async def admin_leads():
    # In a real app, this should be protected by middleware/auth
    leads = await get_all_leads()
    return leads

@router.post("/tracking/login")
async def tracking_login(request: TrackingLoginRequest):
    from app.services.db import get_lead_for_tracking
    lead = await get_lead_for_tracking(request.cnpj, request.phone_suffix)
    if not lead:
        raise HTTPException(status_code=401, detail="Dados não encontrados ou pagamento ainda não aprovado.")
    return lead

@router.delete("/admin/leads/{order_id}")
async def admin_delete_lead(order_id: str):
    from app.services.db import delete_lead
    await delete_lead(order_id)
    return {"status": "ok"}

BRASIL_API_URL = "https://brasilapi.com.br/api/cnpj/v1/"

@router.get("/consultar-cnpj/{cnpj}")
async def consultar_cnpj(cnpj: str):
    # Remove non-numeric characters
    cnpj_clean = "".join(filter(str.isdigit, cnpj))
    
    if len(cnpj_clean) != 14:
        raise HTTPException(status_code=400, detail="CNPJ inválido. Deve conter 14 dígitos.")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BRASIL_API_URL}{cnpj_clean}")
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                raise HTTPException(status_code=404, detail="CNPJ não encontrado.")
            else:
                raise HTTPException(status_code=response.status_code, detail="Erro ao consultar BrasilAPI.")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
