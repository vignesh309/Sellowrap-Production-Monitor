document.addEventListener("DOMContentLoaded", () => {
    const role = localStorage.getItem("userRole");
    const fullName = localStorage.getItem("userFullName");

    if (!role || !fullName || role === "undefined" || fullName === "undefined") {
        window.location.href = "/";
        return; 
    }

    document.getElementById("user-display").innerText = fullName;
    document.getElementById("role-display").innerText = role.toUpperCase();
    document.getElementById("user-avatar").innerText = fullName.charAt(0).toUpperCase(); 

    const now = new Date();
    const offsetDate = new Date(now.getTime() - (now.getTimezoneOffset() * 60000));
    const todayStr = offsetDate.toISOString().split('T')[0];

    document.getElementById("start_date").value = todayStr;
    document.getElementById("end_date").value = todayStr;

    loadMachineDropdown();
});

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

async function loadMachineDropdown() {
    try {
        const response = await fetch('/api/machine_list');
        if (!response.ok) throw new Error("Failed to load machines");
        
        const data = await response.json();
        const select = document.getElementById("machine_filter");
        
        data.machines.forEach(m => {
            let option = document.createElement("option");
            option.value = m.machine_code;
            option.text = m.machine_name;
            select.appendChild(option);
        });
    } catch (error) {
        console.error("Machine Dropdown Error:", error);
    }
}

async function generateReport() {
    const startDate = document.getElementById("start_date").value;
    const endDate = document.getElementById("end_date").value;
    const machine = document.getElementById("machine_filter").value;

    if (!startDate || !endDate) {
        alert("Please select both a Start and End Date.");
        return;
    }

    try {
        const params = new URLSearchParams();
        params.append('start_date', startDate);
        params.append('end_date', endDate);
        if (machine) params.append('machine', machine);

        const response = await fetch(`/api/machinewise_oee_report?${params.toString()}`);
        if (!response.ok) throw new Error("Failed to fetch OEE data");

        const data = await response.json();
        renderDynamicTableColumns(data.records);

    } catch (error) {
        console.error("Data Fetch Error:", error);
        alert("Error loading report. Check console.");
    }
}

function renderDynamicTableColumns(records) {
    const headerRow = document.getElementById("table_header_row");
    const rows = document.querySelectorAll("#table_body tr");
    const sectionRows = document.querySelectorAll("#table_body .section-row");

    // 1. Wipe out existing dynamically generated columns
    const headerCells = headerRow.querySelectorAll("th");
    for (let i = 1; i < headerCells.length; i++) {
        headerCells[i].remove();
    }
    
    rows.forEach(row => {
        if (!row.classList.contains("section-row")) {
            const cells = row.querySelectorAll("td");
            for (let i = 1; i < cells.length; i++) {
                cells[i].remove();
            }
        }
    });

    // Each section row spans the label column plus all dynamic machine columns.
    sectionRows.forEach(row => {
        row.querySelector("td").colSpan = Math.max(records.length + 1, 2);
    });

    // 2. Handle Empty State
    if (records.length === 0) {
        headerRow.innerHTML += `<th class="val-col" style="color: var(--status-red);">No Data Found</th>`;
        rows.forEach(row => {
            if (!row.classList.contains("section-row")) {
                row.innerHTML += `<td class="val-cell">-</td>`;
            }
        });
        return;
    }

    // 3. Inject New Columns Side-By-Side
    records.forEach(r => {
        // Build the Header
        const th = document.createElement("th");
        th.className = "val-col";
        th.innerText = r.machine;
        headerRow.appendChild(th);

        // Build the Rows
        rows.forEach(row => {
            if (!row.classList.contains("section-row")) {
                const key = row.getAttribute("data-key");
                let val = r[key] !== undefined ? r[key] : "-";
                
                // Format OEE percentages
                if (["oee", "availability", "performance", "quality"].includes(key) && val !== "-") {
                    val = `${val}%`;
                }

                const td = document.createElement("td");
                td.className = "val-cell";
                td.innerText = val;
                row.appendChild(td);
            }
        });
    });
}

function exportToExcel() {
    let table = document.getElementById("oee_report_table");
    if (!table || table.innerText.includes("Select criteria")) {
        alert("No data available to export.");
        return;
    }

    let workbook = XLSX.utils.table_to_book(table, { sheet: "Machinewise OEE", raw: true });
    let dateStr = document.getElementById('start_date').value;
    XLSX.writeFile(workbook, `Machinewise_OEE_${dateStr}.xlsx`);
}