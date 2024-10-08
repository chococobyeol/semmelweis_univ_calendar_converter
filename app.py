# 필요한 라이브러리 및 모듈을 임포트합니다.
import os
import re
import uuid
import time
import logging
import threading
import requests
from bs4 import BeautifulSoup
from icalendar import Calendar
from collections import OrderedDict
from flask import Flask, request, render_template, send_file, jsonify

# 로깅 설정을 구성하고 로거를 초기화합니다.
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# 최대 작업 수와 작업 큐 및 결과를 저장할 자료 구조를 설정합니다.
MAX_TASKS = 100
task_queue = OrderedDict()
task_results = OrderedDict()
task_progress = OrderedDict()
queue_lock = threading.Lock()

# 교실 데이터를 저장할 리스트 초기화
CLASSROOM_DATA = []  # 메모리에 교실 데이터를 저장

# 최대 재시도 횟수 및 재시도 간격 설정
MAX_RETRIES = 5
RETRY_DELAY = 5

# 교실 정보를 가져오는 함수
def fetch_classroom_info(classroom_name, partial_search=False):
    logger.debug(f"Searching for classroom: {classroom_name} with partial_search={partial_search}")
    
    # 최소 검색 길이를 5글자로 설정합니다
    MIN_SEARCH_LENGTH = 5
    
    for classroom in CLASSROOM_DATA:
        if classroom_name in classroom[0]:
            logger.debug(f"Found match: {classroom}")
            return classroom
    
    # 부분 검색을 허용하고, 현재 검색 길이가 최소 검색 길이보다 길 때만 재귀 호출
    if partial_search and len(classroom_name) > MIN_SEARCH_LENGTH:
        return fetch_classroom_info(classroom_name[:-1], partial_search=True)
    
    logger.debug(f"No match found for classroom: {classroom_name}")
    return None, None, None, None

# 달력을 처리하는 함수
def process_calendar(temp_file_path, task_id):
    try:
        logger.debug(f"Starting to process calendar for task {task_id}")
        with open(temp_file_path, 'rb') as f:
            cal = Calendar.from_ical(f.read())

        new_cal = Calendar()

        # VEVENT 컴포넌트를 추출
        events = [component for component in cal.walk() if component.name == "VEVENT"]
        total_events = len(events)
        processed_events = 0

        logger.debug(f"Total events to process: {total_events}")

        # 각 이벤트를 처리
        for component in events:
            location = component.get('LOCATION')
            if location:
                logger.debug(f"Processing event with location: {location}")
                classroom_code, classroom_details, pure_department, address_cleaned = fetch_classroom_info(location)
                if not address_cleaned:
                    # 정확한 매칭이 없을 때, 부분 검색 시도
                    classroom_code, classroom_details, pure_department, address_cleaned = fetch_classroom_info(location, partial_search=True)
                    if address_cleaned:
                        location_display = f"*({location}){classroom_code}"
                    else:
                        location_display = location
                else:
                    location_display = classroom_code

                if address_cleaned:
                    new_description = f"{location_display} - {classroom_details}\nDepartment: {pure_department}"
                    component['LOCATION'] = address_cleaned
                    component['DESCRIPTION'] = new_description
                    logger.debug(f"Updated location: {address_cleaned}")
                    logger.debug(f"Updated description: {new_description}")
                else:
                    logger.debug(f"No matching classroom info found for location: {location}")
            new_cal.add_component(component)
            
            processed_events += 1
            progress = int((processed_events / total_events) * 100)
            task_progress[task_id] = progress
            logger.debug(f"Task {task_id}: Processed {processed_events}/{total_events} events. Progress: {progress}%")

            if processed_events % 10 == 0:
                time.sleep(0.1)

        output_file_path = os.path.join('/tmp', f'{task_id}_output.ics')
        with open(output_file_path, 'wb') as f:
            f.write(new_cal.to_ical())

        task_results[task_id] = output_file_path
        logger.debug(f"Task {task_id} completed successfully")
    except Exception as e:
        logger.error(f"Error processing calendar for task {task_id}: {e}", exc_info=True)
        task_results[task_id] = None
    finally:
        with queue_lock:
            if task_id in task_queue:
                del task_queue[task_id]

# 교실 데이터를 가져오는 함수
def fetch_classroom_data():
    url = "https://semmelweis.hu/registrar/information/classroom-finder/"
    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"Fetching classroom data, attempt {attempt + 1}/{MAX_RETRIES}")
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            logger.info("Successfully fetched classroom data")
            return response.text
        except requests.RequestException as e:
            logger.error(f"Error fetching data: {e}")
            if attempt < MAX_RETRIES - 1:
                logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
            else:
                logger.error("Maximum retries reached. Failed to fetch data.")
    return None

# 교실 데이터를 파싱하는 함수
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

# 데이터를 초기화하고 업데이트하는 함수
def initialize_and_update_data():
    global CLASSROOM_DATA
    logger.info("Starting classroom data initialization and update")
    html = fetch_classroom_data()
    if html:
        CLASSROOM_DATA = parse_classroom_data(html)
        logger.info(f"Classroom data updated with {len(CLASSROOM_DATA)} records")
        logger.debug(f"Sample classroom data: {CLASSROOM_DATA[:5]}")
    else:
        logger.error("Failed to fetch classroom data after multiple retries.")
    logger.info("Classroom data initialization and update completed")

# 주기적으로 데이터를 업데이트하는 함수
def update_data_periodically(interval):
    while True:
        initialize_and_update_data()
        logger.info(f"Sleeping for {interval} seconds before the next update.")
        time.sleep(interval)

# Flask 애플리케이션을 생성하는 함수
def create_app():
    app = Flask(__name__)

    def initialize_data():
        logger.info("Initializing application data...")
        initialize_and_update_data()
        
        # 데이터가 로드될 때까지 대기
        timeout = 60  # 60초 타임아웃
        start_time = time.time()
        while not CLASSROOM_DATA:
            if time.time() - start_time > timeout:
                logger.error("Timeout while waiting for classroom data to be loaded.")
                break
            logger.info("Waiting for classroom data to be loaded...")
            time.sleep(5)
        
        if CLASSROOM_DATA:
            logger.info(f"Classroom data loaded with {len(CLASSROOM_DATA)} records")
        else:
            logger.error("Failed to load classroom data")

        # 주기적인 업데이트 스레드 시작
        update_interval = 3600  # 1시간(3600초)
        update_thread = threading.Thread(target=update_data_periodically, args=(update_interval,), daemon=True)
        update_thread.start()

    # 애플리케이션 생성 시 데이터 초기화
    initialize_data()

    @app.route('/', methods=['GET', 'POST'])
    def index():
        global task_queue
        if request.method == 'POST':
            logger.debug("POST request received")
            if 'file' not in request.files:
                logger.warning("No file part in the request")
                return jsonify({'error': 'No file part'})
            file = request.files['file']
            logger.debug(f"File received: {file.filename}")
            if file.filename == '':
                logger.warning("No selected file")
                return jsonify({'error': 'No selected file'})
            if file and file.filename.endswith('.ics'):
                logger.debug(f"Processing file: {file.filename}")
                try:
                    temp_file_path = os.path.join('/tmp', f'{uuid.uuid4()}.ics')
                    file.save(temp_file_path)
                    logger.debug(f"File saved to temporary path: {temp_file_path}")
                    
                    task_id = str(uuid.uuid4())
                    with queue_lock:
                        task_queue[task_id] = temp_file_path
                        task_progress[task_id] = 0
                    
                    logger.debug(f"Task created: {task_id}")
                    logger.debug(f"Current task queue: {task_queue}")
                    
                    if len(task_queue) > MAX_TASKS:
                        oldest_task = next(iter(task_queue))
                        del task_queue[oldest_task]
                        del task_progress[oldest_task]
                    
                    # 새로운 스레드에서 달력 처리를 즉시 시작
                    threading.Thread(target=process_calendar, args=(temp_file_path, task_id)).start()
                    
                    return jsonify({'task_id': task_id})
                except Exception as e:
                    logger.error(f"Error processing file: {e}", exc_info=True)
                    return jsonify({'error': 'Error processing file'})

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

    return app

# Flask 앱을 생성
app = create_app()

# 애플리케이션이 직접 실행될 때 실행
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=False)