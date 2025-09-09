import os
import uuid
import random
import math
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from datetime import datetime, timedelta
from database import db, Tourist, Itinerary, EmergencyContact, Alert, SafetyZone

# Initialize Flask App
app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))

# Configure Database & Session
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'tourist.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-super-secret-key-for-hackathon'

# Initialize DB with app
db.init_app(app)

# A temporary storage for OTPs. In a real app, use Redis or a similar tool.
sent_otps = {}

# --- Helper Functions ---

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculates distance between two lat/lon points in kilometers."""
    R = 6371  # Radius of Earth in kilometers
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat / 2) * math.sin(dLat / 2) + math.cos(math.radians(lat1)) \
        * math.cos(math.radians(lat2)) * math.sin(dLon / 2) * math.sin(dLon / 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def check_for_anomalies(tourist):
    """
    Placeholder for AI-based anomaly detection.
    This function is called after every location update.
    """
    # Simple rule-based anomaly: trigger if safety score is critically low.
    if tourist.safety_score < 30:
        # Prevent spamming alerts by checking for a recent one.
        last_alert = Alert.query.filter_by(tourist_id=tourist.id, alert_type='Anomaly').order_by(Alert.timestamp.desc()).first()
        if not last_alert or (datetime.utcnow() - last_alert.timestamp).total_seconds() > 3600:  # 1-hour cooldown
            anomaly_alert = Alert(
                tourist_id=tourist.id,
                location=tourist.last_known_location,
                alert_type='Anomaly'
            )
            db.session.add(anomaly_alert)
            print(f"DEBUG: AI Anomaly Detected for tourist {tourist.name} due to low safety score.")

# --- Web Page Routes ---

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/register')
def register_page():
    return render_template('register.html')

@app.route('/user_dashboard')
def user_dashboard():
    if 'tourist_id' not in session:
        return redirect(url_for('login_page'))
    tourist = Tourist.query.get(session['tourist_id'])
    return render_template('user_dashboard.html', tourist=tourist)

@app.route('/authorities_dashboard')
def authorities_dashboard():
    return render_template('dashboard.html')

# --- API Endpoints ---

@app.route('/api/send_otp', methods=['POST'])
def send_otp():
    data = request.json
    phone = data.get('phone')
    if not phone: return jsonify({'error': 'Phone number is required'}), 400
    if Tourist.query.filter_by(phone=phone).first(): return jsonify({'error': 'Phone number already registered'}), 409
    otp = str(random.randint(100000, 999999))
    sent_otps[phone] = {'otp': otp, 'timestamp': datetime.utcnow()}
    print(f"DEBUG: Sent OTP '{otp}' to phone number {phone}")
    return jsonify({'message': 'OTP sent successfully'}), 200

@app.route('/api/verify_otp', methods=['POST'])
def verify_otp():
    data = request.json
    phone, otp = data.get('phone'), data.get('otp')
    if not all([phone, otp]): return jsonify({'error': 'Missing phone or OTP'}), 400
    if phone in sent_otps:
        otp_data = sent_otps[phone]
        if (datetime.utcnow() - otp_data['timestamp']).total_seconds() > 300:
            del sent_otps[phone]
            return jsonify({'error': 'OTP has expired'}), 401
        if otp_data['otp'] == otp:
            del sent_otps[phone]
            return jsonify({'message': 'OTP verified successfully'}), 200
        else: return jsonify({'error': 'Invalid OTP'}), 401
    else: return jsonify({'error': 'No OTP was sent for this number'}), 401

@app.route('/api/register', methods=['POST'])
def register_tourist():
    data = request.json
    if not all(k in data for k in ['name', 'kyc_id', 'kyc_type', 'phone', 'visit_duration_days']):
        return jsonify({'error': 'Missing required fields'}), 400
    
    start_date = datetime.utcnow()
    end_date = start_date + timedelta(days=int(data['visit_duration_days']))
    new_tourist = Tourist(
        digital_id=str(uuid.uuid4()),
        name=data['name'],
        kyc_type=data['kyc_type'],
        kyc_id=data['kyc_id'],
        phone=data['phone'],
        visit_start_date=start_date,
        visit_end_date=end_date
    )
    db.session.add(new_tourist)
    db.session.commit()
    session['tourist_id'] = new_tourist.id
    return jsonify({'message': 'Tourist registered successfully', 'tourist_id': new_tourist.id}), 201

@app.route('/api/login_phone', methods=['POST'])
def login_phone():
    data = request.json
    if not data or 'phone' not in data: return jsonify({'error': 'Missing phone number'}), 400
    tourist = Tourist.query.filter_by(phone=data['phone']).first()
    if tourist:
        session['tourist_id'] = tourist.id
        return jsonify({'message': 'Login successful'})
    return jsonify({'error': 'Invalid phone number or not registered'}), 401

@app.route('/api/logout')
def logout_api():
    session.pop('tourist_id', None)
    return redirect(url_for('home'))

@app.route('/api/panic', methods=['POST'])
def panic_button():
    if 'tourist_id' not in session: return jsonify({'error': 'Not authenticated'}), 403
    tourist = Tourist.query.get(session['tourist_id'])
    if not tourist: return jsonify({'error': 'Tourist not found'}), 404
    
    data = request.json
    location = data.get('location', 'Unknown Location')
    
    new_alert = Alert(tourist_id=tourist.id, location=location, alert_type='Panic Button')
    db.session.add(new_alert)
    tourist.last_known_location = location
    tourist.safety_score = max(0, tourist.safety_score - 20)
    db.session.commit()
    return jsonify({'message': 'Panic signal received. Help is on the way.'}), 200

@app.route('/api/update_location', methods=['POST'])
def update_location():
    if 'tourist_id' not in session: return jsonify({'error': 'Not authenticated'}), 403
    tourist = Tourist.query.get(session['tourist_id'])
    if not tourist: return jsonify({'error': 'Tourist not found'}), 404
    
    data = request.json
    lat, lon = data.get('lat'), data.get('lon')
    if not all([lat, lon]): return jsonify({'error': 'Latitude and longitude are required'}), 400

    tourist.last_known_location = f"Lat: {lat:.4f}, Lon: {lon:.4f}"
    
    all_zones = SafetyZone.query.all()
    current_zone = None
    for zone in all_zones:
        distance = calculate_distance(lat, lon, zone.latitude, zone.longitude)
        if distance <= zone.radius:
            current_zone = zone
            break
    
    if current_zone:
        regional_score = current_zone.regional_score
        tourist.safety_score = int((tourist.safety_score * 0.9) + (regional_score * 0.1))
        zone_name = current_zone.name
    else:
        regional_score = 70 # Neutral score for undefined areas
        tourist.safety_score = int((tourist.safety_score * 0.9) + (regional_score * 0.1))
        zone_name = "Undefined Area"

    check_for_anomalies(tourist)
    db.session.commit()
    
    return jsonify({
        'message': 'Location updated',
        'current_zone': zone_name,
        'new_safety_score': tourist.safety_score
    }), 200

@app.route('/api/safety_zones', methods=['GET'])
def get_safety_zones():
    zones = SafetyZone.query.all()
    output = [{'name': z.name, 'latitude': z.latitude, 'longitude': z.longitude, 'radius': z.radius, 'regional_score': z.regional_score} for z in zones]
    return jsonify({'safety_zones': output})

@app.route('/api/dashboard/tourists', methods=['GET'])
def get_all_tourists():
    tourists = Tourist.query.all()
    output = [{'id': t.id, 'digital_id': t.digital_id, 'name': t.name, 'kyc_id': t.kyc_id, 'phone': t.phone, 'visit_end_date': t.visit_end_date.isoformat(), 'safety_score': t.safety_score, 'last_known_location': t.last_known_location, 'is_active': t.is_active} for t in tourists]
    return jsonify({'tourists': output})

@app.route('/api/dashboard/alerts', methods=['GET'])
def get_all_alerts():
    alerts = Alert.query.order_by(Alert.timestamp.desc()).all()
    output = [{'alert_id': a.id, 'tourist_name': a.tourist.name, 'tourist_id': a.tourist_id, 'location': a.location, 'timestamp': a.timestamp.isoformat(), 'alert_type': a.alert_type} for a in alerts]
    return jsonify({'alerts': output})

# --- Database Initialization and Server Run ---

def populate_safety_zones():
    if SafetyZone.query.count() == 0:
        zones = [
            # Seismic Zone V (Most Dangerous) - Score: 10
            SafetyZone(name="Guwahati, Assam (Zone V)", latitude=26.1445, longitude=91.7362, radius=100, regional_score=10),
            SafetyZone(name="Srinagar, J&K (Zone V)", latitude=34.0837, longitude=74.7973, radius=100, regional_score=10),
            SafetyZone(name="Dehradun, Uttarakhand (Zone V)", latitude=30.3165, longitude=78.0322, radius=80, regional_score=10),
            SafetyZone(name="Bhuj, Gujarat (Zone V)", latitude=23.2530, longitude=69.6660, radius=100, regional_score=10),
            
            # Seismic Zone IV (High Risk) - Score: 25
            SafetyZone(name="Delhi (Zone IV)", latitude=28.7041, longitude=77.1025, radius=50, regional_score=25),
        ]
        db.session.bulk_save_objects(zones)
        db.session.commit()
        print("Populated the database with high-risk earthquake zones.")

def initialize_database():
    with app.app_context():
        db.create_all()
        populate_safety_zones()
        print("Database initialized.")

def run_server():
    initialize_database()
    HOST = "127.0.0.1"
    PORT = 5000
    print(f"Starting Flask server on http://{HOST}:{PORT}")
    app.run(host=HOST, port=PORT, debug=True, use_reloader=False)

if __name__ == '__main__':
    run_server()
