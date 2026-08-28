// ==========================================
// 1. PAGE INITIALIZATION 
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

    // Set Default Dates to Today
    const now = new Date();
    const offsetDate = new Date(now.getTime() - (now.getTimezoneOffset() * 60000));
    const todayStr = offsetDate.toISOString().split('T')[0];

    document.getElementById("start_date").value = todayStr;
    document.getElementById("end_date").value = todayStr;

    // Load available machines for the dropdown
    loadMachineDropdown();
});

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

// ==========================================
// 2. FETCH DATA & RENDER
// ==========================================
async function loadMachineDropdown() {
    // You can populate this manually or via an API. For now, we will add common moulding machines.
    // If you have an endpoint like '/api/get_machines', fetch it here instead.
    const machines = ["IM02-350T-1", "IM03-280T-1", "IM04-130T", "IM05-100T-1", "IM06-80T-1", "IM08-80T-2", "IM09-80T-3", "IM10-180T-1", "IM14-180T-2"];
    const select = document.getElementById("machine_filter");
    
    machines.forEach(m => {
        let option = document.createElement("option");
        option.value = m;
        option.text = m;
        select.appendChild(option);
    });
}

async function loadCycleTimeData() {
    const startDate = document.getElementById("start_date").value;
    const endDate = document.getElementById("end_date").value;
    const machine = document.getElementById("machine_filter").value;

    if (!startDate || !endDate) {
        alert("Please select both a Start and End Date.");
        return;
    }

    const tbody = document.getElementById("cycle_table_body");
    tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 30px;">Analyzing millions of IoT records... Please wait.</td></tr>`;

    try {
        const params = new URLSearchParams();
        params.append('start_date', startDate);
        params.append('end_date', endDate);
        if (machine) params.append('machine', machine);

        const response = await fetch(`/api/cycle_time_variance?${params.toString()}`);
        if (!response.ok) throw new Error("Failed to fetch cycle time data");

        const data = await response.json();
        
        if (!data.records || data.records.length === 0) {
            tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--status-yellow); padding: 30px;">No cycle time data found for this date range.</td></tr>`;
            return;
        }

        renderTable(data.records);

    } catch (error) {
        console.error("Data Fetch Error:", error);
        tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--status-red); padding: 30px;">❌ Error processing data.</td></tr>`;
    }
}

function renderTable(records) {
    const tbody = document.getElementById("cycle_table_body");
    let html = "";

    records.forEach(r => {
        // Format the Variance Chip
        let varianceChip = `<span class="variance-badge var-perfect">0.0%</span>`;
        if (r.variance_pct > 2.0) {
            // Slower than standard (+%)
            varianceChip = `<span class="variance-badge var-slower">+${r.variance_pct.toFixed(1)}%</span>`;
        } else if (r.variance_pct < -2.0) {
            // Faster than standard (-%)
            varianceChip = `<span class="variance-badge var-faster">${r.variance_pct.toFixed(1)}%</span>`;
        }

        html += `
            <tr>
                <td style="font-weight: bold; color: var(--accent-cyan);">${r.machine_code}</td>
                <td>${r.part_no}</td>
                <td>${r.process_name}</td>
                <td class="text-right">${r.min_ct.toFixed(1)}</td>
                <td class="text-right">${r.max_ct.toFixed(1)}</td>
                <td class="text-right highlight-col">${r.avg_ct.toFixed(1)}</td>
                <td class="text-right highlight-col" style="color: var(--text-muted);">${r.std_ct > 0 ? r.std_ct.toFixed(1) : '-'}</td>
                <td class="text-center">${r.std_ct > 0 ? varianceChip : '-'}</td>
                <td class="text-right highlight-proposed">${r.median_ct.toFixed(1)}</td>
            </tr>
        `;
    });

    tbody.innerHTML = html;
}

// ==========================================
// 3. EXPORT LOGIC
// ==========================================
function exportToExcel() {
    let table = document.querySelector(".master-table");
    
    if (!table || table.rows.length <= 1 || table.innerText.includes("Analyzing")) {
        alert("No data available to export.");
        return;
    }

    let workbook = XLSX.utils.table_to_book(table, { sheet: "Cycle Time Report", raw: true });
    let dateStr = document.getElementById('start_date').value;
    let fileName = `Cycle_Time_Variance_${dateStr}.xlsx`;

    XLSX.writeFile(workbook, fileName);
}