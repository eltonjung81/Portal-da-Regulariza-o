from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import os
from app.api.endpoints import router as api_router
from app.services.db import init_db

app = FastAPI(title="MEI em Dia API")

@app.on_event("startup")
async def on_startup():
    await init_db()

# Enable CORS for frontend integration
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api/v1")

@app.get("/")
async def root():
    return FileResponse('index.html')

@app.get("/admin-leads")
async def admin():
    return FileResponse('admin-leads.html')

@app.get("/health")
async def health():
    return {"status": "ok", "message": "MEI em Dia API is running", "version": "1.0.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
