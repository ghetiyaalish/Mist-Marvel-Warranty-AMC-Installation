from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # Master Limits (Template for AMCs)
    amc_part_limit_ids = fields.One2many(
        'product.amc.limit', 
        'product_tmpl_id', 
        string="AMC Parts Limits"
    )

class ProductAMCLimit(models.Model):
    _name = 'product.amc.limit'
    _description = 'Master AMC Limits defined on Product'

    product_tmpl_id = fields.Many2one('product.template', string="Product Template")
    part_id = fields.Many2one('product.product', string="Part Name", required=True)
    allowed_qty = fields.Float(string="Allowed Qty (Per Year)", default=1.0)