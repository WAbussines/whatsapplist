# Importowanie potrzebnych modułów
from flask import Flask, request, jsonify, redirect
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_cors import CORS
import re
from functools import wraps

# Inicjalizacja aplikacji Flask
app = Flask(__name__)

# Konfiguracja bazy danych SQLite
# Używamy bazy danych w pliku 'site.db' w folderze projektu
# Render może wymagać innej konfiguracji URI dla baz danych,
# ale dla SQLite w prostych przypadkach to powinno działać.
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Inicjalizacja SQLAlchemy
db = SQLAlchemy(app)

# Konfiguracja CORS
# Pozwoli to frontendom na komunikację z tym backendem.
CORS(app)

# ** Ustawienie hasła administracyjnego (BARDZO NIEBEZPIECZNE W PRODUKCJI!) **
ADMIN_PASSWORD = "bardzotajnehaslo123" # ZMIEŃ TO NA COŚ INNEGO!

# Definicja modelu bazy danych dla kanału
class Channel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    link = db.Column(db.String(200), nullable=False)
    last_promoted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"Channel('{self.name}', '{self.link}', '{self.last_promoted}')"

# Model bazy danych do przechowywania ogólnych logów wizyt (wejście na stronę główną)
class Visit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), nullable=False) # Wystarczająco duże na IPv6
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"Visit('{self.ip_address}', '{self.timestamp}')"

# ** Nowy model bazy danych do przechowywania logów konkretnych akcji (dodanie/promowanie) **
class ActionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    action_type = db.Column(db.String(50), nullable=False) # np. 'add', 'promote'
    channel_id = db.Column(db.Integer, nullable=True) # ID kanału, którego dotyczy akcja (może być None przy dodawaniu?)
    channel_name = db.Column(db.String(120), nullable=True) # Nazwa kanału w momencie akcji

    def __repr__(self):
        return f"ActionLog('{self.ip_address}', '{self.timestamp}', '{self.action_type}', ChannelID: {self.channel_id}, ChannelName: {self.channel_name})"


# Utworzenie tabel w bazie danych, jeśli nie istnieją
with app.app_context():
     db.create_all()

# Wzorzec wyrażenia regularnego dla walidacji linku WhatsApp Channel
WHATSAPP_CHANNEL_LINK_PATTERN = re.compile(r'^https:\/\/whatsapp\.com\/channel\/.*')

# Dekorator do ochrony endpointów hasłem
def require_admin_password(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            provided_password = auth_header.split(' ')[1]
        else:
            try:
                data = request.get_json()
                provided_password = data.get('password')
            except:
                provided_password = None

        if provided_password == ADMIN_PASSWORD:
            return view(**kwargs)
        else:
            return jsonify({'error': 'Wymagane hasło administracyjne'}), 401
    return wrapped_view

# Funkcja pomocnicza do pobierania adresu IP klienta
def get_client_ip():
    # Render (i wiele innych hostingów) używa nagłówka X-Forwarded-For
    # Jeśli ten nagłówek istnieje, bierzemy pierwszy adres IP z listy
    if 'X-Forwarded-For' in request.headers:
        # Nagłówek może zawierać listę adresów IP oddzielonych przecinkami
        ip = request.headers['X-Forwarded-For'].split(',')[0].strip()
    else:
        # W przeciwnym razie używamy adresu IP z połączenia
        ip = request.remote_addr
    return ip


# ŚCIEŻKA GŁÓWNA - PRZEKIEROWANIE DO FRONTENDU I LOGOWANIE IP (ogólna wizyta)
@app.route('/', methods=['GET'])
def home():
    # Adres URL Twojego frontendu na GitHub Pages
    FRONTEND_URL = "https://wabussines.github.io/whatsapplist" # ZASTĄP TYM SWÓJ ADRES GITHUB PAGES!

    # Zaloguj adres IP odwiedzającego jako ogólną wizytę
    ip_address = get_client_ip()
    new_visit = Visit(ip_address=ip_address, timestamp=datetime.utcnow())
    db.session.add(new_visit)
    db.session.commit()
    print(f"Zalogowano ogólną wizytę z IP: {ip_address}")

    # Zwrócenie odpowiedzi przekierowania
    return redirect(FRONTEND_URL, code=302)

# ENDPOINT DO LOGOWANIA OGÓLNYCH WIZYT Z FRONTENDU
# Frontend będzie wywoływał ten endpoint przy ładowaniu strony głównej
@app.route('/api/log_visit', methods=['POST'])
def log_visit():
    ip_address = get_client_ip()
    new_visit = Visit(ip_address=ip_address, timestamp=datetime.utcnow())
    db.session.add(new_visit)
    db.session.commit()
    print(f"Zalogowano ogólną wizytę z IP (API): {ip_address}")

    return jsonify({'message': 'Ogólna wizyta zalogowana'}), 200


# Endpoint API do dodawania nowego kanału (dostępny publicznie)
@app.route('/api/channels', methods=['POST'])
def add_channel():
    data = request.get_json()
    name = data.get('name')
    link = data.get('link')

    if not name or not link:
        return jsonify({'error': 'Nazwa i link są wymagane'}), 400

    if not WHATSAPP_CHANNEL_LINK_PATTERN.match(link):
         return jsonify({'error': 'Niepoprawny format linku WhatsApp. Musi zaczynać się od https://whatsapp.com/channel/'}), 400

    new_channel = Channel(name=name, link=link, last_promoted=datetime.utcnow())

    db.session.add(new_channel)
    # db.session.commit() # Nie commitujemy jeszcze, dodamy log akcji

    # ** Zaloguj akcję dodania kanału **
    ip_address = get_client_ip()
    # ID kanału będzie dostępne po commicie, więc logujemy po nim
    db.session.commit() # Commitujemy dodanie kanału, aby uzyskać ID
    new_action_log = ActionLog(
        ip_address=ip_address,
        timestamp=datetime.utcnow(),
        action_type='add',
        channel_id=new_channel.id,
        channel_name=new_channel.name # Zapisujemy nazwę w momencie dodania
    )
    db.session.add(new_action_log)
    db.session.commit() # Commitujemy log akcji
    print(f"Zalogowano akcję 'add' dla kanału ID {new_channel.id} z IP: {ip_address}")


    return jsonify({'message': 'Kanał dodany pomyślnie', 'channel': {'id': new_channel.id, 'name': new_channel.name, 'link': new_channel.link, 'last_promoted': new_channel.last_promoted.isoformat()}}), 201

# Endpoint API do pobierania listy kanałów (dostępny publicznie, sortowany)
@app.route('/api/channels', methods=['GET'])
def get_channels():
    channels = Channel.query.order_by(Channel.last_promoted.desc()).all()

    channels_list = []
    for channel in channels:
        channels_list.append({
            'id': channel.id,
            'name': channel.name,
            'link': channel.link,
            'lastPromoted': channel.last_promoted.isoformat()
        })

    return jsonify(channels_list), 200

# Endpoint API do promowania kanału (dostępny publicznie, wywoływany po 10 kliknięciach)
@app.route('/api/channels/<int:channel_id>/promote', methods=['POST'])
def promote_channel(channel_id):
    channel = Channel.query.get(channel_id)

    if not channel:
        return jsonify({'error': 'Kanał nie znaleziony'}), 404

    # Aktualizacja daty ostatniego promowania
    channel.last_promoted = datetime.utcnow()
    # db.session.commit() # Nie commitujemy jeszcze, dodamy log akcji

    # ** Zaloguj akcję promowania kanału **
    ip_address = get_client_ip()
    new_action_log = ActionLog(
        ip_address=ip_address,
        timestamp=datetime.utcnow(),
        action_type='promote',
        channel_id=channel.id,
        channel_name=channel.name # Zapisujemy nazwę w momencie promowania
    )
    db.session.add(new_action_log)
    db.session.commit() # Commitujemy promowanie i log akcji
    print(f"Zalogowano akcję 'promote' dla kanału ID {channel.id} z IP: {ip_address}")


    return jsonify({'message': 'Kanał promowany pomyślnie', 'channel': {'id': channel.id, 'name': channel.name, 'link': channel.link, 'last_promoted': channel.last_promoted.isoformat()}}), 200


# ** ENDPOINTY PANELU ADMINISTRACYJNEGO (WYMAGAJĄ HASŁA) **

# Endpoint API do pobierania WSZYSTKICH danych kanałów dla panelu admina
@app.route('/api/admin/channels', methods=['GET'])
@require_admin_password
def get_admin_channels():
    channels = Channel.query.order_by(Channel.id).all()

    channels_list = []
    for channel in channels:
        channels_list.append({
            'id': channel.id,
            'name': channel.name,
            'link': channel.link,
            'lastPromoted': channel.last_promoted.isoformat()
        })

    return jsonify(channels_list), 200

# Endpoint dla panelu admina - POBIERANIE OGÓLNYCH LOGÓW WIZYT
@app.route('/api/admin/visits', methods=['GET'])
@require_admin_password
def get_admin_visits():
    visits = Visit.query.order_by(Visit.timestamp.desc()).all()

    visits_list = []
    for visit in visits:
        visits_list.append({
            'id': visit.id,
            'ip_address': visit.ip_address,
            'timestamp': visit.timestamp.isoformat()
        })

    return jsonify(visits_list), 200

# ** NOWY ENDPOINT DLA PANELU ADMINA - POBIERANIE LOGÓW AKCJI **
@app.route('/api/admin/action_logs', methods=['GET'])
@require_admin_password # Ochrona hasłem
def get_admin_action_logs():
    # Pobranie wszystkich logów akcji, posortowanych malejąco według czasu
    action_logs = ActionLog.query.order_by(ActionLog.timestamp.desc()).all()

    action_logs_list = []
    for log in action_logs:
        action_logs_list.append({
            'id': log.id,
            'ip_address': log.ip_address,
            'timestamp': log.timestamp.isoformat(),
            'action_type': log.action_type,
            'channel_id': log.channel_id,
            'channel_name': log.channel_name
        })

    return jsonify(action_logs_list), 200


# Endpoint API do promowania kanału JEDNYM KLIKNIĘCIEM (dla admina)
@app.route('/api/admin/channels/<int:channel_id>/promote_one_click', methods=['POST'])
@require_admin_password
def admin_promote_channel(channel_id):
    channel = Channel.query.get(channel_id)

    if not channel:
        return jsonify({'error': 'Kanał nie znaleziony'}), 404

    channel.last_promoted = datetime.utcnow()
    db.session.commit()

    # ** Zaloguj akcję promowania przez admina **
    ip_address = get_client_ip()
    new_action_log = ActionLog(
        ip_address=ip_address,
        timestamp=datetime.utcnow(),
        action_type='admin_promote', # Nowy typ akcji dla admina
        channel_id=channel.id,
        channel_name=channel.name
    )
    db.session.add(new_action_log)
    db.session.commit()
    print(f"Zalogowano akcję 'admin_promote' dla kanału ID {channel.id} z IP: {ip_address}")


    return jsonify({'message': 'Kanał promowany pomyślnie (admin)', 'channel': {'id': channel.id, 'name': channel.name, 'link': channel.link, 'last_promoted': channel.last_promoted.isoformat()}}), 200


# Endpoint API do usuwania kanału (dla admina)
@app.route('/api/admin/channels/<int:channel_id>/delete', methods=['DELETE'])
@require_admin_password
def admin_delete_channel(channel_id):
    channel = Channel.query.get(channel_id)

    if not channel:
        return jsonify({'error': 'Kanał nie znaleziony'}), 404

    # ** Zaloguj akcję usunięcia przez admina **
    ip_address = get_client_ip()
    new_action_log = ActionLog(
        ip_address=ip_address,
        timestamp=datetime.utcnow(),
        action_type='admin_delete', # Nowy typ akcji dla admina
        channel_id=channel.id,
        channel_name=channel.name # Zapisujemy nazwę przed usunięciem
    )
    db.session.add(new_action_log)
    db.session.commit() # Commitujemy log akcji przed usunięciem kanału

    db.session.delete(channel)
    db.session.commit() # Commitujemy usunięcie kanału
    print(f"Zalogowano akcję 'admin_delete' dla kanału ID {channel.id} z IP: {ip_address}")


    return jsonify({'message': 'Kanał usunięty pomyślnie (admin)'}), 200


# Uruchomienie aplikacji Flask
if __name__ == '__main__':
    app.run(debug=True)
