import requests
import sqlite3
import logging
from bs4 import BeautifulSoup
import re
import time
import threading

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

DB_PATH = 'classrooms.db'
MAX_RETRIES = 5  # 최대 재시도 횟수
RETRY_DELAY = 5  # 재시도 대기 시간 (초)

def fetch_classroom_data():
    url = "https://semmelweis.hu/registrar/information/classroom-finder/"
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, timeout=60)
            response.raise_for_status()  # 상태 코드가 200이 아닐 경우 예외 발생
            return response.text
        except requests.RequestException as e:
            logger.error(f"Error fetching data: {e}")
            logger.debug(f"Retrying in {RETRY_DELAY} seconds... (Attempt {attempt + 1}/{MAX_RETRIES})")
            time.sleep(RETRY_DELAY)
    logger.error("Maximum retries reached. Failed to fetch data.")
    return None

def parse_classroom_data(html):
    soup = BeautifulSoup(html, 'html.parser')
    results = soup.select("#tablepress-16 > tbody > tr")
    data = []

    for result in results:
        department = result.select_one("td.column-1").get_text(strip=True)
        address = result.select_one("td.column-2").get_text(strip=True)
        address_match = re.search(r'\d.*', address)
        address_cleaned = address_match.group() if address_match else address
        
        department_parts = department.split(' - ', 1)
        classroom_code = department_parts[0]
        classroom_details = department_parts[1] if len(department_parts) > 1 else ""
        
        pure_department = re.sub(r'\d.*$', '', address).strip()
        pure_department = re.sub(r',.*$', '', pure_department).strip()
        
        data.append((classroom_code, classroom_details, pure_department, address_cleaned))
    
    return data

def initialize_database():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS classrooms (
                 classroom_code TEXT,
                 classroom_details TEXT,
                 pure_department TEXT,
                 address_cleaned TEXT)''')
    conn.commit()
    conn.close()

def update_database(data):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM classrooms')
    c.executemany('INSERT INTO classrooms VALUES (?, ?, ?, ?)', data)
    conn.commit()
    conn.close()

def initialize_and_update_db():
    initialize_database()
    logger.debug("Fetching classroom data...")
    html = fetch_classroom_data()
    if html:
        data = parse_classroom_data(html)
        update_database(data)
        logger.debug("Database initialized and updated successfully.")
    else:
        logger.error("Failed to fetch classroom data after multiple retries.")

def update_db_periodically(interval):
    while True:
        initialize_and_update_db()
        logger.debug(f"Sleeping for {interval} seconds before the next update.")
        time.sleep(interval)

if __name__ == '__main__':
    update_interval = 1800  # 30 minutes in seconds
    update_thread = threading.Thread(target=update_db_periodically, args=(update_interval,), daemon=True)
    update_thread.start()

    # Keep the main thread alive to allow the background thread to run
    while True:
        time.sleep(60)