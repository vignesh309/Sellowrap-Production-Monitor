let compressorChart;

document.addEventListener("DOMContentLoaded", () => {
    // 1. Auth Check
    const role = localStorage.getItem("userRole");
    const fullName = localStorage.getItem("userFullName") || localStorage.getItem("userName");

    if (!role || !fullName) {
        window.location.href = "/";
        return;
    }

    document.getElementById("user-display").innerText = fullName;
    document.getElementById("role-display").innerText = role.toUpperCase();
    document.getElementById("user-avatar").innerText = fullName.charAt(0).toUpperCase();

    // 2. Set Default Dates (Yesterday to Today)
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    
    // Adjust for local timezone before generating YYYY-MM-DD string
    const offsetToday = new Date(today.getTime() - (today.getTimezoneOffset() * 60000));
    const offsetYesterday = new Date(yesterday.getTime() - (yesterday.getTimezoneOffset() * 60000));

    document.getElementById("end_date").value = offsetToday.toISOString().split('T')[0];
    document.getElementById("start_date").value = offsetYesterday.toISOString().split('T')[0];

    // 3. Initialize Data
    fetchCompressorsList();
    fetchCompressorData();
});

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

async function fetchCompressorsList() {
    try {
        const response = await fetch('/api/compressor/list');
        if (response.ok) {
            const data = await response.json();
            const select = document.getElementById("compressor_select");
            data.compressors.forEach(comp => {
                const opt = document.createElement("option");
                opt.value = comp;
                opt.innerText = comp;
                select.appendChild(opt);
            });
        }
    } catch (e) {
        console.error("Error fetching compressor list:", e);
    }
}

async function fetchCompressorData() {
    const startDate = document.getElementById("start_date").value;
    const endDate = document.getElementById("end_date").value;
    const compressor = document.getElementById("compressor_select").value;

    document.getElementById("table_body").innerHTML = '<tr><td colspan="6" class="loading-cell">Fetching data...</td></tr>';

    try {
        const response = await fetch(`/api/compressor/readings?start_date=${startDate}&end_date=${endDate}&compressor_code=${compressor}`);
        if (!response.ok) throw new Error("Failed to fetch data");
        
        const data = await response.json();
        const records = data.records;

        updateKPIs(records);
        updateChart(records);
        updateTable(records);

    } catch (error) {
        console.error("API Error:", error);
        document.getElementById("table_body").innerHTML = '<tr><td colspan="6" class="loading-cell" style="color:var(--status-red);">Error loading data.</td></tr>';
    }
}

function updateKPIs(records) {
    if (!records || records.length === 0) {
        document.getElementById("kpi_pressure").innerText = "--";
        document.getElementById("kpi_dis_temp").innerText = "--";
        document.getElementById("kpi_amb_temp").innerText = "--";
        return;
    }

    // The query returns ordered by timestamp ASC, so the last record is the latest
    const latest = records[records.length - 1];
    
    document.getElementById("kpi_pressure").innerText = latest.discharge_pressure_bar != null ? latest.discharge_pressure_bar.toFixed(2) : "--";
    document.getElementById("kpi_dis_temp").innerText = latest.discharge_temp_c != null ? latest.discharge_temp_c.toFixed(1) : "--";
    document.getElementById("kpi_amb_temp").innerText = latest.ambient_temp_c != null ? latest.ambient_temp_c.toFixed(1) : "--";
}

function updateTable(records) {
    const tbody = document.getElementById("table_body");
    tbody.innerHTML = "";

    if (!records || records.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="loading-cell">No readings found for selected range.</td></tr>';
        return;
    }

    // Reverse to show newest at the top of the table
    const reversedRecords = [...records].reverse();

    reversedRecords.forEach(r => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${r.record_date}</td>
            <td>${r.record_time}</td>
            <td><strong>${r.compressor_code}</strong></td>
            <td style="color: var(--accent-cyan); font-weight: bold;">${r.discharge_pressure_bar != null ? r.discharge_pressure_bar.toFixed(2) : '-'}</td>
            <td style="color: var(--status-yellow);">${r.discharge_temp_c != null ? r.discharge_temp_c.toFixed(1) : '-'}</td>
            <td style="color: var(--status-green);">${r.ambient_temp_c != null ? r.ambient_temp_c.toFixed(1) : '-'}</td>
        `;
        tbody.appendChild(tr);
    });
}

function updateChart(records) {
    const ctx = document.getElementById('compressorChart').getContext('2d');
    
    if (compressorChart) {
        compressorChart.destroy();
    }

    if (!records || records.length === 0) return;

    const labels = records.map(r => `${r.record_date} ${r.record_time.substring(0,5)}`);
    const pressureData = records.map(r => r.discharge_pressure_bar);
    const disTempData = records.map(r => r.discharge_temp_c);
    const ambTempData = records.map(r => r.ambient_temp_c);

    compressorChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Discharge Pressure (bar)',
                    data: pressureData,
                    borderColor: '#00e5ff',
                    backgroundColor: 'rgba(0, 229, 255, 0.1)',
                    yAxisID: 'y-pressure',
                    borderWidth: 2,
                    tension: 0.3,
                    pointRadius: 2
                },
                {
                    label: 'Discharge Temp (°C)',
                    data: disTempData,
                    borderColor: '#ffb142',
                    backgroundColor: 'rgba(255, 177, 66, 0.1)',
                    yAxisID: 'y-temp',
                    borderWidth: 2,
                    tension: 0.3,
                    pointRadius: 2
                },
                {
                    label: 'Ambient Temp (°C)',
                    data: ambTempData,
                    borderColor: '#00f076',
                    backgroundColor: 'rgba(0, 240, 118, 0.1)',
                    yAxisID: 'y-temp',
                    borderWidth: 2,
                    borderDash: [5, 5],
                    tension: 0.3,
                    pointRadius: 0
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            scales: {
                x: {
                    grid: { color: 'rgba(81, 128, 230, 0.1)' },
                    ticks: { color: '#c1deff', maxTicksLimit: 12 }
                },
                'y-pressure': {
                    type: 'linear',
                    position: 'left',
                    grid: { color: 'rgba(81, 128, 230, 0.1)' },
                    ticks: { color: '#00e5ff' },
                    title: { display: true, text: 'Pressure (bar)', color: '#00e5ff' }
                },
                'y-temp': {
                    type: 'linear',
                    position: 'right',
                    grid: { drawOnChartArea: false },
                    ticks: { color: '#ffb142' },
                    title: { display: true, text: 'Temperature (°C)', color: '#ffb142' }
                }
            },
            plugins: {
                legend: { labels: { color: '#ffffff' } }
            }
        }
    });
}