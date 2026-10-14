// ==========================================
// STATE
// ==========================================
let currentPage = 1;
const rowsPerPage = 100;
let totalPages = 1;
let totalRowsCount = 0;
let currentRecords = [];

// ==========================================
// INITIALIZATION & AUTHENTICATION
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
    const role = localStorage.getItem("userRole");
    const fullName = localStorage.getItem("userFullName") || localStorage.getItem("userName");

    if (!role || !fullName || role === "undefined" || fullName === "undefined") {
        window.location.href = "/";
        return;
    }

    document.getElementById("user-display").innerText = fullName;
    document.getElementById("role-display").innerText = role.toUpperCase();
    document.getElementById("user-avatar").innerText = fullName.charAt(0).toUpperCase();

    // Default to the current month (YYYY-MM)
    document.getElementById("filter-month").value = new Date().toISOString().slice(0, 7);

    loadParameterData(1);
});

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

// ==========================================
// HELPERS
// ==========================================
function fmt(value, decimals) {
    if (value === null || value === undefined || value === "") return "-";
    const n = Number(value);
    return Number.isNaN(n) ? value : n.toFixed(decimals);
}

// ==========================================
// DATA FETCHING
// ==========================================
async function loadParameterData(page = 1) {
    const month = document.getElementById("filter-month").value;
    const machine = document.getElementById("filter-machine").value;

    if (!month) {
        alert("Please select a target month.");
        return;
    }

    currentPage = page;
    const tbody = document.getElementById("table-body");
    tbody.innerHTML = `<tr><td colspan="12" class="empty-state">Loading data for ${machine}...</td></tr>`;

    try {
        const offset = (currentPage - 1) * rowsPerPage;
        const response = await fetch(
            `/api/moulding_parameters?month=${month}&machine=${encodeURIComponent(machine)}&limit=${rowsPerPage}&offset=${offset}`
        );

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Failed to fetch parameter data.");
        }

        const data = await response.json();
        currentRecords = data.records || [];
        totalRowsCount = data.total_rows || 0;

        renderTable(currentRecords);
        updatePagination();

        document.getElementById("context-badge").innerText = `${machine} · ${month}`;

    } catch (error) {
        console.error("Parameter Fetch Error:", error);
        tbody.innerHTML = `<tr><td colspan="12" class="empty-state error">Error: ${error.message}</td></tr>`;
        currentRecords = [];
        totalRowsCount = 0;
        document.getElementById("pagination-controls").style.display = "none";
        document.getElementById("total-rows-display").innerText = "Total Rows: 0";
        document.getElementById("context-badge").innerText = "No data loaded";
    }
}

// ==========================================
// TABLE RENDER
// ==========================================
function renderTable(records) {
    const tbody = document.getElementById("table-body");

    if (records.length === 0) {
        tbody.innerHTML = `<tr><td colspan="12" class="empty-state">No parameter data found for this period.</td></tr>`;
        return;
    }

    let html = "";
    records.forEach(r => {
        html += `
            <tr>
                <td class="ts">${r.timestamp || "-"}</td>
                <td class="part">${r.part_no || "-"}</td>
                <td>${r.mold_no || "-"}</td>
                <td class="num temp">${fmt(r.barrel_temp_z1, 1)}</td>
                <td class="num temp">${fmt(r.barrel_temp_z2, 1)}</td>
                <td class="num temp">${fmt(r.barrel_temp_z3, 1)}</td>
                <td class="num temp">${fmt(r.barrel_temp_z4, 1)}</td>
                <td class="num temp">${fmt(r.barrel_temp_z5, 1)}</td>
                <td class="num strong">${fmt(r.max_injection_pressure, 2)}</td>
                <td class="num speed">${fmt(r.injection_speed, 2)}</td>
                <td class="num">${fmt(r.injection_time, 2)}</td>
                <td class="num">${fmt(r.cushion_position, 2)}</td>
            </tr>
        `;
    });
    tbody.innerHTML = html;
}

// ==========================================
// PAGINATION
// ==========================================
function updatePagination() {
    document.getElementById("total-rows-display").innerText = `Total Rows: ${totalRowsCount.toLocaleString()}`;

    if (totalRowsCount === 0) {
        document.getElementById("pagination-controls").style.display = "none";
        return;
    }

    totalPages = Math.ceil(totalRowsCount / rowsPerPage);

    const firstRow = (currentPage - 1) * rowsPerPage + 1;
    const lastRow = Math.min(currentPage * rowsPerPage, totalRowsCount);

    document.getElementById("pagination-controls").style.display = "flex";
    document.getElementById("range-info").innerText =
        `Showing ${firstRow.toLocaleString()}–${lastRow.toLocaleString()} of ${totalRowsCount.toLocaleString()}`;
    document.getElementById("page-input").value = currentPage;
    document.getElementById("total-pages").innerText = totalPages.toLocaleString();

    document.getElementById("btn-prev").disabled = (currentPage === 1);
    document.getElementById("btn-next").disabled = (currentPage === totalPages);
}

function changePage(delta) {
    const newPage = Math.min(Math.max(currentPage + delta, 1), totalPages);
    if (newPage !== currentPage) loadParameterData(newPage);
}

function jumpToPage() {
    let n = parseInt(document.getElementById("page-input").value);
    if (isNaN(n) || n < 1) n = 1;
    if (n > totalPages) n = totalPages;

    document.getElementById("page-input").value = n;
    if (n !== currentPage) loadParameterData(n);
}

// ==========================================
// EXCEL EXPORT (current page)
// ==========================================
function exportToExcel() {
    if (currentRecords.length === 0) {
        alert("No data available to export.");
        return;
    }

    const machine = document.getElementById("filter-machine").value;
    const month = document.getElementById("filter-month").value;

    const rows = currentRecords.map(r => ({
        "Timestamp": r.timestamp,
        "Part No": r.part_no,
        "Mold No": r.mold_no,
        "Z1 (°C)": r.barrel_temp_z1,
        "Z2 (°C)": r.barrel_temp_z2,
        "Z3 (°C)": r.barrel_temp_z3,
        "Z4 (°C)": r.barrel_temp_z4,
        "Z5 (°C)": r.barrel_temp_z5,
        "Max Press (MPa)": r.max_injection_pressure,
        "Inj Speed (mm/s)": r.injection_speed,
        "Inj Time (s)": r.injection_time,
        "Cushion (mm)": r.cushion_position
    }));

    const worksheet = XLSX.utils.json_to_sheet(rows);
    worksheet["!cols"] = [{ wch: 20 }, { wch: 18 }, { wch: 14 }, ...Array(9).fill({ wch: 14 })];

    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, "Parameters");
    XLSX.writeFile(workbook, `Parameters_${machine}_${month}_Page${currentPage}.xlsx`);
}