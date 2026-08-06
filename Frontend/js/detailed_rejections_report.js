// ==========================================
// INITIALIZATION & USER PROFILE
// ==========================================
window.onload = () => {
    // 1. Load User Profile from Local Storage
    const username = localStorage.getItem("userName") || "Admin";
    const role = localStorage.getItem("userRole") || "Role";

    document.getElementById("user-display").innerText = username;
    document.getElementById("role-display").innerText = role;
    
    if (username !== "Admin" && username.length > 0) {
        document.getElementById("user-avatar").innerText = username.charAt(0).toUpperCase();
    }

    loadDropdownData();

    // 2. Set Default Dates to Today
    // (Using timezone offset to ensure accuracy)
    const now = new Date();
    const offsetDate = new Date(now.getTime() - (now.getTimezoneOffset() * 60000));
    const today = offsetDate.toISOString().split('T')[0];
    
    document.getElementById('startDate').value = today;
    document.getElementById('endDate').value = today;
};

// ==========================================
// LOGOUT LOGIC
// ==========================================
function logout() {
    localStorage.clear();
    window.location.href = "/";
}

// Add this new function anywhere in your JS file
async function loadDropdownData() {
    try {
        const response = await fetch('/api/get_master_dropdowns');
        if (!response.ok) throw new Error("Failed to fetch master data");
        
        const data = await response.json();
        
        // 1. Populate Machines
        const machineList = document.getElementById('machineList');
        machineList.innerHTML = '<option value="ALL">All Machines</option>';
        data.machines.forEach(m => {
            // value="" is what goes into the input box. The text inside is what the user searches.
            machineList.innerHTML += `<option value="${m.machine_code}">${m.machine_code} - ${m.machine_name}</option>`;
        });

        // 2. Populate Parts
        const partList = document.getElementById('partList');
        partList.innerHTML = ''; 
        data.parts.forEach(p => {
            partList.innerHTML += `<option value="${p.part_number}">${p.part_number} - ${p.part_name}</option>`;
        });

    } catch (error) {
        console.error("Dropdown Error:", error);
    }
}

// ==========================================
// REPORT LOGIC (DYNAMIC PIVOT TABLE)
// ==========================================
async function fetchRejectionData() {
    const start = document.getElementById('startDate').value;
    const end = document.getElementById('endDate').value;
    const shift = document.getElementById('shiftFilter').value;
    const machine = document.getElementById('machineFilter').value;
    const part = document.getElementById('partFilter').value.trim() || "ALL";

    if (!start || !end) {
        alert("Please select a date range.");
        return;
    }

    const tHead = document.getElementById('tableHead');
    const tBody = document.getElementById('tableBody');
    tBody.innerHTML = `<tr><td colspan="100" style="text-align: center; padding: 30px;">Loading data...</td></tr>`;

    try {
        const response = await fetch(`/api/report/detailed_rejections?start_date=${start}&end_date=${end}&shift=${shift}&machine=${machine}&part_no=${part}`);
        
        if (!response.ok) throw new Error("Failed to fetch report data");
        
        const data = await response.json();

        // 1. Build the Dynamic Header
        let headHtml = `
            <tr>
                <th>Date</th>
                <th>Shift</th>
                <th>Machine</th>
                <th>Part No</th>
                <th>Supervisor</th>
                <th>Operator</th>
        `;
        
        // Loop through dynamic defect columns provided by the backend
        data.dynamic_columns.forEach(colName => {
            headHtml += `<th class="dynamic-col">${colName}</th>`;
        });
        
        headHtml += `<th style="color: var(--status-red);">Total Rejections</th></tr>`;
        tHead.innerHTML = headHtml;

        // 2. Build the Rows
        if (!data.rows || data.rows.length === 0) {
            tBody.innerHTML = `<tr><td colspan="100" style="text-align: center; padding: 30px;">No rejections found for this selection.</td></tr>`;
            document.getElementById("topMachine").innerText = "-";
            document.getElementById("topPart").innerText = "-";
            return;
        }

        // 🚨 NEW KPI CALCULATION LOGIC
        let machineTotals = {};
        let partTotals = {};

        // Loop through the data once to tally up all rejections by machine and part
        data.rows.forEach(row => {
            let mac = row.machine;
            let part = row.part_no;
            let rej = row.total_rejections;

            machineTotals[mac] = (machineTotals[mac] || 0) + rej;
            partTotals[part] = (partTotals[part] || 0) + rej;
        });

        // Find the machine and part with the highest numbers
        let topMachine = Object.keys(machineTotals).reduce((a, b) => machineTotals[a] > machineTotals[b] ? a : b, "-");
        let topPart = Object.keys(partTotals).reduce((a, b) => partTotals[a] > partTotals[b] ? a : b, "-");

        let topMachineVal = machineTotals[topMachine] || 0;
        let topPartVal = partTotals[topPart] || 0;

        // Update the UI cards
        document.getElementById("topMachine").innerHTML = `${topMachine} <span class="kpi-count">${topMachineVal} Rej</span>`;
        document.getElementById("topPart").innerHTML = `${topPart} <span class="kpi-count">${topPartVal} Rej</span>`;
        // 🚨 END OF KPI CALCULATION

        let bodyHtml = "";
        data.rows.forEach(row => {
            bodyHtml += `
                <tr>
                    <td>${row.date}</td>
                    <td style="font-weight:bold;">${row.shift}</td>
                    <td style="color: var(--accent-prod); font-weight: bold;">${row.machine}</td>
                    <td>${row.part_no}</td>
                    <td style="color: var(--text-muted);">${row.supervisor}</td>
                    <td style="color: var(--text-muted);">${row.operator}</td>
            `;

            // Loop through the EXACT dynamic columns to place the quantities in the right order
            data.dynamic_columns.forEach(colName => {
                const qty = row.reasons[colName];
                const displayVal = qty > 0 ? qty : "-";
                bodyHtml += `<td class="dynamic-col">${displayVal}</td>`;
            });

            // Final Total Column
            bodyHtml += `<td class="val-ng">${row.total_rejections}</td></tr>`;
        });

        tBody.innerHTML = bodyHtml;

    } catch (error) {
        console.error("Error:", error);
        tBody.innerHTML = `<tr><td colspan="100" style="text-align: center; padding: 30px; color: var(--status-red);">Error loading report. Check console for details.</td></tr>`;
    }
}

// ==========================================
// EXPORT TO EXCEL
// ==========================================
function exportToExcel() {
    let table = document.getElementById("dataTable");
    
    // raw: true prevents Excel from formatting part numbers or dates incorrectly
    let workbook = XLSX.utils.table_to_book(table, { sheet: "Rejections", raw: true });
    
    let dateStr = document.getElementById('startDate').value;
    XLSX.writeFile(workbook, `Detailed_Rejections_${dateStr}.xlsx`);
}