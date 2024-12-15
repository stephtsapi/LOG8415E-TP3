import os
from flask import Flask, request, jsonify
import requests
import logging

# Configuration des logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("gatekeeper.log"),  # Log vers un fichier
        logging.StreamHandler()                # Log vers la console
    ]
)
logger = logging.getLogger(__name__)

# Charger l'IP de l'hôte de confiance (trusted host)
TRUSTED_HOST_IP = "10.0.1.11"  # Modifiez cette valeur selon votre configuration

# Initialisation de l'application Flask
app = Flask(__name__)

@app.route('/directHit', methods=['GET'])
def direct_hit():
    response = requests.get(f"http://{TRUSTED_HOST_IP}:5000/directHit")
    return jsonify(response.json())

@app.route('/randomHit', methods=['GET'])
def random_hit():
    response = requests.get(f"http://{TRUSTED_HOST_IP}:5000/randomHit")
    return jsonify(response.json())

@app.route('/customHit', methods=['GET'])
def custom_hit():
    response = requests.get(f"http://{TRUSTED_HOST_IP}:5000/customHit")
    return jsonify(response.json())

@app.route('/addfilm', methods=['POST'])
def add_film():
    data = {
        "query": "INSERT INTO film (title, release_year, language_id, rental_rate) VALUES ('Example Movie', 1999, 1, 1)"
    }
    response = requests.post(f"http://{TRUSTED_HOST_IP}:5000/addfilm", json=data)
    return jsonify(response.json())

if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5000)
    except Exception as e:
        print(f"Échec du démarrage de l'application : {e}")