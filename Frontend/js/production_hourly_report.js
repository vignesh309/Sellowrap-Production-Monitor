// ==========================================
// USER AUTHENTICATION & PROFILE DISPLAY
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
    const role = localStorage.getItem("userRole");
    const fullName = localStorage.getItem("userFullName");

    // 1. Hard Redirect if Not Logged In (🚨 Upgraded to catch "undefined" ghost data)
    if (!role || !fullName || role === "undefined" || fullName === "undefined") {
        console.warn("Invalid session data. Redirecting to login.");
        window.location.href = "/";
        return; 
    }

    // 2. Safely Update the Navbar UI
    const displayUser = document.getElementById("user-display");
    const displayRole = document.getElementById("role-display");
    const displayAvatar = document.getElementById("user-avatar");

    if (displayUser) {
        displayUser.innerText = fullName; 
    }
    
    if (displayRole) {
        displayRole.innerText = role.toUpperCase(); 
    }
    
    if (displayAvatar) {
        displayAvatar.innerText = fullName.charAt(0).toUpperCase(); 
    }

    // 3. Apply Role-Based Security Hiding
    if (role === "Operator") {
        document.querySelectorAll(".restrict-operator").forEach(el => el.style.display = "none");
    }
    if (role === "Supervisor") {
        document.querySelectorAll(".restrict-supervisor").forEach(el => el.style.display = "none");
    }
});

// Global Logout Function
function logout() {
    localStorage.clear();
    window.location.href = "/";
}
// ==========================================

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

// ==========================================
// DATA FETCHING
// ==========================================

// 🚨 NEW: Populates the machine dropdown dynamically
async function fetchMachineList() {
    try {
        const response = await fetch('/api/get_machines');
        if (response.ok) {
            const data = await response.json();
            const select = document.getElementById("machineFilter");
            if (!select) return;

            data.machines.forEach(m => {
                // Creates an option using the machine code
                const option = document.createElement("option");
                option.value = m.code;
                option.textContent = m.code;
                select.appendChild(option);
            });
        }
    } catch (e) {
        console.error("Could not load machine list", e);
    }
}

async function loadReport() {
    const tbody = document.getElementById("reportTableBody");
    if (!tbody) return;
    
    tbody.innerHTML = `<tr><td colspan="13" style="text-align: center; color: var(--text-muted);">Loading data...</td></tr>`;
    
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
        
        const response = await fetch(`/api/get_production_hourly_report?${params.toString()}`);
        if (!response.ok) throw new Error("Failed to fetch report data.");
        
        const data = await response.json();
        const records = data.records;
        
        if (!records || records.length === 0) {
            tbody.innerHTML = `<tr><td colspan="13" style="text-align: center; color: var(--status-yellow);">No records found for this criteria.</td></tr>`;
            resetSummaries();
            return;
        }

        let html = "";
        let totalOk = 0;
        let totalNg = 0;
        let totalTarget = 0;
        let totalActual = 0;

        records.forEach(r => {
            // Only add to KPI totals if it was an actual planned production hour
            if (!r.is_no_plan) {
                totalOk += r.ok;
                totalNg += r.ng;
                totalTarget += r.target;
                totalActual += r.actual;
            }
            
            // Format styling based on No Plan vs Production
            const rowStyle = r.is_no_plan ? "background: rgba(255,255,255,0.03); opacity: 0.7;" : "";
            const partDisplay = r.is_no_plan ? `<span style="background:#555; padding:3px 8px; border-radius:4px; font-size:10px; font-weight:bold; color:white;">NO PLAN</span>` : r.part_no;
            const rmDisplay = r.is_no_plan ? "-" : (r.rm_lot || "-"); // Added fallback for rm_lot
            
            // Calculate Efficiency safely
            const efficiency = (r.target > 0 && !r.is_no_plan) ? (r.actual / r.target) * 100 : 0;
            const actualColor = (!r.is_no_plan && efficiency < 90) ? 'var(--status-red)' : 'var(--text-main)';

            html += `
                <tr style="${rowStyle}">
                    <td style="color: var(--text-muted);">${r.date}</td>
                    <td style="font-weight: bold;">${r.shift}</td>
                    <td style="color: var(--accent-cyan);">${r.time_block}</td>
                    <td style="font-weight: bold;">${r.machine}</td>
                    <td style="color: var(--text-muted);">${r.process || "Moulding"}</td>
                    <td style="color: var(--text-muted);">${rmDisplay}</td>
                    <td>${partDisplay}</td>
                    <td style="color: var(--text-muted); font-size: 11px;">${r.operator}</td>
                    <td style="font-size: 10px; color: var(--text-muted);">${r.batch}</td>
                    <td>${r.is_no_plan ? "-" : r.target}</td>
                    <td style="font-weight: bold; color: ${actualColor};">${r.is_no_plan ? "-" : r.actual}</td>
                    <td style="color: ${r.is_no_plan ? 'var(--text-muted)' : 'var(--status-green)'};">${r.is_no_plan ? "-" : r.ok}</td>
                    <td style="color: ${r.ng > 0 ? 'var(--status-red)' : 'var(--text-muted)'};">${r.is_no_plan ? "-" : r.ng}</td>
                </tr>
            `;
        });
        
        tbody.innerHTML = html;
        
        // Update summary cards
        document.getElementById("tot-hours").innerText = records.length;
        document.getElementById("tot-ok").innerText = totalOk.toLocaleString();
        document.getElementById("tot-ng").innerText = totalNg.toLocaleString();
        
        const overallEff = totalTarget > 0 ? ((totalActual / totalTarget) * 100).toFixed(1) : 0;
        document.getElementById("avg-eff").innerText = `${overallEff}%`;
        
    } catch (error) {
        console.error("Report Fetch Error:", error);
        tbody.innerHTML = `<tr><td colspan="13" style="text-align: center; color: var(--status-red);">Error loading data. Check console.</td></tr>`;
    }
}

function resetSummaries() {
    document.getElementById("tot-hours").innerText = "0";
    document.getElementById("tot-ok").innerText = "0";
    document.getElementById("tot-ng").innerText = "0";
    document.getElementById("avg-eff").innerText = "0%";
}

// ==========================================
// EXCEL EXPORT LOGIC
// ==========================================
function exportToExcel() {
    // 1. Grab the table from the DOM
    let table = document.querySelector(".table-wrapper table");
    
    if (!table || table.rows.length <= 1) {
        alert("No data available to export.");
        return;
    }

    // 2. Convert the HTML table to an Excel Workbook
    let workbook = XLSX.utils.table_to_book(table, { sheet: "Hourly Report" });

    // 3. Generate a dynamic filename based on today's date
    const today = new Date().toISOString().split('T')[0];
    let filename = `Production_Report_${today}.xlsx`;

    // 4. Trigger the download
    XLSX.writeFile(workbook, filename);
}