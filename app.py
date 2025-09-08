import os
import random
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from datetime import datetime, timedelta
from database import db, Tourist, Itinerary, EmergencyContact, Alert
from flask_socketio import SocketIO, join_room, leave_room, emit

# Initialize Flask App
app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))

# Configure Database & Session
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'tourist.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-super-secret-key-for-hackathon' # Needed for sessions

# Initialize DB with app
db.init_app(app)

# Initialize SocketIO
socketio = SocketIO(app)

# A temporary storage for OTPs. In a production app, use a secure, temporary cache like Firebase or Redis.
sent_otps = {}

# --- Web Page Routes ---

@app.route('/')
def home():
    """Serves the new main homepage."""
    return render_template('home.html')

@app.route('/login')
def login_page():
    """Serves the login page."""
    return render_template('login.html')

@app.route('/register')
def register_page():
    """Serves the registration page."""
    return render_template('register.html')

@app.route('/user_dashboard')
def user_dashboard():
    """Serves the logged-in tourist's personal dashboard."""
    if 'tourist_id' not in session:
        return redirect(url_for('login_page'))
    tourist = Tourist.query.get(session['tourist_id'])
    return render_template('user_dashboard.html', tourist_name=tourist.name)

@app.route('/authorities_dashboard')
def authorities_dashboard():
    """Serves the authorities dashboard page."""
    return render_template('dashboard.html')

# --- API Endpoints ---

@app.route('/api/send_otp_firebase', methods=['POST'])
def send_otp_firebase():
    """Simulates sending an OTP via a Firebase Admin SDK call."""
    data = request.json
    phone = data.get('phone')

    if not phone:
        return jsonify({'error': 'Phone number is required'}), 400

    # In a real application, you would use Firebase Admin SDK here.
    # from firebase_admin.auth import create_custom_token
    # token = create_custom_token(uid)
    
    # For this simulation, we'll generate a dummy token.
    dummy_token = f"dummy-token-{random.randint(1000, 9999)}"
    
    print(f"DEBUG: Simulating Firebase OTP send. Dummy token '{dummy_token}' for phone number {phone}")
    
    return jsonify({'message': 'OTP sent successfully', 'token': dummy_token}), 200

@app.route('/api/verify_otp_firebase', methods=['POST'])
def verify_otp_firebase():
    """Verifies the OTP and token from the client-side."""
    data = request.json
    phone = data.get('phone')
    otp = data.get('otp')
    token = data.get('token')
    
    if not all([phone, otp, token]):
        return jsonify({'error': 'Missing phone, otp, or token'}), 400

    # In a real application, you would verify the token with Firebase here.
    # from firebase_admin import auth
    # user = auth.verify_id_token(token)
    
    # For this simulation, any valid-looking data is accepted.
    if token.startswith('dummy-token-') and len(otp) == 6:
        return jsonify({'message': 'OTP verified successfully'}), 200
    else:
        return jsonify({'error': 'Invalid OTP or token'}), 401

@app.route('/api/register', methods=['POST'])
def register_tourist():
    """Handles tourist registration after OTP verification."""
    data = request.json
    if not all(k in data for k in ['name', 'kyc_type', 'kyc_id', 'phone', 'visit_duration_days']):
        return jsonify({'error': 'Missing required fields for registration'}), 400
    
    if Tourist.query.filter_by(kyc_id=data['kyc_id']).first():
        return jsonify({'error': 'A tourist with this KYC ID is already registered'}), 409
    if Tourist.query.filter_by(phone=data['phone']).first():
        return jsonify({'error': 'A tourist with this phone number is already registered'}), 409

    start_date = datetime.utcnow()
    end_date = start_date + timedelta(days=int(data['visit_duration_days']))
    new_tourist = Tourist(name=data['name'], kyc_type=data['kyc_type'], kyc_id=data['kyc_id'], phone=data['phone'], visit_start_date=start_date, visit_end_date=end_date)
    
    db.session.add(new_tourist)
    db.session.commit()
    session['tourist_id'] = new_tourist.id
    return jsonify({'message': 'Tourist registered successfully', 'tourist_id': new_tourist.id}), 201

@app.route('/api/login', methods=['POST'])
def login_api():
    """Handles tourist login by KYC ID and creates a session."""
    data = request.json
    if not data or 'kyc_id' not in data:
        return jsonify({'error': 'Missing KYC ID'}), 400
    
    tourist = Tourist.query.filter_by(kyc_id=data['kyc_id']).first()
    if tourist:
        session['tourist_id'] = tourist.id
        return jsonify({'message': 'Login successful', 'tourist_id': tourist.id})
    return jsonify({'error': 'Invalid KYC ID'}), 401
    
@app.route('/api/login_phone', methods=['POST'])
def login_phone():
    """Handles tourist login by phone number and creates a session."""
    data = request.json
    if not data or 'phone' not in data:
        return jsonify({'error': 'Missing phone number'}), 400
    
    tourist = Tourist.query.filter_by(phone=data['phone']).first()
    if tourist:
        session['tourist_id'] = tourist.id
        return jsonify({'message': 'Login successful', 'tourist_id': tourist.id})
    return jsonify({'error': 'Invalid phone number or not registered'}), 401

@app.route('/api/logout')
def logout_api():
    session.pop('tourist_id', None)
    return redirect(url_for('home'))

@app.route('/api/panic', methods=['POST'])
def panic_button():
    if 'tourist_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 403
    
    tourist_id = session['tourist_id']
    data = request.json
    location = data.get('location', 'Unknown Location')

    tourist = Tourist.query.get(tourist_id)
    if not tourist:
        return jsonify({'error': 'Tourist not found'}), 404
        
    new_alert = Alert(tourist_id=tourist.id, location=location)
    db.session.add(new_alert)
    tourist.last_known_location = location
    tourist.safety_score -= 20
    db.session.commit()
    return jsonify({'message': 'Panic signal received. Help is on the way.'}), 200

@app.route('/api/dashboard/tourists', methods=['GET'])
def get_all_tourists():
    tourists = Tourist.query.all()
    output = [{'id': t.id, 'name': t.name, 'kyc_id': t.kyc_id, 'visit_end_date': t.visit_end_date.isoformat(), 'safety_score': t.safety_score, 'last_known_location': t.last_known_location, 'is_active': t.is_active} for t in tourists]
    return jsonify({'tourists': output})

@app.route('/api/dashboard/alerts', methods=['GET'])
def get_all_alerts():
    alerts = Alert.query.order_by(Alert.timestamp.desc()).all()
    output = [{'alert_id': a.id, 'tourist_name': a.tourist.name, 'tourist_id': a.tourist_id, 'location': a.location, 'timestamp': a.timestamp.isoformat(), 'alert_type': a.alert_type} for a in alerts]
    return jsonify({'alerts': output})

# --- Final part of the script ---
def initialize_database():
    with app.app_context():
        db.create_all()
        print("Database initialized.")

def run_server():
    """Function to run the Flask server. This is the part web.py will call."""
    initialize_database()
    HOST = "127.0.0.1"
    PORT = 5000
    print(f"Starting Flask server on http://{HOST}:{PORT}")
    app.run(host=HOST, port=PORT, debug=True)

if __name__ == '__main__':
    run_server()
