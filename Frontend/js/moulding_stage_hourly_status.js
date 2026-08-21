document.addEventListener("DOMContentLoaded", () => {
    const role = localStorage.getItem("userRole");
    const fullName = localStorage.getItem("userFullName");
    if (!role || !fullName || role === "undefined" || fullName === "undefined") {
        window.location.href = "/"; return; 
    }
    document.getElementById("user-display").innerText = fullName; 
    document.getElementById("role-display").innerText = role.toUpperCase(); 
    document.getElementById("user-avatar").innerText = fullName.charAt(0).toUpperCase(); 
});

function logout() { localStorage.clear(); window.location.href = "/"; }

function enableFullscreen() {
    const elem = document.documentElement;
    if (elem.requestFullscreen) elem.requestFullscreen();
}

// 🚨 SMART LOGICAL SHIFT CALCULATION 🚨
window.onload = function () {
    const now = new Date();
    let logicalDate = new Date(now);
    let currentShift = "A";
    const currentHour = now.getHours(); 

    if (currentHour >= 0 && currentHour < 7) {
        logicalDate.setDate(logicalDate.getDate() - 1);
        currentShift = "B";
    } else if (currentHour >= 19) {
        currentShift = "B";
    } else {
        currentShift = "A";
    }

    const offsetDate = new Date(logicalDate.getTime() - (logicalDate.getTimezoneOffset() * 60000));
    document.getElementById("dateSelect").value = offsetDate.toISOString().split('T')[0];
    document.getElementById("shiftSelect").value = currentShift;

    fetchMouldingDashboard();
    setInterval(fetchMouldingDashboard, 15000); // Ping PLC data every 15 seconds
};

async function fetchMouldingDashboard() {
    const dateVal = document.getElementById("dateSelect").value;
    const shiftVal = document.getElementById("shiftSelect").value;
    const gridContainer = document.getElementById('dashboardGrid');
    
    if (!gridContainer) return;

    if (gridContainer.innerHTML === "") {
        gridContainer.innerHTML = '<h3 style="color: var(--text-muted); width: 100vw; text-align: center; margin-top: 50px; grid-column: span 5;">Fetching PLC Telemetry...</h3>';
    }

    try {
        const response = await fetch(`/api/live_moulding_dashboard?date=${dateVal}&shift=${shiftVal}`);
        if (!response.ok) throw new Error("Network error");
        
        const data = await response.json();
        const machines = data.machines;

        let html = '';

        machines.forEach(m => {
            
            // 1. 🚨 NEW LOGIC: Status is STRICTLY based on the 3-Minute Idle Flag
            let cardClass = "";
            let modeDisplay = m.mode;
            let modePillClass = "";
            
            if (m.is_idle) {
                // Machine hasn't reported a cycle in 3+ minutes. It is IDLE.
                cardClass = "card-red";
                modeDisplay = "IDLE";
                modePillClass = "mode-abn"; // Uses the red pill style
            } else {
                // Machine is actively cycling!
                cardClass = "card-green";
                
                // Keep the PLC's actual mode (Auto, Semi, etc) for the pill
                if (m.mode === "SEMI-AUTO" || m.mode === "MANUAL") {
                    modePillClass = "mode-semi"; // Yellow pill
                } else {
                    modePillClass = "mode-auto"; // Green pill
                }
            }

            // 2. Format Alarm Box
            let alarmHtml = m.alarm === "NONE" 
                ? `<div class="mc-alarm alarm-none">✅ No Active Alarms</div>`
                : `<div class="mc-alarm alarm-active" title="${m.alarm}">⚠️ ${m.alarm}</div>`;

            // 3. Format Shot Count Color
            let actColorClass = m.shot_count > 0 ? "act-high" : "act-low";

            // 4. Regex Parse Mould and Part Name
            let moldDisplay = m.mould_name || "--";
            let partDisplay = "--";
            
            const match = moldDisplay.match(/^(.*?)\s*\(([^)]+)\)$/);
            if (match) {
                moldDisplay = match[1].trim();
                partDisplay = match[2].trim();
            }

            // 5. Build HTML
            html += `
                <div class="moulding-card ${cardClass}">
                    <div class="mc-header">
                        <h3>${m.machine}</h3>
                        <div class="mc-cycle">⏱ ${m.cycle_time}s</div>
                    </div>
                    
                    <div class="mc-identity">
                        <div class="ident-row" title="${moldDisplay}"><span class="ident-lbl">Mould:</span> <span class="ident-val">${moldDisplay}</span></div>
                        <div class="ident-row" title="${partDisplay}"><span class="ident-lbl">Part:</span> <span class="ident-val part-text">${partDisplay}</span></div>
                    </div>
                    
                    <div class="mc-metrics">
                        <div class="metric-box">
                            <span class="metric-lbl">Shot Count</span>
                            <span class="metric-val ${actColorClass}">${m.shot_count}</span>
                        </div>
                        <div class="metric-box" style="align-items: flex-end;">
                            <span class="metric-lbl">Status</span>
                            <div><span class="mode-pill ${modePillClass}">${modeDisplay}</span></div>
                        </div>
                    </div>

                    ${alarmHtml}
                </div>
            `;
        });

        gridContainer.innerHTML = html;

    } catch (error) {
        console.error("Dashboard Fetch Error:", error);
    }
}