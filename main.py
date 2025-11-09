import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings, setup_logging
from core.database import init_models
from database.base import Base
from api.resume_api import resume_router
from api.job_api import job_router

# Use your existing logging setup
setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API for uploading and processing resumes",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,  # Use settings instead of hardcode
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(resume_router, prefix="/api/v1/resume", tags=["Resume"])
app.include_router(job_router, prefix="/api/v1/job", tags=["Job"])

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    logger.info("🚀 Starting up...")
    await init_models(Base)
    logger.info("✅ Database initialized!")

@app.get("/")
async def root():
    return {"message": f"{settings.PROJECT_NAME} API is running"}

@app.get("/health")
async def health():
    return {"status": "healthy"}