import os
from flask import Flask, request, jsonify
import requests
import logging

# Configuration des logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("trusted_host.log"),  # Log vers un fichier
        logging.StreamHandler()  # Log vers la console
    ]
)
logger = logging.getLogger(__name__)

# Définir l'adresse IP du proxy
PROXY_IP = "10.0.1.12"  # Modifiez avec l'IP du proxy

# Initialisation de l'application Flask
app = Flask(__name__)

# Database queries
get_query = "USE sakila; SELECT COUNT(*) FROM film;"
params = {"query": get_query}


@app.route('/directHit', methods=['GET'])
def direct_hit():
    response = requests.get(f"http://{PROXY_IP}:5000/directHit", params=params)
    return jsonify(response.json())

@app.route('/randomHit', methods=['GET'])
def random_hit():
    response = requests.get(f"http://{PROXY_IP}:5000/randomHit", params=params)
    return jsonify(response.json())

@app.route('/customHit', methods=['GET'])
def custom_hit():
    response = requests.get(f"http://{PROXY_IP}:5000/customHit", params=params)
    return jsonify(response.json())

@app.route('/addfilm', methods=['POST'])
def add_film():
    data = {
        "query": "USE sakila; INSERT INTO film (title, release_year, language_id, rental_rate) VALUES ('Example Movie', 1999, 1, 1);"
    }
    response = requests.post(f"http://{PROXY_IP}:5000/addfilm", json=data)
    return jsonify(response.json())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)