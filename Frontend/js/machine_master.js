const backend = window.location.origin;
let currentMode = "EXPLORE"; 

const formInputs = ["machine_code", "machine_name", "machine_process", "is_active"];
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
    loadMasterData(); 
});

// ==========================================
// 2. MASTER DATA FUNCTIONS
// ==========================================
async function loadMasterData() {
    try {
        const response = await fetch(`${backend}/api/machine_init`);
        if (response.ok) {
            const data = await response.json();
            const machineList = document.getElementById("machine_list");
            
            if (machineList) {
                machineList.innerHTML = ''; 
                data.machines.forEach(m => {
                    machineList.innerHTML += `<option value="${m.machine_code}">${m.machine_code} - ${m.machine_name}</option>`;
                });
            }
        }
    } catch (error) { 
        console.error("Failed to load master data:", error); 
    }
}

function setMode(mode) {
    currentMode = mode;
    const isExplore = mode === "EXPLORE";

    // Safely disable/enable inputs
    formInputs.forEach(id => {
        let el = document.getElementById(id);
        if (el) el.disabled = isExplore;
    });

    const codeInput = document.getElementById("machine_code");
    if (codeInput && mode === "EDIT") codeInput.disabled = true;

    // Safely update button states
    if (btnNew) btnNew.disabled = !isExplore;
    if (btnEdit) btnEdit.disabled = !isExplore || (codeInput && !codeInput.value);
    if (btnSave) btnSave.disabled = isExplore;
    if (btnDelete) btnDelete.disabled = !isExplore || (codeInput && !codeInput.value);

    if (mode === "NEW") {
        clearForm();
        if (codeInput) codeInput.focus();
    }
}

function clearForm() {
    formInputs.forEach(id => {
        let el = document.getElementById(id);
        if (el) {
            if (el.tagName === "SELECT") el.value = "true"; 
            else el.value = "";
        }
    });
    
    const searchInput = document.getElementById("search_machine_code");
    if (searchInput) searchInput.value = "";
}

async function searchMachine() {
    const searchInput = document.getElementById("search_machine_code");
    if (!searchInput) return;
    
    const searchVal = searchInput.value.trim();
    if (!searchVal) return;

    try {
        const response = await fetch(`${backend}/api/machine/${encodeURIComponent(searchVal)}`);
        if (!response.ok) throw new Error("Machine not found.");
        
        const data = await response.json();
        
        // Safely map data to inputs
        const mCode = document.getElementById("machine_code");
        const mName = document.getElementById("machine_name");
        const mProc = document.getElementById("machine_process");
        const mAct = document.getElementById("is_active");

        if (mCode) mCode.value = data.machine_code || "";
        if (mName) mName.value = data.machine_name || "";
        if (mProc) mProc.value = data.machine_process || "";
        if (mAct) mAct.value = data.is_active ? "true" : "false";
        
        setMode("EXPLORE");
    } catch (error) {
        alert(error.message);
        clearForm();
        setMode("EXPLORE");
    }
}

function startNewMachine() { setMode("NEW"); }
function enableEditMode() { setMode("EDIT"); }

async function saveMachine() {
    let payload = {
        machine_code: document.getElementById("machine_code")?.value.trim(),
        machine_name: document.getElementById("machine_name")?.value.trim(),
        machine_process: document.getElementById("machine_process")?.value.trim(),
        is_active: document.getElementById("is_active")?.value === "true"
    };

    if (!payload.machine_code || !payload.machine_name || !payload.machine_process) {
        alert("Machine Code, Name, and Process are all required fields.");
        return;
    }

    if (btnSave) {
        btnSave.innerText = "Saving...";
        btnSave.disabled = true;
    }

    try {
        const response = await fetch(`${backend}/api/machine/save`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Failed to save.");
        }
        
        alert("Machine master data saved!");
        setMode("EXPLORE");
        loadMasterData(); 
    } catch (error) {
        alert(error.message);
    } finally {
        if (btnSave) {
            btnSave.disabled = false;
            btnSave.innerText = "💾 SAVE";
        }
    }
}

async function deleteMachine() {
    const machineCode = document.getElementById("machine_code")?.value.trim();
    if (!machineCode || !confirm(`Delete Machine "${machineCode}"?`)) return;

    try {
        const response = await fetch(`${backend}/api/machine/${encodeURIComponent(machineCode)}`, { method: 'DELETE' });
        if (!response.ok) throw new Error("Failed to delete.");

        alert("Machine deleted.");
        clearForm();
        setMode("EXPLORE");
        loadMasterData(); 
    } catch (error) { alert(error.message); }
}

// Global Logout Function
function logout() { 
    localStorage.clear(); 
    window.location.href = "/"; 
}