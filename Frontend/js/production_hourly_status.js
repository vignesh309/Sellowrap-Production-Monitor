const backend = window.location.origin;

// Time slots mapping EXACTLY as they appear in the database
const shiftATimes = [
    "07:00 - 08:00", "08:00 - 09:00", "09:00 - 10:00", "10:00 - 11:00", 
    "11:00 - 12:00", "12:00 - 13:00", "13:00 - 14:00", "14:00 - 15:00", 
    "15:00 - 16:00", "16:00 - 17:00", "17:00 - 18:00", "18:00 - 19:00"
];

const shiftBTimes = [
    "19:00 - 20:00", "20:00 - 21:00", "21:00 - 22:00", "22:00 - 23:00", 
    "23:00 - 00:00", "00:00 - 01:00", "01:00 - 02:00", "02:00 - 03:00", 
    "03:00 - 04:00", "04:00 - 05:00", "05:00 - 06:00", "06:00 - 07:00"
];

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

// --- Helper function to get current shift parameters ---
function getCurrentTimeBlockInfo() {
    const selectedDate = document.getElementById("dateSelect").value;
    const selectedTimeBlock = document.getElementById("timeSlotSelect").value;

    return {
        date: selectedDate,
        timeBlock: selectedTimeBlock
    };
}

// --- Helper function to format 24h string to 12h AM/PM ---
function formatToAMPM(timeRange) {
    return timeRange.split(" - ").map(timeStr => {
        let [hour, min] = timeStr.split(":");
        hour = parseInt(hour, 10);
        const ampm = hour >= 12 ? 'PM' : 'AM';
        hour = hour % 12 || 12;
        return `${hour}:${min} ${ampm}`;
    }).join(" - ");
}

// --- Build the 24-Hour Dropdown ---
function initTimeDropdown() {
    const select = document.getElementById("timeSlotSelect");
    if (!select) return;
    
    select.innerHTML = "";
    const all24Hours = [...shiftATimes, ...shiftBTimes];

    all24Hours.forEach(slot => {
        const displayStr = formatToAMPM(slot);
        select.innerHTML += `<option value="${slot}" style="background: var(--bg-panel); color: white;">${displayStr}</option>`;
    });

    const now = new Date();
    now.setHours(now.getHours() - 1);
    const startHour = now.getHours();
    const endHour = (startHour + 1) % 24;

    const startStr = startHour.toString().padStart(2, '0') + ":00";
    const endStr = endHour.toString().padStart(2, '0') + ":00";

    select.value = `${startStr} - ${endStr}`;
}

// --- 🚨 UPDATED: Now handles the nested "iot_counts" from the backend ---
async function fetchMissingIoTCounts(timeInfo) {
    const startHour = parseInt(timeInfo.timeBlock.split(":")[0], 10);
    const unsubmittedSpans = document.querySelectorAll('span[data-unsubmitted="true"]');
    
    unsubmittedSpans.forEach(async (span) => {
        const machineCode = span.id.replace("live_act_", "");
        try {
            const res = await fetch(`/api/get_live_iot_count?date=${timeInfo.date}&machine_code=${machineCode}`);
            if (res.ok) {
                const jsonResponse = await res.json();
                
                // 🚨 NEW: Extract the nested "iot_counts" object!
                // (The || jsonResponse is a fallback just in case some other machines send flat data)
                const iotCounts = jsonResponse.iot_counts || jsonResponse;
                
                const liveCount = iotCounts[startHour];
                
                if (liveCount !== undefined && liveCount > 0) {
                    span.innerText = liveCount;
                    // Make it slightly cyan so managers know it's a "live" unsubmitted number
                    span.style.color = "var(--accent-cyan)"; 
                }
            }
        } catch (error) {
            // Silently ignore if a single IoT fetch fails
            console.error(`IoT Fetch error for ${machineCode}:`, error);
            alert(`IoT Fetch error for ${machineCode}: ` + error.message);
            console.error(`IoT Fetch error for ${machineCode}:`, error);
        }
    });
}

// --- Initial Dynamic Machine Populator ---
async function populateMachineGrid() {
    const slider = document.getElementById('sliderContainer');

    if (slider.innerHTML === "") {
        slider.innerHTML = '<h3 style="color: var(--text-muted); width: 100vw; text-align: center; margin-top: 50px;">Connecting to Database...</h3>';
    }

    try {
        const timeInfo = getCurrentTimeBlockInfo();
        const params = new URLSearchParams({
            prod_date: timeInfo.date,
            time_block: timeInfo.timeBlock
        });

        const response = await fetch(`/api/get_live_machine_status?${params.toString()}`);
        if (!response.ok) throw new Error("Network response was not ok");

        const data = await response.json();
        const machines = data.machines;

        const MACHINES_PER_PAGE = 15;
        let html = '';

        for (let i = 0; i < machines.length; i += MACHINES_PER_PAGE) {
            const chunk = machines.slice(i, i + MACHINES_PER_PAGE);
            html += `<div class="grid-page">`;

            chunk.forEach(m => {
                let status = 'red'; 
                if (m.is_no_plan) {
                    status = 'grey';
                } else if (m.target > 0) {
                    const ratio = m.actual / m.target;
                    if (ratio >= 0.95) status = 'green';
                    else if (ratio >= 0.85) status = 'yellow';
                }

                const partDisplay = m.part === "Awaiting Data"
                    ? `<span style="color: var(--text-muted); font-style: italic;">${m.part}</span>`
                    : `<span style="color: var(--accent-cyan); font-weight: bold;">${m.part}</span>`;

                let targetShift = shiftATimes.includes(timeInfo.timeBlock) ? "A" : "B";
                
                // 🚨 NEW: Flag if this machine has not submitted official data yet
                const isUnsubmitted = (m.part === "Awaiting Data" || m.target === 0);

                html += `
                        <div id="card_${m.code}" class="machine-card status-${status}" onclick="goToStage1('${m.code}', '${timeInfo.date}', '${targetShift}')" style="cursor: pointer; transition: transform 0.2s ease;">
                            <div class="mc-title">
                                <h3>${m.code}</h3>
                                <p>${partDisplay}</p>
                            </div>

                            <div class="mc-submetrics">
                                <div class="metric-row"><span class="lbl">Tar:</span> <span class="val">${m.target}</span></div>
                                <div class="metric-row"><span class="lbl">Act:</span> <span class="val" id="live_act_${m.code}" data-unsubmitted="${isUnsubmitted}">${m.actual}</span></div>
                                <div class="metric-row"><span class="lbl">OK:</span> <span class="val" id="live_ok_${m.code}">${m.ok}</span></div>
                                <div class="metric-row"><span class="lbl">NG:</span> <span class="val" id="live_ng_${m.code}">${m.ng}</span></div>
                            </div>
                            <div class="mc-operator">OP: ${m.operator}</div>
                        </div>
                    `;
            });

            html += `</div>`;
        }

        slider.innerHTML = html;
        startAutoScroll();
        
        // 🚨 NEW: Reach out to the IoT sensors to fill in the blanks
        fetchMissingIoTCounts(timeInfo);

    } catch (error) {
        console.error("Machine Fetch Error:", error);
        slider.innerHTML = '<h3 style="color: var(--status-red); width: 100vw; text-align: center; margin-top: 50px;">Failed to load live data. Retrying...</h3>';
    }
}

// --- Silent Background Data Injector ---
async function refreshDashboardData() {
    try {
        const timeInfo = getCurrentTimeBlockInfo();
        const params = new URLSearchParams({
            prod_date: timeInfo.date,
            time_block: timeInfo.timeBlock
        });

        const response = await fetch(`/api/get_live_machine_status?${params.toString()}`);
        if (!response.ok) return;

        const data = await response.json();

        data.machines.forEach(m => {
            const isUnsubmitted = (m.part === "Awaiting Data" || m.target === 0);
            const actSpan = document.getElementById(`live_act_${m.code}`);
            
            if (actSpan) {
                // 🚨 NEW: Update the flag based on live DB status
                actSpan.dataset.unsubmitted = isUnsubmitted;
                
                if (!isUnsubmitted) {
                    // It is official! Override with DB count and reset color
                    actSpan.innerText = m.actual;
                    actSpan.style.color = ""; 
                }
            }

            const okSpan = document.getElementById(`live_ok_${m.code}`);
            if (okSpan) okSpan.innerText = m.ok;

            const ngSpan = document.getElementById(`live_ng_${m.code}`);
            if (ngSpan) ngSpan.innerText = m.ng;

            // Recalculate status colors dynamically (This uses DB data safely)
            const card = document.getElementById(`card_${m.code}`);
            if (card) {
                let status = 'red';
                if (m.is_no_plan) {
                    status = 'grey';
                } else if (m.target > 0) {
                    const ratio = m.actual / m.target;
                    if (ratio >= 0.95) status = 'green';
                    else if (ratio >= 0.85) status = 'yellow';
                }
                card.className = `machine-card status-${status}`;
            }
        });
        
        // 🚨 NEW: Fetch IoT for machines that are STILL unsubmitted
        fetchMissingIoTCounts(timeInfo);

    } catch (error) {
        console.error("Silent IoT Refresh Failed:", error);
    }
}

// --- Navigation to Stage 1 ---
function goToStage1(machineCode, dateVal, shiftVal) {
    window.location.href = `/production-entry-stage-1?machine=${encodeURIComponent(machineCode)}&date=${dateVal}&shift=${shiftVal}`;
}

let scrollInterval; 

function startAutoScroll() {
    const slider = document.getElementById('sliderContainer');
    clearInterval(scrollInterval);

    scrollInterval = setInterval(() => {
        if (slider.scrollLeft + slider.clientWidth >= slider.scrollWidth - 10) {
            slider.scrollTo({ left: 0, behavior: 'smooth' });
        } else {
            slider.scrollBy({ left: slider.clientWidth, behavior: 'smooth' });
        }
    }, 15000); 
}

// Initialize the page on load
window.onload = function () {
    const now = new Date();
    const todayStr = now.getFullYear() + "-" + String(now.getMonth() + 1).padStart(2, '0') + "-" + String(now.getDate()).padStart(2, '0');
    const dateSelect = document.getElementById("dateSelect");
    if(dateSelect) dateSelect.value = todayStr;

    initTimeDropdown();      
    populateMachineGrid();   

    setInterval(refreshDashboardData, 15000);
};