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

    // Load initial data
    loadMachineData();
});

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

// Global variable to store the raw machine data
let allMachinesData = [];

async function loadMachineData() {
    try {
        const response = await fetch('/api/machine_list');
        if (!response.ok) throw new Error("Failed to load machines");
        
        const data = await response.json();
        allMachinesData = data.machines; 
        
        populateLineDropdown();
        populateProcessDropdown("ALL"); 
        populateMachineDropdown("ALL", "ALL"); 

        // 🚨 EVENT: When Line changes, update Process AND Machine dropdowns
        document.getElementById("line_filter").addEventListener("change", function() {
            const selectedLine = this.value;
            populateProcessDropdown(selectedLine);
            populateMachineDropdown(selectedLine, "ALL"); // Reset machine list
        });

        // 🚨 EVENT: When Process changes, update Machine dropdown
        document.getElementById("process_filter").addEventListener("change", function() {
            const selectedLine = document.getElementById("line_filter").value;
            populateMachineDropdown(selectedLine, this.value);
        });

    } catch (error) {
        console.error("Machine Dropdown Error:", error);
    }
}

function populateLineDropdown() {
    const lineSelect = document.getElementById("line_filter");
    const uniqueLines = new Set();
    
    allMachinesData.forEach(m => {
        if (m.production_line) uniqueLines.add(m.production_line);
    });

    uniqueLines.forEach(line => {
        let option = document.createElement("option");
        option.value = line;
        option.text = line;
        lineSelect.appendChild(option);
    });
}

function populateProcessDropdown(selectedLine) {
    const processSelect = document.getElementById("process_filter");
    processSelect.innerHTML = '<option value="ALL">All Processes</option>'; // Reset
    
    const uniqueProcesses = new Set();
    allMachinesData.forEach(m => {
        // If "ALL" lines is selected, or if the machine's line matches the selection
        if (selectedLine === "ALL" || m.production_line === selectedLine) {
            if (m.machine_process) uniqueProcesses.add(m.machine_process);
        }
    });

    uniqueProcesses.forEach(processName => {
        let option = document.createElement("option");
        option.value = processName;
        option.text = processName;
        processSelect.appendChild(option);
    });
}

let selectedMachinesArray = [];

function populateMachineDropdown(selectedLine, selectedProcess) {
    const listContainer = document.getElementById("machine_dropdown_list");
    listContainer.innerHTML = ''; 
    
    // Filter the machines down based on Line and Process
    let filtered = allMachinesData;
    
    if (selectedLine !== "ALL") {
        filtered = filtered.filter(m => m.production_line === selectedLine);
    }
    if (selectedProcess !== "ALL") {
        filtered = filtered.filter(m => m.machine_process === selectedProcess);
    }
    
    // 🚨 AUTO-SELECT ALL FILTERED MACHINES 
    // This instantly creates tags for every machine in the current filter criteria
    selectedMachinesArray = filtered.map(m => ({ code: m.machine_code, name: m.machine_name }));
    
    // Build the dropdown options (they will initially be hidden since they are all selected)
    filtered.forEach(m => {
        let div = document.createElement("div");
        div.className = "dropdown-item";
        div.innerText = m.machine_name;
        div.setAttribute("data-code", m.machine_code);
        div.onclick = function() {
            addMachineTag(m.machine_code, m.machine_name);
        };
        listContainer.appendChild(div);
    });

    // Render the tags to the UI immediately
    renderTags();
}

// --- NEW TAG MANAGEMENT LOGIC ---

function toggleMachineDropdown(event) {
    document.getElementById("machine_dropdown_list").classList.add("show");
    document.getElementById("machine_search").focus();
}

function filterMachineList() {
    const input = document.getElementById("machine_search").value.toLowerCase();
    const items = document.querySelectorAll("#machine_dropdown_list .dropdown-item");
    
    items.forEach(item => {
        const text = item.innerText.toLowerCase();
        // Hide if it doesn't match search OR if it's already selected
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
    filterMachineList(); // Re-evaluate what should be visible in dropdown
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

    // Mark DOM items as selected so they hide from the list
    document.querySelectorAll(".dropdown-item").forEach(item => {
        if (selectedMachinesArray.some(selected => selected.code === item.getAttribute("data-code"))) {
            item.classList.add("selected");
        } else {
            item.classList.remove("selected");
            item.style.display = "block"; 
        }
    });
}

// Close dropdown if user clicks outside of it
document.addEventListener("click", function(event) {
    const container = document.querySelector(".custom-multiselect-container");
    if (!container.contains(event.target)) {
        document.getElementById("machine_dropdown_list").classList.remove("show");
    }
});

async function generateReport() {
    const startDate = document.getElementById("start_date").value;
    const endDate = document.getElementById("end_date").value;
    
    // Extract from our custom array (if empty, prevent sending "ALL" blindly)
    if (selectedMachinesArray.length === 0) {
        alert("Please select at least one machine to generate a report.");
        return;
    }
    const machine = selectedMachinesArray.map(m => m.code).join(',');

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

        // 🚨 MOVED HERE: This is where we actually get the response from the server!
        const data = await response.json();
        window.lastRecords = data.records; // Save globally for the checkboxes
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
    const showTime = document.getElementById("show_time_chk") ? document.getElementById("show_time_chk").checked : true;
    const showPct = document.getElementById("show_pct_chk") ? document.getElementById("show_pct_chk").checked : true;

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
                
                // --- NEW: Format interceptor for Time/Percentage strings ---
                if (typeof val === 'string' && val.includes('(') && val.includes('%')) {
                    // Splits "1d 2h (15.5%)" into "1d 2h" and "15.5%"
                    const parts = val.split(' (');
                    if (parts.length === 2) {
                        const timePart = parts[0].trim();
                        const pctPart = parts[1].replace(')', '').trim();

                        if (showTime && showPct) {
                            val = val; // Keep original
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
    let table = document.getElementById("oee_report_table");
    if (!table || table.innerText.includes("Select criteria")) {
        alert("No data available to export.");
        return;
    }

    let workbook = XLSX.utils.table_to_book(table, { sheet: "Machinewise OEE", raw: true });
    let dateStr = document.getElementById('start_date').value;
    XLSX.writeFile(workbook, `Machinewise_OEE_${dateStr}.xlsx`);
}