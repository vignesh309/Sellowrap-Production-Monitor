let currentPage = 1;
let pageSize = 200;
let totalPages = 1;
let currentPageRecords = [];

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

    pageSize = parseInt(document.getElementById("page_size").value) || 200;

    loadFilterOptions();
    loadData();
});

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

// ==========================================
// FILTER DROPDOWN OPTIONS
// ==========================================
async function loadFilterOptions() {
    try {
        const res = await fetch('/api/old_erp_invoice/filters');
        if (!res.ok) throw new Error("Failed to load filter options");
        const data = await res.json();

        populateSelect("f_prod_category", data.categories);
        populateSelect("f_inv_type", data.inv_types);
        populateSelect("f_stock_type", data.stock_types);
    } catch (error) {
        console.error("Error loading filter options:", error);
    }
}

function populateSelect(elementId, items) {
    const select = document.getElementById(elementId);
    items.forEach(item => {
        const opt = document.createElement("option");
        opt.value = item;
        opt.textContent = item;
        select.appendChild(opt);
    });
}

// ==========================================
// BUILD QUERY STRING FROM FILTERS
// ==========================================
function buildFilterParams() {
    const params = new URLSearchParams();

    const fieldMap = {
        f_inv_from: "inv_from",
        f_inv_to: "inv_to",
        f_inv_no: "inv_no",
        f_cust_code: "cust_code",
        f_cust_name: "cust_name",
        f_cust_city: "cust_city",
        f_prod_code: "prod_code",
        f_prod_desc: "prod_desc",
        f_prod_category: "prod_category",
        f_inv_type: "inv_type",
        f_stock_type: "stock_type",
        f_unit_code: "unit_code"
    };

    for (const [elId, paramName] of Object.entries(fieldMap)) {
        const val = document.getElementById(elId).value.trim();
        if (val) params.append(paramName, val);
    }

    return params;
}

function applyFilters() {
    currentPage = 1;
    loadData();
}

function clearFilters() {
    document.querySelectorAll('.filter-grid input').forEach(el => el.value = "");
    document.querySelectorAll('.filter-grid select').forEach(el => el.value = "");
    currentPage = 1;
    loadData();
}

// ==========================================
// LOAD DATA (paginated)
// ==========================================
async function loadData() {
    const tbody = document.getElementById("table_body");
    tbody.innerHTML = `<tr><td colspan="13" class="empty-row">Loading data...</td></tr>`;

    const params = buildFilterParams();
    params.append("page", currentPage);
    params.append("page_size", pageSize);

    try {
        const res = await fetch(`/api/old_erp_invoice/data?${params.toString()}`);
        if (!res.ok) throw new Error("Failed to load data");
        const data = await res.json();

        currentPageRecords = data.records;
        totalPages = data.total_pages;
        currentPage = data.page;

        renderTable(data.records);
        updateSummary(data);
        updatePaginationUI();
    } catch (error) {
        console.error("Error loading invoice data:", error);
        tbody.innerHTML = `<tr><td colspan="13" class="empty-row">Error loading data.</td></tr>`;
    }
}

function renderTable(records) {
    const tbody = document.getElementById("table_body");
    tbody.innerHTML = "";

    if (records.length === 0) {
        tbody.innerHTML = `<tr><td colspan="13" class="empty-row">No records match the selected filters.</td></tr>`;
        return;
    }

    records.forEach(r => {
        tbody.innerHTML += `
            <tr>
                <td>${r.unit_code ?? ''}</td>
                <td>${r.inv_no ?? ''}</td>
                <td>${r.inv_date ?? ''}</td>
                <td>${r.cust_code ?? ''}</td>
                <td>${r.cust_name ?? ''}</td>
                <td>${r.cust_city_code ?? ''}</td>
                <td>${r.prod_category ?? ''}</td>
                <td>${r.prod_code ?? ''}</td>
                <td>${r.product_desc ?? ''}</td>
                <td>${r.qty.toLocaleString()}</td>
                <td>${r.basic_amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                <td>${r.inv_type ?? ''}</td>
                <td>${r.stock_type ?? ''}</td>
            </tr>
        `;
    });
}

function updateSummary(data) {
    document.getElementById("sum_invoice_count").innerText = data.distinct_invoices.toLocaleString();
    document.getElementById("sum_total_qty").innerText = data.total_qty.toLocaleString();
    document.getElementById("sum_total_amount").innerText = data.total_amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    document.getElementById("sum_total_rows").innerText = data.total_rows.toLocaleString();
}

// ==========================================
// PAGINATION
// ==========================================
function updatePaginationUI() {
    document.getElementById("page_jump_input").value = currentPage;
    document.getElementById("page_total_label").innerText = `of ${totalPages.toLocaleString()}`;

    document.getElementById("btn_prev").disabled = currentPage <= 1;
    document.getElementById("btn_next").disabled = currentPage >= totalPages;
}

function goToPage(n) {
    if (n < 1 || n > totalPages || n === currentPage) return;
    currentPage = n;
    loadData();
}

function jumpToPage() {
    const input = document.getElementById("page_jump_input");
    let n = parseInt(input.value);

    if (isNaN(n) || n < 1) n = 1;
    if (n > totalPages) n = totalPages;

    goToPage(n);
}

function handlePageJumpKey(event) {
    if (event.key === "Enter") {
        jumpToPage();
    }
}

function changePageSize() {
    pageSize = parseInt(document.getElementById("page_size").value) || 200;
    currentPage = 1;
    loadData();
}

// ==========================================
// EXPORT CURRENT PAGE TO XLSX
// ==========================================
function exportCurrentView() {
    if (!currentPageRecords || currentPageRecords.length === 0) {
        alert("No data to export.");
        return;
    }

    const exportRows = currentPageRecords.map(r => ({
        "Unit Code": r.unit_code,
        "Invoice No": r.inv_no,
        "Invoice Date": r.inv_date,
        "Customer Code": r.cust_code,
        "Customer Name": r.cust_name,
        "City": r.cust_city_code,
        "Category": r.prod_category,
        "Product Code": r.prod_code,
        "Product Description": r.product_desc,
        "Qty": r.qty,
        "Basic Amount": r.basic_amount,
        "Invoice Type": r.inv_type,
        "Stock Type": r.stock_type
    }));

    const worksheet = XLSX.utils.json_to_sheet(exportRows);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, "Invoice Data");

    XLSX.writeFile(workbook, `Old_ERP_Invoice_Page${currentPage}.xlsx`);
}