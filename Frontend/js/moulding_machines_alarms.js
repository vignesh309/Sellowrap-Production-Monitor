// --- AUTHENTICATION & NAVBAR LOGIC ---
const role = localStorage.getItem("userRole");
const username = localStorage.getItem("userName") || localStorage.getItem("userFullName") || "User";

if (!role || !username) {
    window.location.href = "/";
}

document.getElementById("user-display").innerText = username;
document.getElementById("role-display").innerText = role;
document.getElementById("user-avatar").innerText = username.charAt(0).toUpperCase();

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

// --- PAGE INITIALIZATION ---
window.onload = () => {
    // Set default dates to today
    const now = new Date();
    const offsetDate = new Date(now.getTime() - (now.getTimezoneOffset() * 60000));
    const todayStr = offsetDate.toISOString().split('T')[0];
    
    document.getElementById("filter_date_from").value = todayStr;
    document.getElementById("filter_date_to").value = todayStr;

    // Auto-fetch data on page load
    fetchAlarmsData();
};

// --- FETCH & RENDER LOGIC ---
async function fetchAlarmsData() {
    const dateFrom = document.getElementById("filter_date_from").value;
    const dateTo = document.getElementById("filter_date_to").value;
    const machineId = document.getElementById("filter_machine").value;
    const tbody = document.getElementById("alarms_table_body");

    if (!dateFrom || !dateTo) {
        alert("Please select a valid date range.");
        return;
    }

    // Show loading state
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state" style="color: var(--accent-prod);">Loading alarms data...</td></tr>`;

    try {
        const response = await fetch(`/api/report/moulding_machines_alarms?start=${dateFrom}&end=${dateTo}&machine=${machineId}`);
        
        if (!response.ok) throw new Error("Failed to fetch data from server");
        
        const data = await response.json();
        tbody.innerHTML = "";

        if (data.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" class="empty-state">No alarms triggered for the selected criteria.</td></tr>`;
            return;
        }

        // Render rows directly from database
        data.forEach(row => {
            const timeObj = new Date(row.alarm_timestamp);
            const timeFormatted = timeObj.toLocaleString('en-IN', { 
                year: 'numeric', month: 'short', day: 'numeric', 
                hour: '2-digit', minute: '2-digit', second: '2-digit',
                hour12: true 
            });

            // Conditionally style the status pill based on whether it is TRIGGERED or RESET
            const statusClass = row.alarm_status === "TRIGGERED" ? "status-triggered" : "status-reset";

            tbody.innerHTML += `
                <tr>
                    <td style="color: var(--text-muted);">${timeFormatted}</td>
                    <td class="col-machine">${row.machine_id}</td>
                    <td class="col-code">${row.alarm_code}</td>
                    <td class="col-message">${row.alarm_message}</td>
                    <td><span class="${statusClass}">${row.alarm_status}</span></td>
                </tr>
            `;
        });

    } catch (error) {
        console.error("Error:", error);
        tbody.innerHTML = `<tr><td colspan="5" class="empty-state" style="color: var(--status-red);">Error loading data. Check server connection.</td></tr>`;
    }
}