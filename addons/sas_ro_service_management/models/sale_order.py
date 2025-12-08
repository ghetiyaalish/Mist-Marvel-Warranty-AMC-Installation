from odoo import models, fields, api ,_
from dateutil.relativedelta import relativedelta
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'


    # warrenty starts when status is active
    
    # def action_confirm(self):
    #     res = super(SaleOrder, self).action_confirm()
    #     for order in self:
    #         for line in order.order_line:
    #             # Auto Create Warranty [cite: 19, 92]
    #             if line.product_id.warranty_months > 0:
    #                 self.env['ro.warranty'].create({
    #                     'partner_id': order.partner_id.id,
    #                     'sale_id': order.id,
    #                     'product_id': line.product_id.id,
    #                     'start_date': fields.Date.today(),
    #                     'end_date': fields.Date.today() + relativedelta(months=line.product_id.warranty_months),
    #                     'state': 'active'
    #                 })
    #     return res
    
    
    # We need to change the logic so that if a product requires installation, the warranty starts as "Draft" instead of "Active"
    # changes for this code made in sale_order.py , installation.py
    def action_confirm(self):
        res = super(SaleOrder, self).action_confirm()
        for order in self:
            for line in order.order_line:
                if line.product_id.warranty_months > 0:
                    # LOGIC CHANGE: Check if installation is required
                    if line.product_id.requires_installation:
                        warranty_state = 'draft' # Wait for installation
                    else:
                        warranty_state = 'active' # Start immediately

                    self.env['ro.warranty'].create({
                        'partner_id': order.partner_id.id,
                        'sale_id': order.id,
                        'product_id': line.product_id.id,
                        'start_date': fields.Date.today(),
                        'end_date': fields.Date.today() + relativedelta(months=line.product_id.warranty_months) - relativedelta(days=1),
                        'state': warranty_state  # Use the variable we set above
                    })
        return res

    def action_create_installation(self):
        """ Button to create Installation Order and OPEN it immediately """
        # 1. SECURITY CHECK: Ensure Invoice Exists
        if not self.invoice_ids:
             raise UserError(_("You cannot schedule an installation yet.\n\nPlease create the Invoice first."))
        
        installation = False
        
        for order in self:
            for line in order.order_line:
                if line.product_id.requires_installation:
                    # Create the record
                    installation = self.env['ro.installation'].create({
                        'partner_id': order.partner_id.id,
                        'sale_id': order.id,
                        'product_id': line.product_id.id,
                        'location': order.partner_shipping_id.contact_address or order.partner_id.contact_address,
                        'status': 'planned'
                    })
                    # Break after finding the first installable product 
                    # (to prevent opening 5 windows if you sell 5 items)
                    break 
        
        # If a record was created, return the action to open it
        if installation:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Installation Order',
                'res_model': 'ro.installation',
                'res_id': installation.id,
                'view_mode': 'form',
                'target': 'current',
            }