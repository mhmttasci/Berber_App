from flask import Flask, render_template, request, redirect, url_for, session, make_response, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from flask_bcrypt import Bcrypt
from datetime import datetime, timedelta
import uuid
import csv
from config import Config
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from sqlalchemy import or_, and_
from flask import jsonify
from datetime import datetime, timedelta, time as dtime

import os
FONT_PATH = os.path.join(os.path.dirname(__file__), 'fonts', 'arial.ttf')
pdfmetrics.registerFont(TTFont('arial', FONT_PATH))

app = Flask(__name__)
app.config.from_object(Config)
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# MODELLER
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)  # Yeni alan
    password = db.Column(db.String(200), nullable=False)
    appointments = db.relationship('Appointment', backref='user', lazy=True)

class Chair(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True, nullable=False)

class Timeslot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    time = db.Column(db.String(5), unique=True, nullable=False)

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reference_number = db.Column(db.String(50), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    chair_id = db.Column(db.Integer, db.ForeignKey('chair.id'), nullable=False)
    date = db.Column(db.String(10), nullable=False)
    time = db.Column(db.String(5), nullable=False)
    device_id = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    chair = db.relationship('Chair')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.template_filter('date_tr')
def date_tr(s):
    # yyyy-mm-dd veya dd.mm.yyyy
    if '-' in s:
        y, m, d = s.split('-')
        return f"{d}.{m}.{y}"
    return s

def generate_reference_number():
    today_str = datetime.now().strftime("%Y%m%d")
    count = Appointment.query.filter_by(
        date=(datetime.now()+timedelta(days=1)).strftime("%d.%m.%Y")
    ).count()
    return f"{today_str}-{count+1:03d}"

# Varsayılan saatleri otomatik ekle
def setup_default_timeslots():
    default_times = [
        '08:00','08:30','09:00','09:30','10:00','10:30','11:00','11:30',
        # 12:00, 12:30, 13:00 YOK
        '13:30','14:00','14:30','15:00','15:30','16:00','16:30'
    ]
    if Timeslot.query.count() == 0:
        for t in default_times:
            db.session.add(Timeslot(time=t))
        db.session.commit()

# Varsayılan koltuk ekle (en az 1 tane)
def setup_default_chairs():
    if Chair.query.count() == 0:
        db.session.add(Chair(name="Koltuk 1"))
        db.session.add(Chair(name="Koltuk 2"))
        db.session.commit()

@app.route('/get_times/<int:chair_id>')
@login_required
def get_times(chair_id):
    tomorrow_dt = datetime.now() + timedelta(days=1)
    date_display = tomorrow_dt.strftime("%d.%m.%Y")
    all_times = [ts.time for ts in Timeslot.query.order_by(Timeslot.time).all()]
    taken_times = [
        a.time for a in Appointment.query.filter_by(date=date_display, chair_id=chair_id).all()
    ]
    free_times = []
    for t in all_times:
        free_times.append({
            "time": t,
            "is_taken": t in taken_times
        })
    return jsonify(free_times)

# Kayıt
@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        username = request.form['username']
        name = request.form['name']
        pw = bcrypt.generate_password_hash(request.form['password']).decode()
        if User.query.filter_by(username=username).first():
            flash("Bu kullanıcı adı zaten alınmış.", "danger")
            return redirect(url_for('register'))
        user=User(username=username, name=name, password=pw)
        db.create_all()
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('user_register.html')


# Giriş

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and bcrypt.check_password_hash(user.password, request.form['password']):
            login_user(user)
            return redirect(url_for('user_panel'))
        else:
            flash("Geçersiz kullanıcı adı veya şifre!", "danger")
    return render_template('user_login.html')


# Çıkış
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Kullanıcı panel & rezervasyon
@app.route('/', methods=['GET','POST'])
@login_required
def user_panel():

    tomorrow_dt = datetime.now() + timedelta(days=1)
    date_display = tomorrow_dt.strftime("%d.%m.%Y")
    date_db = date_display
    now = datetime.now()
    acilis = dtime(9,0)
    kapanis = dtime(17,0)
    randevu_aktif = (now.time() >= acilis and now.time() < kapanis)

    if request.method == 'POST' and not randevu_aktif:
        flash("Randevu alma hizmeti 09:00-17:00 arasında açıktır.", "danger")
        return redirect(url_for('user_panel'))
    device_id = request.cookies.get('device_id') or str(uuid.uuid4())
    chairs = Chair.query.all()
    timeslots = [ts.time for ts in Timeslot.query.order_by(Timeslot.time).all()]
    if request.method == 'POST':
        selected_chair = int(request.form.get('chair_id', chairs[0].id))
    else:
        selected_chair = chairs[0].id

    taken_times = [
        a.time for a in Appointment.query.filter_by(date=date_db, chair_id=selected_chair).all()
    ]

    cooldown = False
    remaining = None
    last = Appointment.query.filter_by(device_id=device_id).order_by(Appointment.created_at.desc()).first()
    if last:
        delta = datetime.utcnow() - last.created_at
        if delta.days < 14:
            cooldown = True
            rem = timedelta(days=14) - delta
            d = rem.days
            h, r = divmod(rem.seconds, 3600)
            m = r // 60
            remaining = f"{d} gün {h} saat {m} dakika"

    if request.method == 'POST' and not cooldown:
        time = request.form['time']
        chair_id = selected_chair
        if time in taken_times:
            flash("Bu saat artık müsait değil.", "danger")
            return redirect(url_for('user_panel'))
        ref = generate_reference_number()
        appt = Appointment(
            reference_number=ref,
            user_id=current_user.id,
            chair_id=chair_id,
            date=date_db,
            time=time,
            device_id=device_id
        )
        db.session.add(appt)
        db.session.commit()
        flash(f"Randevu alındı. Numaranız: {ref}", "success")
        resp = redirect(url_for('user_panel'))
        resp.set_cookie('device_id', device_id, max_age=31536000)
        return resp

    return render_template(
        'user_panel.html',
        date=date_display,
        chairs=chairs,
        selected_chair=selected_chair,
        all_times=timeslots,
        taken_times=taken_times,
        cooldown=cooldown,
        remaining=remaining,
        randevu_aktif=randevu_aktif,
    )

# Admin giriş
@app.route('/admin', methods=['GET','POST'])
def admin_login():
    if request.method=='POST':
        if request.form['username']==app.config['ADMIN_USER'] and \
           request.form['password']==app.config['ADMIN_PASS']:
            session['admin']=True
            return redirect(url_for('admin_panel'))
        else:
            flash("Geçersiz admin bilgisi!", "danger")
    return render_template('admin_login.html')

@app.route('/admin/pdf_export')
def admin_pdf_export():
    if not session.get('admin'): return redirect(url_for('admin_login'))
    date_filter = request.args.get('date', '')
    if not date_filter:
        flash("PDF almak için tarih seçiniz!", "danger")
        return redirect(url_for('admin_panel'))
    # YYYY-MM-DD -> GG.AA.YYYY dönüşüm
    try:
        dt = datetime.strptime(date_filter, "%Y-%m-%d")
        date_filter_tr = dt.strftime("%d.%m.%Y")
    except Exception:
        date_filter_tr = date_filter
    appointments = Appointment.query.filter_by(date=date_filter_tr).order_by(Appointment.time).all()

    # PDF oluştur
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    p.setFont("Helvetica-Bold", 18)
    p.drawCentredString(width/2, height-50, f"{date_filter} Randevu Listesi")
    p.setFont("arial", 12)
    y = height-80
    p.drawString(40, y, "Saat               Koltuk                 İsim                        Ref No")
    y -= 15
    p.line(38, y, width-38, y)
    y -= 20

    for a in appointments:
        p.drawString(40, y, f"{a.time:6}  {a.chair.name:8}  {a.user.name[:20]:20}  {a.reference_number}")
        y -= 18
        if y < 60:
            p.showPage()
            y = height-80

    p.save()
    buffer.seek(0)
    filename = f"randevular_{date_filter}.pdf"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')

# Admin panel
@app.route('/admin_panel', methods=['GET', 'POST'])
def admin_panel():
    if not session.get('admin'): return redirect(url_for('admin_login'))

    # Tarih filtresi (YYYY-MM-DD gelir, GG.AA.YYYY'ye çevir)
    date_filter = request.args.get('date', '')
    if date_filter:
        try:
            # HTML'den YYYY-MM-DD geliyor, GG.AA.YYYY yap
            dt = datetime.strptime(date_filter, "%Y-%m-%d")
            date_filter_tr = dt.strftime("%d.%m.%Y")
        except Exception:
            date_filter_tr = date_filter
        appointments = Appointment.query.filter_by(date=date_filter_tr).order_by(Appointment.time).all()
    else:
        appointments = Appointment.query.order_by(Appointment.date, Appointment.time).all()
        date_filter_tr = ''
    return render_template('admin_panel.html', appointments=appointments, date_filter=date_filter_tr)
# Koltuk yönetimi
@app.route('/admin/chairs', methods=['GET','POST'])
def admin_chairs():
    if not session.get('admin'): return redirect(url_for('admin_login'))
    if request.method=='POST':
        if 'add' in request.form:
            db.session.add(Chair(name=request.form['name']))
            db.session.commit()
        elif 'delete' in request.form:
            Chair.query.filter_by(id=int(request.form['delete'])).delete()
            db.session.commit()
    return render_template('admin_chairs.html', chairs=Chair.query.all())

# Saat yönetimi
@app.route('/admin/timeslots', methods=['GET', 'POST'])
def admin_timeslots():
    if not session.get('admin'): return redirect(url_for('admin_login'))
    if request.method == 'POST':
        if 'add' in request.form:
            t = request.form['new_time'].strip()
            if t and not Timeslot.query.filter_by(time=t).first():
                db.session.add(Timeslot(time=t))
                db.session.commit()
        elif 'delete' in request.form:
            Timeslot.query.filter_by(id=int(request.form['delete'])).delete()
            db.session.commit()
    return render_template('admin_timeslots.html', timeslots=Timeslot.query.order_by(Timeslot.time).all())

# Randevu sil
@app.route('/delete/<int:id>')
def delete(id):
    if not session.get('admin'): return redirect(url_for('admin_login'))
    a=Appointment.query.get_or_404(id)
    db.session.delete(a)
    db.session.commit()
    return redirect(url_for('admin_panel'))

# CSV export
@app.route('/export_csv')
def export_csv():
    if not session.get('admin'): return redirect(url_for('admin_login'))
    path='appointments.csv'
    with open(path,'w',newline='', encoding='utf-8') as f:
        w=csv.writer(f)
        w.writerow(['Ref','User','Koltuk','Date','Time','Device','Created'])
        for a in Appointment.query.all():
            w.writerow([a.reference_number,a.user.name,a.chair.name,a.date,a.time,a.device_id,a.created_at])
    return send_file(path,as_attachment=True)

if __name__=='__main__':
    with app.app_context():
        db.create_all()
        setup_default_chairs()
        setup_default_timeslots()
    app.run(host='172.16.10.4',port=5000, debug=True)
