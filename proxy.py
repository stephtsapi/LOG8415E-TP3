import random
import time
import mysql.connector
from flask import Flask, request, jsonify
import logging
import os
import re
import subprocess
import requests
import ssl

# Configuration des logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("proxy.log"),  # Log vers un fichier
        logging.StreamHandler()           # Log vers la console
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Liste des nœuds MySQL
MYSQL_MANAGER = {"host": "10.0.1.13", "port": 3306, "user": "ubuntu", "password": "ubuntu", "database": "sakila"}
MYSQL_WORKERS = [
    {"host": "10.0.1.14", "port": 3306, "user": "ubuntu", "password": "ubuntu", "database": "sakila"}, 
    {"host": "10.0.1.15", "port": 3306, "user": "ubuntu", "password": "ubuntu", "database": "sakila"},
]

def ping_host(host):
    """Ping a host once and return the latency."""
    try:
        # Use the ping command for a single ping
        output = subprocess.run(
            ["ping", "-c", "1", host],  # Use -n for Windows
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        
        # Extract latency from output using regex
        latency = re.search(r'time=([\d.]+) ms', output.stdout)
        if latency:
            print(f"Latency for {host}: {latency.group(1)} ms")
        else:
            print(f"No latency information available for {host}.")
        
        return float(latency.group(1))
    except subprocess.CalledProcessError:
        print(f"Failed to ping {host}.")
        return False

def manager_connection():
    """Establish a connection to the master database."""
    try:
        connection = mysql.connector.connect(
            host=MYSQL_MANAGER['host'],
            port=MYSQL_MANAGER['port'],
            user=MYSQL_MANAGER['user'],
            password=MYSQL_MANAGER['password'],
            database=MYSQL_MANAGER['database'],
            ssl_disabled=True  # Disable SSL if not needed
        )
        return connection
    except mysql.connector.Error as err:
        logger.error(f"Error connecting to master database: {err}")
        return None
    
def workers_connection():
    connections = []
    for worker in MYSQL_WORKERS:
        try:
            connection = mysql.connector.connect(
                host=worker['host'],
                port=worker['port'],
                user=worker['user'],
                password=worker['password'],
                database=worker['database'],
                ssl_disabled=True  # Disable SSL if not needed
            )
            connections.append(connection)
        except mysql.connector.Error as err:
            logger.error(f"Error connecting to worker {worker['host']}: {err}")
    return connections

def disconnect_all(connections):
    for connection in connections:
        connection.close()

def find_fastest_slaves():
    """Find the fastest slave by latency and return its configuration."""
    slave_connections = workers_connection()
    if not slave_connections:
        logger.warning("No slaves available for random query.")
        return None

    fastest_slave = None
    lowest_latency = float('inf')

    for worker in MYSQL_WORKERS:
        latency = ping_host(worker['host'])
        if latency is not None and latency < lowest_latency:
            lowest_latency = latency
            fastest_slave = worker

    if fastest_slave:
        logger.info(f"Fastest slave is at {fastest_slave['host']} with latency {lowest_latency} ms")
    else:
        logger.warning("No available slaves to determine the fastest one.")
    
    return fastest_slave

def write(query, data=""):
    connection = None
    slave_connections = None
    try:
        # If data is passed, execute the query with the data tuple
        connection = manager_connection()
        if connection is None:
            return {"message": "Failed to connect to master database."}
        
        cursor = connection.cursor()
        if data:  # Only pass data if it's provided
            cursor.execute(query, data, multi=True)  # Passing query and data tuple correctly
        else:
            cursor.execute(query, multi=True)  # Execute without data if not provided
        connection.commit()
        logger.info("Added item to master database.")

        # Sync with slave databases asynchronously
        slave_connections = workers_connection()
        if not slave_connections:
            return {"message": "Failed to connect to slave databases."}
        
        for slave_connection in slave_connections:
            sync_with_slave(slave_connection, query, data)

        return {"message": "Item added to master database and syncing initiated with all slave databases."}
    except Exception as e:
        if connection:
            connection.rollback()  # Rollback if needed (in case of errors before commit)
        logger.error(f"Failed to add item to master database: {str(e)}")
        return {"message": f"Failed to add item to master database: {str(e)}"}
    finally:
        if connection:
            connection.close()
        if slave_connections:
            disconnect_all(slave_connections)

def sync_with_slave(connection, query, data):
    """Sync the data with the given slave connection."""
    try:
        cursor = connection.cursor()
        cursor.execute(query, data)
        connection.commit()  # Commit changes to the slave database
        logger.info(f"Synced data with slave database: {connection}")
    except Exception as e:
        # Handle any exceptions that occur during the sync
        connection.rollback()  # Rollback changes if the sync fails
        logger.error(f"Failed to sync with slave database: {str(e)}")
    finally:
        cursor.close()

def execute_query(connection, query, data=None):
    """Execute a simple query asynchronously with optional parameters."""
    try:
        cursor = connection.cursor()
        if data:  # Check if data is provided (for queries requiring parameters)
            for result in cursor.execute(query, data, multi=True):
                if result.with_rows:
                    result_set = result.fetchall()
                    logger.info(f"Executed query: {query}, Result: {result_set}")
                    return result_set
        else:
            for result in cursor.execute(query, multi=True):  # Execute without parameters for simple queries
                if result.with_rows:
                    result_set = result.fetchall()
                    logger.info(f"Executed query: {query}, Result: {result_set}")
                    return result_set
        logger.info(f"Executed query: {query}, No result set to fetch from.")
        return None
    except mysql.connector.Error as err:
        logger.error(f"Erreur MySQL : {err}")
        return None
    finally:
        cursor.close()
        
def direct_hit(query):
    """Execute a query directly on the master database."""
    logger.info("Direct Hit on Master:")
    connection = manager_connection()
    if connection is None:
        return {"message": "Failed to connect to master database."}
    result = execute_query(connection, query)
    connection.close()
    return result

def random_slave_query(query):
    """Execute a query on a randomly chosen slave."""
    slave_connections = workers_connection()
    if not slave_connections:
        logger.warning("No slaves available for random query.")
        return {"error": "No slaves available."}  # Return an error message

    chosen_slave = random.choice(slave_connections)
    logger.info(f"Random query on slave at {chosen_slave.server_host}:")
    result = execute_query(chosen_slave, query)
    disconnect_all(slave_connections)
    return result

def customized_query(query):
    """Execute a customized query on the fastest slave."""
    fastest_slave = find_fastest_slaves()
    if not fastest_slave:
        logger.warning("No fastest slave found for customized query.")
        return {"error": "No fastest slave available."}

    try:
        connection = mysql.connector.connect(
            host=fastest_slave['host'],
            port=fastest_slave['port'],
            user=fastest_slave['user'],
            password=fastest_slave['password'],
            database=fastest_slave['database'],
            ssl_disabled=True  # Disable SSL if not needed
        )
        result = execute_query(connection, query)
        logger.info(f"Customized query on fastest slave at {fastest_slave['host']}: {result}")
        return result
    except mysql.connector.Error as err:
        logger.error(f"Erreur MySQL : {err}")
        return {"error": str(err)}
    finally:
        if connection:
            connection.close()

@app.route('/')
def root():
    return {"message": "test"}

@app.route('/directHit', methods=['GET'])
def handle_direct_hit():
    query = "USE sakila; SELECT COUNT(*) FROM film;"
    result = direct_hit(query)
    return jsonify(result)

@app.route('/randomHit', methods=['GET'])
def handle_random_hit():
    query = "USE sakila; SELECT COUNT(*) FROM film;"
    result = random_slave_query(query)
    return jsonify(result)

@app.route('/customHit', methods=['GET'])
def handle_custom_hit():
    query = "USE sakila; SELECT COUNT(*) FROM film;"
    result = customized_query(query)
    return jsonify(result)

@app.route('/addfilm', methods=['POST'])
def handle_add_film():
    data = {
        "query": "USE sakila; INSERT INTO film (title, release_year, language_id, rental_rate) VALUES ('Example Movie', 1999, 1, 1);"
    }
    result = write(data['query'])
    return jsonify(result)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)