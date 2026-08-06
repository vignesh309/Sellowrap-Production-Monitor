// ==========================================
// GLOBAL VARIABLES
// ==========================================
let speedChartInstance = null; // Keeps track of the chart so we can destroy/redraw it

// ==========================================
// USER AUTHENTICATION & PROFILE DISPLAY
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
    const role = localStorage.getItem("userRole");
    const fullName = localStorage.getItem("userFullName");

    if (!role || !fullName || role === "undefined" || fullName === "undefined") {
        window.location.href = "/";
        return; 
    }

    const displayUser = document.getElementById("user-display");
    const displayRole = document.getElementById("role-display");
    const displayAvatar = document.getElementById("user-avatar");

    if (displayUser) displayUser.innerText = fullName; 
    if (displayRole) displayRole.innerText = role.toUpperCase(); 
    if (displayAvatar) displayAvatar.innerText = fullName.charAt(0).toUpperCase(); 

    // Initialize Page
    document.getElementById("filterDate").value = new Date().toISOString().split('T')[0];
    fetchMachineList();
});

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

// ==========================================
// DATA FETCHING & UI GENERATION
// ==========================================
async function fetchMachineList() {
    try {
        const response = await fetch('/api/get_machines');
        if (response.ok) {
            const data = await response.json();
            const select = document.getElementById("filterMachine");
            
            data.machines.forEach(m => {
                const option = document.createElement("option");
                option.value = m.code;
                option.textContent = m.code;
                select.appendChild(option);
            });
        }
    } catch (e) {
        console.error("Could not load machine list", e);
    }
}

async function loadIoTSummary() {
    const rawTbody = document.getElementById("iotTableBody");
    const discTbody = document.getElementById("discrepancyTableBody");
    const heatmapContainer = document.getElementById("heatmapContainer");
    
    rawTbody.innerHTML = `<tr><td colspan="11" style="text-align: center; color: gray;">Loading...</td></tr>`;
    discTbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: gray;">Loading...</td></tr>`;
    
    const dateVal = document.getElementById("filterDate").value;
    const mcVal = document.getElementById("filterMachine").value;

    if (!dateVal) {
        alert("Please select a date.");
        return;
    }

    try {
        const response = await fetch(`/api/get_iot_summary?summary_date=${dateVal}&machine_code=${mcVal}`);
        if (!response.ok) throw new Error("Failed to fetch IoT data.");
        
        const data = await response.json();
        const records = data.records;
        
        if (!records || records.length === 0) {
            rawTbody.innerHTML = `<tr><td colspan="11" style="text-align: center; color: var(--status-yellow);">No IoT logs found for this date.</td></tr>`;
            discTbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--status-yellow);">No Data</td></tr>`;
            heatmapContainer.innerHTML = `<div style="text-align: center; color: var(--status-yellow); padding: 20px;">No Data</div>`;
            if (speedChartInstance) speedChartInstance.destroy();
            resetSummaries();
            return;
        }

        // --- 1. Populate Summary Cards ---
        document.getElementById("sum-parts").innerText = data.summary.total_parts.toLocaleString();
        document.getElementById("sum-runtime").innerText = data.summary.total_runtime_hrs;
        document.getElementById("sum-idle").innerText = data.summary.total_idle_hrs;
        document.getElementById("sum-avail").innerText = `${data.summary.hardware_availability}%`;

        // --- 2. Generate Raw Table & Discrepancy Table ---
        let rawHtml = "";
        let discHtml = "";

        records.forEach(r => {
            // Raw Table Build
            rawHtml += `
                <tr>
                    <td style="font-weight: bold; color: var(--text-main);">${r.machine_code}</td>
                    <td style="color: var(--accent-cyan); font-weight: bold;">Hour ${r.hour_no}</td>
                    <td style="color: var(--text-muted);">${r.start_time}</td>
                    <td style="color: var(--text-muted);">${r.stop_time}</td>
                    <td style="font-weight: bold; font-size: 1.1em;">${r.part_count}</td>
                    <td>${r.avg_cycle}</td>
                    <td style="color: var(--status-green);">${r.min_cycle}</td>
                    <td style="color: var(--status-red);">${r.max_cycle}</td>
                    <td style="color: var(--status-green);">${r.runtime_min}</td>
                    <td style="color: var(--status-yellow);">${r.idle_min}</td>
                    <td style="font-size: 11px;">${r.status}</td>
                </tr>
            `;

            // Discrepancy Table Build (Math logic)
            let missing = r.part_count - r.manual_qty;
            let statusText = "Match";
            let statusColor = "var(--status-green)";

            if (missing > 0) {
                statusText = "Under-Reported";
                statusColor = "var(--status-red)";
            } else if (missing < 0) {
                statusText = "Over-Reported (Ghost Scraps?)";
                statusColor = "var(--status-yellow)";
            }

            discHtml += `
                <tr>
                    <td style="font-weight: bold;">${r.machine_code}</td>
                    <td style="color: var(--text-muted);">Hour ${r.hour_no}</td>
                    <td style="color: var(--accent-cyan); font-weight: bold; font-size: 16px;">${r.part_count}</td>
                    <td style="color: var(--status-yellow); font-weight: bold; font-size: 16px;">${r.manual_qty}</td>
                    <td style="color: ${missing !== 0 ? 'var(--status-red)' : 'var(--text-main)'}; font-weight: bold;">${missing}</td>
                    <td style="color: ${statusColor}; font-weight: bold; font-size: 12px; text-transform: uppercase;">${statusText}</td>
                </tr>
            `;
        });
        
        rawTbody.innerHTML = rawHtml;
        discTbody.innerHTML = discHtml;

        // --- 3. Generate Chart.js Speed Chart ---
        generateSpeedChart(records);

        // --- 4. Generate Availability Heatmap ---
        generateHeatmap(records);
        
    } catch (error) {
        console.error("IoT Fetch Error:", error);
        rawTbody.innerHTML = `<tr><td colspan="11" style="text-align: center; color: var(--status-red);">Error loading data.</td></tr>`;
        discTbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--status-red);">Error loading data.</td></tr>`;
    }
}

// ==========================================
// VISUALIZATION LOGIC
// ==========================================
function generateSpeedChart(records) {
    const ctx = document.getElementById('speedChart').getContext('2d');
    
    if (speedChartInstance) {
        speedChartInstance.destroy();
    }

    // Prepare arrays for Chart.js
    const labels = records.map(r => `${r.machine_code} (Hr ${r.hour_no})`);
    const avgData = records.map(r => r.avg_cycle);
    const minData = records.map(r => r.min_cycle);
    const maxData = records.map(r => r.max_cycle);

    speedChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Absolute Fastest (Min Cycle)',
                    data: minData,
                    borderColor: '#00f076', // var(--status-green)
                    backgroundColor: 'rgba(0, 240, 118, 0.1)',
                    borderWidth: 2,
                    tension: 0.3,
                    fill: true
                },
                {
                    label: 'Actual Average Rhythm',
                    data: avgData,
                    borderColor: '#00e5ff', // var(--accent-cyan)
                    backgroundColor: 'transparent',
                    borderWidth: 3,
                    tension: 0.3
                },
                {
                    label: 'Slowest Cycle (Max)',
                    data: maxData,
                    borderColor: '#ff2a7a', // var(--status-red)
                    borderDash: [5, 5], // Dotted line so it doesn't distract
                    backgroundColor: 'transparent',
                    borderWidth: 1,
                    tension: 0.3
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { labels: { color: '#ffffff' } }
            },
            scales: {
                y: {
                    title: { display: true, text: 'Seconds per Cycle', color: '#c1deff' },
                    ticks: { color: '#c1deff' },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                },
                x: {
                    ticks: { color: '#c1deff', maxRotation: 45, minRotation: 45 },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                }
            }
        }
    });
}

function generateHeatmap(records) {
    const container = document.getElementById("heatmapContainer");
    
    // Get unique machines from the dataset
    const machines = [...new Set(records.map(r => r.machine_code))];
    let html = "";

    // Header Row (Hour Labels)
    html += `<div class="heatmap-row" style="margin-bottom: 5px;">
                <div class="heatmap-label" style="color:transparent;">MC</div>`;
    for (let i = 0; i < 24; i++) {
        html += `<div style="flex: 1; text-align: center; font-size: 10px; color: var(--text-muted);">${i}</div>`;
    }
    html += `</div>`;

    // Data Rows
    machines.forEach(mc => {
        html += `<div class="heatmap-row">
                    <div class="heatmap-label">${mc}</div>`;
        
        for (let i = 0; i < 24; i++) {
            // Find if we have a record for this machine at this specific hour
            let hrRecord = records.find(r => r.machine_code === mc && r.hour_no === i);
            
            let bgColor = "rgba(255, 255, 255, 0.05)"; // Default dark grey (Offline/No Data)
            let text = "-";
            let tooltip = `${mc} - Hour ${i}: No Data`;

            if (hrRecord) {
                // Math: Run time / Total recorded time
                let totalMin = hrRecord.runtime_min + hrRecord.idle_min;
                let availPercent = totalMin > 0 ? (hrRecord.runtime_min / totalMin) * 100 : 0;
                
                text = Math.round(availPercent) + "%";
                tooltip = `${mc} - Hour ${i}\nAvailability: ${text}\nRuntime: ${hrRecord.runtime_min}m\nIdle: ${hrRecord.idle_min}m`;

                if (availPercent >= 85) bgColor = "var(--status-green)";
                else if (availPercent >= 50) bgColor = "var(--status-yellow)";
                else bgColor = "var(--status-red)";
            }

            html += `<div class="heatmap-cell" style="background-color: ${bgColor}" title="${tooltip}">${text}</div>`;
        }
        html += `</div>`;
    });

    container.innerHTML = html;
}

function resetSummaries() {
    document.getElementById("sum-parts").innerText = "0";
    document.getElementById("sum-runtime").innerText = "0.00";
    document.getElementById("sum-idle").innerText = "0.00";
    document.getElementById("sum-avail").innerText = "0%";
}