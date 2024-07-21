document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('upload-form');
    const convertBtn = document.getElementById('convert-btn');
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');
    const fileInput = document.getElementById('file-input');

    let currentProgress = 0;
    let targetProgress = 0;

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
        currentProgress = 0;
        targetProgress = 0;
    }
});