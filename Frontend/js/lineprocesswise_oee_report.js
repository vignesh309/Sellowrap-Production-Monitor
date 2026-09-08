let allMachinesData = [];
let uniqueLines = [];
let uniqueProcesses = [];
let selectedTagsArray = [];

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

    loadMasterData();
});

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

async function loadMasterData() {
    try {
        const response = await fetch('/api/machine_list');
        if (!response.ok) throw new Error("Failed to load master data");
        const data = await response.json();
        allMachinesData = data.machines;

        // Extract unique Lines and Processes
        const linesSet = new Set();
        const processesSet = new Set();

        allMachinesData.forEach(m => {
            if (m.production_line) linesSet.add(m.production_line);
            if (m.machine_process) processesSet.add(m.machine_process);
        });

        uniqueLines = Array.from(linesSet).sort();
        uniqueProcesses = Array.from(processesSet).sort();

        // Initialize UI with Line view
        switchViewMode();

    } catch (error) {
        console.error("Master Data Error:", error);
    }
}

function switchViewMode() {
    const viewMode = document.querySelector('input[name="view_mode"]:checked').value;
    const label = document.getElementById("selection_label");
    
    selectedTagsArray = []; // Clear current selections
    let optionsToLoad = [];

    if (viewMode === "line") {
        label.innerHTML = 'Line Selection: <small style="color: var(--text-muted); font-weight: normal;">(Remove tags to exclude. Leave blank for ALL)</small>';
        optionsToLoad = uniqueLines;
    } else {
        label.innerHTML = 'Process Selection: <small style="color: var(--text-muted); font-weight: normal;">(Remove tags to exclude. Leave blank for ALL)</small>';
        optionsToLoad = uniqueProcesses;
    }

    // Auto-select everything in the active category
    selectedTagsArray = [...optionsToLoad];
    populateDropdown(optionsToLoad);
    renderTags();
}

function populateDropdown(options) {
    const listContainer = document.getElementById("dropdown_list");
    listContainer.innerHTML = '';

    options.forEach(opt => {
        let div = document.createElement("div");
        div.className = "dropdown-item";
        div.innerText = opt;
        div.onclick = function() {
            addTag(opt);
        };
        listContainer.appendChild(div);
    });
}

// --- Tag Management ---
function toggleDropdown(event) {
    document.getElementById("dropdown_list").classList.add("show");
    document.getElementById("tag_search").focus();
}

function filterList() {
    const input = document.getElementById("tag_search").value.toLowerCase();
    const items = document.querySelectorAll("#dropdown_list .dropdown-item");
    
    items.forEach(item => {
        const text = item.innerText.toLowerCase();
        if (text.includes(input) && !item.classList.contains("selected")) {
            item.style.display = "block";
        } else {
            item.style.display = "none";
        }
    });
}

function addTag(val) {
    if (!selectedTagsArray.includes(val)) {
        selectedTagsArray.push(val);
    }
    renderTags();
    document.getElementById("tag_search").value = "";
    filterList();
    document.getElementById("dropdown_list").classList.remove("show");
}

function removeTag(val) {
    selectedTagsArray = selectedTagsArray.filter(t => t !== val);
    renderTags();
    filterList();
}

function renderTags() {
    const container = document.getElementById("selected_tags_container");
    container.innerHTML = "";
    
    selectedTagsArray.forEach(val => {
        const tag = document.createElement("div");
        tag.className = "machine-tag";
        tag.innerHTML = `${val} <span class="remove-tag" onclick="removeTag('${val}')">×</span>`;
        container.appendChild(tag);
    });

    document.querySelectorAll(".dropdown-item").forEach(item => {
        if (selectedTagsArray.includes(item.innerText)) {
            item.classList.add("selected");
            item.style.display = "none";
        } else {
            item.classList.remove("selected");
            item.style.display = "block";
        }
    });
}

document.addEventListener("click", function(event) {
    const container = document.querySelector(".custom-multiselect-container");
    if (!container.contains(event.target)) {
        document.getElementById("dropdown_list").classList.remove("show");
    }
});

// --- API Call ---
async function generateReport() {
    const startDate = document.getElementById("start_date").value;
    const endDate = document.getElementById("end_date").value;
    const viewMode = document.querySelector('input[name="view_mode"]:checked').value;

    if (!startDate || !endDate) {
        alert("Please select both a Start and End Date.");
        return;
    }
    if (selectedTagsArray.length === 0) {
        alert("Please select at least one item to generate the report.");
        return;
    }

    const entities = selectedTagsArray.join(',');

    try {
        const params = new URLSearchParams();
        params.append('start_date', startDate);
        params.append('end_date', endDate);
        params.append('view_mode', viewMode);
        params.append('entities', entities);

        const response = await fetch(`/api/lineprocesswise_oee_report?${params.toString()}`);
        if (!response.ok) throw new Error("Failed to fetch OEE data");
        
        const data = await response.json();
        window.lastRecords = data.records;
        renderDynamicTableColumns(data.records);
    } catch (error) {
        console.error("Data Fetch Error:", error);
        alert("Error loading report. Check console.");
    }
}

// Exactly the same render function as your machinewise report, BUT WITH CHECKBOX LOGIC
function renderDynamicTableColumns(records) {
    const headerRow = document.getElementById("table_header_row");
    const rows = document.querySelectorAll("#table_body tr");
    const sectionRows = document.querySelectorAll("#table_body .section-row");
    
    // 🚨 NEW: Grab the current state of the checkboxes (default to true if not found)
    const showTime = document.getElementById("show_time_chk") ? document.getElementById("show_time_chk").checked : true;
    const showPct = document.getElementById("show_pct_chk") ? document.getElementById("show_pct_chk").checked : true;

    // 1. Wipe out existing dynamic columns
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

    sectionRows.forEach(row => {
        row.querySelector("td").colSpan = Math.max(records.length + 1, 2);
    });

    if (records.length === 0) {
        headerRow.innerHTML += `<th class="val-col" style="color: var(--status-red);">No Data Found</th>`;
        rows.forEach(row => {
            if (!row.classList.contains("section-row")) {
                row.innerHTML += `<td class="val-cell">-</td>`;
            }
        });
        return;
    }

    records.forEach(r => {
        const th = document.createElement("th");
        th.className = "val-col";
        // Re-use the "machine" key generic name for the column header (Line 1, Moulding, etc.)
        th.innerText = r.machine; 
        headerRow.appendChild(th);

        rows.forEach(row => {
            if (!row.classList.contains("section-row")) {
                const key = row.getAttribute("data-key");
                let val = r[key] !== undefined ? r[key] : "-";
                
                // 🚨 NEW: Format interceptor for Time/Percentage strings 
                if (typeof val === 'string' && val.includes('(') && val.includes('%')) {
                    // Splits "1d 2h (15.5%)" into "1d 2h" and "15.5%"
                    const parts = val.split(' (');
                    if (parts.length === 2) {
                        const timePart = parts[0].trim();
                        const pctPart = parts[1].replace(')', '').trim();

                        if (showTime && showPct) {
                            val = val; // Keep original "1d 2h (15.5%)"
                        } else if (showTime && !showPct) {
                            val = timePart; // Show only "1d 2h"
                        } else if (!showTime && showPct) {
                            val = pctPart; // Show only "15.5%"
                        } else {
                            val = "-"; // If they uncheck both
                        }
                    }
                }

                // Add % sign to main OEE KPIs if needed
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
    const table = document.getElementById("oee_report_table");
    if (!table) {
        alert("No data available to export!");
        return;
    }

    // 1. Convert the HTML table to a SheetJS workbook
    const wb = XLSX.utils.table_to_book(table, { raw: true });
    const ws = wb.Sheets[wb.SheetNames[0]];

    // 2. Iterate through every cell in the generated sheet to clean the data
    for (const cellAddress in ws) {
        if (cellAddress[0] === '!') continue; // Skip SheetJS metadata keys like !ref or !merges

        let cell = ws[cellAddress];
        if (cell.v && typeof cell.v === 'string') {
            let val = cell.v.trim();

            // Regex to catch standalone percentages like "95.8%" or "(95.8%)"
            let pctMatch = val.match(/^\(?([\d\.]+)\s*%\)?$/);
            
            if (pctMatch) {
                // Extract the number, strip the '%', and convert to a float
                cell.v = parseFloat(pctMatch[1]);
                
                // 'n' explicitly tells Excel to treat this cell as a true Number for formulas
                cell.t = 'n'; 
            } 
            // Also fix standard numbers (like Target/Actual Qty) that might accidentally export as text strings
            else if (/^-?[\d\.]+$/.test(val) && !isNaN(parseFloat(val))) {
                cell.v = parseFloat(val);
                cell.t = 'n';
            }
        }
    }

    // 3. Generate date-stamped filename and trigger the download
    const dateStr = new Date().toISOString().split('T')[0];
    XLSX.writeFile(wb, `OEE_Report_${dateStr}.xlsx`);
}