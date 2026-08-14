const backend = window.location.origin;

// State variables for auto-scroll
let scrollInterval;
let isScrollingDown = true;
let dataRefreshInterval;

window.onload = () => {
    initializeTVDashboard();
    
    // Auto-refresh data every 5 minutes (300000 ms)
    dataRefreshInterval = setInterval(initializeTVDashboard, 300000);
};

function getActiveShiftAndDate() {
    const urlParams = new URLSearchParams(window.location.search);
    let dateVal = urlParams.get('date');
    let shiftVal = urlParams.get('shift');

    // If no URL params are provided, calculate automatically based on current time
    if (!dateVal || !shiftVal) {
        const now = new Date();
        const hours = now.getHours();
        
        let offsetDate = new Date(now.getTime() - (now.getTimezoneOffset() * 60000));
        
        // Assuming Shift A is 07:00 to 19:00
        if (hours >= 7 && hours < 19) {
            shiftVal = 'A';
        } else {
            shiftVal = 'B';
            // If it's past midnight but before 7 AM, it belongs to yesterday's production date
            if (hours < 7) {
                offsetDate.setDate(offsetDate.getDate() - 1);
            }
        }
        dateVal = offsetDate.toISOString().split('T')[0];
    }
    
    return { dateVal, shiftVal };
}

async function initializeTVDashboard() {
    const { dateVal, shiftVal } = getActiveShiftAndDate();
    
    // Update TV Header
    document.getElementById("tv-shift-info").innerText = `DATE: ${dateVal} | SHIFT ${shiftVal}`;

    const tbody = document.getElementById("report-body");
    const emptyState = document.getElementById("empty-state");

    try {
        // Added a timestamp cache-buster to prevent Smart TVs from caching the JSON response
        const timestamp = new Date().getTime();
        const response = await fetch(`${backend}/api/report/shift_summary?date=${dateVal}&shift=${shiftVal}&t=${timestamp}`);
        
        if (!response.ok) throw new Error("Failed to fetch report data");
        
        const data = await response.json();
        tbody.innerHTML = "";
        emptyState.style.display = "none";

        if (data.length === 0) {
            emptyState.style.display = "block";
            return;
        }

        data.forEach(row => {
            tbody.innerHTML += `
                <tr>
                    <td style="font-weight:bold; color: var(--text-main);">${row.machine_code}</td>
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

        // Restart scroll logic with new data length
        const tableContainer = document.querySelector('.table-container');
        startAutoScroll(tableContainer);

    } catch (error) {
        console.error("TV Dashboard Error:", error);
        tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; color: var(--status-red); padding: 40px; font-size: 24px;">Connection Lost. Retrying...</td></tr>`;
    }
}

function startAutoScroll(container) {
    clearInterval(scrollInterval);
    container.scrollTop = 0;
    isScrollingDown = true;
    
    // Wait 4 seconds before starting the scroll so operators can read the top rows
    setTimeout(() => {
        scrollInterval = setInterval(() => {
            // If the content fits on the screen, don't scroll at all
            if (container.scrollHeight <= container.clientHeight) return;

            if (isScrollingDown) {
                container.scrollTop += 1; 
                
                // If we hit the bottom
                if (Math.ceil(container.scrollTop + container.clientHeight) >= container.scrollHeight) {
                    isScrollingDown = false;
                    clearInterval(scrollInterval);
                    setTimeout(() => startAutoScroll(container), 4000); // Pause at bottom, then restart
                }
            } else {
                container.scrollTop = 0;
                isScrollingDown = true;
                clearInterval(scrollInterval);
                setTimeout(() => startAutoScroll(container), 4000);
            }
        }, 50); // Speed of scroll (lower is faster)
    }, 4000); 
}