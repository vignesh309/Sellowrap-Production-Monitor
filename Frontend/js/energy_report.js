let trendChartInstance = null;
let currentTableData = [];

document.addEventListener("DOMContentLoaded", () => {
    // 1. Authenticate & Setup Profile
    const role = localStorage.getItem("userRole");
    const fullName = localStorage.getItem("userFullName") || localStorage.getItem("userName");

    if (!role || !fullName) {
        window.location.href = "/";
        return;
    }

    document.getElementById("user-display").innerText = fullName;
    document.getElementById("role-display").innerText = role.toUpperCase();
    document.getElementById("user-avatar").innerText = fullName.charAt(0).toUpperCase();

    // 2. Default date range: Today
    setQuickRange('today');

    // 3. Load meter list, then load the report
    loadMeterList();
});

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

// ==========================================
// METER LIST
// ==========================================
async function loadMeterList() {
    try {
        const res = await fetch('/api/energy_meters/list');
        if (!res.ok) throw new Error("Failed to fetch meters");
        const data = await res.json();

        const select = document.getElementById("meter_select");
        select.innerHTML = "";
        data.meters.forEach(name => {
            const opt = document.createElement("option");
            opt.value = name;
            opt.textContent = name;
            select.appendChild(opt);
        });

        // Once meters are loaded, load the report for the first meter + today
        loadReport();
    } catch (error) {
        console.error("Error loading meters:", error);
    }
}

// ==========================================
// QUICK DATE RANGE
// ==========================================
function setQuickRange(type) {
    const now = new Date();
    const toStr = toDateInputValue(now);
    let fromDate = new Date(now);

    if (type === 'today') {
        // fromDate stays as today
    } else if (type === 'week') {
        fromDate.setDate(fromDate.getDate() - 6);
    } else if (type === 'month') {
        fromDate.setDate(fromDate.getDate() - 29);
    }

    document.getElementById("from_date").value = toDateInputValue(fromDate);
    document.getElementById("to_date").value = toStr;
}

function toDateInputValue(dateObj) {
    const offsetDate = new Date(dateObj.getTime() - (dateObj.getTimezoneOffset() * 60000));
    return offsetDate.toISOString().split('T')[0];
}

// ==========================================
// LOAD REPORT (summary + chart + table)
// ==========================================
async function loadReport() {
    const meter = document.getElementById("meter_select").value;
    const fromDate = document.getElementById("from_date").value;
    const toDate = document.getElementById("to_date").value;

    if (!meter || !fromDate || !toDate) return;

    const params = `meter_name=${encodeURIComponent(meter)}&from_date=${fromDate}&to_date=${toDate}`;

    await Promise.all([
        loadSummary(params),
        loadTrendChart(params),
        loadTable(params)
    ]);
}

// ==========================================
// SUMMARY CARDS
// ==========================================
async function loadSummary(params) {
    try {
        const res = await fetch(`/api/energy_reports/summary?${params}`);
        if (!res.ok) throw new Error("Failed to fetch summary");
        const data = await res.json();

        document.getElementById("sum_total_kwh").innerText = `${data.total_kwh} kWh`;
        document.getElementById("sum_avg_kw").innerText = `${data.avg_kw} kW`;
        document.getElementById("sum_avg_pf").innerText = data.avg_pf;
        document.getElementById("sum_peak_kw").innerText = `${data.peak_kw} kW`;
        document.getElementById("sum_peak_time").innerText = data.peak_time;
    } catch (error) {
        console.error("Error loading summary:", error);
    }
}

// ==========================================
// TREND CHART
// ==========================================
async function loadTrendChart(params) {
    try {
        const res = await fetch(`/api/energy_reports/trend?${params}`);
        if (!res.ok) throw new Error("Failed to fetch trend");
        const data = await res.json();

        document.getElementById("chart_granularity_badge").innerText =
            data.granularity === 'hour' ? 'Hourly' : 'Daily';

        const labels = data.points.map(p => p.time);
        const values = data.points.map(p => p.kw);

        const ctx = document.getElementById("trendChart").getContext("2d");

        if (trendChartInstance) {
            trendChartInstance.destroy();
        }

        trendChartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Average Power (kW)',
                    data: values,
                    borderColor: '#00e5ff',
                    backgroundColor: 'rgba(0, 229, 255, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.3,
                    pointRadius: 2,
                    pointBackgroundColor: '#00e5ff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { labels: { color: '#c1deff' } }
                },
                scales: {
                    x: {
                        ticks: { color: '#c1deff', maxRotation: 45, minRotation: 45 },
                        grid: { color: 'rgba(81, 128, 230, 0.1)' }
                    },
                    y: {
                        ticks: { color: '#c1deff' },
                        grid: { color: 'rgba(81, 128, 230, 0.1)' },
                        title: { display: true, text: 'kW', color: '#c1deff' }
                    }
                }
            }
        });
    } catch (error) {
        console.error("Error loading trend chart:", error);
    }
}

// ==========================================
// DATA TABLE
// ==========================================
async function loadTable(params) {
    try {
        const res = await fetch(`/api/energy_reports/table?${params}`);
        if (!res.ok) throw new Error("Failed to fetch table data");
        const data = await res.json();

        currentTableData = data.records;
        const tbody = document.getElementById("readingsTableBody");
        tbody.innerHTML = "";

        if (data.records.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="empty-row">No readings found for this range.</td></tr>`;
            return;
        }

        data.records.forEach(r => {
            tbody.innerHTML += `
                <tr>
                    <td>${r.date}</td>
                    <td>${r.time}</td>
                    <td>${r.watts_total.toLocaleString()}</td>
                    <td>${r.pf_average}</td>
                    <td>${r.vll_average}</td>
                    <td>${r.current_total}</td>
                    <td>${r.kwh_received.toLocaleString()}</td>
                </tr>
            `;
        });
    } catch (error) {
        console.error("Error loading table:", error);
    }
}

// ==========================================
// EXPORT TO EXCEL
// ==========================================
function exportToExcel() {
    if (!currentTableData || currentTableData.length === 0) {
        alert("No data to export.");
        return;
    }

    const meter = document.getElementById("meter_select").value;
    const fromDate = document.getElementById("from_date").value;
    const toDate = document.getElementById("to_date").value;

    const exportRows = currentTableData.map(r => ({
        "Date": r.date,
        "Time": r.time,
        "Watts Total (W)": r.watts_total,
        "PF Average": r.pf_average,
        "VLL Average (V)": r.vll_average,
        "Current Total (A)": r.current_total,
        "kWh Received": r.kwh_received
    }));

    const worksheet = XLSX.utils.json_to_sheet(exportRows);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, "Energy Readings");

    XLSX.writeFile(workbook, `Energy_Report_${meter}_${fromDate}_to_${toDate}.xlsx`);
}