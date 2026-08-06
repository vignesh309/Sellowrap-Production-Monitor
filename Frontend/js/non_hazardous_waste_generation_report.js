// ==========================================
// 1. DATA STATE (Mimicking Excel File)
// ==========================================
let esgData = [
    { month: "Apr-25", actual: 12885.4, target: 13900 },
    { month: "May-25", actual: 13760, target: 13900 },
    { month: "Jun-25", actual: 13969, target: 13900 },
    { month: "Jul-25", actual: 12987, target: 13900 },
    { month: "Aug-25", actual: 16420, target: 13900 },
    { month: "Sep-25", actual: 16013, target: 13900 },
    { month: "Oct-25", actual: 12417, target: 13900 },
    { month: "Nov-25", actual: 19458, target: 13900 },
    { month: "Dec-25", actual: 15455, target: 13900 },
    { month: "Jan-26", actual: 17071, target: 13900 },
    { month: "Feb-26", actual: 15299, target: 13900 },
    { month: "Mar-26", actual: null, target: 13900 }
];

let isEditMode = false;
let esgChartInstance = null;

// ==========================================
// 2. INITIALIZATION
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
    renderTable();
    renderChart();
});

// ==========================================
// 3. TABLE RENDERING & LOGIC
// ==========================================
function renderTable() {
    const tbody = document.getElementById("dataTableBody");
    tbody.innerHTML = "";

    esgData.forEach((row, index) => {
        const tr = document.createElement("tr");
        
        // Month Column
        const tdMonth = document.createElement("td");
        tdMonth.innerText = row.month;
        tr.appendChild(tdMonth);

        // Actual Column (Handles Edit Mode UI)
        const tdActual = document.createElement("td");
        if (isEditMode) {
            const input = document.createElement("input");
            input.type = "number";
            input.className = "data-input";
            input.value = row.actual !== null ? row.actual : "";
            input.id = `input_actual_${index}`;
            tdActual.appendChild(input);
        } else {
            let displayVal = row.actual !== null ? row.actual : "-";
            tdActual.innerText = displayVal;
            // Highlight in red if actual exceeds target
            if (row.actual > row.target) {
                tdActual.className = "val-exceeded";
            }
        }
        tr.appendChild(tdActual);

        // Target Column
        const tdTarget = document.createElement("td");
        tdTarget.innerText = row.target;
        tr.appendChild(tdTarget);

        tbody.appendChild(tr);
    });
}

function toggleEditMode() {
    const btn = document.getElementById("btn-edit");

    if (!isEditMode) {
        // Switch TO Edit Mode
        isEditMode = true;
        btn.innerHTML = "💾 Save Data";
        btn.classList.add("btn-save");
        renderTable();
    } else {
        // Save Data & Switch TO View Mode
        saveData();
        isEditMode = false;
        btn.innerHTML = "✏️ Edit Data";
        btn.classList.remove("btn-save");
        renderTable();
        updateChart();
    }
}

function saveData() {
    // Read values from the input fields and update the array
    esgData.forEach((row, index) => {
        const inputEl = document.getElementById(`input_actual_${index}`);
        if (inputEl) {
            const val = parseFloat(inputEl.value);
            row.actual = isNaN(val) ? null : val;
        }
    });
    // NOTE: In the future, this is where we will trigger a fetch() POST to your FastAPI backend.
}

// ==========================================
// 4. CHART.JS RENDERING
// ==========================================
function renderChart() {
    const ctx = document.getElementById('esgChart').getContext('2d');
    
    const labels = esgData.map(d => d.month);
    const actuals = esgData.map(d => d.actual);
    const targets = esgData.map(d => d.target);

    esgChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Target Limit (Kgs)',
                    data: targets,
                    type: 'line',
                    borderColor: '#ff2a7a', // Red limit line
                    borderWidth: 2,
                    pointBackgroundColor: '#ff2a7a',
                    fill: false,
                    order: 1
                },
                {
                    label: 'Actual Generated (Kgs)',
                    data: actuals,
                    backgroundColor: '#00e5ff', // Cyan bars
                    borderRadius: 4,
                    order: 2
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { labels: { color: '#c1deff' } }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(81, 128, 230, 0.1)' },
                    ticks: { color: '#c1deff' }
                },
                x: {
                    grid: { display: false },
                    ticks: { color: '#c1deff' }
                }
            }
        }
    });
}

function updateChart() {
    if (esgChartInstance) {
        esgChartInstance.data.datasets[1].data = esgData.map(d => d.actual);
        esgChartInstance.update();
    }
}