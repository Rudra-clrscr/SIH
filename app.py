import os
import threading
from dotenv import load_dotenv
load_dotenv()
import time
import random
import hashlib
from datetime import datetime, timedelta
from math import radians, sin, cos, sqrt, atan2

import numpy as np
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from sklearn.ensemble import IsolationForest

# --- NEW: Twilio Imports ---
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

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



# --- NEW: Twilio Configuration ---
# Get your credentials from the Twilio console: https://www.twilio.com/console
# It is highly recommended to set these as environment variables for security.
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


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
        CRITICAL_THRESHOLD = 1200 # 20 minutes
        WARNING_THRESHOLD = 600   # 10 minutes

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
                alert_type = "Warning Inactivity (10+ min)"
                ten_minutes_ago = now - timedelta(minutes=10)
                if not Anomaly.query.filter(Anomaly.tourist_id == tourist.id, Anomaly.timestamp > ten_minutes_ago).first():
                    desc = f"Warning inactivity detected. Last update was {inactivity_seconds/60:.1f} minutes ago."
                    db.session.add(Anomaly(tourist_id=tourist.id, anomaly_type=alert_type, description=desc))
                    print(f"WARNING ANOMALY LOGGED for {tourist.name}")

        print("="*50 + "\n")
        db.session.commit()

# --- Helper Function for Distance ---
def haversine(lat1, lon1, lat2, lon2):
    R = 6371 # Earth radius in kilometers
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
# --- MODIFIED: OTP Endpoint ---
@app.route('/api/send_otp', methods=['POST'])
def send_otp():
    data = request.get_json()
    phone = data.get('phone')
    if not phone:
        return jsonify({'error': 'Phone number is required.'}), 400
    
    # Ensure phone number is in E.164 format (e.g., +919999988888)
    if not phone.startswith('+'):
        return jsonify({'error': 'Phone number must be in E.164 format (e.g., +91xxxxxxxxxx).'}), 400

    otp = str(random.randint(100000, 999999))
    otp_storage[phone] = {'otp': otp, 'timestamp': datetime.utcnow()}
    
    try:
        message = twilio_client.messages.create(
            body=f"Your Astra verification code is: {otp}",
            from_=TWILIO_PHONE_NUMBER,
            to=phone
        )
        print(f"OTP SMS sent to {phone} via Twilio. SID: {message.sid}")
        return jsonify({'message': 'OTP sent successfully.'}), 200
    except TwilioRestException as e:
        print(f"Twilio Error: {e}")
        # In case of error, you might not want to expose the exact Twilio error to the client.
        return jsonify({'error': 'Failed to send OTP. Please check the phone number or server configuration.'}), 500
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return jsonify({'error': 'An internal server error occurred.'}), 500

@app.route('/api/verify_otp', methods=['POST'])
def verify_otp():
    data = request.get_json()
    phone = data.get('phone')
    otp_attempt = data.get('otp')

    if phone not in otp_storage:
        return jsonify({'error': 'OTP not requested or has expired.'}), 404

    otp_info = otp_storage[phone]
    if datetime.utcnow() > otp_info['timestamp'] + timedelta(minutes=5):
        del otp_storage[phone]
        return jsonify({'error': 'OTP has expired.'}), 410

    if otp_info['otp'] == otp_attempt:
        del otp_storage[phone]
        return jsonify({'message': 'OTP verified successfully.'}), 200
    else:
        return jsonify({'error': 'Invalid OTP.'}), 400

@app.route('/api/login', methods=['POST'])
def login_user():
    data = request.get_json()
    phone = data.get('phone')
    tourist = Tourist.query.filter_by(phone=phone).first()
    if tourist:
        session['tourist_id'] = tourist.id
        return jsonify({'message': 'Login successful'}), 200
    return jsonify({'error': 'Invalid phone number'}), 401

@app.route('/api/logout')
def logout_user():
    session.clear()
    return redirect(url_for('home'))
    
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
    tourist.last_updated_at = datetime.utcnow()
    
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
    tourist.safety_score = 0
    db.session.commit()
    
    return jsonify({'message': 'Panic alert successfully registered.'}), 200

@app.route('/api/safety_zones')
def get_safety_zones():
    zones = SafetyZone.query.all()
    return jsonify({'safety_zones': [{'name': z.name, 'latitude': z.latitude, 'longitude': z.longitude, 'radius': z.radius, 'regional_score': z.regional_score} for z in zones]})

@app.route('/api/dashboard/tourists')
def get_tourists_data():
    tourists = Tourist.query.all()
    return jsonify({'tourists': [{'id': t.id, 'name': t.name, 'phone': t.phone, 'safety_score': t.safety_score, 'last_known_location': t.last_known_location} for t in tourists]})

@app.route('/api/dashboard/alerts')
def get_alerts_data():
    alerts = Alert.query.order_by(Alert.timestamp.desc()).limit(50).all()
    return jsonify({'alerts': [{'tourist_name': a.tourist.name, 'alert_type': a.alert_type, 'location': a.location, 'timestamp': a.timestamp.strftime('%d-%b-%Y %H:%M:%S')} for a in alerts]})

@app.route('/api/dashboard/anomalies')
def get_anomalies_data():
    anomalies = Anomaly.query.filter_by(status='active').order_by(Anomaly.timestamp.desc()).limit(50).all()
    result = [{'tourist_name': a.tourist.name, 'anomaly_type': a.anomaly_type, 'description': a.description, 'timestamp': a.timestamp.strftime('%d-%b-%Y %H:%M:%S')} for a in anomalies]
    return jsonify({'anomalies': result})

def add_initial_data():
    """Adds a comprehensive list of initial safety zones for India."""
    with app.app_context():
        if SafetyZone.query.count() == 0:
            db.session.bulk_save_objects([
                # === High-Alert & Conflict Zones ===
                SafetyZone(name='High-Alert: Zone near LoC', latitude=34.5266, longitude=74.4735, radius=30, regional_score=5),
                SafetyZone(name='High-Risk: Remote Southern Valley (J&K)', latitude=33.7294, longitude=74.83, radius=25, regional_score=15),
                SafetyZone(name='High-Alert: India-China Border Area (Northeast)', latitude=27.9881, longitude=88.8250, radius=40, regional_score=10),

                # === High Tourist Risk Zones (Scams, Crowds, etc.) ===
                SafetyZone(name='Paharganj Area, Delhi', latitude=28.6439, longitude=77.2124, radius=20, regional_score=45),
                SafetyZone(name='Baga Beach Area (Night), Goa', latitude=15.5562, longitude=73.7547, radius=30, regional_score=55),
                SafetyZone(name='Sudder Street Area, Kolkata', latitude=22.5608, longitude=88.3520, radius=30, regional_score=50),
                SafetyZone(name='Isolated Ghats, Varanasi', latitude=25.2820, longitude=82.9563, radius=50, regional_score=60),

                # === North India ===
                SafetyZone(name='Srinagar (Dal Lake Area)', latitude=34.0837, longitude=74.7973, radius=50, regional_score=85),
                SafetyZone(name='Leh City, Ladakh', latitude=34.1650, longitude=77.5771, radius=120, regional_score=95),
                SafetyZone(name='Lutyens\' Delhi', latitude=28.6139, longitude=77.2090, radius=50, regional_score=98),
                SafetyZone(name='The Ridge, Shimla', latitude=31.1048, longitude=77.1734, radius=30, regional_score=94),
                SafetyZone(name='Pink City, Jaipur', latitude=26.9124, longitude=75.7873, radius=40, regional_score=90),
                SafetyZone(name='Golden Temple, Amritsar', latitude=31.6200, longitude=74.8765, radius=20, regional_score=96),

                # === Uttar Pradesh & Bareilly ===
                SafetyZone(name='Taj Mahal Complex, Agra', latitude=27.1751, longitude=78.0421, radius=20, regional_score=98),
                SafetyZone(name='Hazratganj, Lucknow', latitude=26.8467, longitude=80.9462, radius=20, regional_score=88),
                # Bareilly (Within)
                SafetyZone(name='Bareilly Cantt', latitude=28.3490, longitude=79.4260, radius=4, regional_score=99),
                SafetyZone(name='IVRI Campus, Bareilly', latitude=28.3649, longitude=79.4143, radius=30, regional_score=95),
                SafetyZone(name='Civil Lines, Bareilly', latitude=28.3540, longitude=79.4310, radius=20, regional_score=88),
                SafetyZone(name='Ala Hazrat Dargah, Bareilly', latitude=28.3586, longitude=79.4211, radius=30, regional_score=92),
                SafetyZone(name='Bareilly Old City Area', latitude=28.3680, longitude=79.4150, radius=30, regional_score=60),
                # Bareilly (Around)
                SafetyZone(name='Pilibhit Tiger Reserve', latitude=28.6333, longitude=79.8000, radius=20, regional_score=50),
                SafetyZone(name='Aonla Industrial Area', latitude=28.2778, longitude=79.1633, radius=50, regional_score=65),

                # === West India ===
                SafetyZone(name='South Mumbai', latitude=18.9220, longitude=72.8347, radius=50, regional_score=95),
                SafetyZone(name='Gir National Park, Gujarat', latitude=21.2849, longitude=70.7937, radius=25, regional_score=50),
                SafetyZone(name='Ahmedabad Old City', latitude=23.0225, longitude=72.5714, radius=40, regional_score=85),
                
                # === South India ===
                SafetyZone(name='Hitech City, Hyderabad', latitude=17.4435, longitude=78.3519, radius=50, regional_score=92),
                SafetyZone(name='Munnar Tea Gardens, Kerala', latitude=10.0889, longitude=77.0595, radius=50, regional_score=88),
                SafetyZone(name='Hampi Ruins, Karnataka', latitude=15.3350, longitude=76.4600, radius=50, regional_score=75),
                
                # === East India ===
                SafetyZone(name='Park Street, Kolkata', latitude=22.5529, longitude=88.3542, radius=50, regional_score=87),
                SafetyZone(name='Bodh Gaya, Bihar', latitude=24.6961, longitude=84.9912, radius=50, regional_score=92),
                SafetyZone(name='Puri Beach, Odisha', latitude=19.8055, longitude=85.8275, radius=50, regional_score=70)
            ])
            db.session.commit()
            print("Added comprehensive initial safety zones for India.")

# --- Deployment-Ready Additions ---
with app.app_context():
    db.create_all()
    add_initial_data()

# Endpoint for external cron job to call
@app.route('/cron/run-anomaly-check/<secret_key>')
def run_anomaly_check_cron(secret_key):
    cron_secret = os.environ.get('CRON_SECRET_KEY')
    
    
    if not cron_secret or secret_key != cron_secret:
        return jsonify({'error': 'Unauthorized'}), 401
    
    check_for_anomalies()
    return jsonify({'message': 'Anomaly check successfully initiated.'}), 200

# --- NEW FUNCTION TO RUN THE SERVER ---
def run_server():
    """Function to run the Flask app, callable from another script."""
    # NOTE: debug=False is recommended when packaging
    app.run(host='0.0.0.0', port=5000, debug=False)


# This block is for local development only.
if __name__ == '__main__':
    def anomaly_checker_loop():
        while True:
            with app.app_context():
                check_for_anomalies()
            time.sleep(300) # Run every 5 minutes

    anomaly_thread = threading.Thread(target=anomaly_checker_loop, daemon=True)
    anomaly_thread.start()
    
    # Call the new run function
    run_server()