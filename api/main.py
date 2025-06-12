# api/main.py
import os
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Request, Header
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# --- CONFIGURACIÓN DE BASE DE DATOS (Lee desde variables de entorno) ---
DB_USER = os.getenv("MYSQL_USER")
DB_PASSWORD = os.getenv("MYSQL_PASSWORD")
DB_HOST = os.getenv("DB_HOST") # El endpoint de tu RDS
DB_NAME = os.getenv("MYSQL_DATABASE")
DATABASE_URL = f"mysql+aiomysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"

# SQLAlchemy Async Engine
engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)
Base = declarative_base()

# --- MODELOS ORM (TABLAS DE LA BASE DE DATOS) ---
class System(Base):
    __tablename__ = "systems"
    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String(45), unique=True, index=True, nullable=False)
    os_name = Column(String(255)); os_version = Column(String(255))
    first_seen = Column(DateTime, default=datetime.utcnow); last_seen = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    collections = relationship("Collection", back_populates="system", cascade="all, delete-orphan")

class Collection(Base):
    __tablename__ = "collections"
    id = Column(Integer, primary_key=True, index=True)
    system_id = Column(Integer, ForeignKey("systems.id"), nullable=False)
    collection_timestamp = Column(DateTime, default=datetime.utcnow)
    cpu_usage_percent = Column(Float, nullable=True)
    system = relationship("System", back_populates="collections")
    processes = relationship("Process", back_populates="collection", cascade="all, delete-orphan")
    logged_users = relationship("LoggedUser", back_populates="collection", cascade="all, delete-orphan")

class Process(Base):
    __tablename__ = "processes"
    id = Column(Integer, primary_key=True, index=True)
    collection_id = Column(Integer, ForeignKey("collections.id"), nullable=False)
    pid = Column(Integer); name = Column(String(255)); username = Column(String(255), nullable=True)
    collection = relationship("Collection", back_populates="processes")

class LoggedUser(Base):
    __tablename__ = "logged_users"
    id = Column(Integer, primary_key=True, index=True)
    collection_id = Column(Integer, ForeignKey("collections.id"), nullable=False)
    username = Column(String(255)); terminal = Column(String(255), nullable=True)
    collection = relationship("Collection", back_populates="logged_users")

# --- MODELOS PYDANTIC (SINTAXIS MODERNA) ---
class CPUInfo(BaseModel):
    physical_cores: int | None = None; total_cores: int | None = None; frequency: float | str | None = None; usage_percent: float | None = None; error: str | None = None
class ProcessInfo(BaseModel):
    pid: int; name: str; username: str | None = None
class UserInfo(BaseModel):
    user: str; terminal: str | None = None
class SystemData(BaseModel):
    os_name: str; os_version: str; cpu_info: CPUInfo; running_processes: list[ProcessInfo | dict]; logged_in_users: list[UserInfo] | dict

# --- APP FASTAPI ---
app = FastAPI(title="System Info Collector API - RDS Version", version="3.0.0")
API_TOKEN = os.getenv("API_TOKEN", "micompania_secret_token_12345")

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def verify_token(authorization: str = Header(...)):
    if not authorization.startswith("Bearer ") or authorization.split(" ")[1] != API_TOKEN:
        raise HTTPException(status_code=401, detail="Token de autorización inválido")

@app.post("/collect", status_code=201, dependencies=[Depends(verify_token)])
async def collect_data(data: SystemData, request: Request, db: AsyncSession = Depends(get_db)):
    client_ip = request.headers.get("x-forwarded-for", request.client.host)
    from sqlalchemy.future import select
    result = await db.execute(select(System).where(System.ip_address == client_ip))
    system = result.scalar_one_or_none()
    if not system:
        system = System(ip_address=client_ip, os_name=data.os_name, os_version=data.os_version)
        db.add(system); await db.flush()
    else:
        system.last_seen = datetime.utcnow()
    collection = Collection(system_id=system.id, cpu_usage_percent=data.cpu_info.usage_percent)
    db.add(collection); await db.flush()
    if isinstance(data.running_processes, list):
        for proc_data in data.running_processes:
            if isinstance(proc_data, ProcessInfo): db.add(Process(collection_id=collection.id, pid=proc_data.pid, name=proc_data.name, username=proc_data.username))
    if isinstance(data.logged_in_users, list):
        for user_data in data.logged_in_users: db.add(LoggedUser(collection_id=collection.id, username=user_data.user, terminal=user_data.terminal))
    await db.commit()
    return {"status": "success", "message": f"Datos de {client_ip} almacenados en la base de datos."}

@app.get("/query/{ip_address}", response_model=list[dict])
async def query_data(ip_address: str, db: AsyncSession = Depends(get_db)):
    from sqlalchemy.future import select
    from sqlalchemy.orm import joinedload
    result = await db.execute(select(Collection).join(System).where(System.ip_address == ip_address).options(joinedload(Collection.processes), joinedload(Collection.logged_users)).order_by(Collection.collection_timestamp.desc()).limit(5))
    collections = result.scalars().all()
    if not collections: raise HTTPException(status_code=404, detail=f"No se encontraron datos para la IP: {ip_address}")
    response_data = []
    for c in collections:
        response_data.append({"collection_timestamp": c.collection_timestamp, "cpu_usage": c.cpu_usage_percent, "processes": [{"pid": p.pid, "name": p.name} for p in c.processes], "users": [{"user": u.username} for u in c.logged_users]})
    return response_data