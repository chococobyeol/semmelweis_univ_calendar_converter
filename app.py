from flask import Flask, request, render_template, send_file, jsonify
from icalendar import Calendar
import requests
from bs4 import BeautifulSoup
import tempfile
import os
import re

app = Flask(__name__)

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
                
                # 주소 부분을 제거하고 순수한 부서 이름만 추출합니다.
                pure_department = re.sub(r'\d.*$', '', address).strip()
                pure_department = re.sub(r',.*$', '', pure_department).strip()
                
                return classroom_code, classroom_details, pure_department, address_cleaned
        
        return None, None, None, None
    except Exception as e:
        print(f"Error fetching classroom info: {e}")
        return None, None, None, None

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' not in request.files:
            return 'No file part'
        file = request.files['file']
        if file.filename == '':
            return 'No selected file'
        if file and file.filename.endswith('.ics'):
            # Create a temporary file to store the uploaded calendar
            with tempfile.NamedTemporaryFile(delete=False, suffix='.ics') as temp_file:
                file.save(temp_file.name)
                temp_file_path = temp_file.name

            # Process the calendar
            with open(temp_file_path, 'rb') as f:
                cal = Calendar.from_ical(f.read())

            new_cal = Calendar()

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

            # Save the new calendar to a temporary file
            output_file_path = tempfile.mktemp(suffix='.ics')
            with open(output_file_path, 'wb') as f:
                f.write(new_cal.to_ical())

            # Send the file
            return send_file(output_file_path, as_attachment=True, download_name='updated_calendar.ics')

    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)