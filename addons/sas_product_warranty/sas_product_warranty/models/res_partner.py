from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class ResPartner(models.Model):
    _inherit = 'res.partner'

    product_purchase_ids = fields.One2many(
        'warranty.history',
        'partner_id',
        string='Purchased Products with Warranty'
    )

    @api.depends('sale_order_ids')
    def _compute_warranty_products(self):
        for partner in self:
            warranty_products = self.env['sale.order.line'].search([
                ('order_id.partner_id', '=', partner.id),
                # ('product_id.product_tmpl_id.is_warranty_available', '=', True)
            ]).mapped('product_id.product_tmpl_id')
            _logger.info(f"=====warranty_products===:{warranty_products }")
            partner.warranty_product_ids = warranty_products
   