from app import app, db, Admin

with app.app_context():
    db.create_all()
    admin = Admin(username="admin")
    admin.set_password("12345")
    db.session.add(admin)
    db.session.commit()
    print("Admin oluşturuldu!")