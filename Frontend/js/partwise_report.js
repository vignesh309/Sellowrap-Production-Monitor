window.onload = async () => {
    // Set date to today automatically
    const today = new Date().toISOString().split('T')[0];

    document.getElementById('from_date').value = today;
    document.getElementById('to_date').value = today;

    // Fetch machine list for the dropdown
    try {
        const response = await fetch(`/api/get_machines`);
        if (response.ok) {
            const data = await response.json();
            const select = document.getElementById("machine_filter");
            data.machines.forEach(m => {
                select.innerHTML += `<option value="${m.code}">${m.code}</option>`;
            });
        }
    } catch (e) { console.error("Could not load machines"); }
};

let currentPage = 1;
const PAGE_SIZE = 500;
let totalPages = 1;

// --- User Profile & Logout Logic ---
const role = localStorage.getItem("userRole") || "Unknown";
const username = localStorage.getItem("userName") || "User";

document.addEventListener('DOMContentLoaded', () => {
    const userDisplay = document.getElementById("user-display");
    const roleDisplay = document.getElementById("role-display");
    const userAvatar = document.getElementById("user-avatar");

    if (userDisplay) userDisplay.innerText = username;
    if (roleDisplay) roleDisplay.innerText = role;

    if (username && username !== "User" && userAvatar) {
        userAvatar.innerText = username.charAt(0).toUpperCase();
    }
});

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

function formatIndianDate(dateString) {
    if (!dateString) return '-';

    const parts = dateString.split('-'); // YYYY-MM-DD
    if (parts.length !== 3) return dateString;

    return `${parts[2]}-${parts[1]}-${parts[0]}`;
}

// 🚨 UPDATED: Accepts 'isNewSearch' to reset to Page 1
async function fetchReportData(isNewSearch = false) {
    const fromDateVal = document.getElementById('from_date').value;
const toDateVal = document.getElementById('to_date').value;
    const machineVal = document.getElementById('machine_filter').value;
    const shiftVal = document.getElementById('shift_filter').value; 
    
    if (!fromDateVal) {
        alert("Please select a date.");
        return;
    }

    // Reset to page 1 if the user clicked "Generate Report"
    if (isNewSearch) currentPage = 1;

    const tbody = document.getElementById('report_body');
    const colSpan = shiftVal === 'ALL' ? 40 : 28; 
    
    tbody.innerHTML = `<tr><td colspan="${colSpan}" style="color: var(--accent-cyan); text-align: center; padding: 30px;">Loading Page ${currentPage}...</td></tr>`;

    document.querySelectorAll('.col-shift-a').forEach(th => th.style.display = (shiftVal === 'B') ? 'none' : '');
    document.querySelectorAll('.col-shift-b').forEach(th => th.style.display = (shiftVal === 'A') ? 'none' : '');

    try {
        // 🚨 NEW: Appended page and page_size to the URL!
        const url = `/api/reports/partwise?from_date=${fromDateVal}&to_date=${toDateVal}&machine=${machineVal}&shift=${shiftVal}&page=${currentPage}&page_size=${PAGE_SIZE}`;
        const response = await fetch(url);
        
        if (!response.ok) throw new Error("Failed to fetch report data");
        
        const data = await response.json();
        renderTable(data.rows, shiftVal); 

        // 🚨 NEW: Update Pagination UI
        totalPages = Math.ceil(data.total_rows / PAGE_SIZE) || 1;
        
        let startRow = (currentPage - 1) * PAGE_SIZE + 1;
        let endRow = Math.min(currentPage * PAGE_SIZE, data.total_rows);
        
        if (data.total_rows === 0) {
            startRow = 0;
            endRow = 0;
        }

        document.getElementById("page-info").innerText = `Showing ${startRow}-${endRow} of ${data.total_rows} total rows`;
        document.getElementById("page-number").innerText = `Page ${currentPage} of ${totalPages}`;

        // Disable buttons if at boundaries
        document.getElementById("btn-prev").disabled = currentPage === 1;
        document.getElementById("btn-prev").style.opacity = currentPage === 1 ? "0.5" : "1";
        
        document.getElementById("btn-next").disabled = currentPage === totalPages;
        document.getElementById("btn-next").style.opacity = currentPage === totalPages ? "0.5" : "1";

    } catch (error) {
        console.error("Report Error:", error);
        tbody.innerHTML = `<tr><td colspan="${colSpan}" style="color: var(--status-red); text-align: center; padding: 30px;">Error loading report: ${error.message}</td></tr>`;
    }
}

// 🚨 NEW: Navigation Function
function changePage(direction) {
    currentPage += direction;
    if (currentPage < 1) currentPage = 1;
    if (currentPage > totalPages) currentPage = totalPages;
    fetchReportData(false); // false = do not reset to page 1
}

function renderTable(rows, currentShiftFilter) {
    const tbody = document.getElementById('report_body');
    tbody.innerHTML = "";

    const colSpan = currentShiftFilter === 'ALL' ? 40 : 28;

    if (rows.length === 0) {
        tbody.innerHTML = `<tr><td colspan="${colSpan}" style="color: var(--text-muted); text-align: center; padding: 30px;">No production records found for this selection.</td></tr>`;
        return;
    }

    rows.forEach(row => {
        let tr = document.createElement('tr');

        let hourCells = "";
        for (let i = 0; i < 24; i++) {
            let isShiftA = i < 12;
            let isShiftB = i >= 12;

            let showCol = (currentShiftFilter === 'ALL') ||
                (currentShiftFilter === 'A' && isShiftA) ||
                (currentShiftFilter === 'B' && isShiftB);

            if (showCol) {
                let val = row.hours[i] !== undefined && row.hours[i] !== null ? row.hours[i] : "-";
                hourCells += `<td>${val}</td>`;
            }
        }

        let displayShift = currentShiftFilter === 'ALL' ? 'All' : currentShiftFilter;

        // 🚨 Logic to hide Mould/Die and Cavities for downstream machines
        const proc = row.process ? row.process.toUpperCase() : "";
        const isMouldingOrPressCut = (proc === 'MOULDING' || proc === 'PRESS CUT');

        const displayMould = isMouldingOrPressCut ? (row.mould || '-') : '-';
        const displayCavities = isMouldingOrPressCut ? (row.cavities || '-') : '-';

        tr.innerHTML = `
            <td>${formatIndianDate(row.date)}</td>
            <td style="color: var(--accent-cyan); font-weight: bold;">${displayShift}</td>
            <td style="color: var(--text-main); font-weight: bold;">${row.machine}</td>
            <td>${displayMould}</td>
            <td>${row.part_no}</td>
            <td>${displayCavities}</td>
            <td style="color: var(--text-muted);">${row.supervisor || '-'}</td>
            <td>${row.operator}</td>
            <td style="color: var(--status-yellow); font-weight: bold;">${row.target_qty || 0}</td>
            
            ${hourCells}
            
            <td style="font-weight: bold;">${row.total_actual || 0}</td>
            <td class="val-ok">${row.ok_qty || 0}</td>
            <td class="val-ng">${row.rej_qty || 0}</td>
            <td style="color: var(--accent-cyan); font-weight: bold;">${row.total_qty || 0}</td>
            <td style="color: var(--status-yellow);">${row.major_shortfall || '-'}</td>
            <td style="color: var(--status-red);">${row.major_ng || '-'}</td>
            <td style="color: var(--text-muted); font-style: italic;">${row.remarks || ''}</td>
        `;
        tbody.appendChild(tr);
    });
}

function exportToExcel() {
    let table = document.getElementById("dataTable");
    let workbook = XLSX.utils.table_to_book(table, {
        sheet: "Partwise Report",
        raw: true
    });

    let fromDate = document.getElementById('from_date').value;
    let toDate = document.getElementById('to_date').value;

    let dateStr =
        fromDate === toDate
            ? fromDate
            : `${fromDate}_to_${toDate}`;
    let fileName = `Partwise_Production_Report_${dateStr}.xlsx`;

    XLSX.writeFile(workbook, fileName);
}