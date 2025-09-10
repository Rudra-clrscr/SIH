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
app.secret_key = 'your_super_secret_key' 
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tourist_data.db'
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
    # Updated to modern syntax to fix LegacyAPIWarning
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
    # Updated to modern syntax to fix LegacyAPIWarning
    tourist = db.session.get(Tourist, session['tourist_id'])
    
    if not tourist: return jsonify({'error': 'Tourist not found'}), 404

    # New logic to resolve any active anomalies for this user
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
            tourist.safety_score += 1

    db.session.commit()
    return jsonify({'message': 'Location updated', 'safety_score': tourist.safety_score}), 200

@app.route('/api/panic', methods=['POST'])
def trigger_panic_alert():
    if 'tourist_id' not in session: return jsonify({'error': 'Not authenticated'}), 401
    # Updated to modern syntax to fix LegacyAPIWarning
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
    # This now only fetches anomalies with an 'active' status
    anomalies = Anomaly.query.filter_by(status='active').order_by(Anomaly.timestamp.desc()).limit(50).all()
    result = [{
        'tourist_name': a.tourist.name,
        'anomaly_type': a.anomaly_type,
        'description': a.description,
        'timestamp': a.timestamp.strftime('%d-%b-%Y %H:%M:%S')
    } for a in anomalies]
    return jsonify({'anomalies': result})

@app.route('/api/send_otp', methods=['POST'])
def send_otp():
    phone = request.get_json().get('phone')
    if not phone: return jsonify({'error': 'Phone number is required.'}), 400
    otp = str(random.randint(100000, 999999))
    otp_storage[phone] = otp
    print(f"--- OTP for {phone}: {otp} ---")
    return jsonify({'message': 'OTP sent.'}), 200

@app.route('/api/verify_otp', methods=['POST'])
def verify_otp():
    data = request.get_json()
    if otp_storage.get(data.get('phone')) == data.get('otp'):
        del otp_storage[data.get('phone')]
        return jsonify({'message': 'OTP verified.'}), 200
    return jsonify({'error': 'Invalid OTP.'}), 400

@app.route('/api/login_phone', methods=['POST'])
def login_with_phone():
    tourist = Tourist.query.filter_by(phone=request.get_json().get('phone')).first()
    if tourist:
        session['tourist_id'] = tourist.id
        return jsonify({'message': 'Login successful'}), 200
    return jsonify({'error': 'Account not found.'}), 404

@app.route('/api/logout')
def logout():
    session.pop('tourist_id', None)
    return redirect(url_for('home'))

def add_initial_data():
    """Adds initial safety zones for Uttar Pradesh."""
    if SafetyZone.query.count() == 0:
        db.session.bulk_save_objects([
            # === Agra Zones ===
            SafetyZone(name='Taj Mahal Complex', latitude=27.1751, longitude=78.0421, radius=2, regional_score=98),
            SafetyZone(name='Agra Fort Area', latitude=27.1795, longitude=78.0211, radius=2.5, regional_score=95),
            SafetyZone(name='Fatehpur Sikri', latitude=27.0945, longitude=77.6631, radius=5, regional_score=75),
            SafetyZone(name='Chambal Ravine Outskirts', latitude=26.8500, longitude=78.3500, radius=15, regional_score=20),
            
            # === Bareilly Zones (NEW) ===
            SafetyZone(name='Bareilly Cantt', latitude=28.3490, longitude=79.4260, radius=4, regional_score=99),
            SafetyZone(name='Phoenix United Mall, Bareilly', latitude=28.3984, longitude=79.4312, radius=2, regional_score=94),
            SafetyZone(name='Ala Hazrat Dargah', latitude=28.3586, longitude=79.4211, radius=1.5, regional_score=92),
            SafetyZone(name='Bareilly Old City Area', latitude=28.3680, longitude=79.4150, radius=3, regional_score=60),
            SafetyZone(name='Ramganga River Floodplain', latitude=28.3300, longitude=79.3800, radius=5, regional_score=35),
            
            # === Other Uttar Pradesh Zones (NEW) ===
            SafetyZone(name='Ram Janmabhoomi, Ayodhya', latitude=26.7956, longitude=82.1943, radius=10, regional_score=96),
            SafetyZone(name='Kashi Vishwanath, Varanasi', latitude=25.3109, longitude=83.0107, radius=10, regional_score=95),
            SafetyZone(name='Hazratganj, Lucknow', latitude=26.8467, longitude=80.9462, radius=10, regional_score=88),
            SafetyZone(name='Dudhwa National Park', latitude=28.4892, longitude=80.6488, radius=20, regional_score=50),
            SafetyZone(name='Sangam Area, Prayagraj', latitude=25.4213, longitude=81.8891, radius=10, regional_score=85)
        ])
        db.session.commit()
        print("Added initial safety zones for Uttar Pradesh.")

def run_anomaly_detection_service():
    """Wrapper function to run the anomaly check in a loop."""
    while True:
        time.sleep(30) # Wait for 30 seconds for faster testing
        check_for_anomalies()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        add_initial_data()
    
    anomaly_thread = threading.Thread(target=run_anomaly_detection_service, daemon=True)
    anomaly_thread.start()
    
    # Use threaded=True to handle background tasks gracefully
    app.run(debug=True, port=15000, threaded=True)