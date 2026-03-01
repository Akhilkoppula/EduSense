import random
import string
from flask import Flask, render_template, jsonify, request, redirect, url_for, session
from flask_socketio import SocketIO, emit, join_room
from pymongo import MongoClient
from bson import ObjectId

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mlrit_edusense_2026_key'
socketio = SocketIO(app, cors_allowed_origins="*")

# In-memory live classroom state
CLASSROOM_ROOM = "global_room"
live_students = {}
teacher_sid = None

# --- MONGODB CONNECTION ---
try:
    client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=2000)
    db = client["edusense_db"]
    teachers_col = db["teachers"]
    sessions_col = db["sessions"]
    client.server_info()
    print("✅ MongoDB Connected")
except Exception as e:
    print(f"❌ MongoDB Error: {e}")


# --- CORE ROUTES ---

@app.route('/')
def welcome():
    # This renders the main entry page
    return render_template('welcome.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('welcome'))


# --- TEACHER MODULE ---

@app.route('/teacher_login', methods=['GET', 'POST'])
def teacher_login_page():
    if request.method == 'POST':
        email = request.form.get('email').lower()
        password = request.form.get('password')
        user = teachers_col.find_one({"email": email, "password": password})
        if user:
            session['teacher_name'] = user['name']
            session['teacher_email'] = user['email']
            return redirect(url_for('teacher_console'))
        return render_template('teacher_login.html', error="Invalid Credentials")
    return render_template('teacher_login.html')


@app.route('/teacher_console')
def teacher_console():
    if 'teacher_name' not in session:
        return redirect(url_for('teacher_login_page'))
    upcoming = list(sessions_col.find({"teacher_email": session['teacher_email'], "status": "Pending"}))
    recent = list(sessions_col.find({"teacher_email": session['teacher_email'], "status": "Completed"}))
    return render_template('teacher_console.html', name=session['teacher_name'], upcoming=upcoming, recent=recent)


@app.route('/teacher_live')
def teacher_live():
    if 'teacher_name' not in session:
        return redirect(url_for('teacher_login_page'))
    return render_template('teacher.html')


# --- STUDENT MODULE ---

@app.route('/join')
def student_join_page():
    # This is the route for the "Join Class" button on welcome.html
    return render_template('student_join.html', auto_code=request.args.get('code', ''))


@app.route('/verify_session', methods=['POST'])
def verify_session():
    data = request.json
    sess = sessions_col.find_one({"passcode": data.get('passcode'), "status": "Pending"})
    if sess:
        session['student_auth'] = True
        session['student_name'] = data.get('name')
        session['active_passcode'] = sess['passcode']
        return jsonify({"success": True, "redirect": url_for('student_live_room')})
    return jsonify({"success": False, "message": "Invalid passcode."})


@app.route('/student_live')
def student_live_room():
    if 'student_auth' not in session:
        return redirect(url_for('student_join_page'))
    return render_template('student.html')


def emit_live_summary():
    students = list(live_students.values())
    if not students:
        summary = {
            "online": 0,
            "engagement": 0,
            "confusion": 0,
            "emotion_counts": {"engaged": 0, "neutral": 0, "confused": 0, "distracted": 0},
            "attention_list": []
        }
    else:
        emotions = {"engaged": 0, "neutral": 0, "confused": 0, "distracted": 0}
        for student in students:
            emotions[student.get("emotion", "neutral")] = emotions.get(student.get("emotion", "neutral"), 0) + 1

        summary = {
            "online": len(students),
            "engagement": round(sum(s.get("engagement", 0) for s in students) / len(students)),
            "confusion": round(sum(s.get("confusion", 0) for s in students) / len(students)),
            "emotion_counts": emotions,
            "attention_list": sorted(
                [
                    {
                        "sid": s["sid"],
                        "name": s.get("name", "Student"),
                        "emotion": s.get("emotion", "neutral"),
                        "confusion": s.get("confusion", 0)
                    }
                    for s in students
                    if s.get("confusion", 0) >= 55 or s.get("emotion") in ["confused", "distracted"]
                ],
                key=lambda item: item["confusion"],
                reverse=True
            )[:6]
        }

    emit('class_summary', summary, to=CLASSROOM_ROOM)


# --- SIGNALING RELAY ---
@socketio.on('join_room')
def handle_join(data):
    global teacher_sid

    join_room(CLASSROOM_ROOM)
    role = data.get('role', 'student')

    if role == 'teacher':
        teacher_sid = request.sid
        emit('teacher_ready', {"sid": request.sid}, to=CLASSROOM_ROOM, include_self=False)
        emit_live_summary()
        return

    student = {
        "sid": request.sid,
        "name": data.get('name', 'Student'),
        "engagement": 60,
        "confusion": 20,
        "emotion": "neutral"
    }
    live_students[request.sid] = student
    emit('new_student', student, to=CLASSROOM_ROOM, include_self=False)
    emit_live_summary()


@socketio.on('signal')
def handle_signal(data):
    emit('signal', {"sid": request.sid, "signal": data['signal']}, to=data['to'])


@socketio.on('update_metrics')
def handle_metrics(data):
    if request.sid not in live_students:
        return

    current = live_students[request.sid]
    current['engagement'] = max(0, min(100, int(data.get('engagement', current['engagement']))))
    current['confusion'] = max(0, min(100, int(data.get('confusion', current['confusion']))))
    current['emotion'] = data.get('emotion', current['emotion'])

    emit('metrics_received', {
        "sid": request.sid,
        "name": current['name'],
        "engagement": current['engagement'],
        "confusion": current['confusion'],
        "emotion": current['emotion']
    }, to=CLASSROOM_ROOM, include_self=False)
    emit_live_summary()


@socketio.on('disconnect')
def handle_disconnect():
    global teacher_sid

    if request.sid == teacher_sid:
        teacher_sid = None

    if request.sid in live_students:
        del live_students[request.sid]
        emit('student_left', {"sid": request.sid}, to=CLASSROOM_ROOM)
        emit_live_summary()


if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
