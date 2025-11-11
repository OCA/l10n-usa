document.addEventListener("DOMContentLoaded", function () {
    "use strict";

    const checkbox = document.getElementById("rule_disabled");
    const autopayValues = document.getElementById("autopay-values");
    const autopayEnabledInput = document.getElementById("autopay_enabled");

    if (checkbox && autopayValues && autopayEnabledInput) {
        checkbox.addEventListener("change", function () {
            if (this.checked) {
                autopayValues.classList.remove("d-none");
                autopayEnabledInput.value = "1";

                const anyChecked = document.querySelector(".autopay-radio:checked");
                if (!anyChecked) {
                    const defaultRadio = document.getElementById("rule_1");
                    if (defaultRadio) {
                        defaultRadio.checked = true;
                    }
                }
            } else {
                autopayValues.classList.add("d-none");
                autopayEnabledInput.value = "0";

                const radios = document.querySelectorAll(".autopay-radio");
                radios.forEach((r) => {
                    r.checked = false;
                });
            }
        });
    }
});
