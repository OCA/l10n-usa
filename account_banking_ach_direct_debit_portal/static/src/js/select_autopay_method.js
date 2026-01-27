document.addEventListener("DOMContentLoaded", function () {
    "use strict";

    const dropdown = document.getElementById("bankDropdown");

    if (!dropdown) return;

    const toggle = dropdown.querySelector(".bank-dropdown-toggle");
    const menu = dropdown.querySelector(".bank-dropdown-menu");
    const bank_id_input = dropdown.querySelector("[name='bank_id']");

    toggle.addEventListener("click", function () {
        menu.classList.toggle("d-none");
    });

    menu.querySelectorAll(".bank-option").forEach((option) => {
        option.addEventListener("click", function () {
            bank_id_input.value = this.id;

            toggle.querySelector(".bank-info").innerHTML = this.innerHTML;
            menu.classList.add("d-none");
        });
    });

    document.addEventListener("click", function (e) {
        if (!dropdown.contains(e.target)) {
            menu.classList.add("d-none");
        }
    });
});
