odoo.define("account_banking_ach_direct_debit_portal.payment_form", (require) => {
    "use strict";

    const checkoutForm = require("payment.checkout_form");
    const manageForm = require("payment.manage_form");

    const PaymentMixin = {
        // eslint-disable-next-line no-unused-vars
        _prepareTransactionRouteParams: function (code, paymentOptionId, flow) {
            const transactionRouteParams = this._super(...arguments);
            return {
                ...transactionRouteParams,
                invoices: Array.isArray(this.txContext.invoices)
                    ? this.txContext.invoices
                    : [],
                surcharge_amount: parseFloat(this.txContext.surchargeAmount)
                    ? this.txContext.surchargeAmount
                    : 0.0,
            };
        },
    };

    checkoutForm.include(PaymentMixin);
    manageForm.include(PaymentMixin);
});
