document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('scraper-form');
    const startBtn = document.getElementById('start-btn');
    const stopBtn = document.getElementById('stop-btn');
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');
    const terminalOutput = document.getElementById('terminal-output');
    const clearLogBtn = document.getElementById('clear-log-btn');

    let isRunning = false;
    let eventSource = null;

    // Helper to log to the terminal UI
    const logToTerminal = (message, isHtml = false) => {
        const line = document.createElement('div');
        if (isHtml) {
            line.innerHTML = message;
        } else {
            line.textContent = message;
        }
        
        terminalOutput.appendChild(line);
        terminalOutput.scrollTop = terminalOutput.scrollHeight;
    };

    // Update UI State
    const setRunningState = (running) => {
        isRunning = running;
        startBtn.disabled = running;
        stopBtn.disabled = !running;
        
        if (running) {
            statusDot.className = 'dot running';
            statusText.textContent = 'Scraping...';
            startBtn.innerHTML = '<span class="icon spinner">↻</span> Running';
        } else {
            statusDot.className = 'dot idle';
            statusText.textContent = 'Ready';
            startBtn.innerHTML = '<span class="icon">▶</span> Start Scraping';
            
            // Close SSE connection if exists
            if (eventSource) {
                eventSource.close();
                eventSource = null;
            }
        }
    };

    // Form Submission
    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        // Basic Validation
        const hashtags = document.getElementById('hashtags').value.trim();
        const usernames = document.getElementById('usernames').value.trim();
        
        if (!hashtags && !usernames) {
            alert('Please provide either target hashtags or specific usernames.');
            return;
        }

        const payload = {
            hashtags: hashtags || null,
            usernames: usernames || null,
            minFollowers: document.getElementById('minFollowers').value,
            outputFile: document.getElementById('outputFile').value.trim() || null,
            resetCheckpoint: document.getElementById('resetCheckpoint').checked,
            dryRun: document.getElementById('dryRun').checked
        };

        try {
            logToTerminal('\n=============================================');
            logToTerminal(`Starting Scrape Request...`);
            
            const response = await fetch('/api/scrape', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.error || 'Failed to start scraping');
            }

            setRunningState(true);
            startLogStream();

        } catch (error) {
            logToTerminal(`<span style="color: #ff4b4b;">Error: ${error.message}</span>`, true);
            setRunningState(false);
        }
    });

    // Handle SSE Streaming for real-time logs
    const startLogStream = () => {
        eventSource = new EventSource('/api/stream');

        eventSource.onmessage = (event) => {
            const data = event.data;
            
            if (data === '[PROCESS_COMPLETE]') {
                logToTerminal('\n=============================================');
                logToTerminal('Process completed successfully.');
                setRunningState(false);
                return;
            }

            // Simple colorful formatting for log levels
            let formattedLine = data;
            if (data.includes('DEBUG')) formattedLine = `<span style="color: #00d2ff;">${data}</span>`;
            else if (data.includes('INFO')) formattedLine = `<span style="color: #3b82f6;">${data}</span>`;
            else if (data.includes('WARNING')) formattedLine = `<span style="color: #fbbf24;">${data}</span>`;
            else if (data.includes('ERROR') || data.includes('CRITICAL')) formattedLine = `<span style="color: #f87171; font-weight: bold;">${data}</span>`;
            else if (data.includes('✓')) formattedLine = `<span style="color: #10b981;">${data}</span>`;

            logToTerminal(formattedLine, true);
        };

        eventSource.onerror = (error) => {
            console.error('SSE Error:', error);
            eventSource.close();
            // Don't change state automatically, backend might just have finished stream
        };
    };

    // Stop Button
    stopBtn.addEventListener('click', async () => {
        if (!isRunning) return;

        try {
            logToTerminal(`<span style="color: #fbbf24;">\nSending termination signal...</span>`, true);
            const response = await fetch('/api/stop', { method: 'POST' });
            const result = await response.json();
            
            logToTerminal(result.message);
            setRunningState(false);
        } catch (error) {
            logToTerminal(`<span style="color: #ff4b4b;">Error stopping process: ${error.message}</span>`, true);
        }
    });

    // Clear Logs
    clearLogBtn.addEventListener('click', () => {
        terminalOutput.innerHTML = '';
        logToTerminal('Logs cleared.');
    });
});
