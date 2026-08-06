async function loadLedger(searchQuery = "", startDate = "", endDate = "", machine = "") {
    const container = document.getElementById("ledgerContainer");
    container.innerHTML = `<div style="text-align: center; padding: 20px; color: var(--text-muted);">Loading data...</div>`;
    
    try {
        // Build URLSearchParams cleanly
        const params = new URLSearchParams();
        if (searchQuery) params.append('search', searchQuery);
        if (startDate) params.append('start_date', startDate);
        if (endDate) params.append('end_date', endDate);
        if (machine) params.append('machine', machine); 
        
        const response = await fetch(`/api/get_batch_ledger?${params.toString()}`);
        
        if (!response.ok) throw new Error("Failed to fetch ledger data.");
        
        const data = await response.json();
        
        // DEBUGGING: Prints the backend data to your browser console (F12)
        console.log("API Response Data:", data); 

        const batches = data.ledger;
        container.innerHTML = "";
        
        if (!batches || batches.length === 0) {
            container.innerHTML = `<div style="text-align: center; padding: 20px; color: var(--status-yellow);">No batches found matching your filters.</div>`;
            return;
        }

        let allCardsHTML = ""; 

        batches.forEach(batch => {
            // Safety check
            if (!batch.stages || batch.stages.length === 0) return;

            const lastUpdate = batch.stages[batch.stages.length - 1].timestamp;
            const currentStage = batch.stages[batch.stages.length - 1].process_name;

            // Find ONLY the Moulding stage for the table data
            const mouldingStage = batch.stages.find(stage => stage.process_name === "Moulding" || stage.sequence_no === 1);

            let cardHTML = `
                <div class="batch-card">
                    <div class="batch-header" style="display: flex; justify-content: space-between; align-items: center; gap: 10px;">
                        <div>
                            <span class="batch-title">${batch.batch_id}</span>
                            <span class="batch-subtitle">Last Update: ${lastUpdate} | Current Stage: <span style="color: var(--accent-cyan);">${currentStage}</span></span>
                        </div>
                        <div style="flex-shrink: 0;">
                            <button class="hub-btn label-btn" 
                                    title="Print high-res 60x60 label"
                                    style="margin-left: 10px; border-radius: 6px; padding: 6px 12px; font-size: 11px; background: rgba(0, 229, 255, 0.1); border-color: var(--accent-cyan); color: var(--accent-cyan);"
                                    onclick="printLabel('${batch.batch_id}')">
                                🖨️ Print Label
                            </button>
                        </div>
                    </div>
                    <div class="batch-stages">
                        <table class="stage-table">
                            <thead>
                                <tr>
                                    <th>Seq</th>
                                    <th>Process Stage</th>
                                    <th>Input Qty</th>
                                    <th>OK Qty</th>
                                    <th>NG Qty</th>
                                    <th>Operator</th>
                                    <th>Timestamp</th>
                                </tr>
                            </thead>
                            <tbody>
            `;

            // Only render the row if the Moulding stage exists
            if (mouldingStage) {
                const osBadge = mouldingStage.is_outsourced ? `<span class="badge-os">OS</span>` : ``;
                cardHTML += `
                                <tr>
                                    <td style="color: var(--text-muted);">#${mouldingStage.sequence_no}</td>
                                    <td style="font-weight: bold;">${mouldingStage.process_name} ${osBadge}</td>
                                    <td style="color: var(--text-muted);">${mouldingStage.input_qty}</td>
                                    <td style="color: var(--status-green); font-weight: bold;">${mouldingStage.ok_qty}</td>
                                    <td style="color: var(--status-red); font-weight: bold;">${mouldingStage.ng_qty}</td>
                                    <td>${mouldingStage.emp_code || '-'}</td>
                                    <td style="color: var(--text-muted); font-size: 11px;">${mouldingStage.timestamp}</td>
                                </tr>
                `;
            }

            cardHTML += `
                            </tbody>
                        </table>
                    </div>
                </div>
            `;
            allCardsHTML += cardHTML;
        });
        
        container.innerHTML = allCardsHTML;
        
    } catch (error) {
        console.error("Ledger Fetch Error:", error);
        container.innerHTML = `<div style="text-align: center; color: var(--status-red); padding: 20px;">Error loading data. Check console.</div>`;
    }
}

// --- INVISIBLE IFRAME PRINT TRIGGER (BROWSER-SAFE) ---
function printLabel(batchId) {
    // 1. Clean up the old iframe
    let oldIframe = document.getElementById('print-iframe');
    if (oldIframe) {
        oldIframe.remove();
    }

    // 2. Create a fresh iframe
    let printIframe = document.createElement('iframe');
    printIframe.id = 'print-iframe';
    
    // 🚨 THE FIX: Do NOT use display: none. Hide it off-screen instead.
    printIframe.style.position = 'absolute';
    printIframe.style.width = '1px';
    printIframe.style.height = '1px';
    printIframe.style.left = '-9999px';
    printIframe.style.border = 'none';

    // 3. When the PDF loads, wait a fraction of a second, then print
    printIframe.onload = function() {
        // The setTimeout gives the browser's graphics engine time to 
        // register the PDF before we freeze the screen with the print menu.
        setTimeout(() => {
            printIframe.contentWindow.focus();
            printIframe.contentWindow.print();
        }, 250); 
    };

    // 4. Point it to the PDF with the cache-busting timestamp
    printIframe.src = `/api/download_label/${batchId}?t=${new Date().getTime()}`;

    // 5. Add it to the page
    document.body.appendChild(printIframe);
}

// Handle search button click
function handleSearch() {
    const searchQuery = document.getElementById("searchInput").value.trim();
    const startDate = document.getElementById("startDate").value;
    const endDate = document.getElementById("endDate").value;
    const machine = document.getElementById("machineFilter") ? document.getElementById("machineFilter").value : "";
    
    loadLedger(searchQuery, startDate, endDate, machine);
}

// Clear all filters and reload all data
function clearFilters() {
    document.getElementById("searchInput").value = "";
    document.getElementById("startDate").value = "";
    document.getElementById("endDate").value = "";
    
    const machineDropdown = document.getElementById("machineFilter");
    if (machineDropdown) machineDropdown.value = ""; 
    
    loadLedger(); 
}

async function loadMachines() {
    try {
        const response = await fetch('/api/get_machines');
        if (response.ok) {
            const data = await response.json();
            const machineDropdown = document.getElementById("machineFilter");
            
            data.machines.forEach(m => {
                const displayName = (m.name && m.name !== m.code) ? `${m.code} - ${m.name}` : m.code;
                machineDropdown.innerHTML += `<option value="${m.code}">${displayName}</option>`;
            });
        }
    } catch (error) {
        console.error("Failed to load machine dropdown:", error);
    }
}

window.onload = function() {
    loadMachines(); 
    
    const today = new Date();
    const threeDaysAgo = new Date();
    threeDaysAgo.setDate(today.getDate() - 3);
    
    const startDateStr = threeDaysAgo.toISOString().split('T')[0];
    const endDateStr = today.toISOString().split('T')[0];
    
    document.getElementById("startDate").value = startDateStr;
    document.getElementById("endDate").value = endDateStr;
    
    // Pass empty string for machine on initial load
    loadLedger("", startDateStr, endDateStr, ""); 
};