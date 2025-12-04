

from odoo import models, fields, api ,_
from dateutil.relativedelta import relativedelta
from odoo.exceptions import UserError # <--- Make sure to import UserError


class ROInstallation(models.Model):
    _name = 'ro.installation'
    _description = 'RO Installation Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default='New')
    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    sale_id = fields.Many2one('sale.order', string='Sale Order')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    
    # NEW: Serial Number Link
    lot_id = fields.Many2one('stock.lot', string='Serial Number', domain="[('product_id', '=', product_id)]")
    
    scheduled_date = fields.Datetime(string='Scheduled Date')
    assigned_to = fields.Many2one('res.users', string='Technician')
    status = fields.Selection([
        ('planned', 'Planned'),
        ('assigned', 'Assigned'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='planned', tracking=True)
    
    location = fields.Char(string='Location/Address')
    remarks = fields.Text(string='Remarks')
    done_date = fields.Date(string='Completion Date')

    # NEW: Photos and Signature
    installation_photo = fields.Binary(string="Installation Photo")
    customer_signature = fields.Binary(string="Customer Signature")

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('ro.installation') or 'New'
        return super(ROInstallation, self).create(vals)
        res = super(ROInstallation, self).create(vals)
        return res

    # original code given initially during code generation
    # def action_done(self):
    #     self.write({'status': 'done', 'done_date': fields.Date.today()})
        

    # original code during code generation
    # this code sync with sale_order.py changes
    # def action_done(self):
    #     """ 
    #     Mark installation as Done and Activate the Warranty automatically 
    #     (Delayed Activation Logic)
    #     """
    #     # 1. Mark Installation as Done
    #     today = fields.Date.today()
    #     self.write({'status': 'done', 'done_date': today})

    #     # [cite_start]2. DELAYED ACTIVATION LOGIC [cite: 175]
    #     # Find the draft warranty linked to this Sale and Product
    #     warranty = self.env['ro.warranty'].search([
    #         ('sale_id', '=', self.sale_id.id),
    #         ('product_id', '=', self.product_id.id),
    #         ('state', '=', 'draft')
    #     ], limit=1)

    #     if warranty:
    #         # Calculate new end date based on TODAY (Installation Date)
    #         duration = warranty.product_id.warranty_months
    #         new_end_date = today + relativedelta(months=duration)

    #         # Update and Activate the Warranty
    #         warranty.write({
    #             'start_date': today,
    #             'end_date': new_end_date,
    #             'state': 'active'
    #         })
            
    #         # Log a message in the Installation chatter confirming warranty activation
    #         self.message_post(body=f"Warranty {warranty.name} has been activated automatically.")
    
    
    # new code after changes told
    
    def action_done(self):
        """ Mark Installation Done → Instant Delivery + Warranty Activation (Odoo 17) """
        
        # 1. Strict Invoice Policy
        if self.sale_id and not self.sale_id.invoice_ids.filtered(lambda i: i.state == 'posted'):
            raise UserError(_("Strict Policy: You cannot complete the installation until a posted invoice exists for the linked Sales Order."))

        today = fields.Date.today()
        now = fields.Datetime.now()

        # 2. Get Delivery Operation Type
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'outgoing'),
            ('warehouse_id.company_id', '=', self.env.company.id)
        ], limit=1)

        if not picking_type:
            raise UserError(_("No Delivery operation type found!"))

        customer_loc = self.env.ref('stock.stock_location_customers')

        # 3. Create Picking + Move + Move Line in ONE shot (this bypasses all reservation issues)
        picking = self.env['stock.picking'].create({
            'partner_id': self.partner_id.id,
            'picking_type_id': picking_type.id,
            'location_id': picking_type.default_location_src_id.id,
            'location_dest_id': customer_loc.id,
            'origin': self.name,
            'move_ids_without_package': [(0, 0, {
                'name': self.product_id.display_name or self.product_id.name,
                'product_id': self.product_id.id,
                'product_uom_qty': 1.0,
                'product_uom': self.product_id.uom_id.id,
                'location_id': picking_type.default_location_src_id.id,
                'location_dest_id': customer_loc.id,
                'move_line_ids': [(0, 0, {
                    'product_id': self.product_id.id,
                    'product_uom_id': self.product_id.uom_id.id,
                    'quantity': 1.0,                    # <-- THIS IS THE KEY
                    'lot_id': self.lot_id.id,           # <-- Force serial number
                    'location_id': picking_type.default_location_src_id.id,
                    'location_dest_id': customer_loc.id,
                })]
            })]
        })

        # 4. Confirm + Validate directly (no assign, no manual loop needed)
        picking.action_confirm()
        
        # This validates immediately without any popup or reservation check
        picking.with_context(skip_backorder=True, skip_immediate=True).button_validate()

        # 5. Mark Installation as Done
        self.write({
            'status': 'done',
            'done_date': today,
            'scheduled_date': now,
        })

        # 6. Activate Warranty
        warranty = self.env['ro.warranty'].search([
            ('sale_id', '=', self.sale_id.id),
            ('product_id', '=', self.product_id.id),
            ('state', '=', 'draft')
        ], limit=1)

        if warranty:
            months = int(warranty.product_id.warranty_months or 12)
            warranty.write({
                'start_date': today,
                'end_date': today + relativedelta(months=months),
                'state': 'active',
                'lot_id': self.lot_id.id,
            })
            self.message_post(body=f"Warranty <strong>{warranty.name}</strong> activated automatically.")

        # 7. Success Notification
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success!',
                'message': 'Installation completed! Product delivered & warranty activated.',
                'type': 'success',
                'sticky': False,
            }
        }
    
    
    def action_open_form(self):
        """ Helper to open the form view from the tree view button """
        return {
            'type': 'ir.actions.act_window',
            'name': 'Installation Details',
            'res_model': 'ro.installation',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }