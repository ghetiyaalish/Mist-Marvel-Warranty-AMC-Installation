from odoo import models, fields, api, _
from odoo.exceptions import UserError

class FetchOrdersWizard(models.TransientModel):
    _name = 'ro.fetch.orders.wizard'
    _description = 'Fetch Orders to Invoice'

    partner_id = fields.Many2one('res.partner', string="Customer", required=True)
    # Filter: Only show Chargeable, Done, and NOT Invoiced orders
    service_order_ids = fields.Many2many(
        'ro.service.order', 
        string="Orders to Invoice",
        domain="[('partner_id', '=', partner_id), ('state', '=', 'done'), ('chargeable', '=', True)]"
    )

    def action_create_bulk_invoice(self):
        if not self.service_order_ids:
            raise UserError(_("Please select at least one order to invoice."))

        invoice_lines = []
        
        # Loop through selected orders and gather items
        for order in self.service_order_ids:
            # 1. Add Parts
            for part in order.parts_line_ids:
                invoice_lines.append((0, 0, {
                    'product_id': part.product_id.id,
                    'quantity': part.qty,
                    'price_unit': part.unit_price,
                    'name': f"Part: {part.product_id.name} (Order: {order.name})"
                }))
            
            # 2. Mark order as Invoiced so it doesn't appear again
            order.write({'state': 'invoiced'})

        # 3. Create the Single Invoice
        if not invoice_lines:
            raise UserError(_("No invoiceable lines found in selected orders."))

        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_line_ids': invoice_lines,
        })

        # 4. Open the Invoice
        return {
            'name': _('Consolidated Invoice'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
        }