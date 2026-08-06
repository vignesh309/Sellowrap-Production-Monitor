// ==========================================
// INITIALIZATION & USER PROFILE
// ==========================================
window.onload = () => {
    const username = localStorage.getItem("userName") || "Admin";
    const role = localStorage.getItem("userRole") || "Role";

    document.getElementById("user-display").innerText = username;
    document.getElementById("role-display").innerText = role;
    document.getElementById("user-avatar").innerText = username.charAt(0).toUpperCase();

    const now = new Date();
    const offsetDate = new Date(now.getTime() - (now.getTimezoneOffset() * 60000));
    const todayStr = offsetDate.toISOString().split('T')[0];

    document.getElementById("startDate").value = todayStr;
    document.getElementById("endDate").value = todayStr;

    loadTEEPReport();
};

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

// ==========================================
// REPORT LOGIC
// ==========================================
async function loadTEEPReport() {
    const tbody = document.getElementById("teepTableBody");
    if (!tbody) return;

    tbody.innerHTML = `<tr><td colspan="24" style="text-align: center; color: var(--text-muted); padding: 30px;">Fetching Asset Analytics...</td></tr>`;

    const startDate = document.getElementById("startDate").value;
    const endDate = document.getElementById("endDate").value;
    const machine = document.getElementById("machineFilter").value;
    const shift = document.getElementById("shiftFilter").value;

    try {
        const params = new URLSearchParams();
        if (startDate) params.append('start_date', startDate);
        if (endDate) params.append('end_date', endDate);
        if (machine) params.append('machine', machine);
        if (shift) params.append('shift', shift);

        // 🚨 Pointing to the new TEEP endpoint
        const response = await fetch(`/api/get_teep_summary?${params.toString()}`);
        if (!response.ok) throw new Error("Failed to fetch TEEP data.");

        const data = await response.json();
        const records = data.records;

        if (!records || records.length === 0) {
            tbody.innerHTML = `<tr><td colspan="24" style="text-align: center; color: var(--status-yellow); padding: 30px;">No finalized batches found for this criteria.</td></tr>`;
            return;
        }

        let html = "";

        records.forEach(r => {
            html += `
                <tr>
                    <td>${r.date}</td>
                    <td style="font-weight: bold;">${r.shift}</td>
                    <td style="color: var(--accent-prod); font-weight: bold;">${r.machine}</td>
                    <td class="txt-left">${r.part_no}</td>
                    <td class="txt-left">${r.process_name}</td>
                    
                    <!-- Time Breakdown -->
                    <td>${r.total_time}</td>
                    <td style="color: var(--status-yellow);">${r.planned_dt}</td>
                    <td style="color: var(--status-red);">${r.unplanned_dt}</td>
                    <td style="color: var(--status-green);">${r.actual_run_time}</td>
                    
                    <!-- Production Breakdown -->
                    <td style="color: var(--status-yellow); font-weight: bold;">${r.target_qty}</td>
                    <td style="font-weight: bold;">${r.total_qty}</td>
                    <td style="color: var(--status-green);">${r.ok_qty}</td>
                    <td style="color: ${r.ng_qty > 0 ? 'var(--status-red)' : 'var(--text-main)'};">${r.ng_qty}</td>
                    
                    <!-- Percentage Breakdown -->
                    <td>${r.avail_pct.toFixed(2)}%</td>
                    <td class="highlight-perf">${r.perf_pct}%</td>
                    <td>${r.qual_pct}%</td>
                    <td class='highlight-oee'>${r.teep_pct}%</td>
                </tr>
            `;
        });

        tbody.innerHTML = html;

    } catch (error) {
        console.error("TEEP Fetch Error:", error);
        tbody.innerHTML = `<tr><td colspan="24" style="text-align: center; color: var(--status-red); padding: 30px;">Error loading data. Check console.</td></tr>`;
    }
}