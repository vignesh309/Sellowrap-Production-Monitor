// --- Identity & Access Logic ---
const role = localStorage.getItem("userRole");
const username = localStorage.getItem("userName") || localStorage.getItem("userFullName") || "Admin";

if (!role || !username) { window.location.href = "/"; }
if (role === "Operator") { 
    alert("Access Denied: You do not have permission to view ERP Integration settings.");
    window.location.href = "/hub";
}

document.getElementById("user-display").innerText = username;
document.getElementById("role-display").innerText = role;
document.getElementById("user-avatar").innerText = username.charAt(0).toUpperCase();

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

// --- Scrolling & Navigation Logic ---
function scrollToSection(sectionId, element) {
    const section = document.getElementById('section-' + sectionId);
    if (section) section.scrollIntoView({ behavior: 'smooth' });
    
    document.querySelectorAll('.sidebar-item').forEach(item => item.classList.remove('active'));
    element.classList.add('active');
    
    // Always reset the mode to EXPLORE when switching tabs to prevent ghost data
    setMode(sectionId, 'EXPLORE');
}

// --- Backend to Frontend Category Mapping ---
const dbCategoryMap = {
    'MACHINE': 'machine_code',
    'PART': 'part_no',
    'MOULD': 'mold_no',
    'EMPLOYEE': 'emp_code',
    'REJECTION': 'rejection_reason_code',
    'DOWNTIME': 'short_reason_code',
    'SHIFT': 'SHIFT'
};

// Global variables to store fetched data
let currentMappings = {};
let activeLoadedId = {}; // Tracks the currently loaded DB ID for each category (for deleting/editing)

// ==========================================
// FORM STATE & MODE MANAGEMENT
// ==========================================
function setMode(uiCategory, mode) {
    const isExplore = mode === 'EXPLORE';
    const isNew = mode === 'NEW';

    const internalEl = document.getElementById(`${uiCategory}_internal`);
    const erpEl = document.getElementById(`${uiCategory}_erp`);
    const descEl = document.getElementById(`${uiCategory}_desc`);

    // Enable/Disable Inputs
    if (internalEl) internalEl.disabled = !isNew; // Internal name is only editable when creating a NEW entry
    if (erpEl) erpEl.disabled = isExplore;
    if (descEl) descEl.disabled = isExplore;

    // Enable/Disable Buttons
    document.getElementById(`btn_new_${uiCategory}`).disabled = !isExplore;
    document.getElementById(`btn_edit_${uiCategory}`).disabled = !isExplore || !internalEl.value;
    document.getElementById(`btn_save_${uiCategory}`).disabled = isExplore;
    document.getElementById(`btn_delete_${uiCategory}`).disabled = !isExplore || !internalEl.value;

    if (isNew) {
        if (internalEl) internalEl.value = '';
        if (erpEl) erpEl.value = '';
        if (descEl) descEl.value = '';
        document.getElementById(`search_${uiCategory}`).value = '';
        activeLoadedId[uiCategory] = null;
        if (internalEl) internalEl.focus();
    }
}

// ==========================================
// SEARCH & LOAD
// ==========================================
function searchMapping(uiCategory) {
    const searchVal = document.getElementById(`search_${uiCategory}`).value.trim();
    if (!searchVal) { alert("Please enter a code to search."); return; }

    const dbCategory = dbCategoryMap[uiCategory];
    const categoryData = currentMappings[dbCategory] || [];
    
    // Find the exact mapping in our loaded array
    const foundData = categoryData.find(row => row.internal.toUpperCase() === searchVal.toUpperCase());

    if (!foundData) {
        alert("Mapping not found. You can click 'NEW' to create it.");
        setMode(uiCategory, 'EXPLORE');
        return;
    }

    // Populate the form
    document.getElementById(`${uiCategory}_internal`).value = foundData.internal;
    document.getElementById(`${uiCategory}_erp`).value = foundData.erp;
    document.getElementById(`${uiCategory}_desc`).value = foundData.desc || "";
    
    // Store the ID so Delete works
    activeLoadedId[uiCategory] = foundData.id;
    
    setMode(uiCategory, 'EXPLORE');
}

// ==========================================
// LIVE CRUD Operations
// ==========================================
async function loadAllMappings() {
    try {
        const response = await fetch('/api/erp_mapping/');
        if (!response.ok) throw new Error("Failed to load mappings");
        
        currentMappings = await response.json();
        
        const uiCategories = ['MACHINE', 'PART', 'MOULD', 'EMPLOYEE', 'REJECTION', 'DOWNTIME', 'SHIFT'];
        uiCategories.forEach(cat => renderTable(cat));
        
    } catch (error) {
        console.error(error);
    }
}

function renderTable(uiCategory) {
    const tbody = document.getElementById(`table-${uiCategory}`);
    if (!tbody) return;

    const dbCategory = dbCategoryMap[uiCategory];
    const data = currentMappings[dbCategory] || [];
    
    if (data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="3" class="loading-cell" style="text-align:center; padding:15px; color:gray;">No mappings found.</td></tr>`;
        return;
    }

    let rowsHtml = '';
    data.forEach(row => {
        // We removed the 'Delete' column from the table since the CRUD toolbar handles it now
        rowsHtml += `
            <tr onclick="quickLoadRow('${uiCategory}', '${row.internal}')" style="cursor: pointer;">
                <td style="color: var(--accent-cyan); font-weight: bold;">${row.internal}</td>
                <td style="color: var(--status-green); font-weight: bold;">${row.erp}</td>
                <td style="color: var(--text-muted);">${row.desc || '-'}</td>
            </tr>
        `;
    });
    tbody.innerHTML = rowsHtml;
}

// Helper to let users click a table row to instantly load it into the form
function quickLoadRow(uiCategory, internalVal) {
    document.getElementById(`search_${uiCategory}`).value = internalVal;
    searchMapping(uiCategory);
    scrollToSection(uiCategory, document.querySelector('.sidebar-item.active'));
}

async function saveMapping(uiCategory) {
    const internalInput = document.getElementById(`${uiCategory}_internal`);
    const erpInput = document.getElementById(`${uiCategory}_erp`);
    const descInput = document.getElementById(`${uiCategory}_desc`);

    if (!internalInput.value || !erpInput.value) {
        alert("Internal Name and FINSYS Code are both required.");
        return;
    }

    const payload = {
        category: dbCategoryMap[uiCategory],
        internal_name: internalInput.value.trim(),
        finsys_code: erpInput.value.trim(),
        description: descInput.value.trim()
    };

    const btnSave = document.getElementById(`btn_save_${uiCategory}`);
    if (btnSave) { btnSave.innerText = "Saving..."; btnSave.disabled = true; }

    try {
        // If we are Editing an existing mapping, we safely Delete the old one first before Posting to handle the unique DB constraint smoothly
        if (activeLoadedId[uiCategory] && internalInput.disabled === true) {
            await fetch(`/api/erp_mapping/${activeLoadedId[uiCategory]}`, { method: 'DELETE' });
        }

        const response = await fetch('/api/erp_mapping/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Failed to save mapping");
        }

        alert("Mapping saved successfully!");
        await loadAllMappings();
        
        // Reload it into Explore Mode
        document.getElementById(`search_${uiCategory}`).value = payload.internal_name;
        searchMapping(uiCategory);

    } catch (error) {
        alert(error.message);
        setMode(uiCategory, 'EXPLORE');
    } finally {
        if (btnSave) { btnSave.innerText = "💾 SAVE"; btnSave.disabled = false; }
    }
}

async function deleteMapping(uiCategory) {
    const idToDelete = activeLoadedId[uiCategory];
    const codeName = document.getElementById(`${uiCategory}_internal`).value;
    
    if (!idToDelete) return;
    if (!confirm(`Are you absolutely sure you want to delete the mapping for "${codeName}"?`)) return;
    
    try {
        const response = await fetch(`/api/erp_mapping/${idToDelete}`, { method: 'DELETE' });
        if (!response.ok) throw new Error("Failed to delete mapping");
        
        alert("Mapping deleted successfully.");
        
        // Wipe the form and reload data
        document.getElementById(`search_${uiCategory}`).value = '';
        setMode(uiCategory, 'NEW'); // Clears the form
        setMode(uiCategory, 'EXPLORE'); // Locks it back down
        await loadAllMappings(); 

    } catch (error) {
        alert(error.message);
    }
}

// ==========================================
// MASTER DATA SYNC & LISTS
// ==========================================
async function loadDatalistOptions() {
    try {
        const response = await fetch('/api/erp_mapping/options');
        if (!response.ok) throw new Error("Failed to fetch mapping options");
        
        const data = await response.json();
        const populateList = (listId, items) => {
            const dataList = document.getElementById(listId);
            if (dataList) dataList.innerHTML = items.map(item => `<option value="${item}"></option>`).join('');
        };

        populateList('dl_machines', data.machines);
        populateList('dl_parts', data.parts);
        populateList('dl_moulds', data.moulds);
        populateList('dl_employees', data.employees);
        populateList('dl_rejections', data.rejections);
        populateList('dl_downtimes', data.downtimes);
    } catch (error) { console.error("Error loading datalists:", error); }
}

async function autoSyncMappings() {
    if (!confirm("This will automatically fetch any missing master data (Machines, Parts, Moulds, etc.) and add them to the ERP mapping table. Do you want to proceed?")) return;

    const syncBtn = document.getElementById("btn_autosync");
    const originalText = syncBtn.innerHTML;
    if (syncBtn) { syncBtn.innerHTML = "⏳ Syncing..."; syncBtn.disabled = true; }

    try {
        const response = await fetch('/api/erp_mapping/auto_sync', { method: 'POST' });
        if (!response.ok) throw new Error("Failed to run Auto-Sync.");
        const result = await response.json();
        
        alert(`✅ ${result.message}`);
        await loadAllMappings();
        await loadDatalistOptions();
    } catch (error) {
        alert(`❌ Auto-Sync Error: ${error.message}`);
    } finally {
        if (syncBtn) { syncBtn.innerHTML = originalText; syncBtn.disabled = false; }
    }
}

// Bootstrap Page
window.onload = () => {
    loadAllMappings(); 
    loadDatalistOptions();
    
    // Initialize all sections to EXPLORE mode
    const uiCategories = ['MACHINE', 'PART', 'MOULD', 'EMPLOYEE', 'REJECTION', 'DOWNTIME', 'SHIFT'];
    uiCategories.forEach(cat => setMode(cat, 'EXPLORE'));
};