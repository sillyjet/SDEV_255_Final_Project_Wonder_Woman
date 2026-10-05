const API_BASE = window.location.hostname === "localhost"
    ? ""
    : "https://sdev-255-final-project-wonder-woman.onrender.com";

const loginForm = document.getElementById("login-form");
const message = document.getElementById("message");

loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const username = document.getElementById("username").value;
    const password = document.getElementById("password").value;

    try {
        const response = await fetch(`${API_BASE}/api/login`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                username: username,
                password: password
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || "Login failed.");
        }

        
        localStorage.setItem("user", JSON.stringify(data.user));
        localStorage.setItem("token", data.token);

        
        window.location.href = "index.html";

    } catch (error) {
        message.textContent = error.message;
    }
});