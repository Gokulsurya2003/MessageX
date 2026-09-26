const form = document.querySelector("#signupForm");

if (form) {
    form.addEventListener("submit", function(event) {

        const password = document.querySelector("#password").value;
        const confirmPassword = document.querySelector("#confirmPassword").value;

        if (password !== confirmPassword) {
            event.preventDefault();
            alert("Passwords do not match!");
            return;
        }

        const gender = document.querySelector('input[name="gender"]:checked').value;
        const username = document.querySelector("#username").value;
        const email = document.querySelector("#email").value;

        localStorage.setItem("gender", gender);
        localStorage.setItem("username", username);
        localStorage.setItem("email", email);
    });
}

function togglePassword(id, button) {
    const password = document.getElementById(id);

    if (password.type === "password") {
        password.type = "text";
        button.textContent = "🙈";
    } else {
        password.type = "password";
        button.textContent = "👁️";
    }
}