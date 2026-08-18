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
    fetchHistoryData();
};

// --- FETCH & RENDER LOGIC ---
let currentPage = 1;
const limitPerPage = 500;
let totalPages = 1;

async function fetchHistoryData(page = 1) {
    currentPage = page;

    const dateFrom = document.getElementById("filter_date_from").value;
    const dateTo = document.getElementById("filter_date_to").value;
    const machineId = document.getElementById("filter_machine").value;
    const tbody = document.getElementById("history_table_body");
    const paginationControls = document.getElementById("pagination_controls");

    if (!dateFrom || !dateTo) {
        alert("Please select a valid date range.");
        return;
    }

    // Show loading state and hide pagination
    tbody.innerHTML = `<tr><td colspan="7" class="empty-state" style="color: var(--accent-prod);">Loading page ${currentPage}...</td></tr>`;
    if (paginationControls) paginationControls.style.display = "none";

    try {
        const response = await fetch(`/api/report/moulding_machines_history?start=${dateFrom}&end=${dateTo}&machine=${machineId}&page=${currentPage}&limit=${limitPerPage}`);
        
        if (!response.ok) throw new Error("Failed to fetch data from server");
        
        const responseData = await response.json();
        const data = responseData.data;
        totalPages = responseData.total_pages;
        
        tbody.innerHTML = "";

        if (data.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="empty-state">No parameter changes found for the selected criteria.</td></tr>`;
            return;
        }

        // Render rows
        data.forEach(row => {
            const timeObj = new Date(row.history_timestamp);
            const timeFormatted = timeObj.toLocaleString('en-IN', { 
                year: 'numeric', month: 'short', day: 'numeric', 
                hour: '2-digit', minute: '2-digit', second: '2-digit',
                hour12: true 
            });

            tbody.innerHTML += `
                <tr>
                    <td style="color: var(--text-muted);">${timeFormatted}</td>
                    <td class="col-machine">${row.machine_id}</td>
                    <td class="col-param">${row.parameter_name}</td>
                    <td style="color: var(--text-muted);">${row.unit || '-'}</td>
                    <td class="col-old">${row.old_value}</td>
                    <td class="col-new">${row.new_value}</td>
                    <td class="col-user">${row.changed_by}</td>
                </tr>
            `;
        });

        // Update and show pagination controls
        if (paginationControls) {
            document.getElementById("page_input").value = currentPage;
            document.getElementById("page_total").innerText = `of ${totalPages} (Total: ${responseData.total_rows})`;
            document.getElementById("btn_prev").disabled = currentPage === 1;
            document.getElementById("btn_next").disabled = currentPage === totalPages;
            paginationControls.style.display = "flex";
        }

    } catch (error) {
        console.error("Error:", error);
        tbody.innerHTML = `<tr><td colspan="7" class="empty-state" style="color: var(--status-red);">Error loading data. Check server connection.</td></tr>`;
    }
}

// Function triggered by Previous/Next buttons
function changePage(direction) {
    const newPage = currentPage + direction;
    if (newPage >= 1 && newPage <= totalPages) {
        fetchHistoryData(newPage);
    }
}

// Function to manually jump to a typed page
function jumpToPage() {
    let inputVal = parseInt(document.getElementById("page_input").value);
    
    // Safety checks
    if (isNaN(inputVal) || inputVal < 1) {
        inputVal = 1;
    } else if (inputVal > totalPages) {
        inputVal = totalPages;
    }
    
    // Only fetch if they actually changed the page
    if (inputVal !== currentPage) {
        fetchHistoryData(inputVal);
    } else {
        document.getElementById("page_input").value = currentPage; 
    }
}

// Allow pressing "Enter" in the input box to trigger the jump
function handlePageJump(event) {
    if (event.key === "Enter") {
        jumpToPage();
    }
}