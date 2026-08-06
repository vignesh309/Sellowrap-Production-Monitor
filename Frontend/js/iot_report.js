window.onload = () => {
    // 1. Profile Setup
    const username = localStorage.getItem("userName") || "Admin";
    const role = localStorage.getItem("userRole") || "Role";
    document.getElementById("user-display").innerText = username;
    document.getElementById("role-display").innerText = role;
    if (username !== "Admin") document.getElementById("user-avatar").innerText = username.charAt(0).toUpperCase();

    // 2. Default Dates (First day of month to Today)
    const now = new Date();
    const offsetDate = new Date(now.getTime() - (now.getTimezoneOffset() * 60000));
    const todayStr = offsetDate.toISOString().split('T')[0];
    
    // Set start date to 1st of the current month
    const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
    const firstDayStr = new Date(firstDay.getTime() - (firstDay.getTimezoneOffset() * 60000)).toISOString().split('T')[0];

    document.getElementById('startDate').value = firstDayStr;
    document.getElementById('endDate').value = todayStr;

    // 3. Load Machines
    loadMachines();
};

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

async function loadMachines() {
    try {
        const response = await fetch('/api/get_machines');
        if (response.ok) {
            const data = await response.json();
            const select = document.getElementById("machineFilter");
            data.machines.forEach(m => {
                select.innerHTML += `<option value="${m.code}">${m.code}</option>`;
            });
        }
    } catch (e) { console.error("Error loading machines", e); }
}

async function fetchHistoricalData() {
    const start = document.getElementById('startDate').value;
    const end = document.getElementById('endDate').value;
    const machine = document.getElementById('machineFilter').value;
    const tbody = document.getElementById('tableBody');

    if (!start || !end) return alert("Please select a date range.");

    tbody.innerHTML = `<tr><td colspan="11" style="text-align: center; padding: 30px;">Compiling report...</td></tr>`;

    try {
        const res = await fetch(`/api/report/historical_iot?start_date=${start}&end_date=${end}&machine_code=${machine}`);
        if (!res.ok) throw new Error("Failed to fetch data");
        const data = await res.json();

        if (data.records.length === 0) {
            tbody.innerHTML = `<tr><td colspan="11" style="text-align: center; color: var(--status-yellow); padding: 30px;">No records found for this range.</td></tr>`;
            return;
        }

        let html = "";
        data.records.forEach(r => {
            let statusClass = "val-match";
            if (r.status === "Under-Reported") statusClass = "val-under";
            if (r.status === "Over-Reported") statusClass = "val-over";

            html += `
                <tr>
                    <td>${r.date}</td>
                    <td style="font-weight: bold; color: var(--accent-prod);">${r.machine}</td>
                    <td>${r.hour}</td>
                    <td style="font-weight: bold; font-size: 1.1em; color: var(--text-main);">${r.iot_qty}</td>
                    <td style="font-weight: bold; font-size: 1.1em; color: var(--status-yellow);">${r.manual_qty}</td>
                    <td class="${statusClass}">${r.variance}</td>
                    <td class="${statusClass}" style="font-size: 11px; text-transform: uppercase;">${r.status}</td>
                    <td>${r.runtime_min}</td>
                    <td style="color: var(--text-muted);">${r.idle_min}</td>
                    <td>${r.avg_cycle}</td>
                    <td style="color: var(--text-muted); font-size: 11px;">${r.operator}</td>
                </tr>
            `;
        });
        tbody.innerHTML = html;

    } catch (error) {
        console.error(error);
        tbody.innerHTML = `<tr><td colspan="11" style="text-align: center; color: var(--status-red); padding: 30px;">Error generating report.</td></tr>`;
    }
}

function exportToExcel() {
    let table = document.getElementById("dataTable");
    
    // Check if table actually has data
    if (table.rows.length <= 1 || table.rows[1].innerText.includes("Select filters") || table.rows[1].innerText.includes("No records")) {
        alert("Please generate a valid report before downloading.");
        return;
    }

    let workbook = XLSX.utils.table_to_book(table, { sheet: "IoT_Discrepancy", raw: true });
    
    let start = document.getElementById('startDate').value;
    let end = document.getElementById('endDate').value;
    XLSX.writeFile(workbook, `IoT_Historical_Report_${start}_to_${end}.xlsx`);
}