from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Initialize SQLAlchemy instance.
# This will be linked to the Flask app in the main application file.
db = SQLAlchemy()

# --- Database Models ---

class Tourist(db.Model):
    """Represents a tourist with their digital ID."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    kyc_id = db.Column(db.String(50), unique=True, nullable=False) # Aadhaar or Passport
    email = db.Column(db.String(120), unique=True, nullable=False) # Changed from phone to email
    kyc_type = db.Column(db.String(20), nullable=False)
    visit_start_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    visit_end_date = db.Column(db.DateTime, nullable=False)
    safety_score = db.Column(db.Integer, default=100) # Default safety score
    last_known_location = db.Column(db.String(200), default='N/A')
    is_active = db.Column(db.Boolean, default=True)

    itineraries = db.relationship('Itinerary', backref='tourist', lazy=True, cascade="all, delete-orphan")
    emergency_contacts = db.relationship('EmergencyContact', backref='tourist', lazy=True, cascade="all, delete-orphan")

class Itinerary(db.Model):
    """Represents the planned itinerary for a tourist."""
    id = db.Column(db.Integer, primary_key=True)
    location = db.Column(db.String(200), nullable=False)
    planned_date = db.Column(db.DateTime, nullable=False)
    tourist_id = db.Column(db.Integer, db.ForeignKey('tourist.id'), nullable=False)

class EmergencyContact(db.Model):
    """Represents an emergency contact for a tourist."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    relation = db.Column(db.String(50))
    tourist_id = db.Column(db.Integer, db.ForeignKey('tourist.id'), nullable=False)

class Alert(db.Model):
    """Represents alerts triggered by tourists."""
    id = db.Column(db.Integer, primary_key=True)
    tourist_id = db.Column(db.Integer, db.ForeignKey('tourist.id'), nullable=False)
    location = db.Column(db.String(200), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    alert_type = db.Column(db.String(50), default='Panic Button') # e.g., Panic Button, Anomaly
    tourist = db.relationship('Tourist', backref='alerts')
