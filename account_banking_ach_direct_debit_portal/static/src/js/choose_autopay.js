document.addEventListener("DOMContentLoaded", function () {
    "use strict";

    const autopay_specific_date_input = document.querySelector(
        "[name='autopay_specific_date']"
    );

    document.querySelectorAll(".option-card-input").forEach((radio) => {
        radio.addEventListener("click", function () {
            const card = this.closest(".option-card");
            const extra = card.querySelector(".option-extra");

            document
                .querySelectorAll(".option-extra")
                .forEach((el) => el.classList.add("d-none"));

            if (extra) {
                extra.classList.remove("d-none");
            }

            if (autopay_specific_date_input) {
                autopay_specific_date_input.required = this.value === "specific_date";
            }
        });
    });
});
