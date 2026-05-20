from sqlalchemy import (
create_engine,
Column,
String,
Integer,
DateTime,
Boolean,
Float,
ForeignKey,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from fastapi import FastAPI, Request, HTTPException, Depends
from dotenv import load_dotenv
import os
import uuid
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import parse_qs
import hmac
import hashlib

load_dotenv()

# === Models (встроены в тот же файл ради простоты) ===

Base = declarative_base()


class User(Base):
__tablename__ = "users"
id = Column(Integer, primary_key=True)
telegram_id = Column(String, unique=True)
phone = Column(String, nullable=True)
free_clips_count = Column(Integer, default=0)
has_premium = Column(Boolean, default=False)
premium_expires = Column(DateTime, nullable=True)
has_vip = Column(Boolean, default=False)
vip_expires = Column(DateTime, nullable=True)
created_at = Column(DateTime, default=datetime.utcnow)


class Location(Base):
__tablename__ = "locations"
id = Column(Integer, primary_key=True)
name = Column(String, nullable=False)
city = Column(String)
camera_id = Column(String, nullable=False)
rtsp_url = Column(String, nullable=False)
active = Column(Boolean, default=True)
created_at = Column(DateTime, default=datetime.utcnow)


class Clip(Base):
__tablename__ = "clips"
id = Column(Integer, primary_key=True)
user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
video_url = Column(String, nullable=False)
has_watermark = Column(Boolean, default=True)
paid = Column(Boolean, default=False)
created_at = Column(DateTime, default=datetime.utcnow)
user = relationship("User")
location = relationship("Location")


class Payment(Base):
__tablename__ = "payments"
id = Column(Integer, primary_key=True)
user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
amount = Column(Float, nullable=False)
type = Column(String) # "single", "unlimited", "vip"
paid_at = Column(DateTime, default=datetime.utcnow)
user = relationship("User")


# === Telegram initData validator ===

def validate_telegram_init_data(init_ str, bot_token: str) -> bool:
# разбираем строку и извлекаем hash
parsed = parse_qs(init_data)
hash_val = parsed.pop("hash", [None])[0]
if not hash_val:
return False

data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
return hmac.compare_digest(hash_val, expected_hash)


# === Database setup ===

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://padel:padelpass@db:5432/padel")
BOT_TOKEN = os.getenv("BOT_TOKEN", "123456:ABCDEF")
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/app/output"))
CLIP_SECONDS = int(os.getenv("CLIP_SECONDS", "30"))
PAYMENT_CALLBACK_URL = os.getenv("PAYMENT_CALLBACK_URL", "https://padel-replay-demo.onrender.com/callback")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Создание таблиц
Base.metadata.create_all(bind=engine)


def get_db():
db = SessionLocal()
try:
yield db
finally:
db.close()


app = FastAPI(title="Padel Replay Telegram Mini App")


@app.on_event("startup")
def on_startup():
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# === /auth: авторизация через Telegram initData ===

@app.post("/auth")
async def auth(request: Request, db: Session = Depends(get_db)):
body = await request.json()
init_data = body.get("init_data", "")

if not init_
raise HTTPException(status_code=400, detail="init_data not provided")

# декодируем если надо
import urllib.parse

plain = urllib.parse.unquote(init_data)
if not validate_telegram_init_data(plain, BOT_TOKEN):
raise HTTPException(status_code=403, detail="Invalid Telegram initData")

parsed = urllib.parse.parse_qs(plain)
telegram_id = parsed.get("id", [None])[0]
if not telegram_id:
raise HTTPException(status_code=400, detail="Could not find telegram_id in initData")

user = db.query(User).filter(User.telegram_id == telegram_id).first()
if user is None:
user = User(
telegram_id=telegram_id,
free_clips_count=0,
has_premium=False,
has_vip=False,
)
db.add(user)
db.commit()
db.refresh(user)

# определяем, сколько бесплатных осталось
remaining = max(0, 5 - user.free_clips_count)

return {
"status": "ok",
"user_id": user.id,
"free_clips_remaining": remaining if not user.has_premium else "∞",
"has_premium": user.has_premium,
"premium_expires": user.premium_expires.isoformat() if user.premium_expires else None,
"has_vip": user.has_vip,
"vip_expires": user.vip_expires.isoformat() if user.vip_expires else None,
}


# === /register_location: добавление новой локации ===

@app.post("/register_location")
def register_location(
name: str, city: str, camera_id: str, rtsp_url: str, db: Session = Depends(get_db)
):
loc = Location(
name=name,
city=city,
camera_id=camera_id,
rtsp_url=rtsp_url,
active=True,
)
db.add(loc)
db.commit()
db.refresh(loc)
return {"status": "ok", "location_id": loc.id}


# === /trigger_clip: получение 30‑секундного клипа ===

@app.post("/trigger_clip")
async def trigger_clip(request: Request, db: Session = Depends(get_db)):
payload = await request.json()
user_id = payload.get("user_id")
location_id = payload.get("location_id")
# pay флаг пока не обязателен, используется для различения логики
pay = payload.get("pay", False)

user = db.query(User).filter(User.id == user_id).first()
if user is None:
raise HTTPException(status_code=404, detail="User not found")

loc = (
db.query(Location)
.filter(Location.id == location_id, Location.active == True)
.first()
)
if loc is None:
raise HTTPException(status_code=404, detail="Location not found")

# 1. снимаем raw 30‑секундный клип из RTSP
raw_clip = OUTPUT_DIR / f"{location_id}_{user_id}_{uuid.uuid4().hex}.raw.mp4"
cmd = [
"ffmpeg",
"-y",
"-rtsp_transport",
"tcp",
"-i",
loc.rtsp_url,
"-t",
str(CLIP_SECONDS),
"-c",
"copy",
str(raw_clip),
]
try:
subprocess.run(cmd, check=True, capture_output=True, text=True)
except subprocess.CalledProcessError as e:
# логгируй ошибку в логи Render, чтобы легче отлаживать
raise HTTPException(status_code=500, detail=f"FFmpeg error: {e.stderr}")

# 2. определяем, нужен ли водяной знак
has_watermark = True
if user.has_premium and user.premium_expires and user.premium_expires >= datetime.utcnow():
has_watermark = False
elif user.has_vip and user.vip_expires and user.vip_expires >= datetime.utcnow():
has_watermark = False
elif user.free_clips_count < 5:
has_watermark = False
else:
# использовать watermark и увеличить счётчик
user.free_clips_count += 1
db.commit()

# 3. добавляем водяной знак, если нужно
if has_watermark:
wm_clip = OUTPUT_DIR / raw_clip.name.replace(".raw.mp4", "_wm.mp4")
# простой пример водяного знака
cmd_wm = [
"ffmpeg",
"-y",
"-i",
str(raw_clip),
"-vf",
"drawtext=text='PADEL REPLAY FREE':fontcolor=white:fontsize=24:x=10:y=10",
"-c:a",
"copy",
str(wm_clip),
]
subprocess.run(cmd_wm, check=True, capture_output=True, text=True)
video_url = f"https://storage.yourdomain.com/clips/{wm_clip.name}"
else:
video_url = f"https://storage.yourdomain.com/clips/{raw_clip.name}"

# 4. сохраняем запись в бд
clip = Clip(
user_id=user_id,
location_id=location_id,
video_url=video_url,
has_watermark=has_watermark,
paid=pay,
)
db.add(clip)
db.commit()

# 5. формируем остаток бесплатных клипов
if user.has_premium:
free_remaining = "∞"
else:
free_remaining = max(0, 5 - user.free_clips_count)

return {
"status": "ok",
"video_url": video_url,
"has_watermark": has_watermark,
"free_clips_remaining": free_remaining,
"clip_id": clip.id,
}


# === Заглушка платежей через СБП (single / unlimited / vip) ===

def create_sbp_payment(amount: float, user_id: int, payment_type: str) -> str:
# В реальном мире здесь интеграция с Tinkoff, YooKassa, Robokassa и т.п.
# сейчас просто возвращаем URL
base_url = PAYMENT_CALLBACK_URL.rstrip("/")
return f"{base_url}/payment?amount={amount}&user_id={user_id}&type={payment_type}"


@app.post("/payment/single")
async def payment_single(request: Request, db: Session = Depends(get_db)):
body = await request.json()
user_id = body.get("user_id")
user = db.query(User).filter(User.id == user_id).first()
if user is None:
raise HTTPException(status_code=404, detail="User not found")

url = create_sbp_payment(50, user_id, "single")
return {"status": "ok", "payment_url": url, "amount": 50, "user_id": user_id}


@app.post("/payment/unlimited")
async def payment_unlimited(request: Request, db: Session = Depends(get_db)):
body = await request.json()
user_id = body.get("user_id")
amount = 400.0
user = db.query(User).filter(User.id == user_id).first()
if user is None:
raise HTTPException(status_code=404, detail="User not found")

user.has_premium = True
user.premium_expires = datetime.utcnow() + timedelta(days=30)
db.commit()

url = create_sbp_payment(amount, user_id, "unlimited")
p = Payment(user_id=user_id, amount=amount, type="unlimited")
db.add(p)
db.commit()

return {
"status": "ok",
"payment_url": url,
"amount": amount,
"user_id": user_id,
"has_premium": True,
}


@app.post("/payment/vip")
async def payment_vip(request: Request, db: Session = Depends(get_db)):
body = await request.json()
user_id = body.get("user_id")
amount = 650.0
user = db.query(User).filter(User.id == user_id).first()
if user is None:
raise HTTPException(status_code=404, detail="User not found")

user.has_vip = True
user.vip_expires = datetime.utcnow() + timedelta(days=30)
db.commit()

url = create_sbp_payment(amount, user_id, "vip")
p = Payment(user_id=user_id, amount=amount, type="vip")
db.add(p)
db.commit()

return {
"status": "ok",
"payment_url": url,
"amount": amount,
"user_id": user_id,
"has_vip": True,
}


# === /payment/verify: коллбек от провайдера (пример) ===

@app.post("/payment/verify")
async def verify_payment_callback(request: Request, db: Session = Depends(get_db)):
# в реальности этот эндпоинт должен принимать и валидировать callback от эквайера
body = await request.json()
payment_id = body.get("payment_id")
user_id = body.get("user_id")

# имитация успешной оплаты (в реальности сверяется с провайдером)
if payment_id and user_id:
user = db.query(User).filter(User.id == user_id).first()
if user:
user.premium_expires = datetime.utcnow() + timedelta(days=30)
user.has_premium = True
user.has_vip = True
db.commit()
return {"status": "ok", "has_premium": True, "has_vip": True}
raise HTTPException(status_code=400, detail="Payment verification failed")


# === /feed: список последних клипов (для экрана "Хранение видео") ===

@app.get("/feed")
async def get_feed(db: Session = Depends(get_db)):
# только за последние несколько часов, чтобы не грузить старое
one_hour_ago = datetime.utcnow() - timedelta(hours=1)
clips = (
db.query(Clip).filter(Clip.created_at >= one_hour_ago).order_by(Clip.created_at.desc()).limit(50).all()
)
return {
"clips": [
{
"clip_id": c.id,
"video_url": c.video_url,
"location_name": c.location.name,
"has_watermark": c.has_watermark,
"created_at": c.created_at.isoformat(),
}
for c in clips
]
}


# === /health: служебный эндпоинт для проверки работы сервиса ===

@app.get("/health")
async def health():
return {"status": "ok"}