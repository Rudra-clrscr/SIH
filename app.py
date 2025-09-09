import os
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from datetime import datetime, timedelta
import random
import hashlib
from math import radians, sin, cos, sqrt, atan2
from database import db, Tourist, SafetyZone, Alert

# --- App Configuration ---
app = Flask(__name__)
app.secret_key = 'your_super_secret_key' 
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tourist_data.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

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
    tourist = Tourist.query.get(session['tourist_id'])
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
    tourist = Tourist.query.get(session['tourist_id'])
    
    if not tourist: return jsonify({'error': 'Tourist not found'}), 404

    tourist.last_known_location = f"Lat: {lat}, Lon: {lon}"
    
    # --- CORRECTED SAFETY SCORE LOGIC ---
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
        # If the tourist is inside any zone
        if current_zone_score < tourist.safety_score:
            tourist.safety_score = current_zone_score
        elif current_zone_score > 80 and tourist.safety_score < 100:
            tourist.safety_score += 1
    # If tourist is in a neutral/unmapped area (current_zone_score is None), do nothing.

    db.session.commit()
    return jsonify({'message': 'Location updated', 'safety_score': tourist.safety_score}), 200

@app.route('/api/panic', methods=['POST'])
def trigger_panic_alert():
    if 'tourist_id' not in session: return jsonify({'error': 'Not authenticated'}), 401
    tourist = Tourist.query.get(session['tourist_id'])
    if not tourist: return jsonify({'error': 'Tourist not found'}), 404
    new_alert = Alert(tourist_id=tourist.id, location=tourist.last_known_location, alert_type='Panic Button')
    db.session.add(new_alert)
    db.session.commit()
    print(f"PANIC ALERT: Triggered by {tourist.name} at {tourist.last_known_location}")
    return jsonify({'message': 'Panic alert successfully registered.'}), 200

@app.route('/api/safety_zones')
def get_safety_zones():
    return jsonify({'safety_zones': [{'name': z.name, 'latitude': z.latitude, 'longitude': z.longitude, 'radius': z.radius, 'regional_score': z.regional_score} for z in SafetyZone.query.all()]})

@app.route('/api/dashboard/tourists')
def get_tourists_data():
    return jsonify({'tourists': [{'id': t.id, 'name': t.name, 'phone': t.phone, 'safety_score': t.safety_score, 'last_known_location': t.last_known_location} for t in Tourist.query.all()]})

@app.route('/api/dashboard/alerts')
def get_alerts_data():
    return jsonify({'alerts': [{'tourist_name': a.tourist.name, 'alert_type': a.alert_type, 'location': a.location, 'timestamp': a.timestamp.strftime('%d-%b-%Y %H:%M:%S')} for a in Alert.query.order_by(Alert.timestamp.desc()).limit(50).all()]})

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
    if SafetyZone.query.count() == 0:
        db.session.bulk_save_objects([
            SafetyZone(name='City Center', latitude=28.6139, longitude=77.2090, radius=50, regional_score=95),
            SafetyZone(name='Remote Hills', latitude=28.7041, longitude=77.1025, radius=100, regional_score=70),
            SafetyZone(name='Restricted Area', latitude=28.5355, longitude=77.3910, radius=80, regional_score=25)
        ])
        db.session.commit()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        add_initial_data()
    app.run(debug=True, port=15000)