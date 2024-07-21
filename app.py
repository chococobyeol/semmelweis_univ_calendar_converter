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

app = Flask(__name__)

task_queue = {}
task_results = {}
task_progress = {}

def fetch_classroom_info(classroom_name):
    try:
        search_url = f"https://semmelweis.hu/registrar/information/classroom-finder/?search={classroom_name}"
        res = requests.get(search_url)
        if res.status_code != 200:
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
                
                return classroom_code, classroom_details, pure_department, address_cleaned
        
        return None, None, None, None
    except Exception as e:
        print(f"Error fetching classroom info: {e}")
        return None, None, None, None

def process_calendar(temp_file_path, task_id):
    try:
        with open(temp_file_path, 'rb') as f:
            cal = Calendar.from_ical(f.read())

        new_cal = Calendar()

        total_events = len([component for component in cal.walk() if component.name == "VEVENT"])
        processed_events = 0

        for component in cal.walk():
            if component.name == "VEVENT":
                location = component.get('LOCATION')
                if location:
                    classroom_code, classroom_details, pure_department, address_cleaned = fetch_classroom_info(location)
                    if address_cleaned:
                        new_description = f"{classroom_code} - {classroom_details}\nDepartment: {pure_department}"
                        component['LOCATION'] = address_cleaned
                        component['DESCRIPTION'] = new_description
                new_cal.add_component(component)
                
                processed_events += 1
                progress = int((processed_events / total_events) * 100)
                task_progress[task_id] = progress

        output_file_path = tempfile.mktemp(suffix='.ics')
        with open(output_file_path, 'wb') as f:
            f.write(new_cal.to_ical())

        task_results[task_id] = output_file_path
    except Exception as e:
        print(f"Error processing calendar: {e}")
        task_results[task_id] = None

def worker():
    while True:
        for task_id, file_path in list(task_queue.items()):
            if task_id not in task_results:
                process_calendar(file_path, task_id)
                del task_queue[task_id]
        time.sleep(1)

# 워커 스레드 시작
threading.Thread(target=worker, daemon=True).start()

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'})
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No selected file'})
        if file and file.filename.endswith('.ics'):
            with tempfile.NamedTemporaryFile(delete=False, suffix='.ics') as temp_file:
                file.save(temp_file.name)
                temp_file_path = temp_file.name

            task_id = str(uuid.uuid4())
            task_queue[task_id] = temp_file_path
            return jsonify({'task_id': task_id})

    return render_template('index.html')

@app.route('/status/<task_id>')
def task_status(task_id):
    if task_id in task_results:
        if task_results[task_id]:
            return jsonify({'state': 'SUCCESS', 'progress': 100})
        else:
            return jsonify({'state': 'FAILURE', 'progress': 0})
    elif task_id in task_queue:
        return jsonify({'state': 'PENDING', 'progress': task_progress.get(task_id, 0)})
    else:
        return jsonify({'state': 'UNKNOWN', 'progress': 0})

@app.route('/download/<task_id>')
def download_file(task_id):
    if task_id in task_results and task_results[task_id]:
        output_file_path = task_results[task_id]
        return send_file(output_file_path, as_attachment=True, download_name='updated_calendar.ics')
    return jsonify({'error': 'File not ready or task failed'})

if __name__ == '__main__':
    app.run(debug=True)