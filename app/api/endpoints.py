from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Optional
import uuid
import httpx
from pydantic import BaseModel
import os
import mercadopago
from dotenv import load_dotenv
from app.services.bot import run_mei_automation, search_cnpj_on_google
from app.services.db import save_order, get_order, update_order_status, update_payment_paid, update_contact_phone, update_gov_password, get_all_leads, save_whatsapp_lead

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

class CapturarLeadRequest(BaseModel):
    name: str
    phone: str
    cnpj: Optional[str] = ""
    razao_social: Optional[str] = ""

class DiagnosticoLeadRequest(BaseModel):
    cnpj: str
    nome: str
    atividade: Optional[str] = ""
    tempo_mei: Optional[str] = ""
    situacao_das: Optional[str] = ""
    preocupacoes: Optional[str] = ""
    phone: str
    email: Optional[str] = ""

@router.post("/buscar-cnpj")
async def buscar_cnpj(request: SearchCNPJRequest):
    cnpjs = await search_cnpj_on_google(request.nome, request.cpf)
    return {"cnpjs": cnpjs}

@router.post("/capturar-lead")
async def capturar_lead(request: CapturarLeadRequest):
    """Endpoint principal do novo fluxo: captura lead via botão WhatsApp sem pagamento."""
    lead_id = str(uuid.uuid4())
    lead_data = {
        "id": lead_id,
        "name": request.name.strip(),
        "phone": request.phone,
        "cnpj": request.cnpj or "",
        "razao_social": request.razao_social or ""
    }
    await save_whatsapp_lead(lead_data)
    return {"status": "ok", "id": lead_id}

@router.post("/diagnostico-lead")
async def receive_diagnostico_lead(request: DiagnosticoLeadRequest):
    from app.services.db import save_diagnostico_lead
    lead_id = str(uuid.uuid4())
    lead_data = {
        "id": lead_id,
        "cnpj": request.cnpj,
        "nome": request.nome,
        "atividade": request.atividade,
        "tempo_mei": request.tempo_mei,
        "situacao_das": request.situacao_das,
        "preocupacoes": request.preocupacoes,
        "phone": request.phone,
        "email": request.email
    }
    await save_diagnostico_lead(lead_data)
    return {"status": "ok", "id": lead_id}

@router.post("/checkout")
async def checkout(request: CheckoutRequest):
    order_id = str(uuid.uuid4())
    
    # Force Price and Plan Name (Security and Consistency)
    request.price = 99.90
    request.plan_name = "Regularização Completa MEI"
    
    # Create Mercado Pago Payment
    payment_data = {
        "transaction_amount": float(request.price),
        "description": f"MEI em Dia - {request.plan_name}",
        "payment_method_id": "pix",
        "payer": {
            "email": "cliente@portal-regulariza.com", 
            "first_name": "Cliente",
            "last_name": "MEI"
        }
    }
    
    # Idempotency key
    request_options = mercadopago.config.RequestOptions()
    request_options.custom_headers = {"X-Idempotency-Key": order_id}

    result = sdk.payment().create(payment_data, request_options)
    
    if result["status"] >= 400:
        # Fallback to simulation if token is missing or invalid for testing
        print(f"MP Error: {result['response']}")
        qr_code = "00020126580014BR.GOV.BCB.PIX0136123e4567-e89b-12d3-a456-4266141740005204000053039865802BR5913MEI_EM_DIA_APP6009SAO_PAULO62070503***6304E2CA"
        # Generate a real QR code image using a public API for the fallback key
        qr_code_base64 = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={qr_code}"
        payment_id = "SIMULATED_" + order_id
    else:
        payment = result["response"]
        qr_code = payment["point_of_interaction"]["transaction_data"]["qr_code"]
        # Convert base64 from MP to a proper data URI if it's not already
        raw_base64 = payment["point_of_interaction"]["transaction_data"]["qr_code_base64"]
        qr_code_base64 = f"data:image/png;base64,{raw_base64}"
        payment_id = str(payment["id"])

    order_data = {
        "id": order_id,
        "payment_id": payment_id,
        "cnpj": request.cnpj if request.cnpj else "",
        "razao_social": request.razao_social if request.razao_social else "",
        "plan": request.plan_name,
        "price": request.price,
        "status": "pending_payment",
        "progress": 0,
        "message": "Aguardando pagamento via PIX"
    }
    
    await save_order(order_data)
    
    return {
        "order_id": order_id, 
        "pix_key": qr_code,
        "qr_code_base64": qr_code_base64
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
    
    # If still waiting for payment, check real status in MP
    if order["status"] == "pending_payment" and not order["payment_id"].startswith("SIMULATED_"):
        try:
            payment_info = sdk.payment().get(order["payment_id"])
            mp_status = payment_info["response"].get("status")
            if mp_status == "approved":
                await update_payment_paid(order_id)
                order = await get_order(order_id) # Refresh
        except:
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
