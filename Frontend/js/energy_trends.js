let consumptionChart;
let overallChart;
let loadChart;
let currentLoadMode = 'day'; // Default mode matching the image[cite: 7]

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

    // 2. Set Default Date Filter to Current Month
    const today = new Date();
    const year = today.getFullYear();
    const month = String(today.getMonth() + 1).padStart(2, '0');
    document.getElementById("month_filter").value = `${year}-${month}`;

    // 3. Initialize Data
    fetchMetersList();
    fetchTrendData();

    // Setup Load Consumption Defaults
    const yearSelect = document.getElementById("input_year");
    for (let y = today.getFullYear(); y >= 2015; y--) {
        yearSelect.innerHTML += `<option value="${y}">${y}</option>`;
    }
    document.getElementById("input_month").value = `${year}-${month}`;
    const day = String(today.getDate()).padStart(2, '0');
    document.getElementById("input_day").value = `${year}-${month}-${day}`;

    // Trigger Initial Render
    setLoadMode('day');
});

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

async function fetchMetersList() {
    try {
        const response = await fetch('/api/energy_trends/meters');
        if (response.ok) {
            const data = await response.json();
            const select = document.getElementById("meter_select");
            data.meters.forEach(meter => {
                const opt = document.createElement("option");
                opt.value = meter;
                opt.innerText = meter;
                select.appendChild(opt);
            });
        }
    } catch (e) {
        console.error("Error fetching meters list:", e);
    }
}

async function fetchTrendData() {
    const month = document.getElementById("month_filter").value;
    const meterName = document.getElementById("meter_select").value;

    if (!month) {
        alert("Please select a valid month.");
        return;
    }

    document.getElementById("table_body").innerHTML = '<tr><td colspan="5" class="loading-cell">Fetching data...</td></tr>';

    try {
        const response = await fetch(`/api/energy_trends/daily?month=${month}&meter_name=${encodeURIComponent(meterName)}`);
        if (!response.ok) throw new Error("Failed to fetch data");
        
        const data = await response.json();
        
        updateKPIs(data.kpis);
        updateTable(data.records);
        updateChart(data.records);

    } catch (error) {
        console.error("API Error:", error);
        document.getElementById("table_body").innerHTML = '<tr><td colspan="5" class="loading-cell" style="color:var(--status-red);">Error loading data.</td></tr>';
    }
}

function updateKPIs(kpis) {
    // 1. Update Top KPI Cards
    document.getElementById("kpi_current_month").innerText = kpis.current_month.toLocaleString(undefined, {minimumFractionDigits: 1, maximumFractionDigits: 1});
    document.getElementById("kpi_last_month").innerText = kpis.last_month.toLocaleString(undefined, {minimumFractionDigits: 1, maximumFractionDigits: 1});
    document.getElementById("kpi_avg_daily").innerText = kpis.avg_daily.toLocaleString(undefined, {minimumFractionDigits: 1, maximumFractionDigits: 1});

    // 2. Update Overall Consumption Table
    document.getElementById("tbl_current").innerText = kpis.current_month.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) + " kWh";
    document.getElementById("tbl_last").innerText = kpis.last_month.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) + " kWh";
    document.getElementById("tbl_same_last_year").innerText = kpis.same_month_last_year.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) + " kWh";
    document.getElementById("tbl_last_year").innerText = kpis.last_year_total.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) + " kWh";
    document.getElementById("tbl_avg_monthly").innerText = kpis.avg_monthly.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) + " kWh";
    document.getElementById("tbl_avg_daily").innerText = kpis.avg_daily.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) + " kWh";

    // 3. Render the 3-Bar Comparison Chart
    updateOverallChart(kpis);
}

function updateOverallChart(kpis) {
    const ctx = document.getElementById('overallChart').getContext('2d');
    
    if (overallChart) {
        overallChart.destroy();
    }

    overallChart = new Chart(ctx, {
        type: 'bar',
        data: {
            // Updated to multi-line labels: Friendly text on top, raw date on bottom
            labels: [
                ['Same Month Last Year', kpis.labels.same_month_last_year], 
                ['Last Month', kpis.labels.last_month], 
                ['Current Month', kpis.labels.current_month]
            ],
            datasets: [{
                label: 'Monthly Consumption (kWh)',
                data: [kpis.same_month_last_year, kpis.last_month, kpis.current_month],
                backgroundColor: 'rgba(0, 229, 255, 0.2)',
                borderColor: '#00e5ff',
                borderWidth: 1,
                borderRadius: 4,
                hoverBackgroundColor: 'rgba(0, 229, 255, 0.4)',
                barThickness: 60
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { 
                        color: '#c1deff', 
                        font: { size: 13 },
                        padding: 8 // Adds a little breathing room above the labels
                    }
                },
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(81, 128, 230, 0.1)' },
                    ticks: { color: '#00e5ff' }
                }
            },
            plugins: {
                legend: { display: false }, 
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return context.parsed.y.toLocaleString(undefined, {minimumFractionDigits: 2}) + ' kWh';
                        }
                    }
                }
            }
        }
    });
}

function updateTable(records) {
    const tbody = document.getElementById("table_body");
    tbody.innerHTML = "";

    if (!records || records.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="loading-cell">No consumption records found for this month.</td></tr>';
        return;
    }

    records.forEach(r => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${r.date}</td>
            <td><strong>${r.meter_name}</strong></td>
            <td>${r.start_reading.toFixed(2)}</td>
            <td>${r.end_reading.toFixed(2)}</td>
            <td style="color: var(--accent-cyan); font-weight: bold;">${r.total_consumption.toFixed(2)}</td>
        `;
        tbody.appendChild(tr);
    });
}

function updateChart(records) {
    const ctx = document.getElementById('consumptionChart').getContext('2d');
    
    if (consumptionChart) {
        consumptionChart.destroy();
    }

    if (!records || records.length === 0) return;

    // 1. Group data by date
    // If "All Meters" is selected, we need to sum the daily consumption for all meters into a single bar per day.
    const dailyTotals = {};
    
    // Reverse the records so the chart plots chronologically from left to right (oldest to newest)
    const chartRecords = [...records].reverse();

    chartRecords.forEach(r => {
        if (!dailyTotals[r.date]) {
            dailyTotals[r.date] = 0;
        }
        dailyTotals[r.date] += r.total_consumption;
    });

    const labels = Object.keys(dailyTotals);
    const dataPoints = Object.values(dailyTotals);

    // 2. Render Chart
    consumptionChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Daily Consumption (kWh)',
                    data: dataPoints,
                    backgroundColor: 'rgba(0, 229, 255, 0.2)',
                    borderColor: '#00e5ff',
                    borderWidth: 1,
                    borderRadius: 4,
                    hoverBackgroundColor: 'rgba(0, 229, 255, 0.4)'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    grid: { color: 'rgba(81, 128, 230, 0.1)' },
                    ticks: { color: '#c1deff' }
                },
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(81, 128, 230, 0.1)' },
                    ticks: { color: '#00e5ff' },
                    title: { display: true, text: 'Energy (kWh)', color: '#00e5ff' }
                }
            },
            plugins: {
                legend: { labels: { color: '#ffffff' } },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return context.parsed.y.toFixed(2) + ' kWh';
                        }
                    }
                }
            }
        }
    });
}
function setLoadMode(mode) {
    currentLoadMode = mode;
    
    // Reset all tabs
    const tabs = ['tab_all_year', 'tab_year', 'tab_month', 'tab_day'];
    tabs.forEach(t => document.getElementById(t).classList.remove('active'));
    
    // Activate selected tab
    document.getElementById(`tab_${mode}`).classList.add('active');
    
    fetchLoadData();
}

async function fetchLoadData() {
    const meterName = document.getElementById("meter_select").value;
    let filterVal = "";
    
    // Grab the value from the currently active input
    if (currentLoadMode === 'year') filterVal = document.getElementById("input_year").value;
    if (currentLoadMode === 'month') filterVal = document.getElementById("input_month").value;
    if (currentLoadMode === 'day') filterVal = document.getElementById("input_day").value;

    try {
        const response = await fetch(`/api/energy_trends/load?mode=${currentLoadMode}&val=${filterVal}&meter_name=${encodeURIComponent(meterName)}`);
        if (!response.ok) throw new Error("Failed to fetch load data");
        
        const data = await response.json();
        renderLoadChart(data.data);
    } catch (error) {
        console.error("Load Chart API Error:", error);
    }
}

function renderLoadChart(records) {
    const ctx = document.getElementById('loadChart').getContext('2d');
    
    if (loadChart) {
        loadChart.destroy();
    }

    const labels = records.map(r => r.label);
    const dataPoints = records.map(r => r.value);

    // Using the light green style to match the requested image theme[cite: 7]
    loadChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Energy Consumed (kWh)',
                data: dataPoints,
                backgroundColor: 'rgba(0, 240, 118, 0.4)',
                borderColor: '#00f076',
                borderWidth: 2,
                borderRadius: 4,
                hoverBackgroundColor: 'rgba(0, 240, 118, 0.6)'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { color: '#c1deff' }
                },
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(81, 128, 230, 0.1)' },
                    ticks: { color: '#00f076' }
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return context.parsed.y.toLocaleString(undefined, {minimumFractionDigits: 2}) + ' kWh';
                        }
                    }
                }
            }
        }
    });
}