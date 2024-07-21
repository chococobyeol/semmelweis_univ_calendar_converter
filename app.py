from flask import Flask, request, render_template, send_file, jsonify
from icalendar import Calendar
import aiohttp
import asyncio
from bs4 import BeautifulSoup
import tempfile
import os
import re
import threading
import uuid
import logging
from collections import OrderedDict
from functools import lru_cache
import sqlite3
import requests
import time

app = Flask(__name__)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

MAX_TASKS = 100
task_queue = OrderedDict()
task_results = OrderedDict()
task_progress = OrderedDict()

DB_PATH = 'classrooms.db'
MAX_RETRIES = 5  # 최대 재시도 횟수
RETRY_DELAY = 5  # 재시도 대기 시간 (초)

async def fetch_classroom_info_from_db(classroom_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM classrooms WHERE classroom_code LIKE ?", (f"%{classroom_name}%",))
    result = c.fetchone()
    conn.close()
    if result:
        return result
    else:
        return None, None, None, None

async def process_calendar(temp_file_path, task_id):
    try:
        logger.debug(f"Starting to process calendar for task {task_id}")
        with open(temp_file_path, 'rb') as f:
            cal = Calendar.from_ical(f.read())

        new_cal = Calendar()

        events = [component for component in cal.walk() if component.name == "VEVENT"]
        total_events = len(events)
        processed_events = 0

        logger.debug(f"Total events to process: {total_events}")

        for component in events:
            location = component.get('LOCATION')
            if location:
                logger.debug(f"Processing event with location: {location}")
                classroom_code, classroom_details, pure_department, address_cleaned = await fetch_classroom_info_from_db(location)
                if address_cleaned:
                    new_description = f"{classroom_code} - {classroom_details}\nDepartment: {pure_department}"
                    component['LOCATION'] = address_cleaned
                    component['DESCRIPTION'] = new_description
            new_cal.add_component(component)
            
            processed_events += 1
            progress = int((processed_events / total_events) * 100)
            task_progress[task_id] = progress
            logger.debug(f"Task {task_id}: Processed {processed_events}/{total_events} events. Progress: {progress}%")

            if processed_events % 10 == 0:
                await asyncio.sleep(0.1)

        output_file_path = tempfile.mktemp(suffix='.ics')
        with open(output_file_path, 'wb') as f:
            f.write(new_cal.to_ical())

        task_results[task_id] = output_file_path
        logger.debug(f"Task {task_id} completed successfully")
    except Exception as e:
        logger.error(f"Error processing calendar for task {task_id}: {e}", exc_info=True)
        task_results[task_id] = None
    finally:
        if task_id in task_queue:
            del task_queue[task_id]

def run_worker():
    async def async_worker():
        while True:
            try:
                if task_queue:
                    logger.debug(f"Current task queue: {list(task_queue.keys())}")
                    for task_id, file_path in list(task_queue.items()):
                        if task_id not in task_results:
                            logger.debug(f"Starting to process task {task_id}")
                            await process_calendar(file_path, task_id)
                            break  # Ensure only one task is processed at a time
                else:
                    logger.debug("No tasks in queue. Worker thread sleeping.")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Error in worker thread: {e}", exc_info=True)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(async_worker())

worker_thread = threading.Thread(target=run_worker, daemon=True)
worker_thread.start()

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' not in request.files:
            logger.warning("No file part in the request")
            return jsonify({'error': 'No file part'})
        file = request.files['file']
        if file.filename == '':
            logger.warning("No selected file")
            return jsonify({'error': 'No selected file'})
        if file and file.filename.endswith('.ics'):
            logger.debug(f"Received file: {file.filename}")
            with tempfile.NamedTemporaryFile(delete=False, suffix='.ics') as temp_file:
                file.save(temp_file.name)
                temp_file_path = temp_file.name

            task_id = str(uuid.uuid4())
            task_queue[task_id] = temp_file_path
            task_progress[task_id] = 0
            
            logger.debug(f"Task queue: {task_queue}")
            
            if len(task_queue) > MAX_TASKS:
                oldest_task = next(iter(task_queue))
                del task_queue[oldest_task]
                del task_progress[oldest_task]
            
            logger.debug(f"Created task {task_id} for file {file.filename}")
            return jsonify({'task_id': task_id})

    return render_template('index.html')

@app.route('/status/<task_id>')
def task_status(task_id):
    logger.debug(f"Checking status for task {task_id}")
    if task_id in task_results:
        if task_results[task_id]:
            logger.debug(f"Task {task_id} completed successfully")
            return jsonify({'state': 'SUCCESS', 'progress': 100})
        else:
            logger.warning(f"Task {task_id} failed")
            return jsonify({'state': 'FAILURE', 'progress': 0})
    elif task_id in task_queue:
        progress = task_progress.get(task_id, 0)
        logger.debug(f"Task {task_id} is pending. Progress: {progress}%")
        return jsonify({'state': 'PENDING', 'progress': progress})
    else:
        logger.warning(f"Unknown task {task_id}")
        return jsonify({'state': 'UNKNOWN', 'progress': 0})

@app.route('/download/<task_id>')
def download_file(task_id):
    logger.debug(f"Download requested for task {task_id}")
    if task_id in task_results and task_results[task_id]:
        output_file_path = task_results[task_id]
        logger.debug(f"Sending file for task {task_id}")
        return send_file(output_file_path, as_attachment=True, download_name='updated_calendar.ics')
    logger.warning(f"File not ready or task failed for task {task_id}")
    return jsonify({'error': 'File not ready or task failed'})

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
    # Initial DB setup and update
    initialize_and_update_db()

    # Start periodic updates in the background
    update_interval = 300  # 
        # 5 minutes in seconds
    update_thread = threading.Thread(target=update_db_periodically, args=(update_interval,), daemon=True)
    update_thread.start()

    # Start the Flask app
    app.run(host='0.0.0.0', port=5001, debug=True)