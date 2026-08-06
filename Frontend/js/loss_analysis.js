let rejectionChart = null;
let shortfallChart = null;

async function refreshDashboard() {
    const startDate = document.getElementById("startDate").value;
    const endDate = document.getElementById("endDate").value;
    const machine = document.getElementById("machineFilter").value;

    try {
        const params = new URLSearchParams({
            start_date: startDate,
            end_date: endDate,
            machine: machine
        });

        const response = await fetch(`/api/get_loss_analysis?${params.toString()}`);
        const data = await response.json();

        renderChart('rejectionChart', 'Rejections', data.rejections, '#ff2a7a', rejectionChart, (c) => rejectionChart = c);
        renderChart('shortfallChart', 'Shortfalls', data.shortfalls, '#ffcf00', shortfallChart, (c) => shortfallChart = c);

    } catch (error) {
        console.error("Dashboard Error:", error);
        alert("Failed to load dashboard data. Please check the server logs.");
    }
}

async function populateMachineDropdown() {
    try {
        const response = await fetch('/api/get_machines');
        if (!response.ok) throw new Error("Failed to fetch machines");
        
        const data = await response.json();
        const machineSelect = document.getElementById("machineFilter");
        
        // Loop through the machines and append them to the dropdown
        data.machines.forEach(machine => {
            const option = document.createElement("option");
            option.value = machine.code;
            option.textContent = machine.name; // Displays the name (or code if name is null)
            machineSelect.appendChild(option);
        });
    } catch (error) {
        console.error("Error loading machines:", error);
    }
}

function renderChart(canvasId, label, dataArray, color, existingChart, setChart) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    
    // Destroy previous instance to prevent overlapping
    if (existingChart) existingChart.destroy();

    const labels = dataArray.map(d => d.reason);
    const values = dataArray.map(d => d.count);

    const newChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: label,
                data: values,
                backgroundColor: color + '44', // Transparent
                borderColor: color,
                borderWidth: 2,
                borderRadius: 5
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true, grid: { color: '#262a47' }, ticks: { color: '#c1deff' } },
                x: { grid: { display: false }, ticks: { color: '#c1deff' } }
            },
            plugins: {
                legend: { display: false }
            }
        }
    });

    setChart(newChart);
}

// Initial Load
window.onload = () => {
    const today = new Date().toISOString().split('T')[0];
    document.getElementById("startDate").value = today;
    document.getElementById("endDate").value = today;
    populateMachineDropdown().then(() => {
        refreshDashboard();
    });
};