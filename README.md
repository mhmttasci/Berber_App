# Berber Randevu Pro

## Kurulum

1. Python 3.10+ kurulu olduğundan emin olun.
2. Sanal ortam oluşturup aktifleştirin:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```
3. Paketleri yükleyin:
   ```bash
   pip install -r requirements.txt
   ```
4. Uygulamayı başlatın:
   ```bash
   python app.py
   ```
5. Tarayıcıdan erişin:
   - Kullanıcı: http://127.0.0.1:5000
   - Admin: http://127.0.0.1:5000/admin

## Admin
- Kullanıcı adı: `admin`
- Şifre: `12345`

## Özellikler
- Kayıt/Login zorunlu.
- Randevu yalnızca ertesi gün.
- Saatler 08:00-16:30 (öğle 12:00-13:30 boş).
- Alınan saatler pasif.
- Cihaz kısıtlaması (14 gün).
- Randevu numarası (YYYYMMDD-XXX).
- CSV export (Admin).
- E-posta & SMS template hazır.
