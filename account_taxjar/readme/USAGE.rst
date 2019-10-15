To enable TaxJar special tax calculation on specific products, you must:

* Go to Product Form > Invoicing Tab > Select a TaxJar Category.

.. image:: ./static/img/select_taxjar_category.png
   :width: 80 %
   :align: center

To use TaxJar tax calculation on a invoice order, let's:

* Go to Invoicing > Sales > Customer Invoice and create an entry.

* You must ensure that selected customer has an associated Fiscal Position
  and this one is a Nexus one, otherwise TaxJar Calculation won't be
  executed.


Taxes will automatically generate when Invoice is validated or using
action Update taxes with TaxJar.

Notice that Update taxes with TaxJar action can be performed for multiple
records on a tree view.

.. image:: ./static/img/taxjar_account_invoice.png
   :width: 80 %
   :align: center
