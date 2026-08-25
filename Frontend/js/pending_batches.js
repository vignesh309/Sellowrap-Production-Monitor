// --- Identity & Access Logic ---
document.addEventListener("DOMContentLoaded", () => {
    const role = localStorage.getItem("userRole");
    const username = localStorage.getItem("userName") || localStorage.getItem("userFullName") || "Admin";

    if (!role || !username) { window.location.href = "/"; }
    
    document.getElementById("user-display").innerText = username;
    document.getElementById("role-display").innerText = role;
    document.getElementById("user-avatar").innerText = username.charAt(0).toUpperCase();

    // 🚨 NEW: Set default dates to today's date automatically
    const today = new Date().toISOString().split('T')[0];
    document.getElementById("filter_from").value = today;
    document.getElementById("filter_to").value = today;

    loadPendingBatches();
});

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

// --- Filter Logic ---
function clearFilters() {
    document.getElementById("filter_from").value = "";
    document.getElementById("filter_to").value = "";
    loadPendingBatches();
}

// --- Fetch Data ---
async function loadPendingBatches() {
    const tbody = document.getElementById('table-pending');
    tbody.innerHTML = `<tr><td colspan="8" class="loading-cell">Loading data...</td></tr>`;

    // 🚨 NEW: Grab the dates from the UI
    const fromDate = document.getElementById("filter_from").value;
    const toDate = document.getElementById("filter_to").value;
    
    // 🚨 NEW: Build the dynamic URL with the dates
    let url = '/api/pending_finalization?';
    if (fromDate) url += `from_date=${fromDate}&`;
    if (toDate) url += `to_date=${toDate}`;

    try {
        const response = await fetch(url);
        if (!response.ok) throw new Error("Failed to load data");
        
        const data = await response.json();
        renderTable(data.records);
        
    } catch (error) {
        console.error(error);
        tbody.innerHTML = `<tr><td colspan="8" class="loading-cell" style="color: var(--status-red);">Error loading pending batches.</td></tr>`;
    }
}

// --- Render Table & Smart Routing ---
function renderTable(rows) {
    const tbody = document.getElementById('table-pending');
    
    if (rows.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="loading-cell" style="color: var(--status-green);">🎉 All shifts have been finalized! Everything is up to date.</td></tr>`;
        return;
    }

    let html = '';
    rows.forEach(r => {
        
        // 🚨 BULLETPROOF ROUTING: Default to Stage 1 for Assembly, Welding, Pasting, etc.
        let targetPage = "production-entry-stage-1"; 
        
        // Only send to Moulding if the database explicitly says it's a Moulding machine!
        if (r.process === "MOULDING") {
            targetPage = "moulding-stage"; 
        }

        // Creates a URL that pre-loads the correct machine on the entry page
        const redirectUrl = `/${targetPage}?machine=${encodeURIComponent(r.machine)}&date=${r.date}&shift=${r.shift}`;

        html += `
            <tr>
                <td style="color: var(--text-main); font-weight: bold;">${r.date}</td>
                <td style="color: var(--accent-cyan); font-weight: bold;">${r.shift}</td>
                <td style="color: var(--text-main); font-weight: bold;">${r.machine}</td>
                <td style="color: var(--text-muted);">${r.part}</td>
                <td style="color: var(--text-muted);">${r.operator || '-'}</td>
                <td>
                    <span class="status-pill status-pending" style="font-size: 13px;">${r.hours_logged} / 12</span>
                </td>
                <td style="color: var(--status-green); font-weight: bold; font-size: 16px;">${r.total_ok}</td>
                <td>
                    <button class="hub-btn" style="padding: 6px 12px; font-size: 12px; margin: 0;" onclick="window.location.href='${redirectUrl}'">
                        Review & Finalize ➔
                    </button>
                </td>
            </tr>
        `;
    });
    tbody.innerHTML = html;
}