window.onload = () => {
    // Automatically generate the report for the current month on page load
    loadDashboard();
};

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

// Helper function to turn Year + Month into exact Start/End dates
function getFilterDates() {
    let year = document.getElementById("yearFilter").value;
    let fromM = document.getElementById("fromMonthFilter").value.padStart(2, '0');
    let toM = document.getElementById("toMonthFilter").value.padStart(2, '0');

    // Start date is always the 1st of the From Month
    let startDate = `${year}-${fromM}-01`;
    
    // End date requires calculating the last day of the To Month
    // Creating a date with day '0' of the NEXT month gives the last day of the current month
    let endOfMonth = new Date(year, parseInt(toM), 0).getDate();
    let endDate = `${year}-${toM}-${endOfMonth}`;

    return { startDate, endDate };
}

async function loadDashboard() {
    const oeeTbody = document.getElementById("oeeTableBody");
    const teepTbody = document.getElementById("teepTableBody");

    if (!oeeTbody || !teepTbody) return;

    oeeTbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 20px;">Fetching Aggregated Data...</td></tr>`;
    teepTbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 20px;">Fetching Aggregated Data...</td></tr>`;

    let dates = getFilterDates();
    let process = document.getElementById("processFilter").value;
    let machine = document.getElementById("machineFilter").value;

    try {
        const params = new URLSearchParams();
        params.append('start_date', dates.startDate);
        params.append('end_date', dates.endDate);
        if (process) params.append('process', process);
        if (machine) params.append('machine', machine);

        const response = await fetch(`/api/get_oeeteep_process_summary?${params.toString()}`);
        if (!response.ok) throw new Error("Failed to fetch dashboard data.");

        const data = await response.json();
        const records = data.records;

        if (!records || records.length === 0) {
            let emptyMsg = `<tr><td colspan="8" style="text-align: center; color: var(--status-yellow); padding: 20px;">No production data found for this period.</td></tr>`;
            oeeTbody.innerHTML = emptyMsg;
            teepTbody.innerHTML = emptyMsg;
            return;
        }

        let oeeHtml = "";
        let teepHtml = "";

        records.forEach(r => {
            // Generate OEE Row
            oeeHtml += `
                <tr>
                    <td class="txt-left" style="font-weight: bold; color: white;">${r.process_name}</td>
                    <td>${r.total_batches}</td>
                    <td>${r.planned_prod_time}</td>
                    <td style="color: var(--status-green);">${r.operating_time}</td>
                    <td>${r.oee_avail_pct}%</td>
                    <td class="highlight-perf">${r.perf_pct}%</td>
                    <td>${r.qual_pct}%</td>
                    <td class="highlight-oee">${r.oee_pct}%</td>
                </tr>
            `;

            // Generate TEEP Row
            teepHtml += `
                <tr>
                    <td class="txt-left" style="font-weight: bold; color: white;">${r.process_name}</td>
                    <td>${r.total_batches}</td>
                    <td>${r.total_shift_time}</td>
                    <td style="color: var(--status-green);">${r.operating_time}</td>
                    <td>${r.teep_avail_pct}%</td>
                    <td class="highlight-perf">${r.perf_pct}%</td>
                    <td>${r.qual_pct}%</td>
                    <td style="color: var(--status-green); font-weight: bold; font-size: 13px;">${r.teep_pct}%</td>
                </tr>
            `;
        });

        oeeTbody.innerHTML = oeeHtml;
        teepTbody.innerHTML = teepHtml;

    } catch (error) {
        console.error("Dashboard Fetch Error:", error);
        let errMsg = `<tr><td colspan="8" style="text-align: center; color: var(--status-red); padding: 20px;">Error loading data. Check console.</td></tr>`;
        oeeTbody.innerHTML = errMsg;
        teepTbody.innerHTML = errMsg;
    }
}