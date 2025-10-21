document.addEventListener("DOMContentLoaded", function () {
    "use strict";

    const repeatDay = document.getElementById("repeat-day");
    const autopay_specific_date_input = document.querySelector(
        "[name='autopay_specific_date']"
    );

    function ordinal(n) {
        const j = n % 10,
            k = n % 100;
        if (j === 1 && k !== 11) return n + "st";
        if (j === 2 && k !== 12) return n + "nd";
        if (j === 3 && k !== 13) return n + "rd";
        return n + "th";
    }

    function getRepeatDay() {
        const day = new Date(autopay_specific_date_input.value).getDate();
        if (day) {
            repeatDay.textContent = ordinal(day);
        }
    }

    if (autopay_specific_date_input) {
        autopay_specific_date_input.addEventListener("change", getRepeatDay);
        getRepeatDay();
    }
});
