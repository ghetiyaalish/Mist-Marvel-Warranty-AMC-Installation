from dateutil.relativedelta import relativedelta
from odoo import fields, models
class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    warranty_expiry = fields.Date(string='Warranty Expiry Date')
    warranty_number = fields.Char(string='Warranty Number')


class SaleOrder(models.Model):
    """Inherited sale order to super functions to add additional
    functionalities"""
    _inherit = 'sale.order'

    is_warranty_check = fields.Boolean(string='Warranty Check',
                                       help='Check this box if the item has'
                                            ' warranty.')

    def action_confirm(self):
        """Call the super method to perform the default confirmation
        behavior"""
        super(SaleOrder, self).action_confirm()
        # Loop through the order lines and check warranty for each product
        for order in self:
            for line in order.order_line:
                product = line.product_id
                if product.is_warranty_available:
                    line.warranty_expiry = self.date_order + relativedelta(months=product.warranty_duration)
                    line.warranty_number = product.warranty_number
                    line_lots = self.env['stock.move.line'].search([
                        ('product_id', '=', line.product_id.id),
                        ('lot_id', '!=', False),
                        ('picking_id.origin', '=', self.name),
                    ])

                    lot_ids = line_lots.mapped('lot_id').ids

                    self.env['warranty.history'].create({
                        'partner_id': order.partner_id.id,
                        'product_id': line.product_id.id,
                        'order_id': order.id,
                        'product_quantity': line.product_uom_qty,
                        'warranty_duration': line.product_id.warranty_duration or 0,
                        'warranty_expiry' : line.warranty_expiry,
                        'warranty_number' : line.warranty_number,
                        'lot_ids': [(6, 0, lot_ids)],
                    })
                    self.is_warranty_check = True
                else:
                    self.is_warranty_check = False
        if (self.order_line.
                filtered(lambda x: x.product_id.is_warranty_available)):
            self.is_warranty_check = True
        else:
            self.is_warranty_check = False

    def action_open_smart_tab(self):
        """ To open warranty smart tab"""
        domain = [
            ('id', 'in',
             self.order_line.mapped('product_id.product_tmpl_id.id')),
            ('is_warranty_available', '=', True),
        ]
        products_with_warranty = self.env['product.template'].search(domain)
        for product in products_with_warranty:
            # Calculate the warranty expiry date based on the sale order date
            warranty_expiry_date = self.date_order + relativedelta(
                months=product.warranty_duration)
            product.write({'warranty_expiry': warranty_expiry_date})
        return {
            'type': 'ir.actions.act_window',
            'name': 'Warranty Details',
            'view_mode': 'tree,form',
            'res_model': 'product.template',
            'views': [(self.env.ref('sas_product_warranty.'
                                    'product_template_view_tree').id, 'tree'),
                      (self.env.ref('sas_product_warranty.'
                                    'product_template_view_form').id, 'form')],
            'domain': domain
        }
