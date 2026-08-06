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

    loadOEEReport();
};

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

// ==========================================
// REPORT LOGIC
// ==========================================
async function loadOEEReport() {
    const tbody = document.getElementById("oeeTableBody");
    if (!tbody) return;

    tbody.innerHTML = `<tr><td colspan="24" style="text-align: center; color: var(--text-muted); padding: 30px;">Fetching Analytics...</td></tr>`;

    // Reset KPIs to default before loading
    document.getElementById("top-machine-val").innerText = "--";
    document.getElementById("bottom-machine-val").innerText = "--";
    document.getElementById("top-operator-val").innerText = "--";
    document.getElementById("bottom-operator-val").innerText = "--";

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

        const response = await fetch(`/api/get_oee_summary?${params.toString()}`);
        if (!response.ok) throw new Error("Failed to fetch OEE data.");

        const data = await response.json();
        const records = data.records;

        if (!records || records.length === 0) {
            tbody.innerHTML = `<tr><td colspan="24" style="text-align: center; color: var(--status-yellow); padding: 30px;">No finalized batches found for this criteria.</td></tr>`;
            return;
        }

        // 🚨 --- NEW KPI CALCULATION ENGINE --- 🚨
        let machineStats = {};
        let operatorStats = {};

        records.forEach(r => {
            // Group by Machine for OEE Average
            if (!machineStats[r.machine]) machineStats[r.machine] = { sum: 0, count: 0 };
            machineStats[r.machine].sum += parseFloat(r.oee_pct) || 0;
            machineStats[r.machine].count += 1;

            // Group by Operator for Performance Average
            if (r.operator && r.operator !== "-") {
                if (!operatorStats[r.operator]) operatorStats[r.operator] = { sum: 0, count: 0 };
                operatorStats[r.operator].sum += parseFloat(r.op_perf_pct) || 0;
                operatorStats[r.operator].count += 1;
            }
        });

        let topMac = { name: "--", val: -1 };
        let botMac = { name: "--", val: 999 };
        let topOp = { name: "--", val: -1 };
        let botOp = { name: "--", val: 999 };

        // Find Best & Worst Machine
        for (let m in machineStats) {
            let avg = machineStats[m].sum / machineStats[m].count;
            if (avg > topMac.val) topMac = { name: m, val: avg };
            if (avg < botMac.val) botMac = { name: m, val: avg };
        }

        // Find Best & Worst Operator
        for (let o in operatorStats) {
            let avg = operatorStats[o].sum / operatorStats[o].count;
            if (avg > topOp.val) topOp = { name: o, val: avg };
            if (avg < botOp.val) botOp = { name: o, val: avg };
        }

        // Push KPI calculations to the UI
        if (topMac.name !== "--") document.getElementById("top-machine-val").innerText = `${topMac.name} (${topMac.val.toFixed(1)}%)`;
        if (botMac.val !== 999) document.getElementById("bottom-machine-val").innerText = `${botMac.name} (${botMac.val.toFixed(1)}%)`;
        
        if (topOp.name !== "--") document.getElementById("top-operator-val").innerText = `${topOp.name} (${topOp.val.toFixed(1)}%)`;
        if (botOp.val !== 999) document.getElementById("bottom-operator-val").innerText = `${botOp.name} (${botOp.val.toFixed(1)}%)`;
        // 🚨 --- END KPI ENGINE --- 🚨


        // --- ORIGINAL TABLE RENDERING ---
        let html = "";
        records.forEach(r => {
            html += `
                <tr>
                    <td>${r.date}</td>
                    <td style="font-weight: bold;">${r.shift}</td>
                    <td class="txt-left">${r.customer_name}</td>
                    <td class="txt-left">${r.part_no}</td>
                    <td class="txt-left">${r.part_name}</td>
                    <td style="color: var(--accent-prod); font-weight: bold;">${r.machine}</td>
                    <td class="txt-left">${r.process_name}</td>
                    
                    <td style="color: var(--status-yellow); font-weight: bold;">${r.target_qty}</td>
                    <td style="font-weight: bold;">${r.total_qty}</td>
                    <td style="color: var(--status-green);">${r.ok_qty}</td>
                    <td style="color: ${r.ng_qty > 0 ? 'var(--status-red)' : 'var(--text-main)'};">${r.ng_qty}</td>
                    
                    <td class="txt-left" style="color: var(--status-red);">${r.major_ng}</td>
                    <td class="txt-left" style="color: var(--status-yellow);">${r.major_shortfall}</td>
                    
                    <td>${r.planned_time}</td>
                    <td>${r.actual_time}</td>
                    <td>${r.unplanned_dt_mins}</td> <!-- 🚨 NEW LINE -->
                    
                    <td style="color: var(--accent-prod); font-weight: bold;">
                        ${r.std_cycle_time > 0 ? r.std_cycle_time.toFixed(2) : '-'}
                    </td>
                    
                    <td>${r.avail_pct.toFixed(2)}%</td>
                    <td class="highlight-perf">${r.perf_pct}%</td>
                    <td>${r.qual_pct}%</td>
                    <td class='highlight-oee'>${r.oee_pct}%</td>
                    
                    <td class="txt-left" style="color: var(--text-muted);">${r.operator}</td>
                    <td class="txt-left" style="color: var(--text-muted);">${r.supervisor}</td>
                    <td class="highlight-perf">${r.op_perf_pct}%</td>
                    <td class="txt-left" style="color: var(--text-muted); font-size: 11px;">${r.remarks}</td>
                </tr>
            `;
        });

        tbody.innerHTML = html;

    } catch (error) {
        console.error("OEE Fetch Error:", error);
        tbody.innerHTML = `<tr><td colspan="25" style="text-align: center; color: var(--status-red); padding: 30px;">Error loading data. Check console.</td></tr>`;
    }
}

// ==========================================
// EXCEL EXPORT LOGIC
// ==========================================
function exportToExcel() {
    let table = document.getElementById("dataTable");
    
    if (!table || table.rows.length <= 1) {
        alert("No data available to export.");
        return;
    }

    let workbook = XLSX.utils.table_to_book(table, { sheet: "OEE Summary", raw: true });

    let dateStr = document.getElementById('startDate').value || "Report";
    let fileName = `OEE_Summary_${dateStr}.xlsx`;

    XLSX.writeFile(workbook, fileName);
}