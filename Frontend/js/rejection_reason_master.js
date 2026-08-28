// --- STATE MANAGEMENT ---
let currentMode = "EXPLORE";
let currentReasonData = {}; 
let fullMasterList = []; 
let selectedProcesses = []; // 🚨 NEW: Array to hold accumulated tags

// 🚨 UPDATED: Added process_dropdown to form tracking
const formInputs = ["reason_code", "reason_name", "category", "oee_impact", "process_dropdown", "is_active"];
const btnNew = document.getElementById("btn_new");
const btnEdit = document.getElementById("btn_edit");
const btnSave = document.getElementById("btn_save");
const btnDelete = document.getElementById("btn_delete");

// ==========================================
// 1. PAGE INITIALIZATION & AUTHENTICATION
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
    const role = localStorage.getItem("userRole");
    const fullName = localStorage.getItem("userFullName");

    if (!role || !fullName || role === "undefined" || fullName === "undefined") {
        window.location.href = "/";
        return; 
    }

    // Populate Navbar UI
    const displayUser = document.getElementById("user-display");
    const displayRole = document.getElementById("role-display");
    const displayAvatar = document.getElementById("user-avatar");

    if (displayUser) displayUser.innerText = fullName;
    if (displayRole) displayRole.innerText = role.toUpperCase();
    if (displayAvatar) displayAvatar.innerText = fullName.charAt(0).toUpperCase(); 

    // Initialize Page State
    setMode("EXPLORE");
    refreshMasterList();
    loadProcessDropdown(); // 🚨 NEW: Fetch processes on load
});

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

// ==========================================
// 2. TAG/CHIP UI LOGIC
// ==========================================
async function loadProcessDropdown() {
    try {
        const response = await fetch('/api/get_processes');
        if (!response.ok) throw new Error("Failed to fetch processes");
        
        const data = await response.json();
        const processSelect = document.getElementById("process_dropdown");
        
        processSelect.innerHTML = '<option value="">-- Choose Process --</option>'; 
        
        data.processes.forEach(proc => {
            let option = document.createElement("option");
            option.value = proc;
            option.text = proc;
            processSelect.appendChild(option);
        });
    } catch (error) {
        console.error("Failed to load processes:", error);
    }
}

function addProcess() {
    const dropdown = document.getElementById("process_dropdown");
    const val = dropdown.value;
    
    if (!val) return;
    if (selectedProcesses.includes(val)) {
        alert("This process is already added!");
        return;
    }
    
    selectedProcesses.push(val);
    renderProcessTags();
    dropdown.value = ""; // Reset dropdown after adding
}

function removeProcess(val) {
    if (currentMode === "EXPLORE") return; // Safety lock
    selectedProcesses = selectedProcesses.filter(p => p !== val);
    renderProcessTags();
}

function renderProcessTags() {
    const container = document.getElementById("selected_processes_container");
    if (!container) return; // Safety check in case HTML isn't updated yet
    
    container.innerHTML = "";
    const isExplore = currentMode === "EXPLORE";

    if (selectedProcesses.length === 0) {
        container.innerHTML = `<span class="empty-tag-msg">No processes added yet.</span>`;
        return;
    }

    selectedProcesses.forEach(proc => {
        const tag = document.createElement("div");
        tag.className = "process-tag";
        
        // Hide the remove button if we are just exploring/viewing
        let removeBtnHTML = "";
        if (!isExplore) {
            removeBtnHTML = `<button class="tag-remove" onclick="removeProcess('${proc}')" title="Remove">✕</button>`;
        }

        tag.innerHTML = `<span>${proc}</span> ${removeBtnHTML}`;
        container.appendChild(tag);
    });
}

// ==========================================
// 3. MASTER DATA FUNCTIONS & STATE
// ==========================================
function setMode(mode) {
    currentMode = mode;
    const isExplore = mode === "EXPLORE";
    const isNew = mode === "NEW";

    // Enable/Disable core form inputs based on state
    formInputs.forEach(id => {
        let el = document.getElementById(id);
        if (el) el.disabled = isExplore;
    });

    // Reason Code should be completely locked down during an EDIT
    if (mode === "EDIT") {
        const codeInput = document.getElementById("reason_code");
        if(codeInput) codeInput.disabled = true;
    }

    // Manage Buttons
    btnNew.disabled = !isExplore;
    btnEdit.disabled = !isExplore || !document.getElementById("reason_code").value;
    btnSave.disabled = isExplore;
    btnDelete.disabled = !isExplore || !document.getElementById("reason_code").value;

    const btnAddProcess = document.getElementById("btn_add_process");
    if (btnAddProcess) btnAddProcess.disabled = isExplore; // Lock/Unlock ADD button
    
    renderProcessTags(); // Re-render tags to hide/show the 'x' buttons

    if (isNew) {
        clearForm();
        document.getElementById("is_active").value = "true"; // Default to active for new
        document.getElementById("oee_impact").value = "Quality";
    }
}

function clearForm() {
    formInputs.forEach(id => {
        let el = document.getElementById(id);
        if (el) el.value = "";
    });
    currentReasonData = {};
    selectedProcesses = []; // 🚨 NEW: Clear array
    renderProcessTags();    // 🚨 NEW: Clear UI
}

// ==========================================
// 4. API / DATA FETCHING LOGIC
// ==========================================
async function refreshMasterList() {
    try {
        const response = await fetch('/api/rejection_list');
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json(); 
        fullMasterList = data;
        
        updateSearchDatalist();
        renderOverviewTable();

    } catch (error) {
        console.error("Failed to load master list:", error);
    }
}

function updateSearchDatalist() {
    const dataList = document.getElementById("reason_list");
    const searchInput = document.getElementById("search_reason_id");
    if (!dataList || !searchInput) return;

    const currentVal = searchInput.value;
    
    dataList.innerHTML = '';
    fullMasterList.forEach(r => {
        dataList.innerHTML += `<option value="${r.reason_code}">${r.reason_code} - ${r.reason_name}</option>`;
    });

    if (currentVal) searchInput.value = currentVal;
}

function renderOverviewTable() {
    const tbody = document.getElementById("overview_table_body");
    if(!tbody) return;

    tbody.innerHTML = "";

    if (fullMasterList.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: gray;">No reasons configured.</td></tr>`;
        return;
    }

    fullMasterList.forEach(r => {
        const tr = document.createElement("tr");
        const statusClass = r.is_active ? "chip-active" : "chip-inactive";
        const statusText = r.is_active ? "Active" : "Inactive";
        
        // 🚨 NEW: Safely parse processes for the table display
        const processesDisplay = Array.isArray(r.valid_processes) && r.valid_processes.length > 0 
            ? r.valid_processes.join(", ") 
            : "-";

        // Click row to quick-load it into the form
        tr.onclick = () => {
            document.getElementById("search_reason_id").value = r.reason_code;
            searchReason();
        };

        tr.innerHTML = `
            <td style="font-weight: bold; color: var(--accent-cyan);">${r.reason_code}</td>
            <td>${r.reason_name}</td>
            <td>${r.category}</td>
            <td>${r.oee_impact}</td>
            <td>${processesDisplay}</td> <!-- 🚨 NEW -->
            <td style="text-align: center;"><span class="status-chip ${statusClass}">${statusText}</span></td>
        `;
        tbody.appendChild(tr);
    });
}

async function searchReason() {
    const reasonCode = document.getElementById("search_reason_id").value.trim();
    if (!reasonCode) { alert("Please enter a Reason Code to search."); return; }

    try {
        const response = await fetch(`/api/rejection/${encodeURIComponent(reasonCode)}`);
        if (!response.ok) throw new Error("Reason not found");
        currentReasonData = await response.json();

        populateForm(currentReasonData);

    } catch (error) {
        alert(error.message);
        clearForm();
        setMode("EXPLORE");
    }
}

function populateForm(data) {
    document.getElementById("reason_code").value = data.reason_code || "";
    document.getElementById("reason_name").value = data.reason_name || "";
    document.getElementById("category").value = data.category || "";
    document.getElementById("oee_impact").value = data.oee_impact || "Quality";
    document.getElementById("is_active").value = data.is_active === true ? "true" : "false";

    // 🚨 NEW: Safely load the processes array
    let processes = data.valid_processes || [];
    if (!Array.isArray(processes)) {
        processes = processes.split(',').map(s => s.trim()).filter(Boolean); 
    }
    
    selectedProcesses = processes;

    setMode("EXPLORE"); // This will automatically lock fields and render the tags!
}

// ==========================================
// 5. CRUD ACTIONS
// ==========================================
function startNewReason() { setMode("NEW"); }
function enableEditMode() { setMode("EDIT"); }

async function saveReason() {
    let payload = {
        reason_code: document.getElementById("reason_code").value.trim(),
        reason_name: document.getElementById("reason_name").value.trim(),
        category: document.getElementById("category").value.trim(),
        oee_impact: document.getElementById("oee_impact").value,
        valid_processes: selectedProcesses, // 🚨 NEW: Directly pass the tags array
        is_active: document.getElementById("is_active").value === "true"
    };

    if (!payload.reason_code || !payload.reason_name || !payload.category) {
        alert("Reason Code, Name, and Category are strictly required.");
        return;
    }

    if (currentMode === "NEW") {
        const exists = fullMasterList.some(r => r.reason_code === payload.reason_code);
        if (exists) {
            alert(`Error: Reason Code "${payload.reason_code}" already exists.`);
            return;
        }
    }

    btnSave.innerText = "Saving...";
    btnSave.disabled = true;

    try {
        const response = await fetch('/api/rejection/save', {
             method: 'POST',
             headers: { 'Content-Type': 'application/json' },
             body: JSON.stringify(payload)
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || "Failed to save reason");
        }

        alert("Reason saved successfully!");
        
        setMode("EXPLORE");
        document.getElementById("search_reason_id").value = payload.reason_code;
        refreshMasterList(); 

    } catch (error) {
        alert(`❌ Server Error: ${error.message}`);
    } finally {
        btnSave.disabled = false;
        btnSave.innerText = "💾 SAVE";
    }
}

async function deleteReason() {
    const reasonCode = document.getElementById("reason_code").value.trim();
    if (!reasonCode) return;

    if (!confirm(`Are you absolutely sure you want to delete Reason ${reasonCode}?`)) {
        return;
    }

    try {
        const response = await fetch(`/api/rejection/${encodeURIComponent(reasonCode)}`, { method: 'DELETE' });
        if (!response.ok) throw new Error("Failed to delete reason");

        alert("Reason deleted successfully.");
        document.getElementById("search_reason_id").value = "";
        clearForm();
        setMode("EXPLORE");
        refreshMasterList();

    } catch (error) {
        alert(error.message);
    }
}