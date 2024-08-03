import os
import re
import random
import string
from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_mail import Mail, Message
from werkzeug.utils import secure_filename
from itsdangerous import URLSafeTimedSerializer
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Configuring Flask-Mail and Flask app with environment variables
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')

mail = Mail(app)

# Set up a directory for file uploads
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'txt', 'jpg', 'jpeg', 'png'}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_meeting_code():
    characters = string.ascii_lowercase + string.digits
    code = ''.join(random.choice(characters) for _ in range(9))
    return f"{code[:3]}-{code[3:6]}-{code[6:]}"

# Dummy user data for demonstration purposes
users = {
    "test@example.com": "Password123!"
}

# Track login attempts
login_attempts = {}

# Store meeting details
meetings = {}

# Serializer for generating tokens
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

@app.route('/')
def index():
    return render_template('signin.html')

@app.route('/signin', methods=['POST'])
def signin():
    data = request.json
    email = data.get('email')
    password = data.get('password')

    if email in login_attempts and login_attempts[email] >= 3:
        return jsonify({"success": False, "message": "Your account is blocked due to multiple failed login attempts"}), 403

    if email in users and users[email] == password:
        login_attempts[email] = 0  # Reset login attempts on successful login
        return jsonify({"success": True})
    else:
        login_attempts[email] = login_attempts.get(email, 0) + 1
        return jsonify({"success": False, "message": "Invalid email or password"}), 401

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        data = request.json
        email = data.get('email')
        password = data.get('password')

        # Check if user already exists
        if email in users:
            return jsonify({"success": False, "message": "User already exists"}), 400

        # Add new user to the users dictionary
        users[email] = password
        return jsonify({"success": True})
    return render_template('signup.html')

@app.route('/forgotpassword')
def forgot_password_request():
    return render_template('forgot_password.html')

@app.route('/send-reset-link', methods=['POST'])
def send_reset_link():
    data = request.json
    email = data.get('email')

    if email not in users:
        return jsonify({"success": True, "message": "If your email is registered, you will receive a password reset link."})

    token = serializer.dumps(email, salt='password-reset-salt')
    reset_url = url_for('reset_password', token=token, _external=True)
    msg = Message('Password Reset Request', sender=app.config['MAIL_USERNAME'], recipients=[email])
    msg.body = f"Please click the following link to reset your password: {reset_url}"

    try:
        mail.send(msg)
        return jsonify({"success": True, "message": "If your email is registered, you will receive a password reset link."})
    except Exception as e:
        return jsonify({"success": False, "message": f"Failed to send reset link: {str(e)}"}), 500

@app.route('/reset/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        email = serializer.loads(token, salt='password-reset-salt', max_age=3600)
    except Exception as e:
        return jsonify({"success": False, "message": "Invalid or expired token."})

    if request.method == 'POST':
        data = request.json
        new_password = data.get('password')
        confirm_password = data.get('confirm_password')

        if new_password != confirm_password:
            return jsonify({"success": False, "message": "Passwords do not match."})

        users[email] = new_password
        return jsonify({"success": True, "message": "Password reset successful."})

    return render_template('resetpassword.html')

@app.route('/meeting-options')
def meeting_options():
    return render_template('meeting_options.html')

@app.route('/join', methods=['GET', 'POST'])
def join():
    if request.method == 'POST':
        meeting_code = request.form.get('meeting-code')
        if meeting_code and re.match(r'^[a-z0-9]{3}-[a-z0-9]{3}-[a-z0-9]{3}$', meeting_code):
            return redirect(url_for('meeting'))
        else:
            return render_template('join_meeting.html', error="Invalid meeting code format.")
    return render_template('join_meeting.html')

@app.route('/create-meeting', methods=['GET', 'POST'])
def create_meeting():
    if request.method == 'POST':
        data = request.json
        meeting_name = data.get('name')
        participant_emails = data.get('emails', [])
        occurrence = data.get('occurrence')
        meeting_code = generate_meeting_code()
        meeting_url = f"https://webRTC.com/join/{meeting_code}"

        # Store the meeting details
        meetings[meeting_code] = {"name": meeting_name, "url": meeting_url, "participants": participant_emails, "occurrence": occurrence}

        # Send email invitations
        for email in participant_emails:
            msg = Message('Meeting Invitation',
                          sender=app.config['MAIL_USERNAME'],
                          recipients=[email])
            msg.body = f"You are invited to a meeting: {meeting_name}\nMeeting Code: {meeting_code}\nJoin URL: {meeting_url}"
            try:
                mail.send(msg)
                print(f'Email sent to {email}')
            except Exception as e:
                print(f'Failed to send email to {email}: {e}')

        return jsonify({"success": True, "meeting_code": meeting_code, "meeting_url": meeting_url})

    return render_template('create_meeting.html')

@app.route('/meeting')
def meeting():
    return render_template('meeting.html')

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            return jsonify({"success": False, "message": "No file part"}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({"success": False, "message": "No selected file"}), 400
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            return jsonify({"success": True, "message": "File uploaded successfully"}), 200
        else:
            return jsonify({"success": False, "message": "File type not allowed"}), 400
    return render_template('upload_file.html')

if __name__ == '__main__':
    # Ensure the uploads folder exists
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True, port=5001, use_reloader=False)
