document.addEventListener("DOMContentLoaded", function () {
    "use strict";

    const dropdown = document.getElementById("bankPaymentDropdown");

    if (!dropdown) return;

    const toggle = dropdown.querySelector(".bank-dropdown-toggle");
    const menu = dropdown.querySelector(".bank-dropdown-menu");
    const hiddenInput = dropdown.querySelector("input[type='hidden']");

    toggle.addEventListener("click", function () {
        menu.classList.toggle("d-none");
    });

    const applySelectedFromValue = () => {
        const val = hiddenInput.value;
        menu.querySelectorAll(".bank-option").forEach((opt) => {
            opt.classList.toggle("selected", opt.id === val);
        });
    };
    applySelectedFromValue();

    menu.querySelectorAll(".bank-option").forEach((option) => {
        option.addEventListener("click", function () {
            const bankId = this.id;

            toggle.querySelector(".bank-info").innerHTML = this.innerHTML;
            const checkIcon = toggle.querySelector(".checkmark");
            if (checkIcon) checkIcon.remove();

            hiddenInput.value = bankId;

            menu.classList.add("d-none");

            applySelectedFromValue();
        });
    });

    document.addEventListener("click", function (e) {
        if (!dropdown.contains(e.target)) {
            menu.classList.add("d-none");
        }
    });
});
