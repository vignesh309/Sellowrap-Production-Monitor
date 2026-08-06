// ==========================================
// INITIALIZATION & USER PROFILE
// ==========================================
window.onload = () => {
    const username = localStorage.getItem("userName") || "Admin";
    const role = localStorage.getItem("userRole") || "Role";

    document.getElementById("user-display").innerText = username;
    document.getElementById("role-display").innerText = role;
    
    if (username !== "Admin" && username.length > 0) {
        document.getElementById("user-avatar").innerText = username.charAt(0).toUpperCase();
    }

    const now = new Date();
    const offsetDate = new Date(now.getTime() - (now.getTimezoneOffset() * 60000));
    const today = offsetDate.toISOString().split('T')[0];
    
    document.getElementById('startDate').value = today;
    document.getElementById('endDate').value = today;

    // Load Datalists
    loadDropdownData();
};

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

// ==========================================
// LOAD MASTER DATA FOR DROPDOWNS
// ==========================================
async function loadDropdownData() {
    try {
        const response = await fetch('/api/get_master_dropdowns');
        if (!response.ok) return;
        const data = await response.json();
        
        const machineList = document.getElementById('machineList');
        machineList.innerHTML = '<option value="ALL">All Machines</option>';
        data.machines.forEach(m => {
            machineList.innerHTML += `<option value="${m.machine_code}">${m.machine_code} - ${m.machine_name}</option>`;
        });

        const partList = document.getElementById('partList');
        partList.innerHTML = ''; 
        data.parts.forEach(p => {
            partList.innerHTML += `<option value="${p.part_number}">${p.part_number} - ${p.part_name}</option>`;
        });
    } catch (error) { console.error("Dropdown Error:", error); }
}

// ==========================================
// REPORT LOGIC & KPI CALCULATION
// ==========================================
async function fetchShortfallData() {
    const start = document.getElementById('startDate').value;
    const end = document.getElementById('endDate').value;
    const shift = document.getElementById('shiftFilter').value;
    const machine = document.getElementById('machineFilter').value.trim() || "ALL";
    const part = document.getElementById('partFilter').value.trim() || "ALL";

    if (!start || !end) { alert("Please select a date range."); return; }

    const tHead = document.getElementById('tableHead');
    const tBody = document.getElementById('tableBody');
    tBody.innerHTML = `<tr><td colspan="100" style="text-align: center; padding: 30px;">Loading data...</td></tr>`;

    try {
        const response = await fetch(`/api/report/detailed_shortfalls?start_date=${start}&end_date=${end}&shift=${shift}&machine=${machine}&part_no=${part}`);
        if (!response.ok) throw new Error("Failed to fetch report data");
        const data = await response.json();

        // 1. Build Header
        let headHtml = `
            <tr>
                <th>Date</th>
                <th>Shift</th>
                <th>Machine</th>
                <th>Part No</th>
                <th>Supervisor</th>
                <th>Operator</th>
        `;
        data.dynamic_columns.forEach(colName => {
            headHtml += `<th class="dynamic-col">${colName}</th>`;
        });
        headHtml += `<th style="color: var(--status-yellow);">Total Shortfalls</th></tr>`;
        tHead.innerHTML = headHtml;

        // 2. Build Rows & KPI
        if (!data.rows || data.rows.length === 0) {
            tBody.innerHTML = `<tr><td colspan="100" style="text-align: center; padding: 30px;">No shortfalls found for this selection.</td></tr>`;
            document.getElementById("topMachine").innerText = "-";
            document.getElementById("topPart").innerText = "-";
            return;
        }

        let machineTotals = {};
        let partTotals = {};
        let bodyHtml = "";

        data.rows.forEach(row => {
            let mac = row.machine;
            let part_no = row.part_no;
            let sf = row.total_shortfalls;

            machineTotals[mac] = (machineTotals[mac] || 0) + sf;
            partTotals[part_no] = (partTotals[part_no] || 0) + sf;

            bodyHtml += `
                <tr>
                    <td>${row.date}</td>
                    <td style="font-weight:bold;">${row.shift}</td>
                    <td style="color: var(--accent-prod); font-weight: bold;">${mac}</td>
                    <td>${part_no}</td>
                    <td style="color: var(--text-muted);">${row.supervisor}</td>
                    <td style="color: var(--text-muted);">${row.operator}</td>
            `;

            data.dynamic_columns.forEach(colName => {
                const qty = row.reasons[colName];
                const displayVal = qty > 0 ? qty : "-";
                bodyHtml += `<td class="dynamic-col">${displayVal}</td>`;
            });

            bodyHtml += `<td class="val-sf">${sf}</td></tr>`;
        });

        // 3. Update KPIs
        let topMachine = Object.keys(machineTotals).reduce((a, b) => machineTotals[a] > machineTotals[b] ? a : b, "-");
        let topPart = Object.keys(partTotals).reduce((a, b) => partTotals[a] > partTotals[b] ? a : b, "-");

        document.getElementById("topMachine").innerHTML = `${topMachine} <span class="kpi-count">${machineTotals[topMachine] || 0} Loss</span>`;
        document.getElementById("topPart").innerHTML = `${topPart} <span class="kpi-count">${partTotals[topPart] || 0} Loss</span>`;

        tBody.innerHTML = bodyHtml;

    } catch (error) {
        console.error("Error:", error);
        tBody.innerHTML = `<tr><td colspan="100" style="text-align: center; padding: 30px; color: var(--status-red);">Error loading report.</td></tr>`;
    }
}

// ==========================================
// EXPORT TO EXCEL
// ==========================================
function exportToExcel() {
    let table = document.getElementById("dataTable");
    let workbook = XLSX.utils.table_to_book(table, { sheet: "Shortfalls", raw: true });
    let dateStr = document.getElementById('startDate').value;
    XLSX.writeFile(workbook, `Detailed_Shortfalls_${dateStr}.xlsx`);
}