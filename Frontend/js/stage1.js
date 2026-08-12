// --- RUNTIME STATE (Dynamic Master Data) ---
let partMaster = {};
let mouldMaster = {};
let rejectionCodes = [];
let shortfallCodes = [];
let currentBatchLogs = {};
let machineList = [];

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

// Global Logout Function
function logout() {
    localStorage.clear();
    window.location.href = "/";
}
// ==========================================

// --- UPDATE YOUR EXISTING fetchMasterData() ---
async function fetchMasterData() {
    try {
        const response = await fetch('/init_stage1');
        if (!response.ok) throw new Error("Failed to fetch master data");
        const data = await response.json();

        partMaster = data.parts;
        mouldMaster = data.moulds;
        rejectionCodes = data.rejections;
        shortfallCodes = data.shortfalls;
        machineList = data.machines; // Store the raw data

        // NEW: Populate generic dropdowns
        populateDropdown("part_number", Object.keys(data.parts));
        populateDropdown("operator", data.operators);
        populateDropdown("supervisor", data.supervisors);

        // NEW: Trigger the filter logic to initialize the machine list
        selectProcess(currentActiveProcess);

        document.getElementById("machine").addEventListener("change", checkActiveMachineState);
        document.getElementById("machine").addEventListener("change", handleMachineSelection);
        document.getElementById("global_date").addEventListener("change", checkActiveMachineState);
        document.getElementById("global_shift").addEventListener("change", checkActiveMachineState);
        document.getElementById("part_number").addEventListener("change", filterMoldsByPart);
        document.getElementById("mould_code").addEventListener("change", fetchMoldTargets);
        renderAllHourBlocks();

    } catch (error) {
        console.error("Error loading master data:", error);
        alert("Error loading system data. Please refresh the page.");
    }
}

// --- NEW: DYNAMIC PROCESS SWITCHER ---
let currentActiveProcess = "THERMOWELDING"; // Default on page load

function selectProcess(processName) {
    currentActiveProcess = processName;

    // 1. Update Button Highlights visually
    const buttons = document.querySelectorAll('.process-btn');
    buttons.forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.process === processName) {
            btn.classList.add('active');
            // Auto-scroll the active button into view
            const container = document.getElementById('process_tabs');
            const scrollPos = btn.offsetLeft - (container.offsetWidth / 2) + (btn.offsetWidth / 2);
            container.scrollTo({ left: scrollPos, behavior: 'smooth' });
        }
    });

    // 2. Filter the machine list strictly for this process
    // Note: Assuming your API returns it as 'process', change to 'machine_process' if needed based on your backend
    let filteredMachines = machineList.filter(m => m.process === processName || m.machine_process === processName);
    
    // 3. Update the dropdown datalist
    let machineCodes = filteredMachines.map(m => m.code || m.machine_code); 
    populateDropdown("machine", machineCodes);

    // 4. Wipe the current screen so the operator doesn't mix data
    document.getElementById("machine").value = "";
    wipeScreenForNewMachine();
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

// 🚨 NEW: Handles filtering parts and locking the mould when machine changes
function handleMachineSelection() {
    const selectedCode = document.getElementById("machine").value; 
    const mouldDropdown = document.getElementById("mould_code"); 
    const partDropdown = document.getElementById("part_number"); 
    
    // Find the selected machine object in our saved list
    const selectedMachine = machineList.find(m => m.code === selectedCode);
    const processName = selectedMachine ? selectedMachine.process : "";

    // 🚨 SMART FILTER: Only show parts that have this machine's process in their routing!
    let validParts = [];
    if (processName) {
        validParts = Object.keys(partMaster).filter(partNo => {
            return partMaster[partNo].valid_processes && partMaster[partNo].valid_processes.includes(processName);
        });
    } else {
        validParts = Object.keys(partMaster);
    }
    
    // Update the Datalist
    populateDropdown("part_number", validParts);
    
    // Clear the current part to force the operator to pick a valid one from the new list
    partDropdown.value = "";

    // 🚨 UPDATED: Define processes that use a mold/cavity calculation
    const allowedMoldProcesses = ["MOULDING", "PRESS CUT", "THERMOWELDING"];

    // Mould Locking Logic
    if (allowedMoldProcesses.includes(processName)) {
        mouldDropdown.disabled = false;
        if (mouldDropdown.value === "-") mouldDropdown.value = ""; 
    } else {
        mouldDropdown.disabled = true;
        mouldDropdown.value = "-"; 
    }
    
    // Trigger the UI reset
    filterMoldsByPart();
}

// 🚨 UPDATED: Only manages the cascading dropdown options now
function filterMoldsByPart() {
    const partSelect = document.getElementById("part_number");
    const moldSelect = document.getElementById("mould_code");
    const machineSelect = document.getElementById("machine"); 
    
    const selectedPart = partSelect.value;
    const selectedMachineCode = machineSelect.value;
    
    const selectedMachine = machineList.find(m => m.code === selectedMachineCode);
    const machineProcess = selectedMachine ? selectedMachine.process : "";

    // Save current mold to re-apply it if it's still valid
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

    // Auto-select logic
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

// 🚨 UPDATED: Fetches Hourly Target AND Parameters (Temp, Pressure, Setting) mapped to the Mold
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

    // SCENARIO 1: Look in the Part Master specifically for this exact Mold
    if (partSelect && partMaster[partSelect] && partMaster[partSelect].targets && partMaster[partSelect].targets[machineProcess]) {
        
        const processTargets = partMaster[partSelect].targets[machineProcess];
        
        // Dig into the specific mold dictionary!
        if (processTargets[selectedMold]) {
            const exactTargets = processTargets[selectedMold];
            finalTarget = exactTargets.tgtHourly || 0; 
            
            tTemp = exactTargets.tgtTemp || "";
            tPress = exactTargets.tgtPressure || "";
            tSet = exactTargets.tgtSetting || "";
        }
    }

    // SCENARIO 2: Fallback to Generic Mould Master for Hourly Shots if missing
    if (finalTarget === 0 && selectedMold && selectedMold !== "-" && mouldMaster[selectedMold]) {
        finalTarget = mouldMaster[selectedMold].hourlyShots || 0;
    }

    // --- APPLY TO UI ---
    
    // 1. Hourly Target
    if (targetInput) targetInput.value = finalTarget;
    
    // 2. Target Labels
    const lblTemp = document.getElementById("tgt_temp");
    const lblPress = document.getElementById("tgt_pressure");
    const lblSet = document.getElementById("tgt_setting");
    if (lblTemp) lblTemp.innerText = tTemp || "-";
    if (lblPress) lblPress.innerText = tPress || "-";
    if (lblSet) lblSet.innerText = tSet || "-";

    // 3. Auto-Fill Input Fields
    if (tempInput && tTemp) tempInput.value = tTemp;
    if (pressureInput && tPress) pressureInput.value = tPress;
    if (settingInput && tSet) settingInput.value = tSet;

    updateAllHourBlocks();
}

// --- BUILD DYNAMIC TABS, WRAPPERS & CARDS ---
function renderAllHourBlocks() {
    const grid = document.getElementById("hourly-grid");
    const tabsContainer = document.getElementById("hourly-tabs");

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

        // 1. Build the Tab
        const tab = document.createElement("div");
        tab.className = `hour-tab ${hourIndex === 0 ? 'active' : ''}`;
        tab.id = `tab_${hourIndex}`;
        tab.onclick = () => switchTab(hourIndex);
        tab.innerHTML = `
            <span class="tab-time">${timeObj.start} - ${timeObj.end}</span>
            <span class="tab-status" id="tab_status_${hourIndex}" style="color: var(--status-yellow);">Unsaved (60m left)</span>
        `;
        tabsContainer.appendChild(tab);

        // 2. Build the Wrapper (Only the first one is visible initially)
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

// 🚨 NEW: Logic to switch between tabs
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

// 🚨 UPDATED: Now recognizes "Logged" (No Plan) and "Saved" correctly
function updateTabStatus(hourIndex) {
    let totalSavedMinutes = 0;
    let lastSaveTime = "";
    let isNoPlanTab = false;

    for (let j = 0; j < splitCounts[hourIndex]; j++) {
        let btn = document.getElementById(`btn_submit_${hourIndex}_${j}`);

        // Count the minutes if this specific split is "Saved" OR "Logged" (No Plan)
        if (btn && (btn.innerText.includes("Saved") || btn.innerText.includes("Logged"))) {
            let tStart = document.getElementById(`time_start_${hourIndex}_${j}`).value;
            let tEnd = document.getElementById(`time_end_${hourIndex}_${j}`).value;

            let startMins = (parseInt(tStart.split(':')[0]) * 60) + parseInt(tStart.split(':')[1]);
            let endMins = (parseInt(tEnd.split(':')[0]) * 60) + parseInt(tEnd.split(':')[1]);
            if (endMins < startMins) endMins += (24 * 60); // Handle overnight shifts

            totalSavedMinutes += (endMins - startMins);

            // Extract the timestamp from "Saved ✓ at 10:25 AM" or "Logged ✓ at 10:25 AM"
            let parts = btn.innerText.split('at ');
            if (parts.length > 1) lastSaveTime = parts[1];

            // Flag if this block contains No Plan data
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
    
    // If Admin, they have god-mode. Do not lock anything.
    if (role === "Admin") return;

    const now = new Date();
    const currentHour = now.getHours(); // 0-23
    const globalDate = document.getElementById("global_date").value;
    const todayDate = new Date(now.getTime() - (now.getTimezoneOffset() * 60000)).toISOString().split('T')[0];

    hours.forEach((timeObj, index) => {
        const blockStartHour = parseInt(timeObj.start.split(":")[0]);
        
        let isLocked = false;

        // Rule 1: If they are looking at a past or future DATE, lock everything for Operators
        if (globalDate !== todayDate) {
            isLocked = true;
        } 
        else {
            // Rule 2: Operator Time Window Logic
            // Allow them to edit the CURRENT hour, and the PREVIOUS hour.
            // Example: If it's 15:30, currentHour is 15. They can edit 15:00-16:00 and 14:00-15:00.
            
            // Calculate the difference between the current real-world hour and the block's start hour
            let hourDifference = currentHour - blockStartHour;
            
            // Handle midnight crossover for Shift B (e.g., Current hour 1 AM (1), Block start 23 PM (23))
            if (hourDifference < -12) hourDifference += 24; 
            if (hourDifference > 12) hourDifference -= 24;

            // Lock if the block is more than 1 hour in the past, OR if it's in the future
            if (hourDifference > 1 || hourDifference < 0) {
                isLocked = true;
            }
        }

        // Apply the lock to the UI
        if (isLocked) {
            for (let j = 0; j < splitCounts[index]; j++) {
                let btn = document.getElementById(`btn_submit_${index}_${j}`);
                
                // If it's already saved, leave it alone. If it's unsaved, lock it down.
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
        updateSplitTarget(hourIndex, 0); // Trigger proportional math
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
        updateSplitTarget(hourIndex, 0); // Reset target
    }
}

function addSplitCard(hourIndex, defaultStart = "", defaultEnd = "", canRemove = true) {
    const container = document.getElementById(`sub_blocks_container_${hourIndex}`);
    const splitIndex = splitCounts[hourIndex];

    blockRejections[hourIndex][splitIndex] = [];
    blockShortfalls[hourIndex][splitIndex] = [];

    let currentTarget = document.getElementById("hourlyTargetShots").value || 0;

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
                <input type="number" id="shots_${hourIndex}_${splitIndex}" value="" min="0" oninput="calculateTotals()" style="color: var(--status-yellow); font-weight:bold; font-size: 18px;">
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

// 🚨 NEW PROPORTIONAL TARGET MATH LOGIC
function updateSplitTarget(hourIndex, splitIndex) {
    let tStart = document.getElementById(`time_start_${hourIndex}_${splitIndex}`).value;
    let tEnd = document.getElementById(`time_end_${hourIndex}_${splitIndex}`).value;
    let globalTarget = parseInt(document.getElementById("hourlyTargetShots").value) || 0;

    let targetEl = document.getElementById(`target_${hourIndex}_${splitIndex}`);
    if (!targetEl) return;

    // If split mode is off, just give them the full target
    const isSplitMode = document.getElementById(`split_check_${hourIndex}`).checked;
    if (!isSplitMode && splitIndex === 0) {
        targetEl.innerText = globalTarget;
        calculateTotals();
        return;
    }

    // If inputs are empty, default to full hour target
    if (!tStart || !tEnd) {
        targetEl.innerText = globalTarget;
        calculateTotals();
        return;
    }

    const startMinutes = (parseInt(tStart.split(':')[0]) * 60) + parseInt(tStart.split(':')[1]);
    let endMinutes = (parseInt(tEnd.split(':')[0]) * 60) + parseInt(tEnd.split(':')[1]);

    if (endMinutes < startMinutes) endMinutes += (24 * 60);

    let duration = endMinutes - startMinutes;

    // Calculate Proportional Math
    if (duration <= 0 || duration > 60) {
        targetEl.innerText = globalTarget; // Fallback if they enter weird times
    } else {
        let proportionalTarget = Math.round((duration / 60) * globalTarget);
        targetEl.innerText = proportionalTarget;
    }
    calculateTotals();
}

// 🚨 NEW: Toggles the fields and zeros them out when "No Plan" is checked
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
        updateSplitTarget(hourIndex, splitIndex); // Restores original target
    }
    calculateTotals();
}

// 🚨 UPDATED: Global No Plan Toggle with Auto-Submit
async function toggleGlobalNoPlan() {
    const globalCheckbox = document.getElementById("global_no_plan_check");
    const isGlobalNoPlan = globalCheckbox.checked;

    // SCENARIO 1: Turning it OFF
    if (!isGlobalNoPlan) {
        // Just uncheck the boxes and restore fields for unlocked blocks
        for (let i = 0; i < hours.length; i++) {
            for (let j = 0; j < splitCounts[i]; j++) {
                const btn = document.getElementById(`btn_submit_${i}_${j}`);
                const noPlanCheck = document.getElementById(`no_plan_${i}_${j}`);

                // Ignore blocks that are already saved or locked by time rules
                if (btn && !btn.innerText.includes("Saved") && !btn.innerText.includes("Logged") && !btn.innerText.includes("Locked")) {
                    if (noPlanCheck && noPlanCheck.checked) {
                        noPlanCheck.checked = false;
                        toggleNoPlan(i, j); // Restores your standard targets & inputs
                    }
                }
            }
        }
        return;
    }

    // SCENARIO 2: Turning it ON (The Auto-Submit Logic)
    let submittedCount = 0;
    let remainingBlocks = [];

    // Figure out how many hours are done, and queue up the remaining ones
    for (let i = 0; i < hours.length; i++) {
        let hourHasSaved = false;
        for (let j = 0; j < splitCounts[i]; j++) {
            const btn = document.getElementById(`btn_submit_${i}_${j}`);
            
            if (btn) {
                if (btn.innerText.includes("Saved") || btn.innerText.includes("Logged")) {
                    hourHasSaved = true;
                } else if (!btn.innerText.includes("Locked")) {
                    // It's unlocked and unsaved, add it to our submission queue
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

    // Trigger the Confirmation Popup
    const confirmMsg = `Only ${submittedCount} hour blocks are submitted. Are you sure you want to submit the remaining ${remainingHours} hours as No Plan?`;
    
    if (!confirm(confirmMsg)) {
        // User clicked "No" - Revert the toggle
        globalCheckbox.checked = false;
        return;
    }

    // User clicked "Yes" - Process and submit all remaining blocks sequentially
    globalCheckbox.disabled = true; // Prevent them from clicking it again while saving

    for (const block of remainingBlocks) {
        const { i, j } = block;
        const noPlanCheck = document.getElementById(`no_plan_${i}_${j}`);
        
        // 1. Check the box to trigger UI changes and zero out fields
        if (noPlanCheck && !noPlanCheck.checked) {
            noPlanCheck.checked = true;
            toggleNoPlan(i, j);
        }
        
        // 2. Await the actual database submission using your existing secure function
        await submitBlock(i, j);
    }

    globalCheckbox.disabled = false;
    alert("✅ All remaining hours have been successfully submitted as No Plan.");
}

// --- SHORTFALL BREAKUP LOGIC ---
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

// --- REJECTION BREAKUP LOGIC ---
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

// --- PART CHANGE LOGIC ---
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
        // 🚨 FIX 1: Unlock the Hourly Split checkbox for every block
        let splitCheck = document.getElementById(`split_check_${i}`);
        if (splitCheck) splitCheck.disabled = false;

        for (let j = 0; j < splitCounts[i]; j++) {
            let btn = document.getElementById(`btn_submit_${i}_${j}`);
            if (!btn) continue;

            if (!btn.innerText.includes("Saved")) {
                let shotsInput = document.getElementById(`shots_${i}_${j}`);
                shotsInput.disabled = false;
                shotsInput.value = 0;

                // 🚨 FIX 2: Unlock the time inputs so operators can edit the split times!
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

// --- ACTIVE MACHINE STATE LOGIC ---
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
                
                // 1. Build the Mould dropdown options FIRST
                filterMoldsByPart();

                setTimeout(() => {
                    // 2. NOW set the value of the newly built dropdown
                    document.getElementById("mould_code").value = logData.setup.mould_code || "";
                    document.getElementById("operator").value = logData.setup.operator_code || "";
                    document.getElementById("supervisor").value = logData.setup.supervisor_code || "";

                    // 3. Fetch Targets directly
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
                    
                    // 1. Build the Mould dropdown options FIRST
                    filterMoldsByPart(); 

                    setTimeout(() => {
                        // 2. NOW set the value of the newly built dropdown
                        document.getElementById("mould_code").value = logData.last_known_setup.mould_code || "";
                        document.getElementById("operator").value = logData.last_known_setup.operator_code || "";
                        document.getElementById("supervisor").value = logData.last_known_setup.supervisor_code || "";
                        
                        // 3. Fetch Targets directly
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

    document.getElementById("hourlyTargetShots").value = 0;

    currentBatchLogs = {};
    renderAllHourBlocks();

    if (document.getElementById("batch_remarks")) document.getElementById("batch_remarks").value = "";
    if (document.getElementById("part_change_override")) document.getElementById("part_change_override").checked = false;
}

// 🚨 FIXED: Now ignores saved blocks so old splits don't get their targets overwritten!
function updateAllHourBlocks() {
    for (let i = 0; i < hours.length; i++) {
        for (let j = 0; j < splitCounts[i]; j++) {
            let btn = document.getElementById(`btn_submit_${i}_${j}`);
            if (btn && btn.innerText.includes("Saved")) continue; // DO NOT TOUCH SAVED BLOCKS!

            updateSplitTarget(i, j);
        }
    }
}

// --- CALCULATION LOGIC ---
function calculateTotals() {
    let mouldKey = document.getElementById("mould_code").value;
    let cavityCount = 1.0; // Default to float 1.0
    
    if (mouldKey && mouldMaster[mouldKey]) {
        // 🚨 FIX 1: Use parseFloat instead of implicitly assuming an integer
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
            
            // 🚨 FIX 2: This will now properly calculate fractions (e.g., 50 * 0.5 = 25)
            let totalProducedParts = actualShots * cavityCount;
            let okParts = totalProducedParts - ngParts;
            if (okParts < 0) okParts = 0;

            // 🚨 FIX 3: Round the display outputs to keep clean whole numbers on screen
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

// --- TIME VALIDATION LOGIC ---
function validateTimeRange(hourIndex, splitIndex) {
    let tStart = document.getElementById(`time_start_${hourIndex}_${splitIndex}`).value;
    let tEnd = document.getElementById(`time_end_${hourIndex}_${splitIndex}`).value;

    if (!tStart || !tEnd) {
        alert("Please select both a Start Time and an End Time for this split.");
        return false;
    }

    // 1. Convert everything to minutes for easy math
    const startMinutes = (parseInt(tStart.split(':')[0]) * 60) + parseInt(tStart.split(':')[1]);
    const endMinutes = (parseInt(tEnd.split(':')[0]) * 60) + parseInt(tEnd.split(':')[1]);
    const blockStartLimit = (parseInt(hours[hourIndex].start.split(':')[0]) * 60) + parseInt(hours[hourIndex].start.split(':')[1]);

    let blockEndLimit = (parseInt(hours[hourIndex].end.split(':')[0]) * 60) + parseInt(hours[hourIndex].end.split(':')[1]);
    if (blockEndLimit < blockStartLimit) blockEndLimit += (24 * 60);

    let adjustedStart = startMinutes;
    let adjustedEnd = endMinutes;
    if (adjustedStart < blockStartLimit) adjustedStart += (24 * 60);
    if (adjustedEnd < blockStartLimit) adjustedEnd += (24 * 60);

    // 2. Standard Logic Checks
    if (adjustedStart >= adjustedEnd) {
        alert("End time must be after the start time.");
        return false;
    }

    if (adjustedStart < blockStartLimit || adjustedEnd > blockEndLimit) {
        alert(`Time must be within the bounds of this hour block (${hours[hourIndex].start} to ${hours[hourIndex].end}).`);
        return false;
    }

    // 🚨 3. NEW: The Overlap Checker 🚨
    for (let j = 0; j < splitCounts[hourIndex]; j++) {
        if (j === splitIndex) continue; // Don't check the current card against itself!

        let otherStartStr = document.getElementById(`time_start_${hourIndex}_${j}`).value;
        let otherEndStr = document.getElementById(`time_end_${hourIndex}_${j}`).value;

        // Skip if the other card hasn't been filled out yet
        if (!otherStartStr || !otherEndStr) continue;

        let oStart = (parseInt(otherStartStr.split(':')[0]) * 60) + parseInt(otherStartStr.split(':')[1]);
        let oEnd = (parseInt(otherEndStr.split(':')[0]) * 60) + parseInt(otherEndStr.split(':')[1]);

        if (oEnd < oStart) oEnd += (24 * 60);
        if (oStart < blockStartLimit) oStart += (24 * 60);
        if (oEnd < blockStartLimit) oEnd += (24 * 60);

        // The Overlap Math: (NewStart < OldEnd) AND (NewEnd > OldStart)
        if (adjustedStart < oEnd && adjustedEnd > oStart) {
            alert(`⚠️ OVERLAP DETECTED:\nYour selected time (${tStart} - ${tEnd}) overlaps with another run in this block (${otherStartStr} - ${otherEndStr}).\n\nPlease adjust the times so they do not intersect.`);
            return false; // Blocks the submission!
        }
    }

    return { start: tStart, end: tEnd };
}

// 🚨 UPDATED: Now safely updates numbers on the fly without wiping manual edits!
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

                    // Update if it's 0, OR if it's exactly what we injected 15 seconds ago
                    if (currentVal === 0 || currentVal === lastInjected) {
                        shotsInput.value = autoCount;
                        shotsInput.dataset.lastIot = autoCount; // Memorize this new number!
                    }
                }
            }
        }
    });

    calculateTotals();
}

// --- SUBMISSION ACTIONS ---
async function submitBlock(hourIndex, splitIndex) {
    let dateVal = document.getElementById("global_date").value;
    let shiftVal = document.getElementById("global_shift").value;
    let machine = document.getElementById("machine").value;
    
    // Read the No Plan Status
    const isNoPlan = document.getElementById(`no_plan_${hourIndex}_${splitIndex}`).checked;

    if (!machine) { alert("Machine is strictly required."); return; }

    // Setup variables
    let mould = document.getElementById("mould_code").value || "";
    let part = document.getElementById("part_number").value || "";
    let operator = document.getElementById("operator").value || "";
    let supervisor = document.getElementById("supervisor").value || "";
    let internalBatchNum = document.getElementById("batchNo").value.trim() || "";
    let gTemp = document.getElementById("global_temp").value || 0;
    let gPressure = document.getElementById("global_pressure").value || 0;
    let gSetting = document.getElementById("global_setting").value || 0;

    // 🚨 NEW: Validation Bypass Logic
    if (!isNoPlan) {
        if (!mould || !part) { alert("Please ensure Mould and Part are selected."); return; }
        if (!internalBatchNum) { alert("Please enter a Batch Number."); return; }
        if (!operator || !supervisor) { alert("Please select an Operator and Supervisor."); return; }
        if (!gTemp || !gPressure || !gSetting) { alert("Please enter Actual Temperature, Pressure, and Setting before submitting blocks."); return; }

        let validMachines = Array.from(document.getElementById("machine_options").options).map(opt => opt.value);
        if (!validMachines.includes(machine)) { alert(`❌ INVALID MACHINE:\nThe machine "${machine}" is not recognized.`); return; }

        let validParts = Array.from(document.getElementById("part_options").options).map(opt => opt.value);
        if (!validParts.includes(part)) { alert(`❌ INVALID PART:\nThe planned part "${part}" is not recognized.`); return; }
    } else {
        // Fill empty fields with dummy data for No Plan so the database doesn't crash
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
    
    // Only enforce shortfall matching if it's not a No Plan block
    if (!isNoPlan && missingShots > 0 && loggedSf !== missingShots) {
        alert(`You are missing ${missingShots} shots. You have logged ${loggedSf} in the Shortfall Breakup. These must match.`); return;
    }

    // 🚨 FIX: Explicitly parse as a float for the backend!
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
        is_no_plan: isNoPlan // 🚨 NEW: Send to backend
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

        // Lock UI Elements
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

    // 🚨 NEW: Dynamically find the correct process for this specific machine
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

                // Restore target, times and counts
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

                // Disable inputs for restored logs
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
            document.getElementById(`shots_${hourIndex}_0`).disabled = true;
            document.getElementById(`sf_qty_${hourIndex}_0`).disabled = true;
            document.getElementById(`sf_reason_${hourIndex}_0`).disabled = true;
            document.getElementById(`btn_add_sf_${hourIndex}_0`).disabled = true;
            document.getElementById(`rej_qty_${hourIndex}_0`).disabled = true;
            document.getElementById(`rej_reason_${hourIndex}_0`).disabled = true;
            document.getElementById(`btn_add_rej_${hourIndex}_0`).disabled = true;
            document.getElementById(`split_check_${hourIndex}`).disabled = true;

            const btn = document.getElementById(`btn_submit_${hourIndex}_0`);
            btn.style.background = "var(--border-color)";
            btn.style.color = "var(--text-muted)";
            btn.style.border = "none";
            btn.innerText = "🔒 Locked";
            btn.disabled = true;
        }
    });
    for (let i = 0; i < hours.length; i++) {
        updateTabStatus(i);
    }
    calculateTotals();
    enforceTimeLocks();
}

window.onload = async () => {
    const now = new Date();
    const offsetDate = new Date(now.getTime() - (now.getTimezoneOffset() * 60000));
    const dateInput = document.getElementById("global_date");
    if (dateInput) dateInput.value = offsetDate.toISOString().split('T')[0];

    await fetchMasterData();

    const urlParams = new URLSearchParams(window.location.search);
    const urlMachine = urlParams.get('machine');
    const urlDate = urlParams.get('date');
    const urlShift = urlParams.get('shift');

    if (urlMachine && urlDate && urlShift) {
        let machineSelect = document.getElementById("machine");
        let shiftSelect = document.getElementById("global_shift");

        if (machineSelect) machineSelect.value = urlMachine;
        if (dateInput) dateInput.value = urlDate;

        if (shiftSelect) {
            shiftSelect.value = urlShift;
        }

        checkActiveMachineState();
    }
};

// 🚨 NEW: Background Sync - Pings the server every 15 seconds
setInterval(async () => {
    let machine = document.getElementById("machine").value;
    let dateVal = document.getElementById("global_date").value;
    enforceTimeLocks();
    // Only ping the server if the operator actually has a machine selected
    if (!machine || !dateVal) return;

    try {
        const res = await fetch(`/api/get_live_iot_count?date=${dateVal}&machine_code=${encodeURIComponent(machine)}`);
        if (res.ok) {
            const data = await res.json();
            
            // Push the fresh data into the UI
            injectIoTCounts(data.iot_counts);
        }
    } catch (e) { 
        console.error("IoT Background Sync Error:", e); 
    }
}, 15000);
