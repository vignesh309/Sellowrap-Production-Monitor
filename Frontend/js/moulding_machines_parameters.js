// ==========================================
// STATE
// ==========================================
let currentPage = 1;
const rowsPerPage = 100;
let totalPages = 1;
let totalRowsCount = 0;
let currentRecords = [];

let allMachinesData = [];
let selectedMachinesArray = [];

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

    // Fetch machines on load
    loadMachineData();
});

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

// ==========================================
// MACHINE TAG DROPDOWN LOGIC
// ==========================================
async function loadMachineData() {
    try {
        const response = await fetch('/api/machine_list');
        if (!response.ok) throw new Error("Failed to load machines");
        
        const data = await response.json();
        // Assuming your API returns { machines: [...] } like the OEE report
        allMachinesData = data.machines; 
        
        populateMachineDropdown();
    } catch (error) {
        console.error("Machine Dropdown Error:", error);
    }
}

function populateMachineDropdown() {
    const listContainer = document.getElementById("machine_dropdown_list");
    listContainer.innerHTML = ''; 
    
    // 🚨 FIX: Filter to show ONLY active MOULDING machines
    const mouldingMachines = allMachinesData.filter(m => 
        m.machine_process === "MOULDING" && m.is_active === true
    );
    
    // Auto-select only the filtered moulding machines
    selectedMachinesArray = mouldingMachines.map(m => ({ code: m.machine_code, name: m.machine_name }));
    
    mouldingMachines.forEach(m => {
        let div = document.createElement("div");
        div.className = "dropdown-item";
        div.innerText = m.machine_name || m.machine_code;
        div.setAttribute("data-code", m.machine_code);
        div.onclick = function() {
            addMachineTag(m.machine_code, m.machine_name || m.machine_code);
        };
        listContainer.appendChild(div);
    });

    renderTags();
}

function toggleMachineDropdown(event) {
    document.getElementById("machine_dropdown_list").classList.add("show");
    document.getElementById("machine_search").focus();
}

function filterMachineList() {
    const input = document.getElementById("machine_search").value.toLowerCase();
    const items = document.querySelectorAll("#machine_dropdown_list .dropdown-item");
    
    items.forEach(item => {
        const text = item.innerText.toLowerCase();
        if (text.includes(input) && !item.classList.contains("selected")) {
            item.style.display = "block";
        } else {
            item.style.display = "none";
        }
    });
}

function addMachineTag(code, name) {
    if (!selectedMachinesArray.some(m => m.code === code)) {
        selectedMachinesArray.push({ code, name });
        renderTags();
    }
    document.getElementById("machine_search").value = "";
    filterMachineList(); 
    document.getElementById("machine_dropdown_list").classList.remove("show");
}

function removeMachineTag(code) {
    selectedMachinesArray = selectedMachinesArray.filter(m => m.code !== code);
    renderTags();
    filterMachineList();
}

function clearAllMachines() {
    selectedMachinesArray = [];
    document.getElementById("machine_search").value = "";
    renderTags();
    filterMachineList(); 
}

function renderTags() {
    const container = document.getElementById("selected_machines_container");
    container.innerHTML = "";
    
    selectedMachinesArray.forEach(m => {
        const tag = document.createElement("div");
        tag.className = "machine-tag";
        tag.innerHTML = `${m.name} <span class="remove-tag" onclick="removeMachineTag('${m.code}')">×</span>`;
        container.appendChild(tag);
    });

    document.querySelectorAll(".dropdown-item").forEach(item => {
        if (selectedMachinesArray.some(selected => selected.code === item.getAttribute("data-code"))) {
            item.classList.add("selected");
        } else {
            item.classList.remove("selected");
            item.style.display = "block"; 
        }
    });
}

// Close dropdown on outside click
document.addEventListener("click", function(event) {
    const container = document.querySelector(".custom-multiselect-container");
    if (container && !container.contains(event.target)) {
        document.getElementById("machine_dropdown_list").classList.remove("show");
    }
});

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
    
    if (selectedMachinesArray.length === 0) {
        alert("Please select at least one machine.");
        return;
    }
    const machineCodes = selectedMachinesArray.map(m => m.code).join(',');

    if (!month) {
        alert("Please select a target month.");
        return;
    }

    currentPage = page;
    const tbody = document.getElementById("table-body");
    // 🚨 Colspan is now 13 to account for the new Machine column
    tbody.innerHTML = `<tr><td colspan="13" class="empty-state">Loading data...</td></tr>`;

    try {
        const offset = (currentPage - 1) * rowsPerPage;
        const response = await fetch(
            `/api/moulding_parameters?month=${month}&machine=${encodeURIComponent(machineCodes)}&limit=${rowsPerPage}&offset=${offset}`
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

        // Update badge to show multi-machine state nicely
        const machineBadgeText = selectedMachinesArray.length > 1 
            ? `${selectedMachinesArray.length} Machines` 
            : selectedMachinesArray[0].name;
            
        document.getElementById("context-badge").innerText = `${machineBadgeText} · ${month}`;

    } catch (error) {
        console.error("Parameter Fetch Error:", error);
        tbody.innerHTML = `<tr><td colspan="13" class="empty-state error">Error: ${error.message}</td></tr>`;
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
        tbody.innerHTML = `<tr><td colspan="13" class="empty-state">No parameter data found for this period.</td></tr>`;
        return;
    }

    let html = "";
    records.forEach(r => {
        html += `
            <tr>
                <td class="ts">${r.timestamp || "-"}</td>
                <td class="strong">${r.machine || "-"}</td> <!-- 🚨 NEW MACHINE COLUMN -->
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

    const month = document.getElementById("filter-month").value;

    const rows = currentRecords.map(r => ({
        "Timestamp": r.timestamp,
        "Machine": r.machine, // 🚨 NEW COLUMN ADDED TO EXPORT
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
    // Expand column widths to include the new Machine column cleanly
    worksheet["!cols"] = [{ wch: 20 }, { wch: 15 }, { wch: 18 }, { wch: 14 }, ...Array(9).fill({ wch: 14 })];

    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, "Parameters");
    XLSX.writeFile(workbook, `Moulding_Parameters_${month}_Page${currentPage}.xlsx`);
}