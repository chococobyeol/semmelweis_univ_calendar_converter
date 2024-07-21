document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('upload-form');
    const convertBtn = document.getElementById('convert-btn');
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');
    const fileInput = document.getElementById('file-input');

    const messages = [
        "Please wait a moment until the conversion process is completed.",
        "This may take a few minutes.",
        "Once the conversion is complete, the download will automatically start."
    ];

    let messageIndex = 0;
    let progress = 0;
    let progressInterval;

    form.addEventListener('submit', function(e) {
        e.preventDefault();
        if (fileInput.files.length === 0) {
            alert('Please select a file to upload');
            return;
        }
        convertBtn.style.display = 'none';
        progressContainer.style.display = 'block';
        progress = 0;
        updateProgress();

        // Start progress simulation
        progressInterval = setInterval(() => {
            progress += 0.05; // Increase by 0.05% every second (100% in about 33 minutes)
            if (progress >= 100) {
                clearInterval(progressInterval);
                progress = 100;
            }
            progressBar.style.width = `${progress}%`;
        }, 1000);

        // 실제 파일 업로드 및 변환 프로세스
        const formData = new FormData(form);
        fetch('/', {
            method: 'POST',
            body: formData
        }).then(response => {
            if (response.ok) {
                return response.blob();
            }
            throw new Error('Network response was not ok.');
        }).then(blob => {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = 'updated_calendar.ics';
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            clearInterval(progressInterval);
            progress = 100;
            progressBar.style.width = '100%';
            progressText.textContent = 'Complete';
            progressContainer.style.display = 'none'; // Hide progress bar after completion
            convertBtn.style.display = 'block';
            convertBtn.textContent = 'Complete';
        }).catch(error => {
            console.error('Error:', error);
            alert('An error occurred during the conversion process.');
            convertBtn.style.display = 'block';
            convertBtn.textContent = 'Convert';
        }).finally(() => {
            clearInterval(progressInterval);
            progressContainer.style.display = 'none'; // Hide progress bar after error
        });
    });

    convertBtn.addEventListener('click', function() {
        if (convertBtn.textContent === 'Complete') {
            convertBtn.textContent = 'Convert';
            fileInput.value = '';
            progressContainer.style.display = 'none';
            progress = 0;
            progressBar.style.width = '0%';
            progressText.textContent = '';
        }
    });

    function updateProgress() {
        progressText.textContent = messages[messageIndex];
        messageIndex = (messageIndex + 1) % messages.length;

        if (progress < 100) {
            setTimeout(updateProgress, 3000); // Change message every 3 seconds
        }
    }
});