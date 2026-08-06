// ==========================================
// INITIALIZATION
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
    // 1. Authenticate & Setup Profile
    const role = localStorage.getItem("userRole");
    const username = localStorage.getItem("userName") || localStorage.getItem("userFullName") || "Admin";

    if (!role || !username) {
        window.location.href = "/";
        return;
    }

    document.getElementById("user-display").innerText = username;
    document.getElementById("role-display").innerText = role;
    if (username !== "Admin") document.getElementById("user-avatar").innerText = username.charAt(0).toUpperCase();

    // 2. Setup Active Toggle Label
    const activeToggle = document.getElementById("is_active");
    const statusText = document.getElementById("status-text");
    activeToggle.addEventListener("change", () => {
        if (activeToggle.checked) {
            statusText.innerText = "Active";
            statusText.style.color = "var(--status-green)";
        } else {
            statusText.innerText = "Inactive";
            statusText.style.color = "var(--text-muted)";
        }
    });

    // 3. Setup OTP Toggle Logic
    const otpCheckbox = document.getElementById("toggle-otp-section");
    const otpContainer = document.querySelector(".otp-container");
    otpContainer.style.display = "none"; // Hide by default

    otpCheckbox.addEventListener("change", () => {
        otpContainer.style.display = otpCheckbox.checked ? "block" : "none";
    });

    // 4. Form Submit Listener
    document.getElementById("employeeForm").addEventListener("submit", handleFormSubmit);

    // 5. Load the table
    loadEmployees();
    resetForm(); // Ensures we start in "New Employee" mode
});

function logout() {
    localStorage.clear();
    window.location.href = "/";
}

// ==========================================
// DATA FETCHING & TABLE RENDER
// ==========================================
let allEmployees = [];

async function loadEmployees() {
    try {
        const response = await fetch('/api/employees');
        if (!response.ok) throw new Error("Failed to fetch employees");
        const data = await response.json();
        
        allEmployees = data.employees;
        renderTable(allEmployees);
    } catch (error) {
        console.error("Error loading employees:", error);
    }
}

function renderTable(employees) {
    const tbody = document.getElementById("employeeTableBody");
    tbody.innerHTML = "";

    employees.forEach(emp => {
        let badgeClass = "";
        if (emp.job_role === "Operator") badgeClass = "role-operator";
        else if (emp.job_role === "Supervisor") badgeClass = "role-supervisor";
        else if (emp.job_role === "Admin") badgeClass = "role-admin";

        const statusClass = emp.is_active ? "active" : "inactive";
        const statusText = emp.is_active ? "Active" : "Inactive";

        // Convert the object into a safe JSON string to attach to the button
        const empDataStr = encodeURIComponent(JSON.stringify(emp));

        tbody.innerHTML += `
            <tr>
                <td class="highlight">${emp.emp_code}</td>
                <td>${emp.full_name}</td>
                <td><span class="role-badge ${badgeClass}">${emp.job_role}</span></td>
                <td>${emp.username}</td>
                <td><span class="status-indicator ${statusClass}">${statusText}</span></td>
                <td><button class="btn-edit" onclick="editRow('${empDataStr}')">Edit</button></td>
            </tr>
        `;
    });
}

function filterTable() {
    const query = document.getElementById("searchBox").value.toLowerCase();
    const filtered = allEmployees.filter(emp => 
        emp.full_name.toLowerCase().includes(query) || 
        emp.emp_code.toLowerCase().includes(query) ||
        emp.username.toLowerCase().includes(query)
    );
    renderTable(filtered);
}

// ==========================================
// FORM HANDLING (EDIT vs NEW)
// ==========================================
function editRow(encodedEmpData) {
    const emp = JSON.parse(decodeURIComponent(encodedEmpData));

    // Populate the form
    document.getElementById("emp_id").value = emp.id;
    document.getElementById("emp_code").value = emp.emp_code;
    document.getElementById("full_name").value = emp.full_name;
    document.getElementById("job_role").value = emp.job_role;
    document.getElementById("username").value = emp.username;
    
    // We populate the password hash, but keep the field LOCKED for security
    const passField = document.getElementById("password_hash");
    passField.value = emp.password_hash;
    passField.disabled = true;

    // Set toggle switch
    document.getElementById("is_active").checked = emp.is_active;
    document.getElementById("is_active").dispatchEvent(new Event("change"));

    // Update Form Header & Button
    document.querySelector(".form-section h3").innerText = "Edit Employee";
    document.querySelector(".btn-primary").innerText = "Update Employee";

    // Show the OTP request toggle because they are editing
    document.querySelector(".password-reset-section").style.display = "block";
    document.getElementById("toggle-otp-section").checked = false;
    document.querySelector(".otp-container").style.display = "none";
}

function resetForm() {
    document.getElementById("employeeForm").reset();
    document.getElementById("emp_id").value = "";
    
    // Default to active
    document.getElementById("is_active").checked = true;
    document.getElementById("is_active").dispatchEvent(new Event("change"));

    // Because it's a NEW employee, unlock the password field!
    document.getElementById("password_hash").disabled = false;

    // Update Form Header & Button
    document.querySelector(".form-section h3").innerText = "Add New Employee";
    document.querySelector(".btn-primary").innerText = "Save Employee";

    // Hide the OTP logic because new users don't need authorization to be created
    document.querySelector(".password-reset-section").style.display = "none";
}

async function handleFormSubmit(e) {
    e.preventDefault();
    
    const emp_id = document.getElementById("emp_id").value;
    const isEditMode = !!emp_id;

    const payload = {
        emp_code: document.getElementById("emp_code").value,
        full_name: document.getElementById("full_name").value,
        job_role: document.getElementById("job_role").value,
        username: document.getElementById("username").value,
        password_hash: document.getElementById("password_hash").value,
        is_active: document.getElementById("is_active").checked
    };

    const url = isEditMode ? `/api/employees/${emp_id}` : `/api/employees`;
    const method = isEditMode ? `PUT` : `POST`;

    try {
        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) throw new Error("Failed to save employee");

        alert(`Employee successfully ${isEditMode ? "updated" : "added"}!`);
        resetForm();
        loadEmployees();

    } catch (error) {
        console.error(error);
        alert("Database Error: Could not save employee.");
    }
}

// ==========================================
// OTP AUTHORIZATION LOGIC
// ==========================================
// Trigger the backend to send the Telegram OTP
document.querySelector(".btn-otp").addEventListener("click", async () => {
    try {
        const btn = document.querySelector(".btn-otp");
        btn.innerText = "Sent!";
        btn.disabled = true;

        await fetch('/api/employees/request-otp', { method: 'POST' });
        
        alert("Authorization Code requested! Check your server console (or Telegram).");
        
        // Reset button after 30 seconds
        setTimeout(() => {
            btn.innerText = "Get OTP";
            btn.disabled = false;
        }, 30000);

    } catch (error) {
        console.error("Failed to request OTP:", error);
    }
});

// Verify the OTP against the backend
document.getElementById("btn-verify-otp").addEventListener("click", async () => {
    const otpInput = document.getElementById("otp_code").value;
    
    if (otpInput.length < 6) {
        alert("Please enter a valid 6-digit OTP.");
        return;
    }

    try {
        const response = await fetch('/api/employees/verify-otp', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ otp: otpInput })
        });
        
        const data = await response.json();

        if (data.valid) {
            // SUCCESS! Unlock the password field and highlight it green
            alert("Authorization Granted. You may now change the password.");
            const passField = document.getElementById("password_hash");
            passField.disabled = false;
            passField.style.borderColor = "var(--status-green)";
            passField.focus();
            
            // Clean up the UI
            document.getElementById("otp_code").value = "";
            document.getElementById("toggle-otp-section").checked = false;
            document.querySelector(".otp-container").style.display = "none";
        } else {
            alert("Invalid or Expired OTP. Please try again.");
        }

    } catch (error) {
        console.error("OTP Verification Error:", error);
    }
});