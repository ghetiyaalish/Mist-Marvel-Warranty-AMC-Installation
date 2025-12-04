from dateutil.relativedelta import relativedelta
from odoo import fields, models, api

class WarrantyHistory(models.Model):
    _name = 'warranty.history'
    _description = 'Warranty History'

    partner_id = fields.Many2one('res.partner', string='Customer')
    product_id = fields.Many2one('product.product', string='Product')
    order_id = fields.Many2one('sale.order', string='Sale Order')
    order_date = fields.Datetime(related='order_id.date_order', string='Order Date')
    warranty_duration = fields.Integer(string='Warranty Duration (Month)')
    warranty_number = fields.Char(string="Warranty Number", readonly=True, copy=False, help="Unique warranty number like serial number")
    warranty_expiry = fields.Date(
        compute='_compute_warranty_expiry', store=True, string='Warranty Expiry'
    )
    product_quantity = fields.Integer(string='Product Quantity')
    lot_ids = fields.Many2many('stock.lot', string='Serial Numbers')
