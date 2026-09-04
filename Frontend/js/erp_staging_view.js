// --- Pagination State ---
let pendingRecords = [];
let pushedRecords = [];
const ROWS_PER_PAGE = 200;
let currentPendingPage = 1;
let currentPushedPage = 1;
// NEW: Track selected rows globally
let selectedBatchIds = new Set();

// --- Identity & Access Logic ---
document.addEventListener("DOMContentLoaded", () => {
    const role = localStorage.getItem("userRole");
    const username = localStorage.getItem("userName") || localStorage.getItem("userFullName") || "Admin";

    if (!role || !username) { window.location.href = "/"; }
    
    document.getElementById("user-display").innerText = username;
    document.getElementById("role-display").innerText = role;
    document.getElementById("user-avatar").innerText = username.charAt(0).toUpperCase();

    // Default to today's date for a clean initial view
    const today = new Date().toISOString().split('T')[0];
    document.getElementById("filter_from").value = today;
    document.getElementById("filter_to").value = today;

    loadStagingData();
});

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

function clearFilters() {
    document.getElementById("filter_from").value = "";
    document.getElementById("filter_to").value = "";
    loadStagingData();
}

// --- Fetch Data ---
async function loadStagingData() {
    const fromDate = document.getElementById("filter_from").value;
    const toDate = document.getElementById("filter_to").value;
    
    let url = '/api/erp_mapping/staging_data?';
    if (fromDate) url += `from_date=${fromDate}&`;
    if (toDate) url += `to_date=${toDate}`;

    try {
        const response = await fetch(url);
        if (!response.ok) throw new Error("Failed to load staging data");
        
        const data = await response.json();
        
        // Save to global state for pagination
        pendingRecords = data.pending;
        pushedRecords = data.pushed;
        
        currentPendingPage = 1;
        currentPushedPage = 1;
        selectedBatchIds.clear(); // NEW: Clear selections on fresh load

        renderPendingPage();
        renderPushedPage();
        
    } catch (error) {
        console.error(error);
        document.getElementById('table-pending').innerHTML = `<tr><td colspan="7" class="loading-cell" style="color: var(--status-red);">Error loading data.</td></tr>`;
    }
}

// --- Pagination & Rendering ---
function renderPendingPage() {
    const tbody = document.getElementById('table-pending');
    
    if (pendingRecords.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="loading-cell">No pending records found.</td></tr>`;
        document.getElementById('btn_push').disabled = true;
        document.getElementById('pagination-pending').innerHTML = "";
        return;
    }

    document.getElementById('btn_push').disabled = false;
    
    const start = (currentPendingPage - 1) * ROWS_PER_PAGE;
    const end = start + ROWS_PER_PAGE;
    const paginatedItems = pendingRecords.slice(start, end);

    let html = '';
    paginatedItems.forEach(r => {
        // Check if this row's ID is in our Set
        const isChecked = selectedBatchIds.has(r.batch_id) ? 'checked' : '';
        
        html += `
            <tr>
                <td style="text-align: center;">
                    <input type="checkbox" style="cursor: pointer;" value="${r.batch_id}" ${isChecked} onchange="toggleRowSelection(this)">
                </td>
                <td style="font-weight: bold; font-size: 12px; color: var(--text-muted);">${r.batch_id}</td>
                <td style="color: var(--accent-cyan); font-weight: bold;">${r.machine_erp_code || '-'}</td>
                <td style="color: var(--text-main);">${r.part_erp_code || '-'}</td>
                <td style="color: var(--status-green); font-weight: bold;">${r.ok_qty}</td>
                <td style="color: var(--status-red); font-weight: bold;">${r.rej_qty}</td>
                <td style="color: var(--status-yellow);">${r.total_downtime_mins}</td>
                <td><span class="status-pill status-pending">Pending</span></td>
            </tr>
        `;
    });
    tbody.innerHTML = html;
    
    updateSelectAllState(); // NEW: Sync header checkbox
    tbody.innerHTML = html;
    
    renderPaginationControls(pendingRecords.length, currentPendingPage, 'pagination-pending', (newPage) => {
        currentPendingPage = newPage;
        renderPendingPage();
    });
}

function renderPushedPage() {
    const tbody = document.getElementById('table-pushed');
    
    if (pushedRecords.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="loading-cell">No push history found.</td></tr>`;
        document.getElementById('pagination-pushed').innerHTML = "";
        return;
    }

    const start = (currentPushedPage - 1) * ROWS_PER_PAGE;
    const end = start + ROWS_PER_PAGE;
    const paginatedItems = pushedRecords.slice(start, end);

    let html = '';
    paginatedItems.forEach(r => {
        let pushDate = new Date(r.pushed_at).toLocaleString();
        html += `
            <tr>
                <td style="font-size: 12px; color: #555;">${r.batch_id}</td>
                <td style="color: #777;">${r.machine_erp_code || '-'}</td>
                <td style="color: #777;">${r.part_erp_code || '-'}</td>
                <td style="color: #777;">${r.ok_qty}</td>
                <td style="color: #777;">${r.rej_qty}</td>
                <td style="color: var(--status-green); font-size: 12px;">✓ ${pushDate}</td>
            </tr>
        `;
    });
    tbody.innerHTML = html;

    renderPaginationControls(pushedRecords.length, currentPushedPage, 'pagination-pushed', (newPage) => {
        currentPushedPage = newPage;
        renderPushedPage();
    });
}

function renderPaginationControls(totalItems, currentPage, containerId, pageChangeCallback) {
    const container = document.getElementById(containerId);
    container.innerHTML = "";
    
    const totalPages = Math.ceil(totalItems / ROWS_PER_PAGE);
    if (totalPages <= 1) return; // Hide pagination if only 1 page

    // Prev Button
    if (currentPage > 1) {
        const btn = document.createElement("button");
        btn.innerText = "◀ Prev";
        btn.className = "page-btn";
        btn.onclick = () => pageChangeCallback(currentPage - 1);
        container.appendChild(btn);
    }

    // Page Indicator
    const indicator = document.createElement("span");
    indicator.style.color = "var(--text-muted)";
    indicator.style.fontSize = "13px";
    indicator.style.padding = "5px 10px";
    indicator.innerText = `Page ${currentPage} of ${totalPages}`;
    container.appendChild(indicator);

    // Next Button
    if (currentPage < totalPages) {
        const btn = document.createElement("button");
        btn.innerText = "Next ▶";
        btn.className = "page-btn";
        btn.onclick = () => pageChangeCallback(currentPage + 1);
        container.appendChild(btn);
    }
}

// --- Checkbox Logic ---
function toggleRowSelection(checkbox) {
    if (checkbox.checked) {
        selectedBatchIds.add(checkbox.value);
    } else {
        selectedBatchIds.delete(checkbox.value);
    }
    updateSelectAllState();
}

function toggleSelectAll() {
    const selectAll = document.getElementById("selectAllCheckbox").checked;
    const start = (currentPendingPage - 1) * ROWS_PER_PAGE;
    const end = start + ROWS_PER_PAGE;
    const paginatedItems = pendingRecords.slice(start, end);

    // Select/Deselect all visible items on the CURRENT page
    paginatedItems.forEach(r => {
        if (selectAll) selectedBatchIds.add(r.batch_id);
        else selectedBatchIds.delete(r.batch_id);
    });
    
    renderPendingPage();
}

function updateSelectAllState() {
    const selectAllCb = document.getElementById("selectAllCheckbox");
    if (!selectAllCb) return;
    
    const start = (currentPendingPage - 1) * ROWS_PER_PAGE;
    const end = start + ROWS_PER_PAGE;
    const paginatedItems = pendingRecords.slice(start, end);

    if (paginatedItems.length === 0) {
        selectAllCb.checked = false;
        return;
    }
    // Check if every item on the current page is in the Set
    selectAllCb.checked = paginatedItems.every(r => selectedBatchIds.has(r.batch_id));
}

// --- UPDATED MOCK PUSH ---
async function pushPayload() {
    if (selectedBatchIds.size === 0) {
        alert("⚠️ Please select at least one record to push.");
        return;
    }

    if (!confirm(`Are you sure you want to push ${selectedBatchIds.size} selected record(s) to ERP?`)) return;

    const btn = document.getElementById("btn_push");
    const originalText = btn.innerHTML;
    btn.innerHTML = "⏳ Generating Payload...";
    btn.disabled = true;

    try {
        const payload = { batch_ids: Array.from(selectedBatchIds) };

        const response = await fetch('/api/erp_mapping/push_mock', { 
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Failed to push payload.");
        }

        const data = await response.json();
        alert(`✅ ${data.message}`);
        
        selectedBatchIds.clear(); // Clear selections on success
        loadStagingData();

    } catch (error) {
        alert(`❌ Push Error: ${error.message}`);
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}