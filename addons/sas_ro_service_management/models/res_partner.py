from odoo import models, fields

class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_ro_customer = fields.Boolean(string="Is RO Customer")
    last_service_date = fields.Date(string="Last Service Date")