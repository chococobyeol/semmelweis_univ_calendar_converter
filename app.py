from flask import Flask, request, render_template, send_file, jsonify
from icalendar import Calendar
import requests
from bs4 import BeautifulSoup
import tempfile
import os
import re
import threading
import uuid
import time
import logging
from collections import OrderedDict

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_TASKS = 100
task_queue = OrderedDict()
task_results = OrderedDict()
task_progress = OrderedDict()

def fetch_classroom_info(classroom_name):
    try:
        search_url = f"https://semmelweis.hu/registrar/information/classroom-finder/?search={classroom_name}"
        logger.info(f"Fetching info for classroom: {classroom_name}")
        res = requests.get(search_url, timeout=10)  # 10초 타임아웃 설정
        if res.status_code != 200:
            logger.warning(f"Failed to fetch info for {classroom_name}. Status code: {res.status_code}")
            return None, None, None, None
        
        soup = BeautifulSoup(res.text, 'html.parser')
        results = soup.select("#tablepress-16 > tbody > tr")
        
        for result in results:
            department = result.select_one("td.column-1").get_text(strip=True)
            address = result.select_one("td.column-2").get_text(strip=True)
            if classroom_name.lower().replace(' ', '') in department.lower().replace(' ', ''):
                address_match = re.search(r'\d.*', address)
                address_cleaned = address_match.group() if address_match else address
                
                department_parts = department.split(' - ', 1)
                classroom_code = department_parts[0]
                classroom_details = department_parts[1] if len(department_parts) > 1 else ""
                
                pure_department = re.sub(r'\d.*$', '', address).strip()
                pure_department = re.sub(r',.*$', '', pure_department).strip()
                
                logger.info(f"Info found for {classroom_name}: {classroom_code}, {classroom_details}, {pure_department}, {address_cleaned}")
                return classroom_code, classroom_details, pure_department, address_cleaned
        
        logger.warning(f"No matching info found for {classroom_name}")
        return None, None, None, None
    except requests.Timeout:
        logger.error(f"Timeout occurred while fetching info for {classroom_name}")
        return None, None, None, None
    except Exception as e:
        logger.error(f"Error fetching classroom info for {classroom_name}: {e}")
        return None, None, None, None

def process_calendar(temp_file_path, task_id):
    try:
        logger.info(f"Starting to process calendar for task {task_id}")
        with open(temp_file_path, 'rb') as f:
            cal = Calendar.from_ical(f.read())

        new_cal = Calendar()

        total_events = len([component for component in cal.walk() if component.name == "VEVENT"])
        processed_events = 0

        logger.info(f"Total events to process: {total_events}")

        for component in cal.walk():
            if component.name == "VEVENT":
                location = component.get('LOCATION')
                if location:
                    logger.info(f"Processing event with location: {location}")
                    classroom_code, classroom_details, pure_department, address_cleaned = fetch_classroom_info(location)
                    if address_cleaned:
                        new_description = f"{classroom_code} - {classroom_details}\nDepartment: {pure_department}"
                        component['LOCATION'] = address_cleaned
                        component['DESCRIPTION'] = new_description
                new_cal.add_component(component)
                
                processed_events += 1
                progress = int((processed_events / total_events) * 100)
                task_progress[task_id] = progress
                logger.info(f"Task {task_id}: Processed {processed_events}/{total_events} events. Progress: {progress}%")

        output_file_path = tempfile.mktemp(suffix='.ics')
        with open(output_file_path, 'wb') as f:
            f.write(new_cal.to_ical())

        task_results[task_id] = output_file_path
        logger.info(f"Task {task_id} completed successfully")
    except Exception as e:
        logger.error(f"Error processing calendar for task {task_id}: {e}")
        task_results[task_id] = None
    finally:
        if task_id in task_queue:
            del task_queue[task_id]

def worker():
    while True:
        try:
            for task_id, file_path in list(task_queue.items()):
                if task_id not in task_results:
                    logger.info(f"Starting to process task {task_id}")
                    process_calendar(file_path, task_id)
            time.sleep(1)
        except Exception as e:
            logger.error(f"Error in worker thread: {e}")

worker_thread = threading.Thread(target=worker, daemon=True)
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
            logger.info(f"Received file: {file.filename}")
            with tempfile.NamedTemporaryFile(delete=False, suffix='.ics') as temp_file:
                file.save(temp_file.name)
                temp_file_path = temp_file.name

            task_id = str(uuid.uuid4())
            task_queue[task_id] = temp_file_path
            task_progress[task_id] = 0
            
            if len(task_queue) > MAX_TASKS:
                oldest_task = next(iter(task_queue))
                del task_queue[oldest_task]
                del task_progress[oldest_task]
            
            logger.info(f"Created task {task_id} for file {file.filename}")
            return jsonify({'task_id': task_id})

    return render_template('index.html')

@app.route('/status/<task_id>')
def task_status(task_id):
    logger.info(f"Checking status for task {task_id}")
    if task_id in task_results:
        if task_results[task_id]:
            logger.info(f"Task {task_id} completed successfully")
            return jsonify({'state': 'SUCCESS', 'progress': 100})
        else:
            logger.warning(f"Task {task_id} failed")
            return jsonify({'state': 'FAILURE', 'progress': 0})
    elif task_id in task_queue:
        progress = task_progress.get(task_id, 0)
        logger.info(f"Task {task_id} is pending. Progress: {progress}%")
        return jsonify({'state': 'PENDING', 'progress': progress})
    else:
        logger.warning(f"Unknown task {task_id}")
        return jsonify({'state': 'UNKNOWN', 'progress': 0})

@app.route('/download/<task_id>')
def download_file(task_id):
    logger.info(f"Download requested for task {task_id}")
    if task_id in task_results and task_results[task_id]:
        output_file_path = task_results[task_id]
        logger.info(f"Sending file for task {task_id}")
        return send_file(output_file_path, as_attachment=True, download_name='updated_calendar.ics')
    logger.warning(f"File not ready or task failed for task {task_id}")
    return jsonify({'error': 'File not ready or task failed'})

if __name__ == '__main__':
    app.run(debug=True)