import os
import threading
import time
import random
import hashlib
from datetime import datetime, timedelta
from math import radians, sin, cos, sqrt, atan2

import numpy as np
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from sklearn.ensemble import IsolationForest

# Import database objects from the separate database.py file
from database import db, Tourist, SafetyZone, Alert, Anomaly

# --- App Configuration ---
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your_super_secret_key')

# Use environment variable for database URL in production, but fall back to SQLite for local development
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///tourist_data.db')
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# --- AI Anomaly Detection Function ---
def check_for_anomalies():
    """Checks for tourists who have crossed inactivity time thresholds."""
    with app.app_context():
        now = datetime.utcnow()
        active_tourists = Tourist.query.filter(Tourist.visit_end_date > now).all()

        if not active_tourists:
            return

        print("\n" + "="*50)
        print(f"Running Threshold Check at: {now.strftime('%Y-%m-%d %H:%M:%S')}")

        # Define thresholds in seconds
        CRITICAL_THRESHOLD = 600  
        WARNING_THRESHOLD = 300   

        for tourist in active_tourists:
            inactivity_seconds = (now - tourist.last_updated_at).total_seconds()
            print(f"  - Checking {tourist.name}: Inactivity = {inactivity_seconds:.0f} seconds")

            if inactivity_seconds > CRITICAL_THRESHOLD:
                alert_type = "Critical Inactivity (20+ min)"
                ten_minutes_ago = now - timedelta(minutes=10)
                if not Anomaly.query.filter(Anomaly.tourist_id == tourist.id, Anomaly.timestamp > ten_minutes_ago).first():
                    desc = f"Critical inactivity detected. Last update was {inactivity_seconds/60:.1f} minutes ago."
                    db.session.add(Anomaly(tourist_id=tourist.id, anomaly_type=alert_type, description=desc))
                    print(f"CRITICAL ANOMALY LOGGED for {tourist.name}")

            elif inactivity_seconds > WARNING_THRESHOLD:
                alert_type = "Warning Inactivity "
                ten_minutes_ago = now - timedelta(minutes=10)
                if not Anomaly.query.filter(Anomaly.tourist_id == tourist.id, Anomaly.timestamp > ten_minutes_ago).first():
                    desc = f"Warning inactivity detected. Last update was {inactivity_seconds/60:.1f} minutes ago."
                    db.session.add(Anomaly(tourist_id=tourist.id, anomaly_type=alert_type, description=desc))
                    print(f"WARNING ANOMALY LOGGED for {tourist.name}")

        print("="*50 + "\n")
        db.session.commit()

# --- Helper Function for Distance ---
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    lat1_rad, lon1_rad, lat2_rad, lon2_rad = map(radians, [lat1, lon1, lat2, lon2])
    dlon, dlat = lon2_rad - lon1_rad, lat2_rad - lat1_rad
    a = sin(dlat / 2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

# --- In-memory OTP storage ---
otp_storage = {}

# --- HTML Page Routes ---
@app.route('/')
def home(): return render_template('home.html')

@app.route('/register')
def register_page(): return render_template('register.html')

@app.route('/login')
def login_page(): return render_template('login.html')

@app.route('/user_dashboard')
def user_dashboard():
    if 'tourist_id' not in session: return redirect(url_for('login_page'))
    tourist = db.session.get(Tourist, session['tourist_id'])
    if not tourist:
        session.clear()
        return redirect(url_for('login_page'))
    return render_template('user_dashboard.html', tourist=tourist)

@app.route('/dashboard')
def admin_dashboard(): return render_template('dashboard.html')

# --- API Endpoints ---
@app.route('/api/register', methods=['POST'])
def register_user():
    data = request.get_json()
    if Tourist.query.filter((Tourist.phone == data['phone']) | (Tourist.kyc_id == data['kyc_id'])).first():
        return jsonify({'error': 'Phone or KYC ID already registered.'}), 409
    end_date = datetime.utcnow() + timedelta(days=int(data['visit_duration_days']))
    unique_string = f"{data['name']}:{data['kyc_id']}:{datetime.utcnow()}"
    hex_dig = hashlib.sha256(unique_string.encode()).hexdigest()
    new_tourist = Tourist(digital_id=hex_dig, name=data['name'], phone=data['phone'], kyc_id=data['kyc_id'], kyc_type=data['kyc_type'], visit_end_date=end_date)
    db.session.add(new_tourist)
    db.session.commit()
    session['tourist_id'] = new_tourist.id
    return jsonify({'message': 'Registration successful.'}), 201

@app.route('/api/update_location', methods=['POST'])
def update_location():
    if 'tourist_id' not in session: return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.get_json()
    lat, lon = data.get('latitude'), data.get('longitude')
    tourist = db.session.get(Tourist, session['tourist_id'])
    
    if not tourist: return jsonify({'error': 'Tourist not found'}), 404

    active_anomalies = Anomaly.query.filter_by(tourist_id=tourist.id, status='active').all()
    if active_anomalies:
        for anomaly in active_anomalies:
            anomaly.status = 'resolved'
        print(f"Resolved {len(active_anomalies)} active anomalies for tourist {tourist.name}.")

    tourist.last_known_location = f"Lat: {lat}, Lon: {lon}"
    
    current_zone_score = None
    for zone in SafetyZone.query.all():
        if haversine(lat, lon, zone.latitude, zone.longitude) <= zone.radius:
            if current_zone_score is None or zone.regional_score < current_zone_score:
                current_zone_score = zone.regional_score

            if zone.regional_score < 40:
                ten_minutes_ago = datetime.utcnow() - timedelta(minutes=10)
                if not Alert.query.filter(Alert.tourist_id == tourist.id, Alert.alert_type.like('%Geo-fence Breach%'), Alert.timestamp > ten_minutes_ago).first():
                    db.session.add(Alert(tourist_id=tourist.id, location=tourist.last_known_location, alert_type=f"Geo-fence Breach: Entered {zone.name}"))

    if current_zone_score is not None:
        if current_zone_score < tourist.safety_score:
            tourist.safety_score = current_zone_score
        elif current_zone_score > 80 and tourist.safety_score < 100:
            tourist.safety_score = min(100, tourist.safety_score + 1)

    db.session.commit()
    return jsonify({'message': 'Location updated', 'safety_score': tourist.safety_score}), 200

@app.route('/api/panic', methods=['POST'])
def trigger_panic_alert():
    if 'tourist_id' not in session: return jsonify({'error': 'Not authenticated'}), 401
    tourist = db.session.get(Tourist, session['tourist_id'])
    if not tourist: return jsonify({'error': 'Tourist not found'}), 404
    new_alert = Alert(tourist_id=tourist.id, location=tourist.last_known_location, alert_type='Panic Button')
    db.session.add(new_alert)
    db.session.commit()
    return jsonify({'message': 'Panic alert successfully registered.'}), 200

@app.route('/api/safety_zones')
def get_safety_zones():
    return jsonify({'safety_zones': [{'name': z.name, 'latitude': z.latitude, 'longitude': z.longitude, 'radius': z.radius, 'regional_score': z.regional_score} for z in SafetyZone.query.all()]})

@app.route('/api/dashboard/tourists')
def get_tourists_data():
    return jsonify({'tourists': [{'id': t.id, 'name': t.name, 'phone': t.phone, 'safety_score': t.safety_score, 'last_known_location': t.last_known_location} for t in Tourist.query.all()]})

@app.route('/api/dashboard/alerts')
def get_alerts_data():
    alerts = Alert.query.order_by(Alert.timestamp.desc()).limit(50).all()
    return jsonify({'alerts': [{'tourist_name': a.tourist.name, 'alert_type': a.alert_type, 'location': a.location, 'timestamp': a.timestamp.strftime('%d-%b-%Y %H:%M:%S')} for a in alerts]})

@app.route('/api/dashboard/anomalies')
def get_anomalies_data():
    anomalies = Anomaly.query.filter_by(status='active').order_by(Anomaly.timestamp.desc()).limit(50).all()
    result = [{'tourist_name': a.tourist.name, 'anomaly_type': a.anomaly_type, 'description': a.description, 'timestamp': a.timestamp.strftime('%d-%b-%Y %H:%M:%S')} for a in anomalies]
    return jsonify({'anomalies': result})

# ... (other API routes like OTP and login remain the same) ...

def add_initial_data():
    """Adds initial safety zones for all of India."""
    with app.app_context():
        if SafetyZone.query.count() == 0:
            db.session.bulk_save_objects([
            # === Jammu & Kashmir ===
            SafetyZone(name='High-Alert: Zone near LoC', latitude=34.5266, longitude=74.4735, radius=30, regional_score=5),
            SafetyZone(name='High-Risk: Remote Southern Valley', latitude=33.7294, longitude=74.83, radius=25, regional_score=15),
            SafetyZone(name='Srinagar (Dal Lake Area)', latitude=34.0837, longitude=74.7973, radius=10, regional_score=85),
            SafetyZone(name='Vaishno Devi Shrine, Katra', latitude=33.0298, longitude=74.9482, radius=8, regional_score=98),
            SafetyZone(name='Leh City, Ladakh', latitude=34.1650, longitude=77.5771, radius=12, regional_score=95),
            # === High-Alert & Restricted Zones ===
            SafetyZone(name='High-Alert: Cross-Border Area', latitude=29.5000, longitude=80.2000, radius=50, regional_score=5),
            SafetyZone(name='High-Risk: Remote Insurgency Zone', latitude=24.5000, longitude=83.0000, radius=40, regional_score=10),
            # === North India ===
            SafetyZone(name='Lutyens\' Delhi', latitude=28.6139, longitude=77.2090, radius=5, regional_score=98),
            SafetyZone(name='The Ridge, Shimla', latitude=31.1048, longitude=77.1734, radius=3, regional_score=94),
            SafetyZone(name='Pink City, Jaipur', latitude=26.9124, longitude=75.7873, radius=4, regional_score=90),
            # === Uttar Pradesh ===
            SafetyZone(name='Taj Mahal Complex', latitude=27.1751, longitude=78.0421, radius=2, regional_score=98),
            # ... (all other zones from previous version)
        ])
            db.session.commit()
            print("Added initial safety zones for all of India, including J&K.")


# --- DEPLOYMENT-READY ADDITIONS ---

# Create database tables and initial data if the app is run directly
# In a production environment like Render, this might be handled by a separate setup script.
with app.app_context():
    db.create_all()
    add_initial_data()

# Endpoint for external cron job to call
@app.route('/cron/run-anomaly-check/<secret_key>')
def run_anomaly_check_cron(secret_key):
    # Use a secret key from environment variables to prevent abuse
    cron_secret = os.environ.get('CRON_SECRET_KEY')
    if not cron_secret or secret_key != cron_secret:
        return jsonify({'error': 'Unauthorized'}), 401
    
    check_for_anomalies()
    return jsonify({'message': 'Anomaly check successfully initiated.'}), 200


# This block is for local development only.
# gunicorn (used by Render) will run the 'app' object directly.
if __name__ == '__main__':
    # Start the anomaly detection in a separate thread for local testing
    anomaly_thread = threading.Thread(target=check_for_anomalies, daemon=True)
    anomaly_thread.start()
    app.run(debug=True, port=15000)