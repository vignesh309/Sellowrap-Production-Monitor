const backend = window.location.origin;

window.onload = () => {
    // Set default date to today
    const now = new Date();
    const offsetDate = new Date(now.getTime() - (now.getTimezoneOffset() * 60000));
    document.getElementById("report_date").value = offsetDate.toISOString().split('T')[0];
    
    // Set user info to match hub.html
    const username = localStorage.getItem("userName") || "Admin";
    const role = localStorage.getItem("userRole") || "Role"; 
    
    document.getElementById("user-display").innerText = username;
    document.getElementById("role-display").innerText = role; 
    document.getElementById("user-avatar").innerText = username.charAt(0).toUpperCase();

    // Load initial data
    loadReport();
};

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

async function loadReport() {
    const dateVal = document.getElementById("report_date").value;
    const shiftVal = document.getElementById("report_shift").value;
    const tbody = document.getElementById("report-body");
    const emptyState = document.getElementById("empty-state");

    if (!dateVal || !shiftVal) return;

    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding: 20px; color: var(--accent-cyan);">Loading data...</td></tr>`;
    emptyState.style.display = "none";

    try {
        const response = await fetch(`${backend}/api/report/shift_summary?date=${dateVal}&shift=${shiftVal}`);
        if (!response.ok) throw new Error("Failed to fetch report data");
        
        const data = await response.json();
        tbody.innerHTML = "";

        if (data.length === 0) {
            emptyState.style.display = "block";
            return;
        }

        data.forEach(row => {
            tbody.innerHTML += `
                <tr>
                    <td style="font-weight:bold;">${row.machine_code}</td>
                    <td>${row.part_number}</td>
                    <td>${row.part_name || '-'}</td>
                    <td style="color: var(--text-muted);">${row.customer || '-'}</td>
                    <td class="text-right" style="color: var(--status-yellow); font-weight: bold;">${row.target_qty}</td> 
                    <td class="text-right qty-total">${row.total_qty}</td>
                    <td class="text-right qty-ok">${row.ok_qty}</td>
                    <td class="text-right qty-ng">${row.ng_qty}</td>
                    <td style="color: var(--text-muted);">${row.operators}</td>
                </tr>
            `;
        });

    } catch (error) {
        console.error("Error:", error);
        tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; color: var(--status-red); padding: 20px;">Error loading report.</td></tr>`;
    }
}

function toggleFullScreen() {
    if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().catch(err => {
            alert(`Error attempting to enable fullscreen: ${err.message}`);
        });
    } else {
        document.exitFullscreen();
    }
}

// ==========================================
// 📺 TV MODE AUTO-SCROLL LOGIC
// ==========================================

let scrollInterval;
let isScrollingDown = true;

document.addEventListener('fullscreenchange', () => {
    const tableContainer = document.querySelector('.table-container');
    const fullscreenBtn = document.querySelector('.btn-fullscreen');
    
    if (document.fullscreenElement) {
        fullscreenBtn.innerText = "❌ Exit Fullscreen"; 
        startAutoScroll(tableContainer);
    } else {
        fullscreenBtn.innerText = "📺 Fullscreen";      
        clearInterval(scrollInterval);
        tableContainer.scrollTop = 0;
    }
});

function startAutoScroll(container) {
    clearInterval(scrollInterval);
    
    // Wait 3 seconds before starting the scroll
    setTimeout(() => {
        if (!document.fullscreenElement) return;

        scrollInterval = setInterval(() => {
            if (container.scrollHeight <= container.clientHeight) return;

            if (isScrollingDown) {
                container.scrollTop += 1; 
                
                if (Math.ceil(container.scrollTop + container.clientHeight) >= container.scrollHeight) {
                    isScrollingDown = false;
                    clearInterval(scrollInterval);
                    setTimeout(() => startAutoScroll(container), 3000); 
                }
            } else {
                container.scrollTop = 0;
                isScrollingDown = true;
                clearInterval(scrollInterval);
                setTimeout(() => startAutoScroll(container), 3000);
            }
        }, 40); 
        
    }, 3000); 
}