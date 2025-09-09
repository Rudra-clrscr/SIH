from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

# --- Database Models ---

class Tourist(db.Model):
    """Represents a tourist with their digital ID."""
    id = db.Column(db.Integer, primary_key=True)
    digital_id = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    kyc_id = db.Column(db.String(50), unique=True, nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    kyc_type = db.Column(db.String(20), nullable=False)
    registration_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    visit_end_date = db.Column(db.DateTime, nullable=False)
    safety_score = db.Column(db.Integer, default=100)
    last_known_location = db.Column(db.String(200), default='N/A')
    
    # This timestamp is crucial for detecting inactivity. It updates automatically on record change.
    last_updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    alerts = db.relationship('Alert', backref='tourist', lazy=True, cascade="all, delete-orphan")
    anomalies = db.relationship('Anomaly', backref='tourist', lazy=True, cascade="all, delete-orphan")

class Alert(db.Model):
    """Represents alerts triggered by tourists (e.g., Panic Button)."""
    id = db.Column(db.Integer, primary_key=True)
    tourist_id = db.Column(db.Integer, db.ForeignKey('tourist.id'), nullable=False)
    location = db.Column(db.String(200), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    alert_type = db.Column(db.String(50), default='Panic Button')

class SafetyZone(db.Model):
    """Represents a pre-defined geographical zone with a safety score."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    radius = db.Column(db.Float, nullable=False) # Radius in kilometers
    regional_score = db.Column(db.Integer, nullable=False)

class Anomaly(db.Model):
    """Represents an anomaly detected by the AI model."""
    id = db.Column(db.Integer, primary_key=True)
    tourist_id = db.Column(db.Integer, db.ForeignKey('tourist.id'), nullable=False)
    anomaly_type = db.Column(db.String(100), nullable=False) # e.g., 'Prolonged Inactivity'
    description = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
