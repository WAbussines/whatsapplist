# Importowanie potrzebnych modułów
from flask import Flask, request, jsonify, redirect, url_for # Dodano redirect i url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_cors import CORS # Importowanie CORS do obsługi żądań z frontendu
import re # Importowanie modułu do wyrażeń regularnych (do walidacji linku)

# Inicjalizacja aplikacji Flask
app = Flask(__name__)

# Konfiguracja bazy danych SQLite
# Używamy bazy danych w pliku 'site.db' w folderze projektu
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # Wyłączenie śledzenia modyfikacji (opcjonalne, ale zalecane)

# Inicjalizacja SQLAlchemy
db = SQLAlchemy(app)

# Konfiguracja CORS
# Pozwoli to frontendowi działającemu na innym adresie (np. localhost lub GitHub Pages)
# na komunikację z tym backendem. W środowisku produkcyjnym
# warto ograniczyć CORS tylko do zaufanych domen.
CORS(app)

# Definicja modelu bazy danych dla kanału
class Channel(db.Model):
    # Unikalny identyfikator kanału
    id = db.Column(db.Integer, primary_key=True)
    # Nazwa kanału
    name = db.Column(db.String(120), nullable=False)
    # Link do kanału WhatsApp (powinien być unikalny, ale na potrzeby przykładu nie dajemy unique=True)
    link = db.Column(db.String(200), nullable=False)
    # Data i czas ostatniego promowania. Domyślnie ustawiane na bieżący czas.
    last_promoted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Metoda reprezentująca obiekt jako string (przydatne do debugowania)
    def __repr__(self):
        return f"Channel('{self.name}', '{self.link}', '{self.last_promoted}')"

# Utworzenie tabeli w bazie danych, jeśli nie istnieje
# To powinno zostać wykonane raz, np. przy pierwszym uruchomieniu aplikacji
# Można to zrobić ręcznie w konsoli Pythona lub uruchomić ten skrypt
with app.app_context():
     db.create_all()

# Wzorzec wyrażenia regularnego dla walidacji linku WhatsApp Channel
WHATSAPP_CHANNEL_LINK_PATTERN = re.compile(r'^https:\/\/whatsapp\.com\/channel\/.*')

# ** ZMODYFIKOWANA ŚCIEŻKA GŁÓWNA - PRZEKIEROWANIE **
@app.route('/', methods=['GET'])
def home():
    # ** WAŻNE: Zmień ten URL na rzeczywisty adres URL swojego frontendu (np. na GitHub Pages) **
    FRONTEND_URL = "https://twojanazwauzytkownika.github.io/nazwa-twojego-repozytorium/" # ZASTĄP TEN PLACEHOLDER!

    # Zwrócenie odpowiedzi przekierowania (status 302 Found)
    return redirect(FRONTEND_URL, code=302)


# Endpoint API do dodawania nowego kanału
@app.route('/api/channels', methods=['POST'])
def add_channel():
    # Pobranie danych z żądania POST w formacie JSON
    data = request.get_json()
    name = data.get('name')
    link = data.get('link')

    # Walidacja danych
    if not name or not link:
        return jsonify({'error': 'Nazwa i link są wymagane'}), 400 # Zwrócenie błędu 400 (Bad Request)

    # Walidacja formatu linku po stronie backendu (zalecane!)
    if not WHATSAPP_CHANNEL_LINK_PATTERN.match(link):
         return jsonify({'error': 'Niepoprawny format linku WhatsApp. Musi zaczynać się od https://whatsapp.com/channel/'}), 400


    # Utworzenie nowego obiektu kanału
    # Nowy kanał jest domyślnie promowany (ma bieżącą datę promowania)
    new_channel = Channel(name=name, link=link, last_promoted=datetime.utcnow())

    # Dodanie kanału do sesji bazy danych i zatwierdzenie zmian
    db.session.add(new_channel)
    db.session.commit()

    # Zwrócenie odpowiedzi sukcesu
    return jsonify({'message': 'Kanał dodany pomyślnie', 'channel': {'id': new_channel.id, 'name': new_channel.name, 'link': new_channel.link, 'last_promoted': new_channel.last_promoted.isoformat()}}), 201 # Zwrócenie statusu 201 (Created)

# Endpoint API do pobierania listy kanałów
@app.route('/api/channels', methods=['GET'])
def get_channels():
    # Pobranie wszystkich kanałów z bazy danych i posortowanie ich
    # Sortowanie malejąco według daty ostatniego promowania
    channels = Channel.query.order_by(Channel.last_promoted.desc()).all()

    # Przygotowanie danych do zwrócenia w formacie JSON
    channels_list = []
    for channel in channels:
        channels_list.append({
            'id': channel.id,
            'name': channel.name,
            'link': channel.link,
            'lastPromoted': channel.last_promoted.isoformat() # Formatowanie daty do ISO 8601
        })

    # Zwrócenie listy kanałów w formacie JSON
    return jsonify(channels_list), 200 # Zwrócenie statusu 200 (OK)

# Endpoint API do promowania kanału
# Ten endpoint jest wywoływany PRZEZ FRONTEND po 10 kliknięciach
@app.route('/api/channels/<int:channel_id>/promote', methods=['POST'])
def promote_channel(channel_id):
    # Znalezienie kanału po ID
    channel = Channel.query.get(channel_id)

    # Sprawdzenie, czy kanał istnieje
    if not channel:
        return jsonify({'error': 'Kanał nie znaleziony'}), 404 # Zwrócenie błędu 404 (Not Found)

    # Aktualizacja daty ostatniego promowania na bieżący czas
    # To jest "promocja" w bazie danych, która zmienia kolejność na liście
    channel.last_promoted = datetime.utcnow()

    # Zatwierdzenie zmian w bazie danych
    db.session.commit()

    # Zwrócenie odpowiedzi sukcesu z zaktualizowanymi danymi kanału
    return jsonify({'message': 'Kanał promowany pomyślnie', 'channel': {'id': channel.id, 'name': channel.name, 'link': channel.link, 'last_promoted': channel.last_promoted.isoformat()}}), 200 # Zwrócenie statusu 200 (OK)


# Uruchomienie aplikacji Flask w trybie debugowania
# debug=True powoduje automatyczne przeładowanie serwera po zmianach w kodzie
# W środowisku produkcyjnym debug=False
if __name__ == '__main__':
    # Render uruchamia aplikację za pomocą Gunicorna, więc ten blok
    # jest głównie do testowania lokalnego.
    app.run(debug=True)
