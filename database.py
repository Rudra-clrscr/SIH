from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

db = SQLAlchemy()

class Tourist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    digital_id = db.Column(db.String(128), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    kyc_id = db.Column(db.String(50), unique=True, nullable=False)
    kyc_type = db.Column(db.String(50), nullable=False)
    visit_end_date = db.Column(db.DateTime, nullable=False)
    safety_score = db.Column(db.Integer, default=100)
    last_known_location = db.Column(db.String(100), default='Not Available')
    registration_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    alerts = relationship("Alert", back_populates="tourist")
    anomalies = relationship("Anomaly", back_populates="tourist")

class SafetyZone(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    radius = db.Column(db.Float, nullable=False) # Radius in kilometers
    regional_score = db.Column(db.Integer, nullable=False)

class Alert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tourist_id = db.Column(db.Integer, ForeignKey('tourist.id'), nullable=False)
    location = db.Column(db.String(100))
    alert_type = db.Column(db.String(100))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    tourist = relationship("Tourist", back_populates="alerts")

class Anomaly(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tourist_id = db.Column(db.Integer, ForeignKey('tourist.id'), nullable=False)
    anomaly_type = db.Column(db.String(100))
    description = db.Column(db.String(255))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='active') # active, resolved
    
    tourist = relationship("Tourist", back_populates="anomalies")