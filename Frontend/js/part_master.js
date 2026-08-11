// --- STATE MANAGEMENT ---
let currentMode = "EXPLORE";
let currentPartData = { routing: [] }; // 🚨 Only one unified array now!

// DOM Elements
const formInputs = ["part_no", "part_name", "customer_name"];
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

    // Hard Redirect only if completely missing (not logged in at all)
    if (!role || !fullName || role === "undefined" || fullName === "undefined") {
        console.warn("Invalid session data. Redirecting to login.");
        window.location.href = "/";
        return; 
    }

    // Safely Update the Navbar UI
    const displayUser = document.getElementById("user-display");
    const displayRole = document.getElementById("role-display");
    const displayAvatar = document.getElementById("user-avatar");

    if (displayUser) displayUser.innerText = fullName;
    if (displayRole) displayRole.innerText = role.toUpperCase();
    if (displayAvatar) displayAvatar.innerText = fullName.charAt(0).toUpperCase(); 

    // Initialize the Page Data
    setMode("EXPLORE");
    refreshPartDropdown();
});

// ==========================================
// 2. PART MASTER FUNCTIONS
// ==========================================
async function refreshPartDropdown() {
    try {
        const response = await fetch('/api/part_list');
        if (response.ok) {
            const parts = await response.json();
            const dataList = document.getElementById("part_list");
            const searchInput = document.getElementById("search_part_id");

            const currentVal = searchInput.value;
            dataList.innerHTML = '';

            parts.forEach(p => {
                dataList.innerHTML += `<option value="${p.part_no}">${p.part_no} - ${p.part_name}</option>`;
            });

            if (currentVal) searchInput.value = currentVal;
        }
    } catch (error) {
        console.error("Failed to load part dropdown:", error);
    }
}

function setMode(mode) {
    currentMode = mode;
    const isExplore = mode === "EXPLORE";
    const isNew = mode === "NEW";

    formInputs.forEach(id => {
        let el = document.getElementById(id);
        if (el) el.disabled = isExplore;
    });

    if (mode === "EDIT") {
        document.getElementById("part_no").disabled = true;
    }

    btnNew.disabled = !isExplore;
    btnEdit.disabled = !isExplore || !document.getElementById("part_no").value;
    btnSave.disabled = isExplore;
    btnDelete.disabled = !isExplore || !document.getElementById("part_no").value;

    document.getElementById("btn_add_row").disabled = isExplore;

    // 🚨 THE FIX: This now universally unlocks ALL fields when you click EDIT
    const tableElements = document.querySelectorAll("#unified_table_body input, #unified_table_body button");
    tableElements.forEach(el => {
        el.disabled = isExplore;
    });

    if (isNew) {
        clearForm();
        renderUnifiedTable();
    } else if (mode === "EDIT") {
        // This will immediately sweep through and smartly re-lock the Mold fields 
        // for any process that isn't "Moulding", while leaving all the Target fields perfectly editable!
        document.querySelectorAll(".proc-name").forEach(input => checkProcessType(input));
    }
}

function clearForm() {
    formInputs.forEach(id => {
        let el = document.getElementById(id);
        if (el) el.value = "";
    });
    currentPartData = { routing: [] };
}

// --- DATA FETCHING ---
async function searchPart() {
    const partNo = document.getElementById("search_part_id").value.trim();
    if (!partNo) { alert("Please enter a Part NO to search."); return; }

    try {
        const response = await fetch(`/api/part/${encodeURIComponent(partNo)}`);
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Part not found");
        }

        currentPartData = await response.json();
        populateForm(currentPartData);
        setMode("EXPLORE");

    } catch (error) {
        alert(error.message);
        clearForm();
        renderUnifiedTable();
    }
}

function populateForm(data) {
    document.getElementById("part_no").value = data.part_no || "";
    document.getElementById("part_name").value = data.part_name || "";
    document.getElementById("customer_name").value = data.customer_name || "";

    renderUnifiedTable();
    setMode("EXPLORE");
}

// --- CRUD ACTIONS ---
function startNewPart() { setMode("NEW"); }
function enableEditMode() { setMode("EDIT"); }

async function savePart() {
    let payload = {
        part_no: document.getElementById("part_no").value.trim(),
        part_name: document.getElementById("part_name").value.trim(),
        customer_name: document.getElementById("customer_name").value.trim(),
        routing: [] // 🚨 One single payload destination
    };

    if (!payload.part_no || !payload.part_name) {
        alert("Part NO and Part Name are strictly required.");
        return;
    }

    if (currentMode === "NEW") {
        const existingParts = Array.from(document.getElementById("part_list").options).map(opt => opt.value);
        if (existingParts.includes(payload.part_no)) {
            alert(`Error: Part NO "${payload.part_no}" already exists in the database.`);
            return;
        }
    }

    // 🚨 SMART SCRAPER: Grabs the rows exactly as they are and packages them
    const rows = document.querySelectorAll("#unified_table_body tr.data-row");
    rows.forEach((row, index) => {
        let procName = row.querySelector(".proc-name").value.trim();
        if (procName) {
            payload.routing.push({
                sequence: parseInt(row.querySelector(".proc-seq").value) || (index + 1),
                process_name: procName,
                mold_no: row.querySelector(".mold-no").value.trim() || "-",
                mold_name: row.querySelector(".mold-name").value.trim() || "-",
                cavities: parseFloat(row.querySelector(".mold-cav").value) || 1,
                active_cavities: parseFloat(row.querySelector(".mold-active-cav").value) || 1,
                hourly_target: parseInt(row.querySelector(".proc-tgt").value) || 0,
                target_temp: parseFloat(row.querySelector(".proc-temp").value) || 0,
                target_pressure: parseFloat(row.querySelector(".proc-press").value) || 0,
                target_setting: parseFloat(row.querySelector(".proc-timer").value) || 0
            });
        }
    });

    btnSave.innerText = "Saving...";
    btnSave.disabled = true;

    try {
        const response = await fetch('/api/part/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) throw new Error("Failed to save part");

        alert("Part saved successfully!");
        currentPartData = payload;
        setMode("EXPLORE");

        refreshPartDropdown();
        document.getElementById("search_part_id").value = payload.part_no;

    } catch (error) {
        alert(error.message);
    } finally {
        btnSave.disabled = false;
        btnSave.innerText = "💾 SAVE";
    }
}

async function deletePart() {
    const partNo = document.getElementById("part_no").value.trim();
    if (!partNo) return;

    if (!confirm(`Are you absolutely sure you want to delete Part ${partNo}?`)) {
        return;
    }

    try {
        const response = await fetch(`/api/part/${encodeURIComponent(partNo)}`, { method: 'DELETE' });
        if (!response.ok) throw new Error("Failed to delete part");

        alert("Part deleted successfully.");
        document.getElementById("search_part_id").value = "";
        clearForm();
        setMode("EXPLORE");
        refreshPartDropdown();

    } catch (error) {
        alert(error.message);
    }
}

// --- UNIFIED TABLE RENDERING ---
function renderUnifiedTable() {
    const tbody = document.getElementById("unified_table_body");
    tbody.innerHTML = "";

    if (currentPartData.routing && currentPartData.routing.length > 0) {
        currentPartData.routing.forEach(r => {
            addUnifiedRowToUI(
                r.sequence, r.process_name,
                r.mold_no, r.mold_name, r.cavities, r.active_cavities,
                r.hourly_target, r.target_temp, r.target_pressure, r.target_setting
            );
        });
    } else {
        if (currentMode === "EXPLORE") {
            tbody.innerHTML = `<tr><td colspan="11" style="text-align: center; color: gray;">No routing assigned.</td></tr>`;
        } else if (currentMode === "NEW") {
            addUnifiedRowToUI(1, "MOULDING", "", "", 1, 1, 0, 0, 0, 0);
        }
    }
}

function addUnifiedRow() {
    let rowCount = document.querySelectorAll("#unified_table_body tr.data-row").length;
    addUnifiedRowToUI(rowCount + 1, "", "", "", 1, 1, 0, 0, 0, 0);

    // Trigger formatting on the newly spawned row
    const newRow = document.querySelector("#unified_table_body tr:last-child .proc-name");
    if (newRow) checkProcessType(newRow);
}

function addUnifiedRowToUI(seq, procName, moldNo, moldName, cav, actCav, tgtHr, temp, press, timer) {
    const tbody = document.getElementById("unified_table_body");
    if (tbody.innerHTML.includes("No routing assigned")) tbody.innerHTML = "";

    const isEdit = currentMode !== "EXPLORE";
    const tr = document.createElement("tr");
    tr.className = "data-row";

    tr.innerHTML = `
        <td style="text-align: center;">
            <input type="number" class="proc-seq" value="${seq}" ${!isEdit ? 'disabled' : ''} style="width: 50px; text-align: center; font-weight: bold; color: var(--accent-cyan);">
        </td>
        <td>
            <input list="process_list_options" class="proc-name" value="${procName}" ${!isEdit ? 'disabled' : ''} onchange="checkProcessType(this)" onkeyup="checkProcessType(this)" placeholder="Process..." style="width: 100%; box-sizing: border-box;">
        </td>
        <td><input type="text" class="mold-no" value="${moldNo}" ${!isEdit ? 'disabled' : ''} style="width: 100px;"></td>
        <td><input type="text" class="mold-name" value="${moldName}" ${!isEdit ? 'disabled' : ''} style="width: 120px;"></td>
        <td><input type="number" class="mold-cav" step="any" value="${cav}" ${!isEdit ? 'disabled' : ''} style="width: 50px; text-align: center;"></td>
        <td><input type="number" class="mold-active-cav" step="any" value="${actCav}" ${!isEdit ? 'disabled' : ''} style="width: 50px; text-align: center;"></td>
        <td><input type="number" class="proc-tgt" value="${tgtHr || ''}" ${!isEdit ? 'disabled' : ''} placeholder="0" style="width: 70px;"></td>
        <td><input type="number" class="proc-temp" value="${temp || ''}" ${!isEdit ? 'disabled' : ''} placeholder="0" style="width: 70px;"></td>
        <td><input type="number" class="proc-press" value="${press || ''}" ${!isEdit ? 'disabled' : ''} placeholder="0" style="width: 70px;"></td>
        <td><input type="number" class="proc-timer" value="${timer || ''}" ${!isEdit ? 'disabled' : ''} placeholder="0" style="width: 70px;"></td>
        
        <td style="text-align: center;">
            <button class="btn-remove-row" onclick="this.parentElement.parentElement.remove()" ${!isEdit ? 'disabled' : ''}>✕</button>
        </td>
    `;
    tbody.appendChild(tr);

    // Initial run to format the row correctly based on its starting value
    if (isEdit) {
        checkProcessType(tr.querySelector('.proc-name'));
    }
}

// 🚨 SMART FIELD LOCKER: Locks mold fields for non-moulding/presscut/thermowelding processes
function checkProcessType(inputElement) {
    if (currentMode === "EXPLORE") return; // Don't format during view mode

    const row = inputElement.closest('tr');
    const processVal = inputElement.value.toUpperCase(); // Grab the value and convert to uppercase
    
    // Check if the process matches any of the three allowed processes
    const isMoldProcess = ["MOULDING", "PRESSCUT", "THERMOWELDING"].includes(processVal);

    const moldNo = row.querySelector('.mold-no');
    const moldName = row.querySelector('.mold-name');
    const moldCav = row.querySelector('.mold-cav');
    const moldActCav = row.querySelector('.mold-active-cav');

    if (isMoldProcess) {
        // Unlock mold fields
        moldNo.disabled = false; if (moldNo.value === "-") moldNo.value = "";
        moldName.disabled = false; if (moldName.value === "-") moldName.value = "";
        moldCav.disabled = false; if (moldCav.value === "-") moldCav.value = "1";
        moldActCav.disabled = false; if (moldActCav.value === "-") moldActCav.value = "1";
    } else {
        // Lock mold fields and fill with "-"
        moldNo.disabled = true; moldNo.value = "-";
        moldName.disabled = true; moldName.value = "-";
        moldCav.disabled = true; moldCav.value = "-";
        moldActCav.disabled = true; moldActCav.value = "-";
    }
}

function logout() {
    localStorage.clear();
    window.location.href = "/";
}