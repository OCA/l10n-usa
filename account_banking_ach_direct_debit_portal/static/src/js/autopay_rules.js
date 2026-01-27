document.addEventListener("DOMContentLoaded", function () {
    "use strict";

    const checkbox = document.getElementById("rule_disabled");
    const oldRuleInput = document.querySelector("input[name='old_autopay_rule']");

    if (checkbox) {
        checkbox.addEventListener("change", function (event) {
            const noBankAccounts = document.querySelector("[name='no_bank_accounts']");
            const warningSpan = document.getElementById("autopay-warning");
            const termsAndConditions = document.getElementById("terms-and-conditions");
            const autopayValues = document.getElementById("autopay-values");
            const radioDisabled = document.querySelector(
                "input[name='autopay_value'][value='disabled']"
            );

            if (noBankAccounts && noBankAccounts.value === "True" && this.checked) {
                event.preventDefault();
                this.checked = false;

                if (warningSpan) {
                    warningSpan.classList.remove("d-none");
                }
                return;
            }

            if (warningSpan) {
                warningSpan.classList.add("d-none");
            }

            if (this.checked) {
                termsAndConditions.classList.add("d-none");
                autopayValues.classList.remove("d-none");

                document.querySelectorAll(".option-card-input").forEach((radio) => {
                    if (radio.value === oldRuleInput.value) {
                        radio.checked = true;
                    }
                });
            } else {
                termsAndConditions.classList.remove("d-none");
                autopayValues.classList.add("d-none");

                if (radioDisabled) {
                    radioDisabled.checked = true;
                }
            }
        });
    }
});
