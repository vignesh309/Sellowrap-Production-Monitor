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

let machineList = [];
let currentUser = "";

document.addEventListener("DOMContentLoaded", () => {
    const role = localStorage.getItem("userRole");
    const fullName = localStorage.getItem("userFullName") || localStorage.getItem("userName");

    if (!role || !fullName) {
        window.location.href = "/";
        return;
    }

    // Gate: Admin & Supervisor only
    const roleLower = role.trim().toLowerCase();
    if (roleLower !== "admin" && roleLower !== "supervisor") {
        alert("Access Denied: This tool is restricted to Admins and Supervisors.");
        window.location.href = "/hub";
        return;
    }

    currentUser = fullName;
    document.getElementById("user-display").innerText = fullName;
    document.getElementById("role-display").innerText = role.toUpperCase();
    document.getElementById("user-avatar").innerText = fullName.charAt(0).toUpperCase();

    // Default date: Admin gets today; Supervisor also defaults to today (yesterday still selectable)
    const today = new Date().toISOString().split('T')[0];
    document.getElementById("bn_date").value = today;

    if (roleLower !== "admin") {
        const yesterday = new Date();
        yesterday.setDate(yesterday.getDate() - 1);
        document.getElementById("bn_date").min = yesterday.toISOString().split('T')[0];
        document.getElementById("bn_date").max = today;
    }

    document.getElementById("bn_shift").addEventListener("change", renderHourChecklist);
    document.getElementById("bn_remarks").addEventListener("input", updatePreview);

    renderHourChecklist();
    loadMachines();
});

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

// ==========================================
// LOAD MACHINES
// ==========================================
async function loadMachines() {
    try {
        const res = await fetch('/api/get_machines');
        if (!res.ok) throw new Error("Failed to load machines");
        const data = await res.json();
        machineList = data.machines.filter(m => m.process); // only machines with a known process

        const container = document.getElementById("machine_checklist");
        container.innerHTML = "";

        if (machineList.length === 0) {
            container.innerHTML = `<div class="empty-msg">No active machines found.</div>`;
            return;
        }

        machineList.forEach(m => {
            const div = document.createElement("div");
            div.className = "check-item";
            div.innerHTML = `
                <input type="checkbox" class="machine-check" value="${m.code}" onchange="updatePreview()">
                <span>${m.code} <span style="color: var(--text-muted); font-size: 11px;">(${m.process})</span></span>
            `;
            container.appendChild(div);
        });
    } catch (error) {
        console.error("Error loading machines:", error);
        document.getElementById("machine_checklist").innerHTML = `<div class="empty-msg">Error loading machines.</div>`;
    }
}

function toggleAllMachines(state) {
    document.querySelectorAll(".machine-check").forEach(cb => cb.checked = state);
    updatePreview();
}

// ==========================================
// HOUR CHECKLIST
// ==========================================
function getHoursForShift() {
    const shift = document.getElementById("bn_shift").value;
    return shift === "B" ? shiftBHours : shiftAHours;
}

function renderHourChecklist() {
    const hours = getHoursForShift();
    const container = document.getElementById("hour_checklist");
    container.innerHTML = "";

    hours.forEach((h, idx) => {
        const div = document.createElement("div");
        div.className = "check-item";
        div.innerHTML = `
            <input type="checkbox" class="hour-check" value="${idx}" onchange="updatePreview()">
            <span>${h.start} - ${h.end}</span>
        `;
        container.appendChild(div);
    });
    updatePreview();
}

function toggleAllHours(state) {
    document.querySelectorAll(".hour-check").forEach(cb => cb.checked = state);
    updatePreview();
}

// ==========================================
// PREVIEW
// ==========================================
function getSelectedMachines() {
    return Array.from(document.querySelectorAll(".machine-check:checked")).map(cb => cb.value);
}
function getSelectedHourIndexes() {
    return Array.from(document.querySelectorAll(".hour-check:checked")).map(cb => parseInt(cb.value));
}

function updatePreview() {
    const machines = getSelectedMachines();
    const hourIdxs = getSelectedHourIndexes();
    const remarks = document.getElementById("bn_remarks").value.trim();

    const preview = document.getElementById("preview_summary");
    const btn = document.getElementById("btn_apply");

    if (machines.length === 0 || hourIdxs.length === 0) {
        preview.innerText = "Select at least one machine and one hour block to continue.";
        btn.disabled = true;
        return;
    }

    const total = machines.length * hourIdxs.length;
    preview.innerText = `This will mark ${machines.length} machine${machines.length > 1 ? 's' : ''} × ${hourIdxs.length} hour${hourIdxs.length > 1 ? 's' : ''} = ${total} block${total > 1 ? 's' : ''} as No Plan.`;

    btn.disabled = !remarks;
}

// ==========================================
// APPLY BULK NO PLAN
// ==========================================
async function applyBulkNoPlan() {
    const dateVal = document.getElementById("bn_date").value;
    const shiftVal = document.getElementById("bn_shift").value;
    const remarks = document.getElementById("bn_remarks").value.trim();
    const machines = getSelectedMachines();
    const hourIdxs = getSelectedHourIndexes();
    const hours = getHoursForShift();

    if (!remarks) {
        alert("Please enter a reason for No Plan before continuing.");
        return;
    }
    if (machines.length === 0 || hourIdxs.length === 0) {
        alert("Please select at least one machine and one hour block.");
        return;
    }

    // ---- STEP 1: Eligibility pre-check ----
    const btn = document.getElementById("btn_apply");
    btn.disabled = true;
    btn.innerText = "Checking machine status...";

    const eligibility = {}; // machine -> { eligible: bool, alreadyLogged: Set(startTime) }

    for (const machine of machines) {
        try {
            const res = await fetch(`/api/get_batch_logs?date=${dateVal}&shift=${shiftVal}&machine_code=${encodeURIComponent(machine)}`);
            const data = await res.json();

            const alreadyLogged = new Set((data.logs || []).map(l => l.start_time));
            const isRunning = data.exists && data.logs && data.logs.length > 0 && !data.is_finalized;

            eligibility[machine] = {
                eligible: !isRunning,
                alreadyLogged: alreadyLogged
            };
        } catch (e) {
            eligibility[machine] = { eligible: false, alreadyLogged: new Set(), error: true };
        }
    }

    const blockedMachines = machines.filter(m => !eligibility[m].eligible);
    const eligibleMachines = machines.filter(m => eligibility[m].eligible);

    let confirmMsg = `${eligibleMachines.length} machine(s) are eligible for No Plan submission.\n`;
    if (blockedMachines.length > 0) {
        confirmMsg += `${blockedMachines.length} machine(s) are BLOCKED (running batch not finalized) and will be skipped:\n- ${blockedMachines.join('\n- ')}\n\n`;
    }
    confirmMsg += `\nRemarks: "${remarks}"\n\nProceed?`;

    if (!confirm(confirmMsg)) {
        btn.disabled = false;
        btn.innerText = "Apply No Plan";
        return;
    }

    // ---- STEP 2: Submit blocks ----
    document.getElementById("results_section").style.display = "block";
    document.getElementById("finalize_section").style.display = "none";
    const resultsBody = document.getElementById("results_body");
    resultsBody.innerHTML = "";

    let savedCount = 0, skippedCount = 0, blockedCount = 0, failedCount = 0;
    const machineHourCoverage = {}; // machine -> Set of covered hour start_times (existing + new)

    for (const machine of machines) {
        machineHourCoverage[machine] = new Set(eligibility[machine].alreadyLogged || []);

        if (!eligibility[machine].eligible) {
            hourIdxs.forEach(idx => {
                addResultRow(machine, hours[idx], 'blocked', 'Blocked — running batch not finalized');
            });
            blockedCount += hourIdxs.length;
            continue;
        }

        for (const idx of hourIdxs) {
            const h = hours[idx];

            if (eligibility[machine].alreadyLogged.has(h.start)) {
                addResultRow(machine, h, 'skipped', 'Already logged');
                skippedCount++;
                continue;
            }

            const batchId = `${dateVal}_${shiftVal}_${machine}_N/A_NO PLAN`;
            const payload = {
                batch_id: batchId,
                internal_batch_number: "N/A",
                production_date: dateVal,
                shift: shiftVal,
                start_time: h.start,
                end_time: h.end,
                machine_code: machine,
                mould_code: "N/A",
                part_number: "NO PLAN",
                operator_code: currentUser,
                supervisor_code: currentUser,
                target_shots: 0,
                actual_shots: 0,
                active_cavities: 1.0,
                ok_parts: 0,
                ng_parts: 0,
                actual_temp: 0,
                actual_pressure: 0,
                actual_setting: 0,
                rejections: [],
                shortfalls: [],
                is_no_plan: true
            };

            try {
                const res = await fetch('/api/submit_stage1_block', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                if (res.ok) {
                    addResultRow(machine, h, 'saved', 'No Plan Saved');
                    savedCount++;
                    machineHourCoverage[machine].add(h.start);
                } else {
                    const err = await res.json();
                    addResultRow(machine, h, 'failed', err.detail || 'Failed to save');
                    failedCount++;
                }
            } catch (e) {
                addResultRow(machine, h, 'failed', 'Network error');
                failedCount++;
            }
        }
    }

    document.getElementById("result_summary_text").innerText =
        `${savedCount} saved · ${skippedCount} skipped (already logged) · ${blockedCount} blocked · ${failedCount} failed.`;

    btn.disabled = false;
    btn.innerText = "Apply No Plan";

    // ---- STEP 3: Finalize candidates ----
    renderFinalizeCandidates(machines, machineHourCoverage, eligibility, dateVal, shiftVal, remarks);
}

function addResultRow(machine, hourObj, status, label) {
    const tbody = document.getElementById("results_body");
    const statusClass = {
        saved: 'status-saved',
        skipped: 'status-skipped',
        blocked: 'status-blocked',
        failed: 'status-failed'
    }[status];

    tbody.innerHTML += `
        <tr>
            <td>${machine}</td>
            <td>${hourObj.start} - ${hourObj.end}</td>
            <td><span class="status-pill ${statusClass}">${label}</span></td>
        </tr>
    `;
}

// ==========================================
// FINALIZE CANDIDATES
// ==========================================
function renderFinalizeCandidates(machines, machineHourCoverage, eligibility, dateVal, shiftVal, remarks) {
    const section = document.getElementById("finalize_section");
    const tbody = document.getElementById("finalize_body");
    tbody.innerHTML = "";

    let anyCandidates = false;

    machines.forEach(machine => {
        if (!eligibility[machine].eligible) return; // blocked machines never shown here

        const covered = machineHourCoverage[machine];
        const isComplete = covered.size >= 12;

        if (!isComplete) return; // only show machines with all 12 hours covered

        anyCandidates = true;
        const meta = machineList.find(m => m.code === machine);
        const process = meta ? meta.process : "";
        const targetPage = process === "MOULDING" ? "moulding-stage" : "production-entry-stage-1";
        const machineUrl = `/${targetPage}?machine=${encodeURIComponent(machine)}&date=${dateVal}&shift=${shiftVal}`;

        addFinalizeRow(machine, shiftVal, dateVal, process, remarks, machineUrl);
    });

    section.style.display = anyCandidates ? "block" : "none";
    const finalizeAllButton = document.getElementById("btn_finalize_all");
    if (finalizeAllButton) {
        finalizeAllButton.disabled = !anyCandidates;
        finalizeAllButton.innerText = "Finalize All";
    }
}

function addFinalizeRow(machine, shift, dateVal, process, remarks, machineUrl) {
    const tbody = document.getElementById("finalize_body");
    const rowId = `finalize_row_${machine}_${shift}`.replace(/[^a-zA-Z0-9_]/g, "_");
    const row = document.createElement("tr");
    row.id = rowId;

    const machineCell = document.createElement("td");
    machineCell.textContent = machine;

    const shiftCell = document.createElement("td");
    shiftCell.textContent = shift;

    const statusCell = document.createElement("td");
    const status = document.createElement("span");
    status.className = "status-pill status-saved";
    status.textContent = "12 / 12 Hours Covered";
    statusCell.appendChild(status);

    const actionCell = document.createElement("td");
    const finalizeButton = document.createElement("button");
    finalizeButton.type = "button";
    finalizeButton.className = "btn-finalize finalize-row-btn";
    finalizeButton.dataset.machine = machine;
    finalizeButton.dataset.date = dateVal;
    finalizeButton.dataset.shift = shift;
    finalizeButton.dataset.process = process;
    finalizeButton.dataset.remarks = remarks;
    finalizeButton.textContent = "Finalize";
    finalizeButton.addEventListener("click", () => finalizeMachine(finalizeButton));

    const openButton = document.createElement("button");
    openButton.type = "button";
    openButton.className = "btn-warn-link";
    openButton.textContent = "Open Page";
    openButton.addEventListener("click", () => window.open(machineUrl, "_blank"));

    actionCell.append(finalizeButton, openButton);
    row.append(machineCell, shiftCell, statusCell, actionCell);
    tbody.appendChild(row);
}

async function finalizeAllMachines() {
    const buttons = Array.from(document.querySelectorAll(".finalize-row-btn:not(:disabled)"));

    if (buttons.length === 0) {
        alert("No machines are currently pending finalization.");
        return;
    }

    if (!confirm(`Finalize ${buttons.length} machine(s) now?\n\nThis action cannot be undone for any of them.`)) {
        return;
    }

    const allButton = document.getElementById("btn_finalize_all");
    allButton.disabled = true;
    allButton.innerText = "Finalizing All...";

    let successCount = 0;
    let failCount = 0;

    for (const button of buttons) {
        try {
            await finalizeOneMachine(button);
            successCount++;
        } catch (error) {
            console.error(`Failed to finalize ${button.dataset.machine} Shift ${button.dataset.shift}:`, error);
            failCount++;
        }
    }

    allButton.innerText = "Finalize All";
    allButton.disabled = true;
    alert(`Finalize All complete.\n\n✅ ${successCount} finalized successfully.\n${failCount > 0 ? `❌ ${failCount} failed — check their rows for details.` : ""}`);
}

async function finalizeMachine(button) {
    const machine = button.dataset.machine;
    const dateVal = button.dataset.date;
    const shift = button.dataset.shift;

    if (!confirm(`Finalize batch for ${machine} (${dateVal}, Shift ${shift})?\n\nThis action cannot be undone.`)) {
        return;
    }

    try {
        await finalizeOneMachine(button);
    } catch (error) {
        alert("Error: " + error.message);
        button.disabled = false;
        button.innerText = "Finalize";
    }
}

async function finalizeOneMachine(button) {
    const { machine, date, shift, process, remarks } = button.dataset;
    button.disabled = true;
    button.innerText = "Finalizing...";

    try {
        const logRes = await fetch(`/api/get_batch_logs?date=${date}&shift=${shift}&machine_code=${encodeURIComponent(machine)}`);
        if (!logRes.ok) throw new Error("Failed to load the machine's saved logs.");
        const logData = await logRes.json();

        if (!logData.exists || !logData.logs || logData.logs.length === 0) {
            button.innerText = "❌ No Logs";
            throw new Error("No logs found — nothing to finalize.");
        }

        if (logData.is_finalized) {
            button.innerText = "Already Finalized";
            return;
        }

        const batchId = logData.setup && logData.setup.batch_id;
        if (!batchId) {
            button.innerText = "❌ No Batch ID";
            throw new Error("Could not determine the batch ID.");
        }

        const payload = {
            batch_id: batchId,
            sequence_no: 1,
            process_name: process || "Unknown Process",
            input_qty: 0,
            ok_qty: 0,
            ng_qty: 0,
            emp_code: currentUser,
            is_outsourced: false,
            fg_part_number: "NO PLAN",
            remarks: remarks
        };

        const res = await fetch('/api/finalize_batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            const err = await res.json();
            button.innerText = "❌ Failed";
            throw new Error(err.detail || "Failed to finalize.");
        }

        button.innerText = "Finalized";
        const openButton = button.parentElement.querySelector(".btn-warn-link");
        if (openButton) openButton.style.display = "none";
    } catch (error) {
        if (button.innerText === "Finalizing...") button.innerText = "❌ Failed";
        throw error;
    }
}