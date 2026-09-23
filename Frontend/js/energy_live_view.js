// ==========================================
// HIERARCHY DEFINITION 
// ==========================================
const METER_TREE = {
    name: "Main Panel",
    children: [
        {
            name: "Moulding Stage",
            children: [
                { name: "Moulding SSB1" },
                { name: "Moulding SSB2" }
            ]
        },
        {
            name: "Utility",
            children: [
                { name: "Utility Sub 1" },
                { name: "Utility Sub 2" }
            ]
        },
        {
            name: "Fire Pump",
            children: [
                { name: "Fire Pump Sub 1" },
                { name: "Fire Pump Sub 2" }
            ]
        }
    ]
};

let liveMeterData = {};

document.addEventListener("DOMContentLoaded", () => {
    const role = localStorage.getItem("userRole");
    const fullName = localStorage.getItem("userFullName") || localStorage.getItem("userName");

    if (!role || !fullName) {
        window.location.href = "/";
        return;
    }

    document.getElementById("user-display").innerText = fullName;
    document.getElementById("role-display").innerText = role.toUpperCase();
    document.getElementById("user-avatar").innerText = fullName.charAt(0).toUpperCase();

    loadLiveData();
    setInterval(loadLiveData, 15000);
});

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

// ==========================================
// FETCH + RENDER
// ==========================================
async function loadLiveData() {
    try {
        const res = await fetch('/api/energy_reports/live_status');
        if (!res.ok) throw new Error("Failed to fetch live status");
        const data = await res.json();

        liveMeterData = data.meters;
        renderTree();
    } catch (error) {
        console.error("Error loading live meter data:", error);
    }
}

function renderTree() {
    const container = document.getElementById("meter_tree");
    container.innerHTML = `<ul class="horizontal-tree">${buildNode(METER_TREE, true)}</ul>`;
}

function buildNode(node, isRoot = false) {
    const info = liveMeterData[node.name];
    const hasChildren = node.children && node.children.length > 0;
    
    const boxHtml = buildBox(node.name, info, isRoot, node.children, hasChildren);

    let childrenHtml = "";
    if (hasChildren) {
        childrenHtml = `<ul>${node.children.map(c => buildNode(c, false)).join("")}</ul>`;
    }

    return `<li>${boxHtml}${childrenHtml}</li>`;
}

function buildBox(name, info, isRoot, children, hasChildren) {
    const childrenClass = hasChildren ? 'has-children' : '';
    const rootClass = isRoot ? 'root-box' : '';

    if (!info) {
        return `
            <div class="meter-box ${rootClass} ${childrenClass}">
                <div class="box-status"><span class="status-dot offline"></span> OFFLINE</div>
                <div class="box-name">${name}</div>
                <div class="box-kw" style="color: var(--text-muted);">-- kW</div>
                <div class="box-meta">
                    <span>No Data Received</span>
                </div>
            </div>
        `;
    }

    const kw = (info.watts_total / 1000).toFixed(1);
    const statusClass = getFreshnessStatus(info.recorded_at);
    const statusLabel = statusClass === 'live' ? 'LIVE' : statusClass === 'stale' ? 'STALE' : 'OFFLINE';

    let balanceHtml = "";
    if (hasChildren) {
        const childrenSumW = children.reduce((sum, c) => {
            const childInfo = liveMeterData[c.name];
            return sum + (childInfo ? childInfo.watts_total : 0);
        }, 0);
        const childrenSumKw = (childrenSumW / 1000).toFixed(1);
        const diffPct = info.watts_total > 0
            ? Math.abs(((childrenSumW - info.watts_total) / info.watts_total) * 100).toFixed(1)
            : 0;
        
        const balanceClass = diffPct <= 5 ? 'ok' : 'warn';
        balanceHtml = `<div class="box-balance ${balanceClass}">Sub-Meters: ${childrenSumKw} kW (Δ ${diffPct}%)</div>`;
    }

    return `
        <div class="meter-box ${rootClass} ${childrenClass}">
            <div class="box-status">
                <span class="status-dot ${statusClass}"></span> ${statusLabel}
            </div>
            <div class="box-name">${name}</div>
            <div class="box-kw">${kw} kW</div>
            <div class="box-meta">
                <span>PF ${info.pf_average}</span>
                <span>${info.current_total} A</span>
            </div>
            ${balanceHtml}
        </div>
    `;
}

function getFreshnessStatus(recordedAtStr) {
    if (!recordedAtStr) return 'offline';
    const recordedAt = new Date(recordedAtStr.replace(' ', 'T'));
    const now = new Date();
    const diffMinutes = (now - recordedAt) / 60000;

    if (diffMinutes <= 2) return 'live';
    if (diffMinutes <= 15) return 'stale';
    return 'offline';
}