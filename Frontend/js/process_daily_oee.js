document.addEventListener("DOMContentLoaded", () => {
    const role = localStorage.getItem("userRole");
    const fullName = localStorage.getItem("userFullName");

    if (!role || !fullName) {
        window.location.href = "/";
        return;
    }

    document.getElementById("user-display").innerText = fullName;
    document.getElementById("role-display").innerText = role.toUpperCase();
    document.getElementById("user-avatar").innerText = fullName.charAt(0).toUpperCase();

    // Set default dates to the last 7 days
    const now = new Date();
    const offsetDate = new Date(now.getTime() - (now.getTimezoneOffset() * 60000));
    const todayStr = offsetDate.toISOString().split('T')[0];
    
    let lastWeek = new Date(offsetDate);
    lastWeek.setDate(lastWeek.getDate() - 7);
    const lastWeekStr = lastWeek.toISOString().split('T')[0];

    document.getElementById("start_date").value = lastWeekStr;
    document.getElementById("end_date").value = todayStr;

    // Load initial data
    generateTrendReport();
});

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

async function generateTrendReport() {
    const startDate = document.getElementById("start_date").value;
    const endDate = document.getElementById("end_date").value;

    if (!startDate || !endDate) {
        alert("Please select both a Start and End Date.");
        return;
    }

    const tbody = document.getElementById("table_body");
    const theadRow = document.getElementById("table_header_row");

    tbody.innerHTML = `<tr><td colspan="10" class="loading-cell">Loading matrix... Please wait.</td></tr>`;

    try {
        const response = await fetch(`/api/report/process_daily_oee_trend?start_date=${startDate}&end_date=${endDate}`);
        if (!response.ok) throw new Error("Failed to fetch trend data");
        
        const data = await response.json();
        const records = data.records;

        // 1. Extract all unique dates and sort them
        const uniqueDates = [...new Set(records.map(r => r.date))].sort();

        // 2. Clear Header and Inject Dynamic Date Columns
        theadRow.innerHTML = '<th class="sticky-col">PROCESS</th>';
        
        if (uniqueDates.length === 0) {
            theadRow.innerHTML += '<th class="val-col">No Data</th>';
            tbody.innerHTML = `<tr><td colspan="2" class="loading-cell">No production logged in this date range.</td></tr>`;
            return;
        }

        uniqueDates.forEach(dateStr => {
            const th = document.createElement("th");
            th.className = "val-col";
            th.innerText = dateStr; // e.g., "2026-09-01"
            theadRow.appendChild(th);
        });

        // 3. Pivot the data into a Process Dictionary
        const processMatrix = {};
        records.forEach(r => {
            if (!processMatrix[r.process]) {
                processMatrix[r.process] = {};
            }
            processMatrix[r.process][r.date] = r.oee;
        });

        // 4. Render the Rows
        tbody.innerHTML = "";
        
        // Sort processes alphabetically
        const sortedProcesses = Object.keys(processMatrix).sort();

        sortedProcesses.forEach(process => {
            const tr = document.createElement("tr");

            // Process Name (Sticky Column)
            const tdLabel = document.createElement("td");
            tdLabel.className = "sticky-col";
            tdLabel.innerText = process;
            tr.appendChild(tdLabel);

            // Date Values
            uniqueDates.forEach(dateStr => {
                const tdVal = document.createElement("td");
                tdVal.className = "val-cell";
                
                const oeeValue = processMatrix[process][dateStr];
                
                if (oeeValue !== undefined) {
                    tdVal.innerText = `${oeeValue}%`;
                    // Color code the text
                    if (oeeValue >= 80) tdVal.style.color = "var(--status-green)";
                    else if (oeeValue >= 50) tdVal.style.color = "var(--status-yellow)";
                    else tdVal.style.color = "var(--status-red)";
                } else {
                    tdVal.innerText = "-";
                    tdVal.style.color = "var(--text-muted)";
                }
                
                tr.appendChild(tdVal);
            });

            tbody.appendChild(tr);
        });

    } catch (error) {
        console.error("Trend Fetch Error:", error);
        tbody.innerHTML = `<tr><td colspan="10" class="loading-cell" style="color: var(--status-red);">Error loading report. Check console.</td></tr>`;
    }
}

function exportToExcel() {
    const table = document.getElementById("oee_trend_table");
    if (!table || table.innerText.includes("Ready to generate")) {
        alert("No data available to export!");
        return;
    }

    const wb = XLSX.utils.table_to_book(table, { raw: true });
    const ws = wb.Sheets[wb.SheetNames[0]];

    // Clean up percentages for Excel so they act as numbers, not text
    for (const cellAddress in ws) {
        if (cellAddress[0] === '!') continue;
        let cell = ws[cellAddress];
        
        if (cell.v && typeof cell.v === 'string') {
            let val = cell.v.trim();
            if (val.includes('%')) {
                let num = parseFloat(val.replace('%', ''));
                if (!isNaN(num)) {
                    cell.v = num;
                    cell.t = 'n'; // Tell Excel it's a number
                }
            }
        }
    }

    const dateStr = new Date().toISOString().split('T')[0];
    XLSX.writeFile(wb, `Process_OEE_Trend_${dateStr}.xlsx`);
}