document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('upload-form');
    const convertBtn = document.getElementById('convert-btn');
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');
    const fileInput = document.getElementById('file-input');
    const dropArea = document.getElementById('drop-area');
    const fileLabel = document.getElementById('file-label');
    const helpIcon = document.getElementById('help-icon');
    const helpPopup = document.getElementById('help-popup');
    const closePopup = document.getElementById('close-popup');
    const container = document.querySelector('.container');

    let currentProgress = 0;
    let targetProgress = 0;

    // 초기 로드 시 컨테이너 크기 조정
    adjustContainerSize();

    // 윈도우 리사이즈 시 컨테이너 크기 재조정
    window.addEventListener('resize', adjustContainerSize);

    function adjustContainerSize() {
        const windowWidth = window.innerWidth;
        const containerWidth = container.offsetWidth;
        if (windowWidth < containerWidth) {
            const scale = windowWidth / containerWidth;
            container.style.transform = `scale(${scale})`;
        } else {
            container.style.transform = 'none';
        }
    }

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, preventDefaults, false);
        document.body.addEventListener(eventName, preventDefaults, false);
    });

    ['dragenter', 'dragover'].forEach(eventName => {
        dropArea.addEventListener(eventName, highlight, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, unhighlight, false);
    });

    dropArea.addEventListener('drop', handleDrop, false);
    fileInput.addEventListener('change', handleFileInputChange);

    dropArea.addEventListener('click', function(e) {
        if (e.target !== fileInput) {
            e.preventDefault();
            fileInput.click();
        }
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    function highlight() {
        dropArea.classList.add('dragover');
    }

    function unhighlight() {
        dropArea.classList.remove('dragover');
    }

    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;

        // 파일 입력 필드 업데이트
        const newDt = new DataTransfer();
        newDt.items.add(files[0]);
        fileInput.files = newDt.files;

        handleFiles(files);
    }

    function handleFileInputChange(e) {
        handleFiles(e.target.files);
    }

    function handleFiles(files) {
        if (files.length > 0) {
            updateFileLabel(files[0].name);
        }
    }

    function updateFileLabel(fileName) {
        if (fileName) {
            fileLabel.innerHTML = `<span title="${fileName}">${fileName}</span>`;
        } else {
            fileLabel.innerHTML = '<span>Click to browse or<br>Drag & drop your .ics file here</span>';
        }
    }

    form.addEventListener('submit', function(e) {
        e.preventDefault();

        if (fileInput.files.length === 0) {
            alert('Please select a file to upload');
            return;
        }

        convertBtn.style.display = 'none';
        progressContainer.style.display = 'block';
        progressBar.style.width = '0%';
        progressText.textContent = 'Uploading and processing...';

        currentProgress = 0;
        targetProgress = 0;

        const formData = new FormData(form);

        fetch('/', {
            method: 'POST',
            body: formData
        }).then(response => response.json())
        .then(data => {
            if (data.task_id) {
                checkStatus(data.task_id);
            } else {
                throw new Error('No task ID received');
            }
        }).catch(error => {
            console.error('Error:', error);
            alert('An error occurred during file upload.');
            resetForm();
        });
    });

    function checkStatus(taskId) {
        fetch(`/status/${taskId}`)
        .then(response => response.json())
        .then(data => {
            if (data.state === 'SUCCESS') {
                targetProgress = 100;
                updateProgressBar();
                progressText.textContent = 'Processing complete. Downloading...';
                window.location.href = `/download/${taskId}`;
                setTimeout(resetForm, 3000);
            } else if (data.state === 'FAILURE') {
                alert('An error occurred during the conversion process.');
                resetForm();
            } else {
                targetProgress = data.progress;
                updateProgressBar();
                progressText.textContent = `Processing... ${Math.round(currentProgress)}% complete. This may take several minutes.`;
                setTimeout(() => checkStatus(taskId), 1000);
            }
        }).catch(error => {
            console.error('Error:', error);
            alert('An error occurred while checking the status.');
            resetForm();
        });
    }

    function updateProgressBar() {
        if (currentProgress < targetProgress) {
            currentProgress += (targetProgress - currentProgress) * 0.1;
            progressBar.style.width = `${currentProgress}%`;
            requestAnimationFrame(updateProgressBar);
        }
    }

    function resetForm() {
        convertBtn.style.display = 'block';
        progressContainer.style.display = 'none';
        progressBar.style.width = '0%';
        fileInput.value = '';
        updateFileLabel();
        currentProgress = 0;
        targetProgress = 0;
    }

    // Help popup event listeners
    helpIcon.addEventListener('click', function() {
        helpPopup.style.display = 'block';
    });

    closePopup.addEventListener('click', function() {
        helpPopup.style.display = 'none';
    });

    helpPopup.addEventListener('click', function(event) {
        event.stopPropagation();
    });

    window.addEventListener('click', function(event) {
        if (event.target !== helpPopup && !helpPopup.contains(event.target) && event.target !== helpIcon) {
            helpPopup.style.display = 'none';
        }
    });

    // 바이미커피 버튼 업데이트 함수
    function updateBuyMeCoffeeButton() {
        const buyMeCoffeeBtn = document.getElementById('buymeacoffee-btn');
        const timestamp = new Date().getTime(); // 현재 시간을 이용해 캐시 방지
        buyMeCoffeeBtn.src = `https://img.buymeacoffee.com/button-api/?text=Buy me a coffee&emoji=☕&slug=chococo&button_colour=ffffff&font_colour=000000&font_family=Cookie&outline_colour=000000&coffee_colour=FFDD00&t=${timestamp}`;
    }

    // 페이지 로드 시 바이미커피 버튼 업데이트
    updateBuyMeCoffeeButton();
});