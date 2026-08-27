function toggleTheme() {
            const root = document.documentElement;
            const current = root.getAttribute('data-theme') || 'dark';
            const newTheme = current === 'light' ? 'dark' : 'light';
            
            root.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            
            document.getElementById('theme-toggle').innerHTML = newTheme === 'light' ? '🌙 Dark' : '☀️ Light';
            
            if (window.histogramChart) {
                if (newTheme === 'light') {
                    Chart.defaults.color = '#64748b';
                    histogramChart.options.scales.x.grid.color = 'rgba(0,0,0,0.05)';
                    histogramChart.options.scales.y.grid.color = 'rgba(0,0,0,0.05)';
                    histogramChart.options.plugins.tooltip.backgroundColor = 'rgba(255, 255, 255, 0.9)';
                    histogramChart.options.plugins.tooltip.titleColor = '#0284c7';
                    histogramChart.options.plugins.tooltip.borderColor = 'rgba(0,0,0,0.1)';
                } else {
                    Chart.defaults.color = '#94a3b8';
                    histogramChart.options.scales.x.grid.color = 'rgba(255,255,255,0.05)';
                    histogramChart.options.scales.y.grid.color = 'rgba(255,255,255,0.05)';
                    histogramChart.options.plugins.tooltip.backgroundColor = 'rgba(13, 22, 38, 0.9)';
                    histogramChart.options.plugins.tooltip.titleColor = '#00f0ff';
                    histogramChart.options.plugins.tooltip.borderColor = 'rgba(255,255,255,0.1)';
                }
                histogramChart.update();
            }
            if (window.poreScanChart) {
                if (newTheme === 'light') {
                    poreScanChart.options.scales.x.grid.color = 'rgba(0,0,0,0.05)';
                    poreScanChart.options.scales.y.grid.color = 'rgba(0,0,0,0.05)';
                    poreScanChart.options.plugins.tooltip.backgroundColor = 'rgba(255, 255, 255, 0.9)';
                    poreScanChart.options.plugins.tooltip.titleColor = '#0284c7';
                    poreScanChart.options.plugins.tooltip.bodyColor = '#333';
                    poreScanChart.options.plugins.tooltip.borderColor = 'rgba(0,0,0,0.1)';
                    poreScanChart.options.plugins.legend.labels.color = '#64748b';
                } else {
                    poreScanChart.options.scales.x.grid.color = 'rgba(255,255,255,0.05)';
                    poreScanChart.options.scales.y.grid.color = 'rgba(255,255,255,0.05)';
                    poreScanChart.options.plugins.tooltip.backgroundColor = 'rgba(13, 22, 38, 0.9)';
                    poreScanChart.options.plugins.tooltip.titleColor = '#00f0ff';
                    poreScanChart.options.plugins.tooltip.bodyColor = '#fff';
                    poreScanChart.options.plugins.tooltip.borderColor = 'rgba(255,255,255,0.1)';
                    poreScanChart.options.plugins.legend.labels.color = '#94a3b8';
                }
                poreScanChart.update();
            }
        }

        document.addEventListener('DOMContentLoaded', () => {
            const current = document.documentElement.getAttribute('data-theme') || 'dark';
            document.getElementById('theme-toggle').innerHTML = current === 'light' ? '🌙 Dark' : '☀️ Light';
        });

        // Number formatter
        const fmt = new Intl.NumberFormat('en-US');
        
        // Chart.js Setup
        const isLight = document.documentElement.getAttribute('data-theme') === 'light';
        Chart.defaults.color = isLight ? '#64748b' : '#94a3b8';
        Chart.defaults.font.family = "'Inter', sans-serif";
        
        const ctx = document.getElementById('histogramChart').getContext('2d');
        const histogramChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [{
                    label: 'Reads',
                    data: [],
                    backgroundColor: 'rgba(0, 240, 255, 0.2)',
                    borderColor: 'rgba(0, 240, 255, 0.8)',
                    borderWidth: 1,
                    borderRadius: 4,
                    hoverBackgroundColor: 'rgba(0, 240, 255, 0.4)'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        grid: { color: isLight ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.05)' }
                    },
                    y: {
                        beginAtZero: true,
                        grid: { color: isLight ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.05)' },
                        ticks: {
                            callback: function(value) {
                                return value > 1000 ? (value/1000).toFixed(1) + 'k' : value;
                            }
                        }
                    }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: isLight ? 'rgba(255, 255, 255, 0.9)' : 'rgba(13, 22, 38, 0.9)',
                        titleColor: isLight ? '#0284c7' : '#00f0ff',
                        padding: 10,
                        borderColor: isLight ? 'rgba(0,0,0,0.1)' : 'rgba(255,255,255,0.1)',
                        borderWidth: 1
                    }
                },
                animation: { duration: 500 }
            }
        });

        const qCtx = document.getElementById('qscoreChart').getContext('2d');
        const qscoreChart = new Chart(qCtx, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [{
                    label: 'Reads',
                    data: [],
                    backgroundColor: 'rgba(255, 0, 57, 0.2)', // accent-rose
                    borderColor: 'rgba(255, 0, 57, 0.8)',
                    borderWidth: 1,
                    borderRadius: 4,
                    barPercentage: 1.0,
                    categoryPercentage: 1.0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        grid: { display: false, drawBorder: false },
                        ticks: { maxRotation: 45, minRotation: 45, autoSkip: true, maxTicksLimit: 20 }
                    },
                    y: {
                        beginAtZero: true,
                        grid: { color: isLight ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.05)', drawBorder: false },
                        ticks: {
                            callback: function(value) { return fmt.format(value); }
                        }
                    }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: isLight ? 'rgba(255,255,255,0.95)' : 'rgba(20,20,20,0.95)',
                        titleColor: isLight ? '#0284c7' : '#ff0039',
                        padding: 10,
                        borderColor: isLight ? 'rgba(0,0,0,0.1)' : 'rgba(255,255,255,0.1)',
                        borderWidth: 1
                    }
                },
                animation: { duration: 500 }
            }
        });

        const pCtx = document.getElementById('poreScanChart').getContext('2d');
        const poreScanChart = new Chart(pCtx, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [
                    { label: 'Sequencing', data: [], backgroundColor: '#10b981', borderRadius: 4 },
                    { label: 'Available', data: [], backgroundColor: '#00f0ff', borderRadius: 4 },
                    { label: 'Inactive', data: [], backgroundColor: '#f43f5e', borderRadius: 4 }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        stacked: true,
                        grid: { color: isLight ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.05)' }
                    },
                    y: {
                        stacked: true,
                        beginAtZero: true,
                        grid: { color: isLight ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.05)' }
                    }
                },
                plugins: {
                    legend: {
                        display: true,
                        labels: { color: isLight ? '#64748b' : '#94a3b8' }
                    },
                    tooltip: {
                        backgroundColor: isLight ? 'rgba(255, 255, 255, 0.9)' : 'rgba(13, 22, 38, 0.9)',
                        titleColor: isLight ? '#0284c7' : '#00f0ff',
                        bodyColor: isLight ? '#333' : '#fff',
                        padding: 10,
                        borderColor: isLight ? 'rgba(0,0,0,0.1)' : 'rgba(255,255,255,0.1)',
                        borderWidth: 1
                    }
                },
                animation: { duration: 500 }
            }
        });

        function formatBases(bases) {
            if (bases >= 1e9) return (bases / 1e9).toFixed(2) + ' Gb';
            if (bases >= 1e6) return (bases / 1e6).toFixed(2) + ' Mb';
            if (bases >= 1e3) return (bases / 1e3).toFixed(2) + ' kb';
            return fmt.format(bases);
        }

        let currentTab = 'main';

        function switchTab(tabId) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            
            document.getElementById('tab-' + tabId).classList.add('active');
            event.currentTarget.classList.add('active');
            
            currentTab = tabId;
            updateStats(); // Poll immediately on switch
        }

        function updateStats() {
            const targetPos = document.getElementById('pos-select') ? document.getElementById('pos-select').value : '';
            let url = '/api/stats?tab=' + currentTab;
            if (targetPos) {
                url += '&position=' + encodeURIComponent(targetPos);
            }
            fetch(url)
                .then(response => response.json())
                .then(data => {
                    const statusBadge = document.getElementById('connection-status');
                    
                    if (data.active) {
                        statusBadge.innerText = data.state.toUpperCase() === 'RUNNING' ? 'SEQUENCING' : data.state.toUpperCase();
                        
                        if (data.state === 'Paused' || data.state === 'Pausing') {
                            statusBadge.className = "badge paused";
                        } else {
                            statusBadge.className = "badge active";
                        }
                        
                        if (document.getElementById('pos-name')) {
                            document.getElementById('pos-name').innerText = data.position;
                        }
                        
                        if (document.getElementById('fc-id')) {
                            document.getElementById('fc-id').innerText = data.flow_cell_id || '--';
                        }
                        
                        if (document.getElementById('run-id')) {
                            document.getElementById('run-id').innerText = data.run_id || '--';
                        }
                        if (document.getElementById('run-state')) {
                            const stateEl = document.getElementById('run-state');
                            stateEl.innerText = data.state;
                            if (data.state === 'Running') {
                                stateEl.classList.add('state-pulse');
                            } else {
                                stateEl.classList.remove('state-pulse');
                            }
                        }
                        if (document.getElementById('run-exp')) {
                            document.getElementById('run-exp').innerText = data.experiment || '--';
                        }
                        if (document.getElementById('run-sample')) {
                            document.getElementById('run-sample').innerText = data.sample || '--';
                        }
                        if (document.getElementById('run-kit')) {
                            document.getElementById('run-kit').innerText = data.kit || '--';
                        }
                        if (document.getElementById('run-model')) {
                            document.getElementById('run-model').innerText = data.model || 'Off';
                        }
                        
                        if (data.debug_pores) {
                            document.getElementById('run-state').innerText += " | PORES ERR: " + data.debug_pores;
                        }

                        // Yields
                        document.getElementById('bases-val').innerText = formatBases(data.yield.bases);
                        document.getElementById('reads-val').innerText = fmt.format(data.yield.reads);
                        
                        // N50 and Temp
                        document.getElementById('n50-val').innerText = fmt.format(Math.round(data.read_length.n50));
                        document.getElementById('temp-val').innerText = data.temperature ? data.temperature.toFixed(1) : '--';

                        // Pores
                        const seq = data.pores.sequencing || 0;
                        const avail = data.pores.available || 0;
                        const inact = data.pores.inactive || 0;
                        const total = seq + avail + inact;
                        
                        document.getElementById('pore-total').innerText = fmt.format(total);
                        document.getElementById('val-seq').innerText = fmt.format(seq);
                        document.getElementById('val-avail').innerText = fmt.format(avail);
                        document.getElementById('val-inact').innerText = fmt.format(inact);
                        
                        if(total > 0) {
                            document.getElementById('bar-seq').style.width = (seq / total * 100) + '%';
                            document.getElementById('bar-avail').style.width = (avail / total * 100) + '%';
                            document.getElementById('bar-inact').style.width = (inact / total * 100) + '%';
                        }

                        // Histogram
                        if (data.read_length.histogram && data.read_length.histogram.length > 0) {
                            const labels = [];
                            const counts = [];
                            data.read_length.histogram.forEach(bin => {
                                const startLabel = bin.start >= 1000 ? (bin.start/1000) + 'k' : bin.start;
                                const endLabel = bin.end >= 1000 ? (bin.end/1000) + 'k' : bin.end;
                                labels.push(`${startLabel}-${endLabel}`);
                                counts.push(bin.count);
                            });
                            histogramChart.data.labels = labels;
                            histogramChart.data.datasets[0].data = counts;
                            histogramChart.update();
                        }

                        // Q-Score Histogram
                        if (data.qscore && data.qscore.histogram && data.qscore.histogram.length > 0) {
                            const qLabels = [];
                            const qCounts = [];
                            data.qscore.histogram.forEach(bin => {
                                qLabels.push(`Q${bin.start.toFixed(1)}`);
                                qCounts.push(bin.count);
                            });
                            qscoreChart.data.labels = qLabels;
                            qscoreChart.data.datasets[0].data = qCounts;
                            qscoreChart.update();
                        }

                        // Pore Scans Stacked Bar
                        if (data.pore_scans && data.pore_scans.length > 0) {
                            const times = [];
                            const seqs = [];
                            const avails = [];
                            const inacts = [];
                            data.pore_scans.forEach(scan => {
                                times.push(scan.time);
                                seqs.push(scan.sequencing);
                                avails.push(scan.available);
                                inacts.push(scan.inactive);
                            });
                            poreScanChart.data.labels = times;
                            poreScanChart.data.datasets[0].data = seqs;
                            poreScanChart.data.datasets[1].data = avails;
                            poreScanChart.data.datasets[2].data = inacts;
                            poreScanChart.update();
                        }
                    } else {
                        statusBadge.innerText = "OFFLINE: " + (data.status || "Unknown Error");
                        statusBadge.className = "badge offline";
                    }
                    
                    if (data.gpu) {
                        document.getElementById('gpu-temp-val').innerText = data.gpu.temp;
                        document.getElementById('gpu-usage-val').innerText = data.gpu.usage;
                    }
                    
                    document.getElementById('last-update').innerText = "Last updated: " + data.timestamp + " (Polling every 10s)";
                })
                .catch(err => {
                    console.error("Fetch error:", err);
                    const statusBadge = document.getElementById('connection-status');
                    statusBadge.innerText = "DISCONNECTED";
                    statusBadge.className = "badge offline";
                });
        }

        function startFlowCellCheck() {
            if (confirm("🩺 Are you sure you want to run a Flow Cell Check (Platform QC)? This will interrupt any active sequencing.")) {
                fetch('/api/flow_cell_check', { 
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ position: document.getElementById('pos-select') ? document.getElementById('pos-select').value : '' })
                })
                    .then(response => response.json())
                    .then(res => {
                        alert(res.message);
                        updateStats();
                    })
                    .catch(err => {
                        alert("Error starting flow cell check.");
                    });
            }
        }

        function startRun() {
            if (confirm("⚠️ WARNING: You are about to START a new sequencing run with the configured settings. Do you want to proceed?")) {
                
                const payload = {
                    position: document.getElementById('pos-select') ? document.getElementById('pos-select').value : '',
                    experiment_name: document.getElementById('exp-name').value,
                    sample_name: document.getElementById('sample-name').value,
                    output_dir: document.getElementById('out-dir').value,
                    run_duration: parseFloat(document.getElementById('run-duration').value) || 72.0,
                    lib_kit: document.getElementById('lib-kit').value,
                    basecall_model: document.getElementById('bc-model').value,
                    save_pod5: document.getElementById('save-pod5').checked,
                    save_fastq: document.getElementById('save-fastq').checked,
                    save_bam: document.getElementById('save-bam').checked
                };

                fetch('/api/start', { 
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                })
                    .then(response => response.json())
                    .then(res => {
                        alert(res.message);
                        updateStats();
                    });
            }
        }

        function pauseRun() {
            if (confirm("⏸ Are you sure you want to PAUSE the current sequencing run?")) {
                fetch('/api/pause', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ position: document.getElementById('pos-select') ? document.getElementById('pos-select').value : '' })
                })
                    .then(response => response.json())
                    .then(res => {
                        alert(res.message);
                        updateStats();
                    });
            }
        }

        function resumeRun() {
            if (confirm("▶️ Are you sure you want to RESUME the paused sequencing run?")) {
                fetch('/api/resume', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ position: document.getElementById('pos-select') ? document.getElementById('pos-select').value : '' })
                })
                    .then(response => response.json())
                    .then(res => {
                        alert(res.message);
                        updateStats();
                    });
            }
        }

        function stopRun() {
            if (confirm("🚨 WARNING: Are you sure you want to STOP the sequencing run? (This will stop data acquisition but allow basecalling to finish)")) {
                fetch('/api/stop', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ position: document.getElementById('pos-select') ? document.getElementById('pos-select').value : '' })
                })
                    .then(response => response.json())
                    .then(res => {
                        alert(res.message);
                        updateStats();
                    });
            }
        }

        // PERFORMANCE OPTIMIZATION: Only poll when the dashboard tab is active/visible
        let pollInterval;
        
        function startPolling() {
            if (!pollInterval) {
                pollInterval = setInterval(updateStats, 10000);
            }
        }
        
        function stopPolling() {
            if (pollInterval) {
                clearInterval(pollInterval);
                pollInterval = null;
            }
        }

        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                stopPolling();
            } else {
                updateStats(); // Fetch immediately when returning
                startPolling();
            }
        });

        function fetchPositions() {
            fetch('/api/positions')
                .then(response => response.json())
                .then(data => {
                    const select = document.getElementById('pos-select');
                    if (data.success && data.positions && data.positions.length > 0) {
                        const currentVal = select.value;
                        select.innerHTML = '';
                        data.positions.forEach(pos => {
                            const option = document.createElement('option');
                            option.value = pos;
                            option.textContent = pos;
                            select.appendChild(option);
                        });
                        if (currentVal && data.positions.includes(currentVal)) {
                            select.value = currentVal;
                        }
                    } else {
                        select.innerHTML = '<option value="">No Positions Found</option>';
                    }
                })
                .catch(err => console.error("Error fetching positions:", err));
        }

        document.getElementById('pos-select').addEventListener('change', () => {
            updateStats();
        });

        function toggleSafeguard() {
            const toggle = document.getElementById('safeguard-toggle');
            const btn = document.getElementById('tab-btn-controls');
            if (toggle.checked) {
                btn.style.display = 'inline-block';
            } else {
                btn.style.display = 'none';
                // If they hide it while currently on the tab, switch them back to main
                if (currentTab === 'experimental') {
                    switchTab('main');
                }
            }
        }

        // Initial setup
        fetchPositions();
        setInterval(fetchPositions, 60000); // Check for new positions every 60s
        startPolling();