// --- Identity & Access Logic ---
document.addEventListener("DOMContentLoaded", () => {
    const role = localStorage.getItem("userRole");
    const username = localStorage.getItem("userName") || localStorage.getItem("userFullName") || "Admin";

    if (!role || !username) { window.location.href = "/"; }
    
    document.getElementById("user-display").innerText = username;
    document.getElementById("role-display").innerText = role;
    document.getElementById("user-avatar").innerText = username.charAt(0).toUpperCase();

    loadStagingData();
});

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

// --- Fetch Data ---
async function loadStagingData() {
    try {
        const response = await fetch('/api/erp_mapping/staging_data');
        if (!response.ok) throw new Error("Failed to load staging data");
        
        const data = await response.json();
        renderPending(data.pending);
        renderPushed(data.pushed);
        
    } catch (error) {
        console.error(error);
        document.getElementById('table-pending').innerHTML = `<tr><td colspan="7" class="loading-cell" style="color: red;">Error loading data.</td></tr>`;
    }
}

function renderPending(rows) {
    const tbody = document.getElementById('table-pending');
    if (rows.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="loading-cell">No pending records. Everything is up to date!</td></tr>`;
        document.getElementById('btn_push').disabled = true;
        return;
    }

    document.getElementById('btn_push').disabled = false;
    let html = '';
    rows.forEach(r => {
        html += `
            <tr>
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
}

function renderPushed(rows) {
    const tbody = document.getElementById('table-pushed');
    if (rows.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="loading-cell">No push history found.</td></tr>`;
        return;
    }

    let html = '';
    rows.forEach(r => {
        // Format the date to look clean
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
}

// --- MOCK PUSH (JSON GENERATOR) ---
async function pushPayload() {
    if (!confirm("Are you sure you want to generate the JSON payload and mark these records as pushed?")) return;

    const btn = document.getElementById("btn_push");
    const originalText = btn.innerHTML;
    btn.innerHTML = "⏳ Generating Payload...";
    btn.disabled = true;

    try {
        const response = await fetch('/api/erp_mapping/push_mock', { method: 'POST' });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Failed to push payload.");
        }

        const data = await response.json();
        
        // Let the user know the file was created on the server
        alert(`✅ ${data.message}`);
        
        // Reload tables to reflect the new state
        loadStagingData();

    } catch (error) {
        alert(`❌ Push Error: ${error.message}`);
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}