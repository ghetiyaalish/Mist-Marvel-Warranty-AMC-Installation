
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
    
    # Add this new field
    # installation_type = fields.Selection([
    #     ('new', 'New Installation'),
    #     ('reinstall', 'Reinstallation / Shifting')
    # ], string='Order Type', default='new', required=True, tracking=True)
    
    
    
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
    installation_line_ids = fields.One2many('ro.installation.line', 'installation_id', string="Extra Parts Used")
    
    # New Field to link the created invoice
    invoice_id = fields.Many2one('account.move', string="Invoice", readonly=True)

    installation_type = fields.Selection([
        ('new', 'New Installation'),
        ('reinstall', 'Reinstallation / Shifting')
    ], string='Job Type', default='new', required=True)


    new_shifting_address = fields.Text(string="New Address (Shifting To)", 
                                     help="Enter the new location where RO will be installed")

    # --- AUTO-FILL LOGIC ---
    @api.onchange('partner_id')
    def _onchange_partner_data_reinstall(self):
        """
        When Customer is selected:
        1. Auto-fill 'location' with their current address.
        2. Auto-find the Product (check Warranty first, then last Installation).
        """
        if self.partner_id:
            # 1. Fill Current Address into your 'location' field
            self.location = self.partner_id.contact_address

            # 2. Find their Product automatically
            # Priority A: Check Active Warranty
            # (Assuming you have a model 'ro.warranty', otherwise remove this block)
            warranty = self.env['ro.warranty'].search([
                ('partner_id', '=', self.partner_id.id),
                ('state', '=', 'active')
            ], limit=1)
            
            if warranty:
                self.product_id = warranty.product_id.id
            else:
                # Priority B: Check Last Done Installation
                last_install = self.env['ro.installation'].search([
                    ('partner_id', '=', self.partner_id.id),
                    ('status', '=', 'done')
                ], order='done_date desc', limit=1)
                
                if last_install:
                    self.product_id = last_install.product_id.id
                    # self.sale_id = last_install.sale_id.id  

    def action_create_invoice(self):
        """ Create an Invoice for the Extra Parts used """
        self.ensure_one()

        # 1. Validation: Don't create if no parts or already invoiced
        if not self.installation_line_ids:
            raise UserError(_("There are no extra parts to invoice."))
        
        if self.invoice_id:
            raise UserError(_("An invoice has already been created for this installation."))


        gst_treatment = self.partner_id.l10n_in_gst_treatment
        
        # List of B2B Treatments
        b2b_types = ['regular', 'composition', 'special_economic_zone', 'deemed_export']
        
        if gst_treatment in b2b_types:
            # Search for the B2B Journal we created in Step 1
            journal = self.env['account.journal'].search([('code', '=', 'B2B'), ('type', '=', 'sale')], limit=1)
        else:
            # Default to B2C for Consumer / Unregistered
            journal = self.env['account.journal'].search([('code', '=', 'B2C'), ('type', '=', 'sale')], limit=1)

        # Fallback: If journals aren't found, use the default one
        if not journal:
            journal = self.env['account.journal'].search([('type', '=', 'sale')], limit=1)


        # 2. Prepare Invoice Lines
        invoice_lines = []
        for line in self.installation_line_ids:
            invoice_lines.append((0, 0, {
                'product_id': line.product_id.id,
                'name': f"Extra Part: {line.product_id.name}",
                'quantity': line.qty,
                'price_unit': line.unit_price,
            }))

        # 3. Create the Invoice Record
        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_origin': self.name,
            'journal_id': journal.id,  # <--- THIS LINE SETS THE SEQUENCE (B2B/B2C)
            'ro_technician_id': self.assigned_to.id,
            'invoice_line_ids': invoice_lines,
        }
        
        invoice = self.env['account.move'].create(invoice_vals)
        self.invoice_id = invoice.id

        # 4. Return action to show the invoice immediately
        return {
            'type': 'ir.actions.act_window',
            'name': 'Invoice',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_view_invoice(self):
        """ Smart button to view the invoice later """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Invoice',
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

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
                'end_date': today + relativedelta(months=months) - relativedelta(days=1),
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
        
        
        
# --- NEW CLASS FOR THE LINES ---
class RoInstallationLine(models.Model):
    _name = 'ro.installation.line'
    _description = 'Installation Extra Parts'

    installation_id = fields.Many2one('ro.installation', string="Installation Ref")
    
    product_id = fields.Many2one('product.product', string="Product", required=True)
    qty = fields.Float(string="Quantity", default=1.0)
    unit_price = fields.Float(string="Unit Price", related='product_id.list_price', readonly=False)
    
    # Simple subtotal
    subtotal = fields.Float(string="Subtotal", compute='_compute_subtotal')

    @api.depends('qty', 'unit_price')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.qty * line.unit_price


