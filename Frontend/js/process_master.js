const backend = window.location.origin;
let currentMode = "EXPLORE"; 

const formInputs = ["process_id", "process_name", "production_line"];
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
        console.warn("Invalid session data. Redirecting to login.");
        window.location.href = "/";
        return; 
    }

    const displayUser = document.getElementById("user-display");
    const displayRole = document.getElementById("role-display");
    const displayAvatar = document.getElementById("user-avatar");

    if (displayUser) displayUser.innerText = fullName;
    if (displayRole) displayRole.innerText = role.toUpperCase();
    if (displayAvatar) displayAvatar.innerText = fullName.charAt(0).toUpperCase(); 

    setMode("EXPLORE");
    loadMasterData(); 
});

// ==========================================
// 2. MASTER DATA FUNCTIONS
// ==========================================
async function loadMasterData() {
    try {
        const response = await fetch(`${backend}/api/process_init`);
        if (response.ok) {
            const data = await response.json();
            const processList = document.getElementById("process_list");
            
            if (processList) {
                processList.innerHTML = ''; 
                data.processes.forEach(p => {
                    processList.innerHTML += `<option value="${p.id}">${p.id} - ${p.process}</option>`;
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

    const codeInput = document.getElementById("process_id");
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
            if (el.tagName === "SELECT") el.value = ""; 
            else el.value = "";
        }
    });
    
    const searchInput = document.getElementById("search_process_id");
    if (searchInput) searchInput.value = "";
}

async function searchProcess() {
    const searchInput = document.getElementById("search_process_id");
    if (!searchInput) return;
    
    const searchVal = searchInput.value.trim();
    if (!searchVal) return;

    try {
        const response = await fetch(`${backend}/api/process/${encodeURIComponent(searchVal)}`);
        if (!response.ok) throw new Error("Process not found.");
        
        const data = await response.json();
        
        const pId = document.getElementById("process_id");
        const pName = document.getElementById("process_name");
        const pLine = document.getElementById("production_line");

        if (pId) pId.value = data.id || "";
        if (pName) pName.value = data.process || "";
        if (pLine) pLine.value = data.production_line || "";
        
        setMode("EXPLORE");
    } catch (error) {
        alert(error.message);
        clearForm();
        setMode("EXPLORE");
    }
}

function startNewProcess() { setMode("NEW"); }
function enableEditMode() { setMode("EDIT"); }

async function saveProcess() {
    let payload = {
        id: document.getElementById("process_id")?.value.trim(),
        process_name: document.getElementById("process_name")?.value.trim(),
        production_line: document.getElementById("production_line")?.value.trim()
    };

    if (!payload.id || !payload.process_name) {
        alert("Process ID and Process Name are required fields.");
        return;
    }

    if (btnSave) {
        btnSave.innerText = "Saving...";
        btnSave.disabled = true;
    }

    try {
        const response = await fetch(`${backend}/api/process/save`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Failed to save.");
        }
        
        alert("Process master data saved!");
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

async function deleteProcess() {
    const pId = document.getElementById("process_id")?.value.trim();
    if (!pId || !confirm(`Delete Process ID "${pId}"?`)) return;

    try {
        const response = await fetch(`${backend}/api/process/${encodeURIComponent(pId)}`, { method: 'DELETE' });
        if (!response.ok) throw new Error("Failed to delete.");

        alert("Process deleted.");
        clearForm();
        setMode("EXPLORE");
        loadMasterData(); 
    } catch (error) { alert(error.message); }
}

function logout() { 
    localStorage.clear(); 
    window.location.href = "/"; 
}