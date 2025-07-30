document.addEventListener("DOMContentLoaded", async function () {
    "use strict";

    async function getLinkToken() {
        const res = await fetch("/payment/plaid/get_link_token", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({}),
        });

        const response = await res.json();
        return response.result;
    }

    const response = await getLinkToken();

    if (response.error) {
        console.error("Error getting link token: " + response.error);
        return;
    }

    const tryAgainBtn = document.getElementById("try-again-btn");

    /* global Plaid */
    const handler = Plaid.create({
        token: response.link_token,
        onSuccess: async function (public_token, metadata) {
            const verifyRes = await fetch("/my/banks/verify_submit", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    public_token: public_token,
                    account_id: metadata.accounts[0].id,
                }),
            });

            const verifyResponse = await verifyRes.json();

            const result = verifyResponse.result;

            if (result.status === "success") {
                window.location.href = "/my/banks?add_success=1";
            } else {
                console.error("Verification failed: " + result.error);
            }
        },
        onExit: function (err, metadata) {
            console.warn("User exited Plaid Link", err, metadata);
            tryAgainBtn.classList.remove("d-none");
        },
    });

    handler.open();

    tryAgainBtn.onclick = function () {
        tryAgainBtn.classList.add("d-none");
        handler.open();
    };
});
