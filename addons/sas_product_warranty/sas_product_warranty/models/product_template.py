from odoo import fields, models,api


class ProductTemplate(models.Model):
    """Inherited product template to add fields"""
    _inherit = 'product.template'

    is_warranty_available = fields.Boolean(string="Warranty Available",
                                           help="Boolean field to check"
                                                "the warranty availability")
    warranty_duration = fields.Integer(string="Warranty Duration (months)",
                                       help="Warranty duration")
    warranty_expiry = fields.Date(string="Warranty Expiry Date",
                                  help="Warranty expiry date")
    warranty_number = fields.Char(string="Warranty Number", readonly=True, copy=False, help="Unique warranty number like serial number")

    warranty_partner_id = fields.Many2one('res.partner', string="Warranty Customer")

    @api.model
    def create(self, vals):
        if not vals.get('warranty_number'):
            vals['warranty_number'] = self.env['ir.sequence'].next_by_code('product.warranty.number') or '/'
        return super(ProductTemplate, self).create(vals)