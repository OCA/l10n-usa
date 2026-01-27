document.addEventListener("DOMContentLoaded", function () {
    "use strict";

    const checkboxes = document.querySelectorAll(".invoice-checkbox");
    const payButton = document.querySelector(".pay-btn");
    const manageBankBtn = document.querySelector(".manage-bank-btn");

    function updateActionVisibility() {
        const anyChecked = Array.from(checkboxes).some((cb) => cb.checked);
        if (anyChecked) {
            payButton.classList.remove("d-none");

            if (manageBankBtn) {
                manageBankBtn.classList.add("d-none");
            }
        } else {
            payButton.classList.add("d-none");

            if (manageBankBtn) {
                manageBankBtn.classList.remove("d-none");
            }
        }
    }

    if (checkboxes && payButton) {
        checkboxes.forEach((cb) => {
            cb.addEventListener("change", updateActionVisibility);
        });

        // Initial state
        updateActionVisibility();

        payButton.addEventListener("click", function () {
            const selectedInvoices = [];
            document
                .querySelectorAll(".invoice-checkbox:checked")
                .forEach(function (checkbox) {
                    selectedInvoices.push(checkbox.value);
                });

            let url = "/select-payment-method";

            if (selectedInvoices.length > 0) {
                const query = selectedInvoices
                    .map((id) => "invoice=" + encodeURIComponent(id))
                    .join("&");
                url += "?" + query;

                window.location.href = url;
            }
        });
    }
});
