from odoo import api, models


class File(models.Model):
    _inherit = "dms.file"

    @api.model_create_multi
    def create(self, vals_list):
        document = super().create(vals_list=vals_list)
        # Find a matching workflow rule
        rule = self.env["dms.workflow.rule"].search(
            [("dms_exemption_folder", "=", document.directory_id.parent_id.id)], limit=1
        )
        if (
            rule
            and rule.dms_exemption_folder == document.root_directory_id
            and self.env.company.documents_exemption_settings
        ):
            rule.apply_rule(document)
        return document
