const backend = window.location.origin;


// ==========================================
// USER AUTHENTICATION & PROFILE DISPLAY
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
    const role = localStorage.getItem("userRole");
    const fullName = localStorage.getItem("userFullName");
    
    // 1. Hard Redirect if Not Logged In
    if (!role || !fullName) {
        window.location.href = "/";
        return; 
    }
    
    // 2. Safely Update the Navbar UI
    const displayUser = document.getElementById("user-display");
    const displayRole = document.getElementById("role-display");
    const displayAvatar = document.getElementById("user-avatar");
    
    if (displayUser) {
        displayUser.innerText = fullName; // Displays "Mike Bossman" instead of "mikeb"
    }
    
    if (displayRole) {
        displayRole.innerText = role.toUpperCase(); // Displays "SUPERVISOR"
    }
    
    if (displayAvatar) {
        // Grabs the first letter of their full name for the avatar bubble
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

let globalMachineList = []; // 🚨 NEW: Stores machines so we can filter them locally

// Global Logout Function
function logout() {
    localStorage.clear();
    window.location.href = "/";
}
// ==========================================

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

window.onload = async () => {
    // 1. 🚨 SMART LOGICAL SHIFT CALCULATION 🚨
    const now = new Date();
    let logicalDate = new Date(now);
    const currentHour = now.getHours();

    // If it is before 7 AM, the "current" production day is physically yesterday
    if (currentHour >= 0 && currentHour < 7) {
        logicalDate.setDate(logicalDate.getDate() - 1);
    }

    // Format the date string properly avoiding timezone shifting bugs
    const offsetDate = new Date(logicalDate.getTime() - (logicalDate.getTimezoneOffset() * 60000));
    const logicalDateStr = offsetDate.toISOString().split('T')[0];

    const liveDateInput = document.getElementById('live_date');
    if(liveDateInput) liveDateInput.value = logicalDateStr;
    
    await fetchMachineList();
    fetchLiveStatus();
    
    setInterval(fetchLiveStatus, 300000); 

    document.addEventListener('fullscreenchange', () => {
        if (!document.fullscreenElement) {
            const topNav = document.getElementById('top-navbar');
            const filterBar = document.getElementById('filter-bar');
            
            if(topNav) topNav.style.display = 'flex';
            if(filterBar) filterBar.style.display = 'flex';
            
            stopContinuousScroll();
        }
    });
};

// --- API: Fetch Machine List for Dropdown ---
async function fetchMachineList() {
    try {
        const response = await fetch(`${backend}/api/get_machines`); 
        if (response.ok) {
            const data = await response.json();
            globalMachineList = data.machines; 
            
            // Build the initial dropdown with ALL machines
            updateMachineDropdown("ALL");
        }
    } catch (e) {
        console.error("Could not load machine list", e);
    }
}

// --- Cascading Dropdown Logic ---
function updateMachineDropdown(selectedProcess) {
    const select = document.getElementById("machine_select");
    if (!select) return;
    
    // Reset options
    select.innerHTML = '<option value="ALL">-- All Machines --</option>';

    globalMachineList.forEach(m => {
        // Force both sides to UPPERCASE so "Moulding" always matches "MOULDING"
        const mProcess = (m.process || m.machine_process || "").toUpperCase();
        const selProcess = selectedProcess.toUpperCase();
        
        if (selectedProcess === "ALL" || mProcess === selProcess) {
            select.innerHTML += `<option value="${m.code}">${m.code} - ${m.name}</option>`;
        }
    });
}

// --- 🚨 NEW: Triggered when Process dropdown changes ---
function handleProcessChange() {
    const selectedProcess = document.getElementById("process_select").value;
    updateMachineDropdown(selectedProcess);
    fetchLiveStatus(); // Refresh the board with the new process filter
}

// --- API: Fetch Live Floor Data ---
async function fetchLiveStatus() {
    const selectedDate = document.getElementById('live_date').value;
    const selectedProcess = document.getElementById('process_select').value;
    const selectedMachine = document.getElementById('machine_select').value;
    
    if (!selectedDate) return;

    try {
        const response = await fetch(`${backend}/api/live_factory_status?date=${selectedDate}`);
        if (!response.ok) throw new Error("Failed to fetch data");
        
        const res = await response.json();
        let machinesData = res.data;

        // 🚨 NEW: Apply Process Filter to the visual cards
        if (selectedProcess !== "ALL") {
            const selProcess = selectedProcess.toUpperCase();
            
            const validMachineCodes = globalMachineList
                .filter(m => (m.process || m.machine_process || "").toUpperCase() === selProcess)
                .map(m => m.code);
            
            machinesData = machinesData.filter(m => validMachineCodes.includes(m.machine));
        }

        // Apply Machine Filter
        if (selectedMachine !== "ALL") {
            machinesData = machinesData.filter(m => m.machine === selectedMachine);
        }

        // 1. Render the main grid with DB data
        renderDashboard(machinesData);
        
        // 2. Fetch IoT counts to fill in the blank hourly table cells
        fetchDetailedIoTCounts(selectedDate, machinesData);
        
    } catch (error) {
        console.error("Error fetching live status:", error);
    }
}

// --- 🚨 UPDATED: Fetches both shifts and prevents Time Travel! ---
async function fetchDetailedIoTCounts(dateVal, machines) {
    const now = new Date();

    machines.forEach(async (mac) => {
        const machineCode = mac.machine;
        
        // Skip machines with NO PLAN
        if (mac.current_part_no === "NO PLAN") return;

        try {
            // Because the API now requires a shift, we ask for both Shift A and B to fill the whole dashboard
            const [resA, resB] = await Promise.all([
                fetch(`/api/get_live_iot_count?date=${dateVal}&shift=A&machine_code=${encodeURIComponent(machineCode)}`),
                fetch(`/api/get_live_iot_count?date=${dateVal}&shift=B&machine_code=${encodeURIComponent(machineCode)}`)
            ]);

            let iotCounts = {};
            if (resA.ok) {
                const jsonA = await resA.json();
                Object.assign(iotCounts, jsonA.iot_counts || jsonA);
            }
            if (resB.ok) {
                const jsonB = await resB.json();
                Object.assign(iotCounts, jsonB.iot_counts || jsonB);
            }
                
            // Scan all 24 possible hours
            for (let hour = 0; hour < 24; hour++) {
                const cell = document.getElementById(`dtl_act_${machineCode}_${hour}`);
                
                if (cell && cell.dataset.unsubmitted === "true") {
                    
                    // --- TIME TRAVEL PREVENTION LOGIC ---
                    let blockDate = new Date(dateVal);
                    // If hour is 0-6 (Midnight to 6 AM), it belongs to Shift B and happens on the NEXT calendar day
                    if (hour < 7) {
                        blockDate.setDate(blockDate.getDate() + 1);
                    }
                    blockDate.setHours(hour, 0, 0, 0);

                    // If this block's physical time hasn't happened yet, skip it!
                    if (now < blockDate) continue;
                    // ------------------------------------

                    const liveCount = iotCounts[hour];
                        
                    if (liveCount !== undefined && liveCount > 0) {
                        cell.innerHTML = `<span style="color: var(--accent-cyan); font-weight: bold; font-style: italic;" title="Live Sensor Pulse">${liveCount}</span>`;
                    }
                }
            }
        } catch (error) {
            console.error(`Detailed IoT Fetch error for ${machineCode}:`, error);
        }
    });
}

// --- TV MODE & SCROLLING LOGIC ---
let scrollAnimation; 

function enableFullscreen() {
    const elem = document.documentElement;
    if (elem.requestFullscreen) {
        elem.requestFullscreen();
    }

    const topNav = document.getElementById('top-navbar');
    const filterBar = document.getElementById('filter-bar');
    
    if(topNav) topNav.style.display = 'none';
    if(filterBar) filterBar.style.display = 'none';
    
    startContinuousScroll();
}

function startContinuousScroll() {
    const grid = document.querySelector('.machine-grid');
    if (!grid) return;

    grid.style.scrollBehavior = 'auto';
    cancelAnimationFrame(scrollAnimation);

    let exactScrollPos = grid.scrollLeft;
    const scrollSpeed = 0.5; 

    function step() {
        exactScrollPos += scrollSpeed;
        grid.scrollLeft = exactScrollPos;

        if (grid.scrollLeft + grid.clientWidth >= grid.scrollWidth - 2) {
            grid.scrollLeft = 0; 
            exactScrollPos = 0; 
        }
        scrollAnimation = requestAnimationFrame(step);
    }
    
    scrollAnimation = requestAnimationFrame(step);
}

function stopContinuousScroll() {
    cancelAnimationFrame(scrollAnimation);
    const grid = document.querySelector('.machine-grid');
    if (grid) {
        grid.style.scrollBehavior = 'smooth';
    }
}

// --- RENDERING LOGIC ---
function renderDashboard(machines) {
    const grid = document.querySelector('.machine-grid');
    if (!grid) return;
    
    grid.innerHTML = ""; 

    if (machines.length === 0) {
        grid.innerHTML = "<h3 style='color: white; width: 100%; text-align: center; margin-top: 40px;'>No production data found.</h3>";
        return;
    }

    machines.forEach((mac, index) => {
        const gaugeId = `gauge_${index}`;
        
        const isIdle = mac.current_part_no === "NO PLAN" || mac.current_part_no === "Idle";
        const titleColor = isIdle ? "color: var(--text-muted);" : "color: var(--accent-cyan);";
        
        // 🚨 UPDATED: Passing the mac.machine variable into the buildShiftTable function
        let cardHTML = `
        <div class="machine-card">
            <div class="card-top">
                <div class="mc-info">
                    <div class="info-row"><span class="lbl">Machine:</span> <span class="val-cyan" style="${titleColor}">${mac.machine}</span></div>
                    <div class="info-row"><span class="lbl">Part No:</span> <span class="val" style="${titleColor}">${mac.current_part_no}</span></div>
                    <div class="info-row"><span class="lbl">Part Name:</span> <span class="val" style="${titleColor}">${mac.current_part_name}</span></div>
                    <div class="info-row"><span class="lbl">Operator:</span> <span class="val">${mac.current_operator}</span></div>
                    <div class="info-row"><span class="lbl">Target / Shift:</span> <span class="val">${mac.shift_target}</span></div>
                    <div class="info-row"><span class="lbl">Actual:</span> <span class="val">${mac.shift_actual}</span></div>
                    <div class="info-row"><span class="lbl">OK:</span> <span class="val" style="color: var(--status-green)">${mac.shift_ok}</span></div>
                    <div class="info-row"><span class="lbl">NG:</span> <span class="val" style="color: var(--status-red)">${mac.shift_ng}</span></div>
                </div>
                
                <div class="mc-gauge">
                    <canvas id="${gaugeId}" width="200" height="120"></canvas>
                    <div class="gauge-value">
                        <span class="g-lbl">ACTUAL</span>
                        <span class="g-num" style="${isIdle && mac.shift_actual === 0 ? 'color: var(--text-muted);' : ''}">${mac.shift_actual}</span>
                    </div>
                </div>
            </div>

            <div class="card-bottom">
                ${buildShiftTable("A Shift (07:00 - 19:00)", shiftATimes, mac.hourly_data["A"] || {}, mac.machine)}
                ${buildShiftTable("B Shift (19:00 - 07:00)", shiftBTimes, mac.hourly_data["B"] || {}, mac.machine)}
            </div>
        </div>
        `;
        grid.innerHTML += cardHTML;
    });

    machines.forEach((mac, index) => {
        drawGauge(`gauge_${index}`, mac.shift_actual, mac.shift_target);
    });
}

// 🚨 UPDATED: Function now accepts machineCode to generate unique cell IDs
function buildShiftTable(title, times, dataObj, machineCode) {
    let html = `
    <div class="table-section">
        <div class="table-title">${title}</div>
        <table class="hourly-table">
            <tr><th class="row-title">Time Slot</th>`;
    
    // Top header row
    times.forEach(t => {
        let shortTime = t.substring(0,2) + "-" + t.substring(8,10);
        html += `<th>${shortTime}</th>`;
    });
    
    html += `</tr><tr><td class="row-title">Target</td>`;
    
    const formatCell = (val, colorHex) => {
        if (val === "NP") return `<span style="color: #666; font-style: italic;">NP</span>`;
        if (val === undefined || val === null) return '-';
        return colorHex ? `<span style="color: ${colorHex}">${val}</span>` : val;
    };

    // Target Row
    times.forEach(t => html += `<td>${formatCell(dataObj[t] ? dataObj[t].target : null)}</td>`);
    
    // 🚨 UPDATED: Actual Row (Adds ID and Data Attributes for IoT Injection)
    html += `</tr><tr><td class="row-title">Actual</td>`;
    times.forEach(t => {
        const startHour = parseInt(t.split(":")[0], 10);
        const dbVal = dataObj[t] ? dataObj[t].actual : null;
        
        // If DB has no value (and it isn't "NP"), flag it as unsubmitted
        const isUnsubmitted = (dbVal === null || dbVal === undefined);
        
        html += `<td id="dtl_act_${machineCode}_${startHour}" data-unsubmitted="${isUnsubmitted}">`;
        html += formatCell(dbVal, "var(--accent-cyan)");
        html += `</td>`;
    });
    
    // OK and NG Rows
    html += `</tr><tr><td class="row-title">OK</td>`;
    times.forEach(t => html += `<td>${formatCell(dataObj[t] ? dataObj[t].ok : null, "var(--status-green)")}</td>`);
    html += `</tr><tr><td class="row-title">NG</td>`;
    times.forEach(t => html += `<td>${formatCell(dataObj[t] ? dataObj[t].ng : null, "var(--status-red)")}</td>`);
    
    html += `</tr></table></div>`;
    return html;
}

function drawGauge(canvasId, actual, target) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    
    ctx.clearRect(0, 0, w, h);
    
    const maxTarget = target > 0 ? target : 100; 
    let pct = actual / maxTarget;
    if (pct > 1) pct = 1; 
    if (target === 0 && actual === 0) pct = 0; 

    ctx.beginPath();
    ctx.arc(w/2, h - 10, w/2 - 20, Math.PI, 0);
    ctx.lineWidth = 15;
    ctx.strokeStyle = "rgba(255, 255, 255, 0.1)";
    ctx.stroke();

    if (actual > 0 || pct > 0) {
        ctx.beginPath();
        ctx.arc(w/2, h - 10, w/2 - 20, Math.PI, Math.PI + (Math.PI * pct));
        ctx.lineWidth = 15;
        
        ctx.strokeStyle = pct >= 0.95 ? "#00E5FF" : (pct > 0.5 ? "#FFD700" : "#FF5252");
        ctx.stroke();
    }
}