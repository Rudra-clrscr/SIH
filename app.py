import os
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import random

# --- App Configuration ---
app = Flask(__name__)
# Set a secret key for session management. In a real app, use a secure, random key.
app.secret_key = 'your_super_secret_key' 
# Configure the database path. It will create a 'tourist_data.db' file in your project directory.
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tourist_data.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- In-memory OTP storage (for demonstration purposes) ---
# In a production environment, you would use a more robust solution like Redis.
otp_storage = {}


# --- Database Models ---
class Tourist(db.Model):
    """Represents a tourist in the system."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15), unique=True, nullable=False)
    kyc_id = db.Column(db.String(50), unique=True, nullable=False)
    kyc_type = db.Column(db.String(20), nullable=False, default='Aadhaar')
    registration_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    visit_end_date = db.Column(db.DateTime, nullable=False)
    last_known_location = db.Column(db.String(100), nullable=True)
    safety_score = db.Column(db.Integer, default=100)
    
    def __repr__(self):
        return f'<Tourist {self.name}>'

# --- HTML Page Routes ---
@app.route('/')
def home():
    """Renders the main landing page."""
    return render_template('home.html')

@app.route('/register')
def register_page():
    """Renders the user registration page."""
    return render_template('register.html')

@app.route('/login')
def login_page():
    """Renders the user login page."""
    return render_template('login.html')

@app.route('/user_dashboard')
def user_dashboard():
    """Renders the dashboard for a logged-in tourist."""
    if 'tourist_id' not in session:
        return redirect(url_for('login_page'))
    tourist = Tourist.query.get(session['tourist_id'])
    if not tourist:
        return redirect(url_for('login_page'))
    return render_template('user_dashboard.html', tourist=tourist)

@app.route('/dashboard')
def admin_dashboard():
    """Renders the main dashboard for authorities."""
    return render_template('dashboard.html')


# --- API Endpoints ---
@app.route('/api/send_otp', methods=['POST'])
def send_otp():
    """Generates and 'sends' an OTP for phone verification."""
    data = request.get_json()
    phone = data.get('phone')
    if not phone:
        return jsonify({'error': 'Phone number is required.'}), 400
    
    # Simulate OTP generation
    otp = str(random.randint(100000, 999999))
    otp_storage[phone] = otp
    
    # In a real application, you would integrate with an SMS gateway here.
    # For now, we'll print it to the console for easy testing.
    print(f"--- OTP for {phone}: {otp} ---")
    
    return jsonify({'message': 'OTP sent successfully to your phone.'}), 200

@app.route('/api/verify_otp', methods=['POST'])
def verify_otp():
    """Verifies the OTP submitted by the user."""
    data = request.get_json()
    phone = data.get('phone')
    otp = data.get('otp')
    
    if otp_storage.get(phone) == otp:
        # OTP is correct, remove it from storage
        del otp_storage[phone]
        return jsonify({'message': 'OTP verified successfully.'}), 200
    else:
        return jsonify({'error': 'Invalid or expired OTP.'}), 400

@app.route('/api/register', methods=['POST'])
def register_user():
    """Registers a new tourist in the database."""
    data = request.get_json()
    
    # Check if user already exists
    if Tourist.query.filter_by(phone=data['phone']).first() or Tourist.query.filter_by(kyc_id=data['kyc_id']).first():
        return jsonify({'error': 'Phone number or KYC ID already registered.'}), 409
        
    # Calculate visit end date
    visit_duration = int(data['visit_duration_days'])
    end_date = datetime.utcnow() + timedelta(days=visit_duration)
    
    new_tourist = Tourist(
        name=data['name'],
        phone=data['phone'],
        kyc_id=data['kyc_id'],
        kyc_type=data['kyc_type'],
        visit_end_date=end_date
    )
    db.session.add(new_tourist)
    db.session.commit()
    
    # Automatically log the user in after registration
    session['tourist_id'] = new_tourist.id
    
    return jsonify({'message': 'Registration successful.'}), 201

@app.route('/api/login_phone', methods=['POST'])
def login_with_phone():
    """Logs a user in using their phone number."""
    data = request.get_json()
    phone = data.get('phone')
    tourist = Tourist.query.filter_by(phone=phone).first()
    
    if tourist:
        session['tourist_id'] = tourist.id
        return jsonify({'message': 'Login successful'}), 200
    else:
        return jsonify({'error': 'No account found with that phone number.'}), 404

@app.route('/api/logout')
def logout():
    """Logs the current user out."""
    session.pop('tourist_id', None)
    return redirect(url_for('home'))

@app.route('/api/update_location', methods=['POST'])
def update_location():
    """Updates the last known location of the logged-in tourist."""
    if 'tourist_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
        
    data = request.get_json()
    location_str = f"Lat: {data.get('latitude')}, Lon: {data.get('longitude')}"
    
    tourist = Tourist.query.get(session['tourist_id'])
    tourist.last_known_location = location_str
    db.session.commit()
    
    return jsonify({'message': 'Location updated successfully'}), 200

@app.route('/api/dashboard/tourists')
def get_tourists_data():
    """Provides data for the authorities' dashboard."""
    tourists = Tourist.query.all()
    tourist_list = [
        {
            'id': t.id,
            'name': t.name,
            'phone': t.phone,
            'last_known_location': t.last_known_location,
            'safety_score': t.safety_score,
            'visit_end_date': t.visit_end_date.strftime('%Y-%m-%d')
        } for t in tourists
    ]
    return jsonify({'tourists': tourist_list})

@app.route('/api/safety_zones')
def get_safety_zones():
    """Provides predefined safety zone data for the user map."""
    # This is dummy data. In a real app, this would come from a database.
    zones = [
        {'name': 'Safe Zone A', 'latitude': 28.6139, 'longitude': 77.2090, 'radius': 50, 'regional_score': 95},
        {'name': 'Moderate Zone B', 'latitude': 19.0760, 'longitude': 72.8777, 'radius': 100, 'regional_score': 70},
        {'name': 'High-Risk Zone C', 'latitude': 34.0837, 'longitude': 74.7973, 'radius': 80, 'regional_score': 25}
    ]
    return jsonify({'safety_zones': zones})


# --- Main Execution ---
if __name__ == '__main__':
    # Create the database and tables if they don't exist
    with app.app_context():
        db.create_all()
    # Run the Flask app in debug mode
    app.run(debug=True, port=15000)