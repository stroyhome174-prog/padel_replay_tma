from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

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
amount = Column(Integer, nullable=False)
type = Column(String) # "single", "unlimited", "vip"
paid_at = Column(DateTime, default=datetime.utcnow)
user = relationship("User")
