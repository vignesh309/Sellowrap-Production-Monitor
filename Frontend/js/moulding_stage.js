// --- RUNTIME STATE (Dynamic Master Data) ---
let partMaster = {};
let mouldMaster = {};
let rejectionCodes = ["Flash", "Short Shot", "Burn Mark", "Sink Mark", "Warping"]; // Moulding Specific Default
let shortfallCodes = [];
let currentBatchLogs = {};
let machineList = [];
let lastCheckedPlcString = ""; // Prevents spamming alerts every 60s

// --- HOURLY TRACKING STATE ---
const shiftAHours = [
    { start: "07:00", end: "08:00" }, { start: "08:00", end: "09:00" }, { start: "09:00", end: "10:00" },
    { start: "10:00", end: "11:00" }, { start: "11:00", end: "12:00" }, { start: "12:00", end: "13:00" },
    { start: "13:00", end: "14:00" }, { start: "14:00", end: "15:00" }, { start: "15:00", end: "16:00" },
    { start: "16:00", end: "17:00" }, { start: "17:00", end: "18:00" }, { start: "18:00", end: "19:00" }
];
const shiftBHours = [
    { start: "19:00", end: "20:00" }, { start: "20:00", end: "21:00" }, { start: "21:00", end: "22:00" },
    { start: "22:00", end: "23:00" }, { start: "23:00", end: "00:00" }, { start: "00:00", end: "01:00" },
    { start: "01:00", end: "02:00" }, { start: "02:00", end: "03:00" }, { start: "03:00", end: "04:00" },
    { start: "04:00", end: "05:00" }, { start: "05:00", end: "06:00" }, { start: "06:00", end: "07:00" }
];
let hours = shiftAHours;

let blockRejections = {};
let blockShortfalls = {};
let splitCounts = {};

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

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

// ==========================================
// MOULDING PLC TELEMETRY SYNC (NEW)
// ==========================================
async function syncMouldingTelemetry() {
    let machine = document.getElementById("machine").value;
    let dateVal = document.getElementById("global_date").value;
    
    enforceTimeLocks();

    if (!machine || !dateVal) return;

    try {
        const res = await fetch(`/api/get_live_moulding_data?machine_code=${encodeURIComponent(machine)}&date=${dateVal}`);
        
        if (res.ok) {
            const data = await res.json();
            
            // 1. Update Mode
            const modeEl = document.getElementById("live_mode");
            const modeText = document.getElementById("live_mode_text");
            if (modeText && modeEl) {
                modeText.innerText = data.mode_status || "UNKNOWN";
                
                if(data.mode_status === "FULLY AUTO") {
                    modeEl.style.color = "var(--status-green)";
                } else if (data.mode_status === "ABNORMAL") {
                    modeEl.style.color = "var(--status-red)";
                } else {
                    modeEl.style.color = "var(--status-yellow)";
                }
            }

            // 2. Update Cycle Time
            const cycleEl = document.getElementById("live_cycle_time");
            if (cycleEl) cycleEl.innerText = data.cycle_time ? `${data.cycle_time} s` : "-- s";

            // 3. Update Alarms
            const alarmEl = document.getElementById("live_alarm");
            if (alarmEl) {
                if(data.alarm_status === "TRIGGERED") {
                    alarmEl.innerText = data.alarm_message || "FAULT ACTIVE";
                    alarmEl.style.color = "var(--status-red)";
                } else {
                    alarmEl.innerText = "NONE";
                    alarmEl.style.color = "var(--status-green)";
                }
            }

            // 4. Update Mold from PLC & Run Smart Auto-Fill
            const moldEl = document.getElementById("live_mold_name");
            const plcMoldString = data.mold_name || "";
            if (moldEl) moldEl.innerText = plcMoldString;

            // 🚨 NEW: Auto-Populate Part & Mould Logic
            if (plcMoldString && plcMoldString !== "--" && plcMoldString !== lastCheckedPlcString) {
                lastCheckedPlcString = plcMoldString; // Remember it so we don't spam alerts
                
                // Regex looks for "Mould Name (Part Number)" format
                const match = plcMoldString.match(/^(.*?)\s*\(([^)]+)\)$/);
                
                if (match) {
                    const extractedMould = match[1].trim();
                    const extractedPart = match[2].trim();
                    
                    const partInput = document.getElementById("part_number");
                    
                    const partExists = partMaster.hasOwnProperty(extractedPart);
                    const mouldExists = mouldMaster.hasOwnProperty(extractedMould);
                    
                    if (partExists && mouldExists) {
                        // 🚨 REMOVED the "is empty" check. 
                        // Now, if the PLC reports a NEW valid setup, it ALWAYS updates the UI!
                        
                        // 1. Auto-Select Part
                        partInput.value = extractedPart;
                        filterMoldsByPart(); // Builds the mould dropdown synchronously
                        
                        // 2. Auto-Select Mould
                        document.getElementById("mould_code").value = extractedMould;
                        fetchMoldTargets(); // Fetches targets based on selections
                        
                    } else {
                        // Show warning if the database is missing this setup
                        alert(`⚠️ UNREGISTERED MOULD SETUP DETECTED:\n\nThe PLC is running:\nPart: ${extractedPart}\nMould: ${extractedMould}\n\nOne or both are missing from your Master database. Please create them in the Part Master page first to use auto-fill.`);
                    }
                }
            }

            // 5. Inject Shots into hourly blocks
            if (data.iot_counts) {
                injectIoTCounts(data.iot_counts); 
            }
        }
    } catch (e) { 
        console.error("Telemetry Sync Error:", e); 
    }
}

// Ping the PLC database tables every 15 seconds
setInterval(syncMouldingTelemetry, 15000);

// --- INITIALIZE DATA ON PAGE LOAD ---
async function fetchMasterData() {
    try {
        const response = await fetch('/api/init_moulding_stage');
        if (!response.ok) throw new Error("Failed to fetch master data");
        const data = await response.json();

        partMaster = data.parts;
        mouldMaster = data.moulds;
        
        // Only override if data is provided, otherwise keep moulding specific defaults
        if (data.rejections && data.rejections.length > 0) rejectionCodes = data.rejections;
        shortfallCodes = data.shortfalls;

        machineList = data.machines;
        let machineCodes = machineList.map(m => m.code);
        populateDropdown("machine", machineCodes);
        populateDropdown("part_number", Object.keys(data.parts));
        populateDropdown("operator", data.operators);
        populateDropdown("supervisor", data.supervisors);

        document.getElementById("machine").addEventListener("change", checkActiveMachineState);
        document.getElementById("machine").addEventListener("change", handleMachineSelection);
        document.getElementById("machine").addEventListener("change", syncMouldingTelemetry);
        document.getElementById("global_date").addEventListener("change", checkActiveMachineState);
        document.getElementById("global_shift").addEventListener("change", checkActiveMachineState);
        document.getElementById("part_number").addEventListener("change", filterMoldsByPart);
        document.getElementById("mould_code").addEventListener("change", fetchMoldTargets);

    } catch (error) {
        console.error("Error loading master data:", error);
        alert("Error loading system data. Please refresh the page.");
    }
}

function populateDropdown(elementId, items) {
    let el = document.getElementById(elementId);
    if (!el || !items) return;

    if (el.tagName === 'INPUT' && el.hasAttribute('list')) {
        let listId = el.getAttribute('list');
        let dataList = document.getElementById(listId);
        if (dataList) {
            dataList.innerHTML = '';
            items.forEach(item => {
                dataList.innerHTML += `<option value="${item}"></option>`;
            });
        }
    } else {
        let htmlStr = '<option value="">-- Select --</option>';
        items.forEach(item => {
            htmlStr += `<option value="${item}">${item}</option>`;
        });
        el.innerHTML = htmlStr;
    }
}

// --- DYNAMIC CASCADING DROPDOWNS ---

function handleMachineSelection() {
    const selectedCode = document.getElementById("machine").value; 
    const mouldDropdown = document.getElementById("mould_code"); 
    const partDropdown = document.getElementById("part_number"); 
    
    const selectedMachine = machineList.find(m => m.code === selectedCode);
    const processName = selectedMachine ? selectedMachine.process : "";

    // 🚨 SMART FILTER: Case-insensitive process matching
    let validParts = [];
    if (processName) {
        const cleanProcessName = processName.toUpperCase();
        
        validParts = Object.keys(partMaster).filter(partNo => {
            const partProcesses = partMaster[partNo].valid_processes || [];
            // Convert all part processes to uppercase for a safe comparison
            const cleanPartProcesses = partProcesses.map(p => p.toUpperCase());
            
            return cleanPartProcesses.includes(cleanProcessName);
        });
    } else {
        validParts = Object.keys(partMaster);
    }
    
    populateDropdown("part_number", validParts);
    partDropdown.value = "";

    const allowedMoldProcesses = ["MOULDING", "PRESS CUT", "THERMOWELDING"];

    if (allowedMoldProcesses.includes(processName)) {
        mouldDropdown.disabled = false;
        if (mouldDropdown.value === "-") mouldDropdown.value = ""; 
    } else {
        mouldDropdown.disabled = true;
        mouldDropdown.value = "-"; 
    }
    
    filterMoldsByPart();
}

function filterMoldsByPart() {
    const partSelect = document.getElementById("part_number");
    const moldSelect = document.getElementById("mould_code");
    const machineSelect = document.getElementById("machine"); 
    
    const selectedPart = partSelect.value;
    const selectedMachineCode = machineSelect.value;
    
    const selectedMachine = machineList.find(m => m.code === selectedMachineCode);
    const machineProcess = selectedMachine ? selectedMachine.process : "";

    const currentMold = moldSelect.value;
    moldSelect.innerHTML = '';

    const allowedMoldProcesses = ["MOULDING", "PRESS CUT", "THERMOWELDING"];

    if (!allowedMoldProcesses.includes(machineProcess)) {
        moldSelect.innerHTML = '<option value="-">- (Not Required)</option>';
        moldSelect.value = "-";
        moldSelect.disabled = true;
        fetchMoldTargets(); 
        return;
    }

    moldSelect.disabled = false;
    moldSelect.innerHTML = '<option value="" disabled selected>Select Mould</option>';

    if (!selectedPart) {
        fetchMoldTargets();
        return;
    }

    let matchCount = 0;
    let lastMatchedMold = "";
    let moldStillValid = false;

    for (const [moldNo, moldInfo] of Object.entries(mouldMaster)) {
        if (moldInfo.linked_parts && moldInfo.linked_parts.includes(selectedPart)) {
            const option = document.createElement("option");
            option.value = moldNo;
            option.textContent = `${moldNo} (${moldInfo.cavities} Cavity)`;
            moldSelect.appendChild(option);
            matchCount++;
            lastMatchedMold = moldNo;
            
            if (moldNo === currentMold) moldStillValid = true;
        }
    }

    if (moldStillValid) {
        moldSelect.value = currentMold;
    } else if (matchCount === 1) {
        moldSelect.value = lastMatchedMold;
    } else if (matchCount === 0) {
        const option = document.createElement("option");
        option.value = "";
        option.textContent = "No Molds Found for this Part!";
        option.disabled = true;
        moldSelect.appendChild(option);
    }
    
    fetchMoldTargets();
}

function fetchMoldTargets() {
    const moldSelect = document.getElementById("mould_code");
    const partSelect = document.getElementById("part_number").value;
    const machineSelect = document.getElementById("machine").value;
    
    const selectedMold = moldSelect ? moldSelect.value : "-"; 
    
    const targetInput = document.getElementById("hourlyTargetShots");
    const tempInput = document.getElementById("global_temp");
    const pressureInput = document.getElementById("global_pressure");
    const settingInput = document.getElementById("global_setting");

    const selectedMachine = machineList.find(m => m.code === machineSelect);
    const machineProcess = selectedMachine ? selectedMachine.process : "";

    let finalTarget = 0;
    let tTemp = "", tPress = "", tSet = "";

    if (partSelect && partMaster[partSelect] && partMaster[partSelect].targets && partMaster[partSelect].targets[machineProcess]) {
        const processTargets = partMaster[partSelect].targets[machineProcess];
        if (processTargets[selectedMold]) {
            const exactTargets = processTargets[selectedMold];
            finalTarget = exactTargets.tgtHourly || 0; 
            
            tTemp = exactTargets.tgtTemp || "";
            tPress = exactTargets.tgtPressure || "";
            tSet = exactTargets.tgtSetting || "";
        }
    }

    if (finalTarget === 0 && selectedMold && selectedMold !== "-" && mouldMaster[selectedMold]) {
        finalTarget = mouldMaster[selectedMold].hourlyShots || 0;
    }

    if (targetInput) targetInput.value = finalTarget;
    
    const lblTemp = document.getElementById("tgt_temp");
    const lblPress = document.getElementById("tgt_pressure");
    const lblSet = document.getElementById("tgt_setting");
    if (lblTemp) lblTemp.innerText = tTemp || "-";
    if (lblPress) lblPress.innerText = tPress || "-";
    if (lblSet) lblSet.innerText = tSet || "-";

    if (tempInput && tTemp) tempInput.value = tTemp;
    if (pressureInput && tPress) pressureInput.value = tPress;
    if (settingInput && tSet) settingInput.value = tSet;

    updateAllHourBlocks();
}

// --- BUILD DYNAMIC TABS, WRAPPERS & CARDS ---
function renderAllHourBlocks() {
    const grid = document.getElementById("hourly-grid");
    const tabsContainer = document.getElementById("hourly-tabs");

    if (!grid || !tabsContainer) return;

    grid.innerHTML = "";
    tabsContainer.innerHTML = "";

    let dataListsHtml = `
        <datalist id="sf_reasons_list">
            ${shortfallCodes.map(code => `<option value="${code}"></option>`).join('')}
        </datalist>
        <datalist id="rej_reasons_list">
            ${rejectionCodes.map(code => `<option value="${code}"></option>`).join('')}
        </datalist>
    `;
    grid.innerHTML = dataListsHtml;

    hours.forEach((timeObj, hourIndex) => {
        splitCounts[hourIndex] = 0;
        blockRejections[hourIndex] = {};
        blockShortfalls[hourIndex] = {};

        const tab = document.createElement("div");
        tab.className = `hour-tab ${hourIndex === 0 ? 'active' : ''}`;
        tab.id = `tab_${hourIndex}`;
        tab.onclick = () => switchTab(hourIndex);
        tab.innerHTML = `
            <span class="tab-time">${timeObj.start} - ${timeObj.end}</span>
            <span class="tab-status" id="tab_status_${hourIndex}" style="color: var(--status-yellow);">Unsaved (60m left)</span>
        `;
        tabsContainer.appendChild(tab);

        const wrapper = document.createElement("div");
        wrapper.className = `hour-block-wrapper ${hourIndex === 0 ? 'active-block' : ''}`;
        wrapper.id = `wrapper_${hourIndex}`;

        wrapper.innerHTML = `
            <div class="hour-block-header">
                <div style="display: flex; align-items: center; gap: 15px;">
                    <h3 class="hour-block-title">🕒 Block ${hourIndex + 1}: ${timeObj.start} - ${timeObj.end}</h3>
                    <label class="custom-checkbox-container" style="width: auto; padding: 0;">
                        <input type="checkbox" id="split_check_${hourIndex}" onchange="toggleSplitMode(${hourIndex})">
                        <span class="checkmark"></span>
                        <span class="checkbox-text" style="font-size: 12px;">Hourly Split</span>
                    </label>
                </div>
                <button id="btn_add_split_${hourIndex}" class="btn-split" style="display: none;" onclick="addSplitCard(${hourIndex})">
                    ➕ Add Part Run
                </button>
            </div>
            <div class="sub-blocks-container" id="sub_blocks_container_${hourIndex}"></div>
        `;
        grid.appendChild(wrapper);

        addSplitCard(hourIndex, timeObj.start, timeObj.end, false);
    });

    calculateTotals();
    enforceTimeLocks();
}

function switchTab(activeIndex) {
    for (let i = 0; i < hours.length; i++) {
        const tab = document.getElementById(`tab_${i}`);
        const wrapper = document.getElementById(`wrapper_${i}`);

        if (i === activeIndex) {
            tab.classList.add("active");
            wrapper.classList.add("active-block");
        } else {
            tab.classList.remove("active");
            wrapper.classList.remove("active-block");
        }
    }
}

function updateTabStatus(hourIndex) {
    let totalSavedMinutes = 0;
    let lastSaveTime = "";
    let isNoPlanTab = false;

    for (let j = 0; j < splitCounts[hourIndex]; j++) {
        let btn = document.getElementById(`btn_submit_${hourIndex}_${j}`);

        if (btn && (btn.innerText.includes("Saved") || btn.innerText.includes("Logged"))) {
            let tStart = document.getElementById(`time_start_${hourIndex}_${j}`).value;
            let tEnd = document.getElementById(`time_end_${hourIndex}_${j}`).value;

            let startMins = (parseInt(tStart.split(':')[0]) * 60) + parseInt(tStart.split(':')[1]);
            let endMins = (parseInt(tEnd.split(':')[0]) * 60) + parseInt(tEnd.split(':')[1]);
            if (endMins < startMins) endMins += (24 * 60); 

            totalSavedMinutes += (endMins - startMins);

            let parts = btn.innerText.split('at ');
            if (parts.length > 1) lastSaveTime = parts[1];

            if (btn.innerText.includes("Logged")) {
                isNoPlanTab = true;
            }
        }
    }

    let tabEl = document.getElementById(`tab_${hourIndex}`);
    let tabStatusEl = document.getElementById(`tab_status_${hourIndex}`);

    if (totalSavedMinutes >= 60) {
        if (isNoPlanTab) {
            tabStatusEl.innerText = `Idle Time ✓ ${lastSaveTime}`;
            tabStatusEl.style.color = "var(--status-yellow)";
            tabEl.style.borderColor = "var(--status-yellow)";
        } else {
            tabStatusEl.innerText = `Saved ✓ ${lastSaveTime}`;
            tabStatusEl.style.color = "var(--status-green)";
            tabEl.style.borderColor = "var(--status-green)";
        }
    } else {
        let minsLeft = 60 - totalSavedMinutes;
        tabStatusEl.innerText = `Unsaved (${minsLeft}m left)`;
        tabStatusEl.style.color = "var(--status-yellow)";
        tabEl.style.borderColor = "var(--border-color)";
    }
}

function enforceTimeLocks() {
    const role = localStorage.getItem("userRole") || "Unknown";
    
    if (role === "Admin") return;

    const now = new Date();
    const currentHour = now.getHours(); 
    const globalDate = document.getElementById("global_date").value;
    const todayDate = new Date(now.getTime() - (now.getTimezoneOffset() * 60000)).toISOString().split('T')[0];

    hours.forEach((timeObj, index) => {
        const blockStartHour = parseInt(timeObj.start.split(":")[0]);
        let isLocked = false;

        if (globalDate !== todayDate) {
            isLocked = true;
        } 
        else {
            let hourDifference = currentHour - blockStartHour;
            
            if (hourDifference < -12) hourDifference += 24; 
            if (hourDifference > 12) hourDifference -= 24;

            if (hourDifference > 1 || hourDifference < 0) {
                isLocked = true;
            }
        }

        if (isLocked) {
            for (let j = 0; j < splitCounts[index]; j++) {
                let btn = document.getElementById(`btn_submit_${index}_${j}`);
                
                if (btn && !btn.innerText.includes("Saved")) {
                    let shotsInput = document.getElementById(`shots_${index}_${j}`);
                    if (shotsInput) shotsInput.disabled = true;
                    
                    document.getElementById(`sf_qty_${index}_${j}`).disabled = true;
                    document.getElementById(`sf_reason_${index}_${j}`).disabled = true;
                    document.getElementById(`btn_add_sf_${index}_${j}`).disabled = true;
                    document.getElementById(`rej_qty_${index}_${j}`).disabled = true;
                    document.getElementById(`rej_reason_${index}_${j}`).disabled = true;
                    document.getElementById(`btn_add_rej_${index}_${j}`).disabled = true;

                    btn.style.background = "var(--border-color)";
                    btn.style.color = "var(--text-muted)";
                    btn.style.border = "none";
                    btn.innerText = "🔒 Time Locked";
                    btn.disabled = true;
                }
            }
        }
    });
}

function toggleSplitMode(hourIndex) {
    const isChecked = document.getElementById(`split_check_${hourIndex}`).checked;
    const addBtn = document.getElementById(`btn_add_split_${hourIndex}`);

    const firstCardStart = document.getElementById(`time_start_${hourIndex}_0`);
    const firstCardEnd = document.getElementById(`time_end_${hourIndex}_0`);
    const staticTimeDisplay = document.getElementById(`static_time_${hourIndex}_0`);

    if (isChecked) {
        addBtn.style.display = "flex";
        firstCardStart.style.display = "block";
        firstCardEnd.style.display = "block";
        staticTimeDisplay.style.display = "none";
        updateSplitTarget(hourIndex, 0); 
    } else {
        if (splitCounts[hourIndex] > 1) {
            alert("Please remove the extra split cards before disabling Hourly Split.");
            document.getElementById(`split_check_${hourIndex}`).checked = true;
            return;
        }
        addBtn.style.display = "none";
        firstCardStart.style.display = "none";
        firstCardEnd.style.display = "none";
        staticTimeDisplay.style.display = "block";

        firstCardStart.value = hours[hourIndex].start;
        firstCardEnd.value = hours[hourIndex].end;
        updateSplitTarget(hourIndex, 0); 
    }
}

function addSplitCard(hourIndex, defaultStart = "", defaultEnd = "", canRemove = true) {
    const container = document.getElementById(`sub_blocks_container_${hourIndex}`);
    const splitIndex = splitCounts[hourIndex];

    blockRejections[hourIndex][splitIndex] = [];
    blockShortfalls[hourIndex][splitIndex] = [];

    const targetInput = document.getElementById("hourlyTargetShots");
    let currentTarget = targetInput ? (targetInput.value || 0) : 0;

    const card = document.createElement("div");
    card.className = "sub-block-card hour-card";
    card.id = `card_${hourIndex}_${splitIndex}`;

    const displayInputs = splitIndex === 0 ? "none" : "block";
    const displayStatic = splitIndex === 0 ? "block" : "none";

    card.innerHTML = `
        ${canRemove ? `<button class="btn-remove-split" onclick="removeSplitCard(${hourIndex}, ${splitIndex})" title="Remove this split">✕</button>` : ''}
        
        <div class="time-inputs-row">
            <span id="static_time_${hourIndex}_${splitIndex}" style="display: ${displayStatic}; width: 100%; text-align: center; font-weight: bold; color: white;">
                ${hours[hourIndex].start} - ${hours[hourIndex].end}
            </span>
            <input type="time" id="time_start_${hourIndex}_${splitIndex}" value="${defaultStart}" style="display: ${displayInputs};" onchange="updateSplitTarget(${hourIndex}, ${splitIndex})">
            <span style="display: ${displayInputs}; color: var(--text-muted);">to</span>
            <input type="time" id="time_end_${hourIndex}_${splitIndex}" value="${defaultEnd}" style="display: ${displayInputs};" onchange="updateSplitTarget(${hourIndex}, ${splitIndex})">
        </div>

        <div style="text-align: right; margin-top: -10px; margin-bottom: -5px; padding-right: 10px;">
            <label class="custom-checkbox-container small-checkbox" style="display: inline-flex; width: auto; padding: 0;">
                <input type="checkbox" id="no_plan_${hourIndex}_${splitIndex}" onchange="toggleNoPlan(${hourIndex}, ${splitIndex})">
                <span class="checkmark"></span>
                <span class="checkbox-text" style="font-size: 11px;">No Plan</span>
            </label>
        </div>

        <div class="hour-header">
            <span class="hour-target">Target Shots: <span id="target_${hourIndex}_${splitIndex}" style="color: var(--status-yellow); font-weight:bold;">${currentTarget}</span></span>
        </div>

        <div class="hour-inputs">
            <div>
                <label>Actual Shots</label>
                <input type="number" id="shots_${hourIndex}_${splitIndex}" value="0" min="0" oninput="calculateTotals()" style="color: var(--status-yellow); font-weight:bold; font-size: 18px;">
            </div>
        </div>
        
        <div class="shortfall-area">
            <div style="display:flex; justify-content: space-between;">
               <label>Shortfall Breakup</label>
               <span style="font-size: 11px; color: var(--text-muted)">Missing: <span id="missing_shots_${hourIndex}_${splitIndex}" style="color: var(--status-yellow); font-weight: bold;">0</span></span>
            </div>
            <div class="breakup-controls">
                <input type="number" id="sf_qty_${hourIndex}_${splitIndex}" placeholder="Shots" min="1">
                <input list="sf_reasons_list" id="sf_reason_${hourIndex}_${splitIndex}" placeholder="Reason...">
                <button type="button" class="btn-add-sf" id="btn_add_sf_${hourIndex}_${splitIndex}" onclick="addShortfall(${hourIndex}, ${splitIndex})">Add</button>
            </div>
            <div class="breakup-list" id="shortfall_list_${hourIndex}_${splitIndex}"></div>
            <div style="text-align: right; font-size: 11px; margin-top: 5px; color: var(--text-muted);">
                Total Logged: <span id="sf_total_${hourIndex}_${splitIndex}" style="color: var(--status-yellow); font-weight: bold;">0</span>
            </div>
        </div>

        <div class="rejection-area">
            <label>Rejection Breakup (NG)</label>
            <div class="breakup-controls">
                <input type="number" id="rej_qty_${hourIndex}_${splitIndex}" placeholder="Parts" min="1">
                <input list="rej_reasons_list" id="rej_reason_${hourIndex}_${splitIndex}" placeholder="Reason...">
                <button type="button" class="btn-add-rej" id="btn_add_rej_${hourIndex}_${splitIndex}" onclick="addRejection(${hourIndex}, ${splitIndex})">Add</button>
            </div>
            <div class="breakup-list" id="reject_list_${hourIndex}_${splitIndex}"></div>
            <div style="text-align: right; font-size: 11px; margin-top: 5px; color: var(--text-muted);">
                Total NG: <span id="ng_total_${hourIndex}_${splitIndex}" style="color: var(--status-red); font-weight: bold;">0</span>
            </div>
        </div>

        <div class="hour-actual">
            <div style="display: flex; flex-direction: column;">
                <span style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">OK Qty</span>
                <span class="calculated-ok" id="ok_${hourIndex}_${splitIndex}">0 pcs</span>
            </div>
            <div class="display: flex; flex-direction: column; text-align: right;">
                <span style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">Total Produced</span>
                <span style="color: var(--text-main); font-size: 18px;" id="actual_${hourIndex}_${splitIndex}">0 pcs</span>
            </div>
        </div>

        <button id="btn_submit_${hourIndex}_${splitIndex}" class="btn-outline" onclick="submitBlock(${hourIndex}, ${splitIndex})">Submit Run</button>
    `;

    container.appendChild(card);
    splitCounts[hourIndex]++;

    if (splitIndex > 0) {
        updateSplitTarget(hourIndex, splitIndex);
    }
}

function removeSplitCard(hourIndex, splitIndex) {
    const card = document.getElementById(`card_${hourIndex}_${splitIndex}`);
    if (card) {
        card.remove();
        blockRejections[hourIndex][splitIndex] = [];
        blockShortfalls[hourIndex][splitIndex] = [];
        calculateTotals();
    }
}

function updateSplitTarget(hourIndex, splitIndex) {
    let tStart = document.getElementById(`time_start_${hourIndex}_${splitIndex}`).value;
    let tEnd = document.getElementById(`time_end_${hourIndex}_${splitIndex}`).value;
    const targetInput = document.getElementById("hourlyTargetShots");
    let globalTarget = targetInput ? (parseInt(targetInput.value) || 0) : 0;

    let targetEl = document.getElementById(`target_${hourIndex}_${splitIndex}`);
    if (!targetEl) return;

    const isSplitMode = document.getElementById(`split_check_${hourIndex}`).checked;
    if (!isSplitMode && splitIndex === 0) {
        targetEl.innerText = globalTarget;
        calculateTotals();
        return;
    }

    if (!tStart || !tEnd) {
        targetEl.innerText = globalTarget;
        calculateTotals();
        return;
    }

    const startMinutes = (parseInt(tStart.split(':')[0]) * 60) + parseInt(tStart.split(':')[1]);
    let endMinutes = (parseInt(tEnd.split(':')[0]) * 60) + parseInt(tEnd.split(':')[1]);

    if (endMinutes < startMinutes) endMinutes += (24 * 60);

    let duration = endMinutes - startMinutes;

    if (duration <= 0 || duration > 60) {
        targetEl.innerText = globalTarget; 
    } else {
        let proportionalTarget = Math.round((duration / 60) * globalTarget);
        targetEl.innerText = proportionalTarget;
    }
    calculateTotals();
}

function toggleNoPlan(hourIndex, splitIndex) {
    const isNoPlan = document.getElementById(`no_plan_${hourIndex}_${splitIndex}`).checked;
    const shotsInput = document.getElementById(`shots_${hourIndex}_${splitIndex}`);
    const targetEl = document.getElementById(`target_${hourIndex}_${splitIndex}`);
    const btn = document.getElementById(`btn_submit_${hourIndex}_${splitIndex}`);

    if (isNoPlan) {
        targetEl.innerText = "0";
        shotsInput.value = 0;
        shotsInput.disabled = true;
        
        document.getElementById(`sf_qty_${hourIndex}_${splitIndex}`).disabled = true;
        document.getElementById(`sf_reason_${hourIndex}_${splitIndex}`).disabled = true;
        document.getElementById(`btn_add_sf_${hourIndex}_${splitIndex}`).disabled = true;
        document.getElementById(`rej_qty_${hourIndex}_${splitIndex}`).disabled = true;
        document.getElementById(`rej_reason_${hourIndex}_${splitIndex}`).disabled = true;
        document.getElementById(`btn_add_rej_${hourIndex}_${splitIndex}`).disabled = true;

        btn.innerText = "Submit (No Plan)";
        btn.style.borderColor = "var(--status-yellow)";
        btn.style.color = "var(--status-yellow)";
    } else {
        shotsInput.disabled = false;
        
        document.getElementById(`sf_qty_${hourIndex}_${splitIndex}`).disabled = false;
        document.getElementById(`sf_reason_${hourIndex}_${splitIndex}`).disabled = false;
        document.getElementById(`btn_add_sf_${hourIndex}_${splitIndex}`).disabled = false;
        document.getElementById(`rej_qty_${hourIndex}_${splitIndex}`).disabled = false;
        document.getElementById(`rej_reason_${hourIndex}_${splitIndex}`).disabled = false;
        document.getElementById(`btn_add_rej_${hourIndex}_${splitIndex}`).disabled = false;

        btn.innerText = "Submit Run";
        btn.style.borderColor = "var(--accent-cyan)";
        btn.style.color = "var(--accent-cyan)";
        updateSplitTarget(hourIndex, splitIndex); 
    }
    calculateTotals();
}

async function toggleGlobalNoPlan() {
    const globalCheckbox = document.getElementById("global_no_plan_check");
    const isGlobalNoPlan = globalCheckbox.checked;

    if (!isGlobalNoPlan) {
        for (let i = 0; i < hours.length; i++) {
            for (let j = 0; j < splitCounts[i]; j++) {
                const btn = document.getElementById(`btn_submit_${i}_${j}`);
                const noPlanCheck = document.getElementById(`no_plan_${i}_${j}`);

                if (btn && !btn.innerText.includes("Saved") && !btn.innerText.includes("Logged") && !btn.innerText.includes("Locked")) {
                    if (noPlanCheck && noPlanCheck.checked) {
                        noPlanCheck.checked = false;
                        toggleNoPlan(i, j); 
                    }
                }
            }
        }
        return;
    }

    let submittedCount = 0;
    let remainingBlocks = [];

    for (let i = 0; i < hours.length; i++) {
        let hourHasSaved = false;
        for (let j = 0; j < splitCounts[i]; j++) {
            const btn = document.getElementById(`btn_submit_${i}_${j}`);
            
            if (btn) {
                if (btn.innerText.includes("Saved") || btn.innerText.includes("Logged")) {
                    hourHasSaved = true;
                } else if (!btn.innerText.includes("Locked")) {
                    remainingBlocks.push({ i, j });
                }
            }
        }
        if (hourHasSaved) submittedCount++;
    }

    let remainingHours = hours.length - submittedCount;

    if (remainingBlocks.length === 0) {
        alert("There are no remaining unlocked hours to submit.");
        globalCheckbox.checked = false;
        return;
    }

    const confirmMsg = `Only ${submittedCount} hour blocks are submitted. Are you sure you want to submit the remaining ${remainingHours} hours as No Plan?`;
    
    if (!confirm(confirmMsg)) {
        globalCheckbox.checked = false;
        return;
    }

    globalCheckbox.disabled = true; 

    for (const block of remainingBlocks) {
        const { i, j } = block;
        const noPlanCheck = document.getElementById(`no_plan_${i}_${j}`);
        
        if (noPlanCheck && !noPlanCheck.checked) {
            noPlanCheck.checked = true;
            toggleNoPlan(i, j);
        }
        
        await submitBlock(i, j);
    }

    globalCheckbox.disabled = false;
    alert("✅ All remaining hours have been successfully submitted as No Plan.");
}

function addShortfall(hourIndex, splitIndex) {
    let qtyInput = document.getElementById(`sf_qty_${hourIndex}_${splitIndex}`);
    let reasonSelect = document.getElementById(`sf_reason_${hourIndex}_${splitIndex}`);
    let qty = parseInt(qtyInput.value) || 0;
    let reason = reasonSelect.value.trim();

    if (qty <= 0 || !reason) { alert("Please enter valid missing shots and a reason."); return; }
    if (!shortfallCodes.includes(reason)) { alert("Invalid reason. Please select from the dropdown list."); return; }

    blockShortfalls[hourIndex][splitIndex].push({ qty: qty, reason: reason });
    qtyInput.value = ""; reasonSelect.value = "";
    renderShortfallList(hourIndex, splitIndex);
}

function removeShortfall(hourIndex, splitIndex, sfIndex) {
    let isSubmitted = document.getElementById(`btn_submit_${hourIndex}_${splitIndex}`).innerText.includes("Saved");
    if (isSubmitted) return;
    blockShortfalls[hourIndex][splitIndex].splice(sfIndex, 1);
    renderShortfallList(hourIndex, splitIndex);
}

function renderShortfallList(hourIndex, splitIndex) {
    let listContainer = document.getElementById(`shortfall_list_${hourIndex}_${splitIndex}`);
    listContainer.innerHTML = "";
    let totalSf = 0;
    blockShortfalls[hourIndex][splitIndex].forEach((sf, i) => {
        totalSf += sf.qty;
        listContainer.innerHTML += `
            <div class="shortfall-chip">
                <span>${sf.qty}x ${sf.reason}</span>
                <button class="remove-btn" id="rm_sf_${hourIndex}_${splitIndex}_${i}" onclick="removeShortfall(${hourIndex}, ${splitIndex}, ${i})">✕</button>
            </div>
        `;
    });
    document.getElementById(`sf_total_${hourIndex}_${splitIndex}`).innerText = totalSf;
}

function addRejection(hourIndex, splitIndex) {
    let qtyInput = document.getElementById(`rej_qty_${hourIndex}_${splitIndex}`);
    let reasonSelect = document.getElementById(`rej_reason_${hourIndex}_${splitIndex}`);
    let qty = parseInt(qtyInput.value) || 0;
    let reason = reasonSelect.value.trim();

    if (qty <= 0 || !reason) { alert("Please enter a valid NG quantity and a reason."); return; }
    if (!rejectionCodes.includes(reason)) { alert("Invalid reason. Please select from the dropdown list."); return; }

    blockRejections[hourIndex][splitIndex].push({ qty: qty, reason: reason });
    qtyInput.value = ""; reasonSelect.value = "";
    renderRejectionList(hourIndex, splitIndex);
    calculateTotals();
}

function removeRejection(hourIndex, splitIndex, rejIndex) {
    let isSubmitted = document.getElementById(`btn_submit_${hourIndex}_${splitIndex}`).innerText.includes("Saved");
    if (isSubmitted) return;
    blockRejections[hourIndex][splitIndex].splice(rejIndex, 1);
    renderRejectionList(hourIndex, splitIndex);
    calculateTotals();
}

function renderRejectionList(hourIndex, splitIndex) {
    let listContainer = document.getElementById(`reject_list_${hourIndex}_${splitIndex}`);
    listContainer.innerHTML = "";
    let totalNg = 0;
    blockRejections[hourIndex][splitIndex].forEach((rej, i) => {
        totalNg += rej.qty;
        listContainer.innerHTML += `
            <div class="reject-chip">
                <span>${rej.qty}x ${rej.reason}</span>
                <button class="remove-btn" id="rm_rej_${hourIndex}_${splitIndex}_${i}" onclick="removeRejection(${hourIndex}, ${splitIndex}, ${i})">✕</button>
            </div>
        `;
    });
    document.getElementById(`ng_total_${hourIndex}_${splitIndex}`).innerText = totalNg;
}

function triggerPartChange() {
    if (document.getElementById("part_change_override")) document.getElementById("part_change_override").checked = false;

    let finalizeBtn = document.getElementById("btn_finalize");
    if (finalizeBtn && !finalizeBtn.innerText.includes("🔒")) {
        alert("❌ ACTION DENIED:\nYou must 'Finalize Batch' to officially close out the current part's production before you can initiate a Part Change.");
        return;
    }

    if (!confirm("Initiate Part Change?\n\nThis will keep your finished hours locked and unlock the remaining empty hours so you can start a new part.")) {
        return;
    }

    const fieldsToUnlock = ["part_number", "mould_code", "batchNo", "operator", "supervisor"];
    fieldsToUnlock.forEach(id => {
        let el = document.getElementById(id);
        if (el) el.disabled = false;
    });

    document.getElementById("part_number").value = "";
    filterMoldsByPart();

    for (let i = 0; i < hours.length; i++) {
        let splitCheck = document.getElementById(`split_check_${i}`);
        if (splitCheck) splitCheck.disabled = false;

        for (let j = 0; j < splitCounts[i]; j++) {
            let btn = document.getElementById(`btn_submit_${i}_${j}`);
            if (!btn) continue;

            if (!btn.innerText.includes("Saved")) {
                let shotsInput = document.getElementById(`shots_${i}_${j}`);
                shotsInput.disabled = false;
                shotsInput.value = 0;

                let timeStart = document.getElementById(`time_start_${i}_${j}`);
                let timeEnd = document.getElementById(`time_end_${i}_${j}`);
                if (timeStart) timeStart.disabled = false;
                if (timeEnd) timeEnd.disabled = false;

                document.getElementById(`ok_${i}_${j}`).innerText = "0 pcs";
                document.getElementById(`actual_${i}_${j}`).innerText = "0 pcs";

                document.getElementById(`sf_qty_${i}_${j}`).disabled = false;
                document.getElementById(`sf_reason_${i}_${j}`).disabled = false;
                document.getElementById(`btn_add_sf_${i}_${j}`).disabled = false;
                document.getElementById(`rej_qty_${i}_${j}`).disabled = false;
                document.getElementById(`rej_reason_${i}_${j}`).disabled = false;
                document.getElementById(`btn_add_rej_${i}_${j}`).disabled = false;

                btn.style.background = "rgba(0, 229, 255, 0.1)";
                btn.style.color = "var(--accent-cyan)";
                btn.style.border = "1px solid var(--accent-cyan)";
                btn.innerText = "Submit Run";
                btn.disabled = false;
            }
        }
    }

    if (finalizeBtn) {
        finalizeBtn.innerText = "Finalize Batch";
        finalizeBtn.disabled = false;
        finalizeBtn.style.background = "";
        finalizeBtn.style.color = "";
    }

    calculateTotals();
    document.getElementById("part_number").focus();
}

async function checkActiveMachineState() {
    let shiftVal = document.getElementById("global_shift").value;
    hours = (shiftVal === "B") ? shiftBHours : shiftAHours;

    renderAllHourBlocks();

    let machine = document.getElementById("machine").value;
    let dateVal = document.getElementById("global_date").value;

    if (!machine || !dateVal || !shiftVal) return;

    try {
        const logRes = await fetch(`/api/get_batch_logs?date=${dateVal}&shift=${shiftVal}&machine_code=${encodeURIComponent(machine)}`);
        if (logRes.ok) {
            const logData = await logRes.json();

            if (logData.exists && logData.logs.length > 0) {
                document.getElementById("batchNo").value = logData.setup.internal_batch_number || "";
                document.getElementById("part_number").value = logData.setup.part_number;
                
                filterMoldsByPart();

                setTimeout(() => {
                    document.getElementById("mould_code").value = logData.setup.mould_code || "";
                    document.getElementById("operator").value = logData.setup.operator_code || "";
                    document.getElementById("supervisor").value = logData.setup.supervisor_code || "";

                    fetchMoldTargets();

                    currentBatchLogs = {};
                    currentBatchLogs[dateVal] = {};
                    logData.logs.forEach(log => {
                        if (!currentBatchLogs[dateVal][log.start_time]) {
                            currentBatchLogs[dateVal][log.start_time] = [];
                        }
                        currentBatchLogs[dateVal][log.start_time].push(log);
                    });

                    applyRestoredLogs(logData.is_finalized);

                    if (logData.is_finalized) {
                        let finalizeBtn = document.getElementById("btn_finalize");
                        if (finalizeBtn) {
                            finalizeBtn.innerText = "🔒 Batch Finalized & Closed";
                            finalizeBtn.disabled = true;
                            finalizeBtn.style.background = "var(--border-color)";
                            finalizeBtn.style.color = "var(--text-muted)";
                        }
                    }
                    
                    injectIoTCounts(logData.iot_counts);

                }, 100);
            } else {
                wipeScreenForNewMachine();
                
                if (logData.last_known_setup) {
                    document.getElementById("part_number").value = logData.last_known_setup.part_number || "";
                    
                    filterMoldsByPart(); 

                    setTimeout(() => {
                        document.getElementById("mould_code").value = logData.last_known_setup.mould_code || "";
                        document.getElementById("operator").value = logData.last_known_setup.operator_code || "";
                        document.getElementById("supervisor").value = logData.last_known_setup.supervisor_code || "";
                        
                        fetchMoldTargets();
                    }, 100);
                }
                
                setTimeout(() => {
                    injectIoTCounts(logData.iot_counts);
                }, 100);
            }
        }
    } catch (e) { console.error(e); }
}

function wipeScreenForNewMachine() {
    document.getElementById("part_number").value = "";
    filterMoldsByPart();
    document.getElementById("batchNo").value = "";
    document.getElementById("operator").value = "";
    document.getElementById("supervisor").value = "";

    let prodQtyEl = document.getElementById("prodQty");
    if (prodQtyEl) prodQtyEl.innerText = "0";

    const targetInput = document.getElementById("hourlyTargetShots");
    if (targetInput) targetInput.value = 0;

    currentBatchLogs = {};
    renderAllHourBlocks();

    if (document.getElementById("batch_remarks")) document.getElementById("batch_remarks").value = "";
    if (document.getElementById("part_change_override")) document.getElementById("part_change_override").checked = false;
    lastCheckedPlcString = "";
}

function updateAllHourBlocks() {
    for (let i = 0; i < hours.length; i++) {
        for (let j = 0; j < splitCounts[i]; j++) {
            let btn = document.getElementById(`btn_submit_${i}_${j}`);
            if (btn && btn.innerText.includes("Saved")) continue; 

            updateSplitTarget(i, j);
        }
    }
}

function calculateTotals() {
    let mouldKey = document.getElementById("mould_code") ? document.getElementById("mould_code").value : "";
    let cavityCount = 1.0; 
    
    if (mouldKey && mouldMaster[mouldKey]) {
        cavityCount = parseFloat(mouldMaster[mouldKey].active_cavities) || 1.0;
    }

    let grandShots = 0, grandOk = 0, grandNg = 0, grandTotalParts = 0;

    for (let i = 0; i < hours.length; i++) {
        for (let j = 0; j < splitCounts[i]; j++) {
            let shotsInput = document.getElementById(`shots_${i}_${j}`);
            if (!shotsInput) continue;

            let targetShots = parseInt(document.getElementById(`target_${i}_${j}`).innerText) || 0;
            let actualShots = parseInt(shotsInput.value) || 0;

            let missingShots = targetShots - actualShots;
            if (missingShots < 0) missingShots = 0;
            document.getElementById(`missing_shots_${i}_${j}`).innerText = missingShots;

            let ngParts = parseInt(document.getElementById(`ng_total_${i}_${j}`).innerText) || 0;
            
            let totalProducedParts = actualShots * cavityCount;
            let okParts = totalProducedParts - ngParts;
            if (okParts < 0) okParts = 0;

            document.getElementById(`ok_${i}_${j}`).innerText = `${Math.round(okParts)} pcs`;
            document.getElementById(`actual_${i}_${j}`).innerText = `${Math.round(totalProducedParts)} pcs`;

            grandShots += actualShots;
            grandOk += okParts;
            grandNg += ngParts;
            grandTotalParts += totalProducedParts;
        }
    }

    document.getElementById("grand-shots").innerText = grandShots;
    document.getElementById("grand-ok").innerText = Math.round(grandOk);
    document.getElementById("grand-ng").innerText = grandNg;
    document.getElementById("grand-actual").innerText = Math.round(grandTotalParts);
}

function validateTimeRange(hourIndex, splitIndex) {
    let tStart = document.getElementById(`time_start_${hourIndex}_${splitIndex}`).value;
    let tEnd = document.getElementById(`time_end_${hourIndex}_${splitIndex}`).value;

    if (!tStart || !tEnd) {
        alert("Please select both a Start Time and an End Time for this split.");
        return false;
    }

    const startMinutes = (parseInt(tStart.split(':')[0]) * 60) + parseInt(tStart.split(':')[1]);
    const endMinutes = (parseInt(tEnd.split(':')[0]) * 60) + parseInt(tEnd.split(':')[1]);
    const blockStartLimit = (parseInt(hours[hourIndex].start.split(':')[0]) * 60) + parseInt(hours[hourIndex].start.split(':')[1]);

    let blockEndLimit = (parseInt(hours[hourIndex].end.split(':')[0]) * 60) + parseInt(hours[hourIndex].end.split(':')[1]);
    if (blockEndLimit < blockStartLimit) blockEndLimit += (24 * 60);

    let adjustedStart = startMinutes;
    let adjustedEnd = endMinutes;
    if (adjustedStart < blockStartLimit) adjustedStart += (24 * 60);
    if (adjustedEnd < blockStartLimit) adjustedEnd += (24 * 60);

    if (adjustedStart >= adjustedEnd) {
        alert("End time must be after the start time.");
        return false;
    }

    if (adjustedStart < blockStartLimit || adjustedEnd > blockEndLimit) {
        alert(`Time must be within the bounds of this hour block (${hours[hourIndex].start} to ${hours[hourIndex].end}).`);
        return false;
    }

    for (let j = 0; j < splitCounts[hourIndex]; j++) {
        if (j === splitIndex) continue; 

        let otherStartStr = document.getElementById(`time_start_${hourIndex}_${j}`).value;
        let otherEndStr = document.getElementById(`time_end_${hourIndex}_${j}`).value;

        if (!otherStartStr || !otherEndStr) continue;

        let oStart = (parseInt(otherStartStr.split(':')[0]) * 60) + parseInt(otherStartStr.split(':')[1]);
        let oEnd = (parseInt(otherEndStr.split(':')[0]) * 60) + parseInt(otherEndStr.split(':')[1]);

        if (oEnd < oStart) oEnd += (24 * 60);
        if (oStart < blockStartLimit) oStart += (24 * 60);
        if (oEnd < blockStartLimit) oEnd += (24 * 60);

        if (adjustedStart < oEnd && adjustedEnd > oStart) {
            alert(`⚠️ OVERLAP DETECTED:\nYour selected time (${tStart} - ${tEnd}) overlaps with another run in this block (${otherStartStr} - ${otherEndStr}).\n\nPlease adjust the times so they do not intersect.`);
            return false; 
        }
    }

    return { start: tStart, end: tEnd };
}

function injectIoTCounts(iotCounts) {
    if (!iotCounts) return;

    hours.forEach((timeObj, hourIndex) => {
        const startHour = parseInt(timeObj.start.split(":")[0], 10);
        const autoCount = iotCounts[startHour];

        if (autoCount !== undefined) {
            const btn = document.getElementById(`btn_submit_${hourIndex}_0`);
            
            if (btn && !btn.innerText.includes("Saved")) {
                const shotsInput = document.getElementById(`shots_${hourIndex}_0`);
                
                if (shotsInput) {
                    let currentVal = parseInt(shotsInput.value) || 0;
                    let lastInjected = parseInt(shotsInput.dataset.lastIot) || 0;

                    if (currentVal === 0 || currentVal === lastInjected) {
                        shotsInput.value = autoCount;
                        shotsInput.dataset.lastIot = autoCount; 
                    }
                }
            }
        }
    });

    calculateTotals();
}

async function submitBlock(hourIndex, splitIndex) {
    let dateVal = document.getElementById("global_date").value;
    let shiftVal = document.getElementById("global_shift").value;
    let machine = document.getElementById("machine").value;
    
    const isNoPlan = document.getElementById(`no_plan_${hourIndex}_${splitIndex}`).checked;

    if (!machine) { alert("Machine is strictly required."); return; }

    let mould = document.getElementById("mould_code") ? document.getElementById("mould_code").value : "";
    let part = document.getElementById("part_number") ? document.getElementById("part_number").value : "";
    let operator = document.getElementById("operator") ? document.getElementById("operator").value : "";
    let supervisor = document.getElementById("supervisor") ? document.getElementById("supervisor").value : "";
    let internalBatchNum = document.getElementById("batchNo") ? document.getElementById("batchNo").value.trim() : "";
    
    // NEW SAFE CODE FOR PARAMETERS
    let tempEl = document.getElementById("global_temp");
    let pressEl = document.getElementById("global_pressure");
    let setEl = document.getElementById("global_setting");

    let gTemp = tempEl ? (tempEl.value || 0) : 0;
    let gPressure = pressEl ? (pressEl.value || 0) : 0;
    let gSetting = setEl ? (setEl.value || 0) : 0;

    if (!isNoPlan) {
        if (!mould || !part) { alert("Please ensure Mould and Part are selected."); return; }
        if (!internalBatchNum) { alert("Please enter a Batch Number."); return; }
        if (!operator || !supervisor) { alert("Please select an Operator and Supervisor."); return; }
        
        // Parameter check relaxed for moulding since they are automatically fetched via PLC usually, 
        // but if manual inputs still exist and are empty, alert.
        if ((tempEl && !gTemp) || (pressEl && !gPressure) || (setEl && !gSetting)) { 
            alert("Please enter Actual Temperature, Pressure, and Setting before submitting blocks."); return; 
        }

        let validMachines = Array.from(document.getElementById("machine_options").options).map(opt => opt.value);
        if (!validMachines.includes(machine)) { alert(`❌ INVALID MACHINE:\nThe machine "${machine}" is not recognized.`); return; }

        let validParts = Array.from(document.getElementById("part_options").options).map(opt => opt.value);
        if (!validParts.includes(part)) { alert(`❌ INVALID PART:\nThe planned part "${part}" is not recognized.`); return; }
    } else {
        part = part || "NO PLAN";
        mould = mould || "N/A";
        internalBatchNum = internalBatchNum || "N/A";
        operator = operator || "N/A";
        supervisor = supervisor || "N/A";
    }

    let generatedBatchId = `${dateVal}_${shiftVal}_${machine}_${mould}_${part}`;

    const isSplitMode = document.getElementById(`split_check_${hourIndex}`).checked;
    let finalStart = hours[hourIndex].start;
    let finalEnd = hours[hourIndex].end;

    if (isSplitMode || splitIndex > 0) {
        const timeCheck = validateTimeRange(hourIndex, splitIndex);
        if (!timeCheck) return;
        finalStart = timeCheck.start;
        finalEnd = timeCheck.end;
    }

    let targetShots = parseInt(document.getElementById(`target_${hourIndex}_${splitIndex}`).innerText) || 0;
    let actualShots = parseInt(document.getElementById(`shots_${hourIndex}_${splitIndex}`).value) || 0;
    let okParts = parseInt(document.getElementById(`ok_${hourIndex}_${splitIndex}`).innerText) || 0;
    let ngParts = parseInt(document.getElementById(`ng_total_${hourIndex}_${splitIndex}`).innerText) || 0;

    let missingShots = targetShots - actualShots;
    let loggedSf = blockShortfalls[hourIndex][splitIndex] ? blockShortfalls[hourIndex][splitIndex].reduce((s, r) => s + r.qty, 0) : 0;
    
    if (!isNoPlan && missingShots > 0 && loggedSf !== missingShots) {
        alert(`You are missing ${missingShots} shots. You have logged ${loggedSf} in the Shortfall Breakup. These must match.`); return;
    }

    let activeCavs = 1.0;
    if (mould && mouldMaster[mould]) {
        activeCavs = parseFloat(mouldMaster[mould].active_cavities) || 1.0;
    }

    const payload = {
        batch_id: generatedBatchId,
        internal_batch_number: internalBatchNum,
        production_date: dateVal,
        shift: shiftVal,
        start_time: finalStart,
        end_time: finalEnd,
        machine_code: machine,
        mould_code: mould,
        part_number: part,
        operator_code: operator,
        supervisor_code: supervisor,
        target_shots: targetShots,
        actual_shots: actualShots,
        active_cavities: activeCavs,
        ok_parts: okParts,
        ng_parts: ngParts,
        actual_temp: parseFloat(gTemp),
        actual_pressure: parseFloat(gPressure),
        actual_setting: parseFloat(gSetting),
        rejections: blockRejections[hourIndex][splitIndex] || [],
        shortfalls: blockShortfalls[hourIndex][splitIndex] || [],
        is_no_plan: isNoPlan 
    };

    const btn = document.getElementById(`btn_submit_${hourIndex}_${splitIndex}`);
    btn.innerText = "Saving...";
    btn.disabled = true;

    try {
        const response = await fetch('/api/submit_stage1_block', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || "Failed to save to database");
        }

        let noPlanCheck = document.getElementById(`no_plan_${hourIndex}_${splitIndex}`);
        if(noPlanCheck) noPlanCheck.disabled = true;
        
        document.getElementById(`time_start_${hourIndex}_${splitIndex}`).disabled = true;
        document.getElementById(`time_end_${hourIndex}_${splitIndex}`).disabled = true;
        document.getElementById(`shots_${hourIndex}_${splitIndex}`).disabled = true;
        document.getElementById(`sf_qty_${hourIndex}_${splitIndex}`).disabled = true;
        document.getElementById(`sf_reason_${hourIndex}_${splitIndex}`).disabled = true;
        document.getElementById(`btn_add_sf_${hourIndex}_${splitIndex}`).disabled = true;
        document.getElementById(`rej_qty_${hourIndex}_${splitIndex}`).disabled = true;
        document.getElementById(`rej_reason_${hourIndex}_${splitIndex}`).disabled = true;
        document.getElementById(`btn_add_rej_${hourIndex}_${splitIndex}`).disabled = true;

        if (blockShortfalls[hourIndex][splitIndex]) blockShortfalls[hourIndex][splitIndex].forEach((_, i) => { let rmBtn = document.getElementById(`rm_sf_${hourIndex}_${splitIndex}_${i}`); if (rmBtn) rmBtn.style.display = 'none'; });
        if (blockRejections[hourIndex][splitIndex]) blockRejections[hourIndex][splitIndex].forEach((_, i) => { let rmBtn = document.getElementById(`rm_rej_${hourIndex}_${splitIndex}_${i}`); if (rmBtn) rmBtn.style.display = 'none'; });

        const saveTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        
        if (isNoPlan) {
            btn.style.background = "var(--status-yellow)";
            btn.innerText = `No Plan Logged ✓ at ${saveTime}`;
        } else {
            btn.style.background = "var(--status-green)";
            btn.innerText = `Saved ✓ at ${saveTime}`;
        }
        
        btn.style.color = "black";
        btn.style.border = "none";
        updateTabStatus(hourIndex);

        const rmBtn = btn.parentElement.querySelector('.btn-remove-split');
        if (rmBtn) rmBtn.style.display = 'none';

    } catch (error) {
        console.error("Submission Error:", error);
        alert("Error saving run: " + error.message);
        btn.innerText = isNoPlan ? "Submit (No Plan)" : "Submit Run";
        btn.disabled = false;
    }
}

async function finalizeBatch() {
    let overrideBox = document.getElementById("part_change_override");
    let isOverrideChecked = overrideBox ? overrideBox.checked : false;

    let savedWrappersCount = 0;
    for (let i = 0; i < hours.length; i++) {
        let hasSavedRun = false;
        for (let j = 0; j < splitCounts[i]; j++) {
            let btn = document.getElementById(`btn_submit_${i}_${j}`);
            if (btn && btn.innerText.includes("Saved")) {
                hasSavedRun = true;
                break;
            }
        }
        if (hasSavedRun) savedWrappersCount++;
    }

    if (!isOverrideChecked && savedWrappersCount < hours.length) {
        alert(`❌ VALIDATION FAILED:\nYou have only submitted production data for ${savedWrappersCount} out of 12 hours.\n\nYou must have at least one saved run in all 12 hours to close the shift. If you are finalizing early to start a new part, please check the "Part Change Finalization" box.`);
        return;
    }

    let confirmMessage = "Are you sure you want to Finalize this batch?\n\nThis will close the production run and lock the shift. This action cannot be undone.";

    if (!confirm(confirmMessage)) return;

    let totalActual = parseInt(document.getElementById("grand-actual").innerText) || 0;
    if (totalActual === 0) { alert("You cannot generate a batch with 0 production."); return; }

    let operatorCode = document.getElementById("operator").value;
    if (!operatorCode) { alert("Please select an Operator before finalizing."); return; }

    let dateVal = document.getElementById("global_date").value;
    let shiftVal = document.getElementById("global_shift").value;
    let machine = document.getElementById("machine").value;
    let mould = document.getElementById("mould_code").value;
    let part = document.getElementById("part_number").value;

    let generatedBatchId = `${dateVal}_${shiftVal}_${machine}_${mould}_${part}`;

    let okParts = parseInt(document.getElementById("grand-ok").innerText) || 0;
    let ngParts = parseInt(document.getElementById("grand-ng").innerText) || 0;

    let remarksInput = document.getElementById("batch_remarks");
    let shiftRemarks = remarksInput ? remarksInput.value.trim() : "";

    const selectedMachine = machineList.find(m => m.code === machine);
    const actualProcess = selectedMachine ? selectedMachine.process : "Unknown Process";

    let finalizeBtn = document.getElementById("btn_finalize");
    let originalText = finalizeBtn.innerText;
    finalizeBtn.innerText = "Processing...";
    finalizeBtn.disabled = true;

    const payload = {
        batch_id: generatedBatchId,
        sequence_no: 1,
        process_name: actualProcess,
        input_qty: 0,
        ok_qty: okParts,
        ng_qty: ngParts,
        emp_code: operatorCode,
        is_outsourced: false,
        fg_part_number: part,
        remarks: shiftRemarks
    };

    try {
        const response = await fetch('/api/finalize_batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Failed to finalize batch.");
        }

        document.getElementById("binOutput").innerText = `✅ Success! Shift Lot ${generatedBatchId} tracked successfully.`;
        finalizeBtn.style.background = "var(--status-green)";
        finalizeBtn.style.color = "black";
        finalizeBtn.innerText = "Batch Finalized Successfully";

    } catch (error) {
        console.error("Finalize Error:", error);
        alert(error.message);
        finalizeBtn.innerText = originalText;
        finalizeBtn.disabled = false;
    }
}

function applyRestoredLogs(isFinalized = false) {
    let dateVal = document.getElementById("global_date").value;
    if (!currentBatchLogs[dateVal]) return;

    hours.forEach((timeObj, hourIndex) => {
        const logsForThisHour = [];
        for (const [logStartTime, logArray] of Object.entries(currentBatchLogs[dateVal])) {
            if (logStartTime.substring(0, 2) === timeObj.start.substring(0, 2)) {
                logsForThisHour.push(...logArray);
            }
        }

        if (logsForThisHour.length > 0) {
            logsForThisHour.sort((a, b) => a.start_time.localeCompare(b.start_time));

            if (logsForThisHour.length > 1) {
                document.getElementById(`split_check_${hourIndex}`).checked = true;
                toggleSplitMode(hourIndex);
            }

            logsForThisHour.forEach((log, logIdx) => {
                if (logIdx >= splitCounts[hourIndex]) {
                    addSplitCard(hourIndex, log.start_time, log.end_time, false);
                }

                const btn = document.getElementById(`btn_submit_${hourIndex}_${logIdx}`);
                const shotsInput = document.getElementById(`shots_${hourIndex}_${logIdx}`);
                const noPlanCheck = document.getElementById(`no_plan_${hourIndex}_${logIdx}`);

                if (noPlanCheck) {
                    noPlanCheck.checked = !!log.is_no_plan;
                    noPlanCheck.disabled = true;
                }

                const targetEl = document.getElementById(`target_${hourIndex}_${logIdx}`);
                if (targetEl) targetEl.innerText = log.target_shots;

                const tStartEl = document.getElementById(`time_start_${hourIndex}_${logIdx}`);
                const tEndEl = document.getElementById(`time_end_${hourIndex}_${logIdx}`);
                if (tStartEl) tStartEl.value = log.start_time;
                if (tEndEl) tEndEl.value = log.end_time;

                if (shotsInput) shotsInput.value = log.actual_shots;
                const okEl = document.getElementById(`ok_${hourIndex}_${logIdx}`);
                if (okEl) okEl.innerText = `${log.ok_parts} pcs`;
                const ngEl = document.getElementById(`ng_total_${hourIndex}_${logIdx}`);
                if (ngEl) ngEl.innerText = log.ng_parts;

                if (log.rejections && log.rejections.length > 0) {
                    blockRejections[hourIndex][logIdx] = log.rejections.map(r => ({ reason: r.reason, qty: r.qty }));
                    renderRejectionList(hourIndex, logIdx);
                }

                if (log.shortfalls && log.shortfalls.length > 0) {
                    blockShortfalls[hourIndex][logIdx] = log.shortfalls.map(s => ({ reason: s.reason, qty: s.qty }));
                    renderShortfallList(hourIndex, logIdx);
                }

                if (tStartEl) tStartEl.disabled = true;
                if (tEndEl) tEndEl.disabled = true;
                if (shotsInput) shotsInput.disabled = true;
                const sfQty = document.getElementById(`sf_qty_${hourIndex}_${logIdx}`);
                const sfReason = document.getElementById(`sf_reason_${hourIndex}_${logIdx}`);
                const btnAddSf = document.getElementById(`btn_add_sf_${hourIndex}_${logIdx}`);
                const rejQty = document.getElementById(`rej_qty_${hourIndex}_${logIdx}`);
                const rejReason = document.getElementById(`rej_reason_${hourIndex}_${logIdx}`);
                const btnAddRej = document.getElementById(`btn_add_rej_${hourIndex}_${logIdx}`);

                if (sfQty) sfQty.disabled = true;
                if (sfReason) sfReason.disabled = true;
                if (btnAddSf) btnAddSf.disabled = true;
                if (rejQty) rejQty.disabled = true;
                if (rejReason) rejReason.disabled = true;
                if (btnAddRej) btnAddRej.disabled = true;

                if (btn) {
                    if (log.is_no_plan) {
                        btn.style.background = "var(--status-yellow)";
                        btn.innerText = `Idle Time Logged ✓ at ${log.created_at}`;
                    } else {
                        btn.style.background = "var(--status-green)";
                        btn.innerText = `Saved ✓ at ${log.created_at}`;
                    }
                    btn.style.color = "black";
                    btn.style.border = "none";
                    btn.disabled = true;

                    const rmBtn = btn.parentElement && btn.parentElement.querySelector('.btn-remove-split');
                    if (rmBtn) rmBtn.style.display = 'none';
                }
            });

        } else if (isFinalized) {
            let shotsEl = document.getElementById(`shots_${hourIndex}_0`);
            if (shotsEl) shotsEl.disabled = true;
            let sfQtyEl = document.getElementById(`sf_qty_${hourIndex}_0`);
            if (sfQtyEl) sfQtyEl.disabled = true;
            let sfReasonEl = document.getElementById(`sf_reason_${hourIndex}_0`);
            if (sfReasonEl) sfReasonEl.disabled = true;
            let addSfEl = document.getElementById(`btn_add_sf_${hourIndex}_0`);
            if (addSfEl) addSfEl.disabled = true;
            let rejQtyEl = document.getElementById(`rej_qty_${hourIndex}_0`);
            if (rejQtyEl) rejQtyEl.disabled = true;
            let rejReasonEl = document.getElementById(`rej_reason_${hourIndex}_0`);
            if (rejReasonEl) rejReasonEl.disabled = true;
            let addRejEl = document.getElementById(`btn_add_rej_${hourIndex}_0`);
            if (addRejEl) addRejEl.disabled = true;
            let splitCheckEl = document.getElementById(`split_check_${hourIndex}`);
            if (splitCheckEl) splitCheckEl.disabled = true;

            const btn = document.getElementById(`btn_submit_${hourIndex}_0`);
            if (btn) {
                btn.style.background = "var(--border-color)";
                btn.style.color = "var(--text-muted)";
                btn.style.border = "none";
                btn.innerText = "🔒 Locked";
                btn.disabled = true;
            }
        }
    });
    for (let i = 0; i < hours.length; i++) {
        updateTabStatus(i);
    }
    calculateTotals();
    enforceTimeLocks();
}

// ==========================================
// PAGE INITIALIZATION & BOOTSTRAP
// ==========================================
window.onload = async () => {
    const now = new Date();
    let logicalDate = new Date(now);
    let currentShift = "A";

    const currentHour = now.getHours(); // Returns 0-23

    // 🚨 SMART LOGICAL SHIFT CALCULATION 🚨
    if (currentHour >= 0 && currentHour < 7) {
        // Between Midnight and 7 AM: The logical shift belongs to YESTERDAY'S Shift B.
        logicalDate.setDate(logicalDate.getDate() - 1);
        currentShift = "B";
    } 
    else if (currentHour >= 19) {
        // Between 7 PM and Midnight: The logical shift is TODAY'S Shift B.
        currentShift = "B";
    } 
    else {
        // Between 7 AM and 7 PM: The logical shift is TODAY'S Shift A.
        currentShift = "A";
    }

    // Format the date string properly avoiding timezone shifting bugs
    const offsetDate = new Date(logicalDate.getTime() - (logicalDate.getTimezoneOffset() * 60000));
    const logicalDateStr = offsetDate.toISOString().split('T')[0];
    
    const dateInput = document.getElementById("global_date");
    const shiftInput = document.getElementById("global_shift");

    if (dateInput) dateInput.value = logicalDateStr;
    if (shiftInput) shiftInput.value = currentShift;

    // 2. Fetch the Master Data (This will automatically trigger renderAllHourBlocks inside it)
    await fetchMasterData();

    // 3. Fallback render just to ensure the UI paints immediately
    renderAllHourBlocks();

    // 4. Handle URL parameters (if redirecting from a hub)
    const urlParams = new URLSearchParams(window.location.search);
    const urlMachine = urlParams.get('machine');
    const urlDate = urlParams.get('date');
    const urlShift = urlParams.get('shift');

    if (urlMachine && urlDate && urlShift) {
        let machineSelect = document.getElementById("machine");
        
        if (machineSelect) machineSelect.value = urlMachine;
        if (dateInput) dateInput.value = urlDate;
        if (shiftInput) shiftInput.value = urlShift;
        
        checkActiveMachineState();
    }
};