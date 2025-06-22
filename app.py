from flask import Flask, render_template, request,jsonify, redirect, url_for, flash, session, Response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta, time as dtime
import pandas as pd
from fpdf import FPDF
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
import os
FONT_PATH = os.path.join(os.path.dirname(__file__), 'fonts', 'arial.ttf')
pdfmetrics.registerFont(TTFont('arial', FONT_PATH))

app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///berber.db'
db = SQLAlchemy(app)

@app.template_filter('todatetime')
def todatetime_filter(s):
    # Eğer None gelirse veya boşsa None dönsün
    if not s:
        return None
    return datetime.strptime(s, "%d.%m.%Y")

### MODELLER

from werkzeug.security import generate_password_hash, check_password_hash



class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True)
    password_hash = db.Column(db.String(256))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Person(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    emekli_no = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)

class Chair(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True, nullable=False)

class Timeslot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    time = db.Column(db.String(5), unique=True, nullable=False)

class VipTimeslot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    day_of_week = db.Column(db.String(10))  # e.g. 'Cuma'
    time = db.Column(db.String(5))
    chair_id = db.Column(db.Integer, db.ForeignKey('chair.id'))
    tip = db.Column(db.String(10), nullable=False, default='VIP')  # <-- Yeni alan!

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    emekli_no = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    chair_id = db.Column(db.Integer, db.ForeignKey('chair.id'), nullable=False)
    date = db.Column(db.String(10), nullable=False)
    time = db.Column(db.String(5), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    chair = db.relationship('Chair')

ADMIN_USER = 'admin'
ADMIN_PASS = '12345'

TURKCE_GUNLER = ['Pazartesi','Salı','Çarşamba','Perşembe','Cuma','Cumartesi','Pazar']
@app.template_filter('todatetime')
def todatetime_filter(s):
    return datetime.strptime(s, "%d.%m.%Y")
def gun_ismi(dt):
    return TURKCE_GUNLER[dt.weekday()]
def randevu_alabilir_mi():
    simdi = datetime.now().time()
    return dtime(9, 0) <= simdi < dtime(17, 0)
def setup_defaults():
    if Chair.query.count() == 0:
        db.session.add(Chair(name="Koltuk 1"))
        db.session.add(Chair(name="Koltuk 2"))
    if Timeslot.query.count() == 0:
        saatler = ['08:00','08:30','09:00','09:30','10:00','10:30','11:00','11:30',
                   '13:30','14:00','14:30','15:00','15:30','16:00','16:30']
        for s in saatler:
            db.session.add(Timeslot(time=s))
    db.session.commit()



### -------------- KULLANICI PANELİ --------------
@app.route('/dolu_saatler')
def dolu_saatler():
    koltuk_id = request.args.get('koltuk_id')
    tarih = request.args.get('tarih')
    dolu_randevular = Appointment.query.filter_by(chair_id=koltuk_id, date=tarih).all()
    dolu_saatler = [r.time for r in dolu_randevular]
    return jsonify(dolu_saatler)
@app.route('/', methods=['GET', 'POST'])
def user_panel():
    randevu_aktif = randevu_alabilir_mi()
    chairs = Chair.query.all()
    timeslots = [ts.time for ts in Timeslot.query.order_by(Timeslot.time).all()]
    tomorrow_dt = datetime.now() + timedelta(days=1)
    date_display = tomorrow_dt.strftime("%d.%m.%Y")
    gun = gun_ismi(tomorrow_dt)
    now = datetime.now()
    randevu_aktif = (now.time() >= dtime(9, 0)) and (now.time() < dtime(17, 0))

    # --- Koltuk seçimi:
    if request.method == "POST" and "chair_id" in request.form and "refresh" in request.form:
        secili_koltuk_id = int(request.form["chair_id"])
    elif request.method == "POST" and "chair_id" in request.form:
        secili_koltuk_id = int(request.form["chair_id"])
    else:
        secili_koltuk_id = chairs[0].id if chairs else None

    # VIP Saatler (günü ve koltuğu kapsayan)
    vips = VipTimeslot.query.filter_by(day_of_week=gun).all()
    vip_saatler = set((v.time, v.chair_id) for v in vips if v.tip == "VIP")
    izinli_saatler = set((v.time, v.chair_id) for v in vips if v.tip == "İzinli")

    # Koltuk-bazlı dolu saatler
    dolu_saatler = {c.id: [] for c in chairs}
    appts = Appointment.query.filter_by(date=date_display).all()
    for a in appts:
        dolu_saatler[a.chair_id].append(a.time)

    emekli_no = request.form.get('emekli_no', '')
    aranan_name = ''
    kalan_gun = 0
    if emekli_no:
        person = Person.query.filter_by(emekli_no=emekli_no).first()
        if person:
            aranan_name = person.name
            son_randevu = Appointment.query.filter_by(emekli_no=emekli_no).order_by(Appointment.created_at.desc()).first()
            if son_randevu:
                son_tarih = son_randevu.created_at.date()
                bugun = datetime.today().date()
                fark = (bugun - son_tarih).days
                if fark < 14:
                    kalan_gun = 14 - fark
                    flash (f"{kalan_gun} gün sonra tekrar randevu alabilirsiniz!","danger")
        else:
            flash("Kullanıcı bulunamadı!", "danger")
        
            

            

    # Randevu alma işlemi (refresh butonuna basılmadıysa)
    if request.method == 'POST' and 'randevu_al'  in request.form:
        emekli_no = request.form.get('emekli_no')
        chair_id = int(request.form.get('chair_id'))
        time_ = request.form.get('time')
        person = Person.query.filter_by(emekli_no=emekli_no).first()
        if not person:
            flash("Kullanıcı bulunamadı! Randevu alınamaz.", "danger")
            return render_template('user_panel.html')
        # 14 gün kontrolü
        son = Appointment.query.filter_by(emekli_no=emekli_no).order_by(Appointment.created_at.desc()).first()
        if son and (son.created_at + timedelta(days=14) > datetime.now()):
            diff = (son.created_at + timedelta(days=14)) - datetime.now()
            flash(f"{diff.days+1} gün sonra tekrar randevu alabilirsiniz!", "danger")
            return redirect(url_for('user_panel'))
        # Koltuk/saat dolu kontrolü
        if time_ in dolu_saatler[chair_id]:
            flash("Bu koltuk ve saat dolu!", "danger")
            return redirect(url_for('user_panel'))
        # VIP saat kontrolü
        if (time_, chair_id) in vip_saatler:
            flash("Bu saat VIP olarak ayrılmıştır, admin izni gerektirir!", "danger")
            return redirect(url_for('user_panel'))
        if (time_, chair_id) in izinli_saatler:
            flash("Bu saat VIP olarak ayrılmıştır, admin izni gerektirir!", "danger")
            return redirect(url_for('user_panel'))
        appt = Appointment(
            emekli_no=emekli_no,
            name=person.name,
            chair_id=chair_id,
            date=date_display,
            time=time_
        )
        db.session.add(appt)
        db.session.commit()
        flash("Randevu başarıyla alındı.", "success")
        return redirect(url_for('user_panel') + f"?emekli_no={emekli_no}")
    
    return render_template('user_panel.html',
        chairs=chairs,
        timeslots=timeslots,
        date=date_display,
        gun=gun,
        randevu_aktif=randevu_aktif,
        dolu_saatler=dolu_saatler,
        vip_saatler=vip_saatler,
        izinli_saatler=izinli_saatler,
        emekli_no=emekli_no,
        aranan_name=aranan_name,
        kalan_gun=kalan_gun,
        secili_koltuk_id=secili_koltuk_id,
     
    )

@app.route('/api/person/<emekli_no>')
def api_person(emekli_no):
    person = Person.query.filter_by(emekli_no=emekli_no).first()
    if person:
        # Kalan gün bilgisi
        son = Appointment.query.filter_by(emekli_no=emekli_no).order_by(Appointment.created_at.desc()).first()
        kalan_gun = 0
        if son:
            diff = (son.created_at + timedelta(days=14)) - datetime.now()
            kalan_gun = diff.days if diff.days > 0 else 0
        return {"success": True, "name": person.name, "kalan_gun": kalan_gun}
    else:
        return {"success": False}

### -------------- RANDEVULARIM --------------
from datetime import datetime

@app.route('/randevularim')
def randevularim():
    emekli_no = request.args.get('emekli_no')
    if not emekli_no:
        flash("Lütfen önce emekli sandığı numaranızla arama yapınız.", "danger")
        return redirect(url_for('user_panel'))
    randevular = Appointment.query.filter_by(emekli_no=emekli_no).order_by(Appointment.date.desc(), Appointment.time).all()
    current_date = datetime.now().strftime('%d.%m.%Y')
    return render_template('randevularim.html',
                           randevular=randevular,
                           emekli_no=emekli_no,
                           current_date=current_date)


@app.route('/iptal/<int:id>', methods=['POST'])
def randevu_iptal(id):
    appt = Appointment.query.get_or_404(id)
    db.session.delete(appt)
    db.session.commit()
    flash("Randevu başarıyla iptal edildi.", "success")
      # Admin panelinden geldiyse admin_panel'e, kullanıcıdan geldiyse randevularim'e dönebiliriz
    ref = request.referrer
    if ref and "admin" in ref:
        return redirect(url_for('admin_panel'))
    return redirect(url_for('randevularim', emekli_no=appt.emekli_no))

### -------------- ADMIN LOGIN --------------
@app.route('/admin/personel_list', methods=['GET', 'POST'])
def admin_personel_list():

    if not session.get('admin'): return redirect(url_for('admin'))
    if request.method == 'POST':
        emekli_no = request.form['emekli_no'].strip()
        name = request.form['name'].strip()
        if emekli_no and name and not Person.query.filter_by(emekli_no=emekli_no).first():
            db.session.add(Person(emekli_no=emekli_no, name=name))
            db.session.commit()
            flash("Personel eklendi.", "success")
    personeller = Person.query.order_by(Person.name).all()
    return render_template('admin_personel_list.html', personeller=personeller)

@app.route('/admin/personel_sil/<int:id>', methods=['POST'])
def admin_personel_sil(id):
    if not session.get('admin'): return redirect(url_for('admin'))
    person = Person.query.get_or_404(id)
    db.session.delete(person)
    db.session.commit()
    flash("Kişi silindi.", "success")
    return redirect(url_for('admin_personel_list'))

@app.route('/admin/personel_duzenle/<int:id>', methods=['POST'])
def admin_personel_duzenle(id):
    if not session.get('admin'): return redirect(url_for('admin'))
    person = Person.query.get_or_404(id)
    name = request.form['name'].strip()
    person.name = name
    db.session.commit()
    flash("Kişi güncellendi.", "success")
    return redirect(url_for('admin_personel_list'))

@app.route('/admin/personel_import', methods=['GET', 'POST'])
def admin_personel_import():
    if not session.get('admin'): return redirect(url_for('admin'))
    if request.method == 'POST':
        file = request.files['file']
        tumunu_sil = bool(request.form.get('tumunu_sil'))
        df = pd.read_excel(file)
        if tumunu_sil:
            Person.query.delete()
            db.session.commit()
        count = 0
        for _, row in df.iterrows():
            emekli_no = str(row['EmekliNo']).strip()
            name = str(row['AdSoyad']).strip()
            if emekli_no and name and not Person.query.filter_by(emekli_no=emekli_no).first():
                db.session.add(Person(emekli_no=emekli_no, name=name))
                count += 1
        db.session.commit()
        flash(f"{count} personel eklendi.", "success")
    return render_template('admin_personel_import.html')

@app.route('/admin', methods=['GET','POST'])
def admin():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        admin = Admin.query.filter_by(username=username).first()
        if admin and admin.check_password(password):
            session['admin'] = True
            return redirect(url_for('admin_panel'))
        else:
            flash('Kullanıcı adı veya şifre yanlış!', 'danger')
    return render_template('admin_login.html')

### -------------- ADMIN PANEL --------------
@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)  # Eğer session ile admin login tutuluyorsa
    return redirect(url_for('admin'))  # Giriş ekranı route'unu kullan
@app.route('/admin/settings', methods=['GET', 'POST'])
def admin_settings():
    admin = Admin.query.first()
    if request.method == 'POST':
        old_username = request.form['current_username']
        old_password = request.form['current_password']
        new_username = request.form['new_username']
        new_password = request.form['new_password']
        new_password2 = request.form['new_password2']

        if old_username != admin.username or not admin.check_password(old_password):
            flash("Mevcut kullanıcı adı ya da şifre yanlış!", "danger")
        elif new_password != new_password2:
            flash("Yeni şifreler uyuşmuyor!", "danger")
        else:
            admin.username = new_username
            admin.set_password(new_password)
            db.session.commit()
            flash("Kullanıcı adı ve şifre başarıyla güncellendi.", "success")
            return redirect(url_for('admin_settings'))
    return render_template('admin_settings.html')



@app.route('/admin_panel')
def admin_panel():
    
    current_date = datetime.now().strftime('%d.%m.%Y')
    if not session.get('admin'):
        return redirect(url_for('admin'))

    date_filter = request.args.get('date')
    appointments = Appointment.query

    if date_filter:
        appointments = appointments.filter_by(date=date_filter)
        appointments = appointments.order_by(Appointment.date, Appointment.time).all()
    else:
        appointments = appointments.order_by(Appointment.date, Appointment.time).all()

    return render_template(
        'admin_panel.html',
        appointments=appointments,
        date_filter=date_filter,
        current_date=current_date
    )



@app.route('/admin/pdf_randevular')
def admin_pdf_randevular():
    if not session.get('admin'):
        return redirect(url_for('admin'))

    tarih = request.args.get('date')
    if not tarih:
        return "Tarih parametresi eksik!", 400

    appts = Appointment.query.filter_by(date=tarih).all()
     # Sıralama:
    appts = sorted(appts, key=lambda r: datetime.strptime(r.time, "%H:%M"))
    if not appts:
        return f"<h3>{tarih} tarihinde randevu bulunamadı.</h3>", 200

    df = pd.DataFrame([
        {'Saat': a.time, 'Ad Soyad': a.name, 'Koltuk': a.chair.name}
        for a in appts
    ])

    pdf = FPDF()
    pdf.add_page()
    pdf.add_font('DejaVu', '', 'DejaVuSans.ttf', uni=True)
    pdf.set_font('DejaVu', '', 13)
    pdf.set_text_color(0, 0, 0)

    pdf.cell(0, 12, f'{tarih} Randevuları', 0, 1, 'C')
    pdf.set_font('DejaVu', '', 11)
    pdf.cell(30, 8, "Saat", 1, 0, 'C')
    pdf.cell(80, 8, "Ad Soyad", 1, 0, 'C')
    pdf.cell(40, 8, "Koltuk", 1, 0, 'C')
    pdf.cell(30, 8, "İmza", 1, 1, 'C')

    for _, row in df.iterrows():
        pdf.cell(30, 8, f"{row['Saat']}", 1, 0)
        pdf.cell(80, 8, f"{row['Ad Soyad']}", 1, 0)
        pdf.cell(40, 8, f"{row['Koltuk']}", 1, 0) 
        pdf.cell(30, 8, "", 1, 1) 
      
    return Response(pdf.output(dest='S').encode('latin1'),
        mimetype='application/pdf',
        headers={"Content-Disposition": f"attachment;filename=randevular_{tarih}.pdf"})



### -- ADMIN: KOLTUK EKLE/SİL --
@app.route('/admin/chairs', methods=['GET','POST'])
def admin_chairs():
    if not session.get('admin'): return redirect(url_for('admin'))
    if request.method == 'POST':
        if 'ekle' in request.form:
            name = request.form['koltuk_adi'].strip()
            if name:
                db.session.add(Chair(name=name))
        elif 'sil' in request.form:
            chair_id = int(request.form['chair_id'])
            Chair.query.filter_by(id=chair_id).delete()
        db.session.commit()
        return redirect(url_for('admin_chairs'))
    chairs = Chair.query.all()
    return render_template('admin_chairs.html', chairs=chairs)

### -- ADMIN: SAAT EKLE/SİL --
@app.route('/admin/timeslots', methods=['GET','POST'])
def admin_timeslots():
    if not session.get('admin'): return redirect(url_for('admin'))
    if request.method == 'POST':
        if 'ekle' in request.form:
            saat = request.form['saat'].strip()
            if saat:
                db.session.add(Timeslot(time=saat))
        elif 'sil' in request.form:
            ts_id = int(request.form['ts_id'])
            Timeslot.query.filter_by(id=ts_id).delete()
        db.session.commit()
        return redirect(url_for('admin_timeslots'))
    timeslots = Timeslot.query.order_by(Timeslot.time).all()
    return render_template('admin_timeslots.html', timeslots=timeslots)

### -- ADMIN: VIP SAATLER YÖNET --
@app.route('/admin/vip', methods=['GET','POST'])
def admin_vip():
    if not session.get('admin'): return redirect(url_for('admin'))
    chairs = Chair.query.all()
    timeslots = Timeslot.query.all()
    if request.method == 'POST':
        if 'ekle' in request.form:
            day = request.form['day_of_week']
            time = request.form['time']
            chair_id = int(request.form['chair_id'])
            tip = request.form.get('tip')
            db.session.add(VipTimeslot(day_of_week=day, time=time, chair_id=chair_id,tip=tip))
            db.session.commit()
        elif 'sil' in request.form:
            vip_id = int(request.form['vip_id'])
            VipTimeslot.query.filter_by(id=vip_id).delete()
            db.session.commit()
        return redirect(url_for('admin_vip'))
    vips = VipTimeslot.query.all()
    return render_template('admin_vip.html', vips=vips, chairs=chairs, timeslots=timeslots, gunler=TURKCE_GUNLER)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        setup_defaults()
        app.run(host="0.0.0.0", port=5000, debug=True)
        
     
