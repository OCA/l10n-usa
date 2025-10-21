document.addEventListener("DOMContentLoaded", function () {
    "use strict";

    const saveBtn = document.getElementById("autopay-rules-save-button");

    const oldRuleInput = document.querySelector("input[name='old_autopay_rule']");
    const oldAutopayMethod = document.querySelector("input[name='old_autopay_method']");
    const oldDateInput = document.querySelector(
        "input[name='old_autopay_specific_date']"
    );

    const ruleToggle = document.getElementById("rule_disabled");

    const autopayValueRadios = document.querySelectorAll("input[name='autopay_value']");
    const autopayMethodInput = document.querySelector("input[name='bank_id']");
    const dateInput = document.querySelector("input[name='autopay_specific_date']");

    if (!saveBtn) return;

    const initialState = {
        rule: oldRuleInput.value || "disabled",
        method: oldAutopayMethod.value || "",
        date: oldDateInput.value || "",
    };

    function getCurrentState() {
        let selected = "disabled";
        autopayValueRadios.forEach(function (radio) {
            if (radio.checked) {
                selected = radio.value;
            }
        });

        return {
            rule: selected,
            method: autopayMethodInput ? autopayMethodInput.value : "",
            date: dateInput ? dateInput.value || "" : "",
        };
    }

    function checkChanges() {
        const current = getCurrentState();

        const ruleChanged = current.rule !== initialState.rule;
        const methodChanged =
            current.rule !== "disabled" &&
            current.method !== String(initialState.method);
        const dateChanged =
            current.rule === "specific_date" && current.date !== initialState.date;

        if (ruleChanged || methodChanged || dateChanged) {
            saveBtn.classList.remove("d-none");
        } else {
            saveBtn.classList.add("d-none");
        }
    }

    if (ruleToggle) {
        ruleToggle.addEventListener("change", () => {
            setTimeout(checkChanges, 0);
        });
    }

    autopayValueRadios.forEach(function (radio) {
        radio.addEventListener("change", checkChanges);
    });

    if (dateInput) {
        dateInput.addEventListener("change", checkChanges);
        dateInput.addEventListener("input", checkChanges);
    }

    const bankOptions = document.querySelectorAll(".bank-option");
    bankOptions.forEach(function (option) {
        option.addEventListener("click", function () {
            setTimeout(checkChanges, 0);
        });
    });
});
