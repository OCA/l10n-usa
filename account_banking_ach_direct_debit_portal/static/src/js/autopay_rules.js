document.addEventListener("DOMContentLoaded", function () {
    "use strict";

    const checkbox = document.getElementById("rule_disabled");

    if (checkbox) {
        checkbox.addEventListener("change", function () {
            const autopayValue = this.checked ? "end_of_month" : "disabled";

            fetch("/autopay-rules/change", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                    "X-CSRFToken": odoo.csrf_token,
                },
                body: JSON.stringify({
                    autopay_rule: autopayValue,
                }),
            })
                .then((response) => response.json())
                .then(() => {
                    window.location.href = "/autopay-rules";
                })
                .catch((error) => {
                    console.error("Error:", error);
                });
        });
    }
});
