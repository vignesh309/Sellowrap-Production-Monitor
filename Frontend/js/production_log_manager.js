
// ==========================================
// 1. PAGE SECURITY & INITIALIZATION
// ==========================================

function enforcePagePassword() {
    // Set your desired page password here
    const pagePassword = "AdminLog2026"; 
    
    // Trigger the browser's native password prompt
    let userEntry = prompt("🔒 Security Check: Please enter the admin password to access the Log Manager.");

    if (userEntry !== pagePassword) {
        alert("❌ Incorrect password. Access denied.");
        window.location.href = "/hub"; // Kick them back to the safe zone
        return false; 
    }
    
    return true; 
}

let selectedLogIds = new Set();
let currentLogs = [];

document.addEventListener("DOMContentLoaded", () => {
    // 🚨 RUN THE PASSWORD CHECK FIRST
    if (!enforcePagePassword()) {
        return; // Stop the rest of the page from initializing if they fail
    }

    // Existing Identity check
    const role = localStorage.getItem("userRole");
    const fullName = localStorage.getItem("userFullName");

    if (!role || !fullName || role === "undefined" || fullName === "undefined") {
        window.location.href = "/";
        return; 
    }

    document.getElementById("user-display").innerText = fullName;
    document.getElementById("role-display").innerText = role.toUpperCase();
    document.getElementById("user-avatar").innerText = fullName.charAt(0).toUpperCase(); 

    // Set Default Date to Today
    const now = new Date();
    const offsetDate = new Date(now.getTime() - (now.getTimezoneOffset() * 60000));
    const todayStr = offsetDate.toISOString().split('T')[0];
    document.getElementById("filter_date").value = todayStr;

    // Load Dropdowns & Initial Data
    loadMachineDropdown();
    loadLogs();
});

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

// ==========================================
// 2. FETCH DATA & RENDER
// ==========================================
async function loadMachineDropdown() {
    try {
        const response = await fetch('/api/machine_list');
        if (!response.ok) throw new Error("Failed to load machines");
        
        const data = await response.json();
        const select = document.getElementById("filter_machine");
        
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

function clearFilters() {
    document.getElementById("filter_date").value = "";
    document.getElementById("filter_shift").value = "ALL";
    document.getElementById("filter_machine").value = "ALL";
    loadLogs();
}

async function loadLogs() {
    const filterDate = document.getElementById("filter_date").value;
    const filterShift = document.getElementById("filter_shift").value;
    const filterMachine = document.getElementById("filter_machine").value;

    const tbody = document.getElementById("logs_table_body");
    tbody.innerHTML = `<tr><td colspan="9" class="empty-state">Loading logs...</td></tr>`;

    try {
        const params = new URLSearchParams();
        if (filterDate) params.append('filter_date', filterDate);
        if (filterShift !== "ALL") params.append('filter_shift', filterShift);
        if (filterMachine !== "ALL") params.append('filter_machine', filterMachine);

        const response = await fetch(`/api/production_logs?${params.toString()}`);
        if (!response.ok) throw new Error("Failed to fetch logs");

        const data = await response.json();
        currentLogs = data.records;
        
        // Clear previous selections when loading new data
        selectedLogIds.clear(); 
        
        renderTable();

    } catch (error) {
        console.error("Fetch Error:", error);
        tbody.innerHTML = `<tr><td colspan="9" class="empty-state" style="color: var(--status-red);">❌ Error loading logs.</td></tr>`;
    }
}

function renderTable() {
    const tbody = document.getElementById("logs_table_body");
    
    if (currentLogs.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" class="empty-state">No hourly logs found for these filters.</td></tr>`;
        updateSelectionState();
        return;
    }

    let html = "";
    currentLogs.forEach(r => {
        const isChecked = selectedLogIds.has(r.log_id) ? "checked" : "";
        
        html += `
            <tr>
                <td style="text-align: center;">
                    <input type="checkbox" style="cursor: pointer;" value="${r.log_id}" ${isChecked} onchange="toggleRowSelection(this)">
                </td>
                <td style="font-weight: bold; color: var(--text-muted);">#${r.log_id}</td>
                <td>${r.date_shift}</td>
                <td style="color: var(--accent-cyan); font-weight: bold;">${r.machine}</td>
                <td>${r.part_no}</td>
                <td style="color: var(--status-yellow);">${r.time_block}</td>
                <td class="text-right">${r.target}</td>
                <td class="text-right" style="color: var(--status-green); font-weight: bold;">${r.actual}</td>
                <td class="text-center">
                    <svg fill="currentColor" class="action-icon" viewBox="0 0 24 24" width="20" height="20" onclick="deleteSingleLog(${r.log_id})">
                        <path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"></path>
                    </svg>
                </td>
            </tr>
        `;
    });

    tbody.innerHTML = html;
    updateSelectionState();
}

// ==========================================
// 3. SELECTION & DELETE LOGIC
// ==========================================
function toggleRowSelection(checkbox) {
    const logId = parseInt(checkbox.value);
    if (checkbox.checked) {
        selectedLogIds.add(logId);
    } else {
        selectedLogIds.delete(logId);
    }
    updateSelectionState();
}

function toggleSelectAll() {
    const selectAllCb = document.getElementById("selectAllCheckbox");
    const isChecked = selectAllCb.checked;

    currentLogs.forEach(r => {
        if (isChecked) {
            selectedLogIds.add(r.log_id);
        } else {
            selectedLogIds.delete(r.log_id);
        }
    });
    
    renderTable();
}

function updateSelectionState() {
    const btn = document.getElementById("btn_delete_selected");
    const selectAllCb = document.getElementById("selectAllCheckbox");

    // Enable/Disable the delete button
    if (selectedLogIds.size > 0) {
        btn.disabled = false;
        btn.innerHTML = `<svg viewBox="0 0 24 24" style="width: 18px; height: 18px; fill: currentColor; margin-right: 5px; vertical-align: middle;"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"></path></svg> Delete Selected (${selectedLogIds.size})`;
    } else {
        btn.disabled = true;
        btn.innerHTML = `<svg viewBox="0 0 24 24" style="width: 18px; height: 18px; fill: currentColor; margin-right: 5px; vertical-align: middle;"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"></path></svg> Delete Selected`;
    }

    // Sync the "Select All" checkbox header
    if (currentLogs.length > 0 && selectedLogIds.size === currentLogs.length) {
        selectAllCb.checked = true;
    } else {
        selectAllCb.checked = false;
    }
}

// Quick shortcut for the trash can icon on individual rows
function deleteSingleLog(logId) {
    selectedLogIds.clear();
    selectedLogIds.add(logId);
    renderTable();
    deleteSelectedLogs();
}

async function deleteSelectedLogs() {
    if (selectedLogIds.size === 0) return;

    if (!confirm(`Are you absolutely sure you want to permanently delete ${selectedLogIds.size} hourly block(s)?\n\nThis will also wipe the linked Shortfalls, Rejections, and FINSYS ERP Payload staging data for these hours. Operators will need to re-enter this data.`)) {
        return;
    }

    const btn = document.getElementById("btn_delete_selected");
    const originalText = btn.innerHTML;
    btn.innerHTML = "⏳ Deleting...";
    btn.disabled = true;

    try {
        const payload = { log_ids: Array.from(selectedLogIds) };

        const response = await fetch('/api/production_logs/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Failed to delete logs.");
        }

        const data = await response.json();
        alert(`✅ ${data.message}`);
        
        // Refresh the table
        loadLogs();

    } catch (error) {
        alert(`❌ Delete Error: ${error.message}`);
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}