from odoo import models, fields, api, _
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta
from datetime import date, timedelta

import logging
_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'
    
    ro_technician_id = fields.Many2one('res.users', string="Technician", help="Technician who performed the service")
    
    # Reporting Fields
    customer_contact = fields.Char(related='partner_id.phone', string="Contact", store=True)
    voucher_type = fields.Char(string="Vch. Type", compute='_compute_voucher_type', store=True)
    payment_mode_name = fields.Char(string="Payment Mode", compute='_compute_payment_info', store=True)
    amount_paid_total = fields.Monetary(string="Paid Amt", currency_field='currency_id', compute='_compute_amount')

    @api.depends('move_type', 'invoice_origin')
    def _compute_voucher_type(self):
        for rec in self:
            if rec.move_type == 'out_invoice':
                if rec.invoice_origin and 'SRV' in rec.invoice_origin:
                    rec.voucher_type = 'COMPLAIN'
                elif rec.invoice_origin and 'AMC' in rec.invoice_origin:
                    rec.voucher_type = 'BOS-AMC'
                else:
                    rec.voucher_type = 'BOS-SALES'
            else:
                rec.voucher_type = 'OTHER'

    @api.depends('payment_state')
    def _compute_payment_info(self):
        for rec in self:
            if rec.payment_state in ['paid', 'in_payment']:
                payments = rec._get_reconciled_payments()
                if payments:
                    rec.payment_mode_name = payments[0].journal_id.name
                else:
                    rec.payment_mode_name = 'Paid'
            else:
                rec.payment_mode_name = 'Unpaid'

class ROServiceOrder(models.Model):
    _name = 'ro.service.order'
    _description = 'Service Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default='New')
    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    # partner_address = fields.Char(related='partner_id.contact_address', string="Address",store=True)
    partner_address = fields.Char(string="Address")
    contract_id = fields.Many2one('ro.amc', string='AMC Contract')
    warranty_id = fields.Many2one('ro.warranty', string='Warranty')
    
    # product_id = fields.Many2one('product.product', string='Product' )
    product_id = fields.Many2one(
        'product.product', 
        string='Product'
    )
    allowed_product_ids = fields.Many2many('product.product', string="Allowed Products", compute='_compute_allowed_products', store=False)
    
    
    reported_date = fields.Date(string='Reported Date', default=fields.Date.context_today)
    scheduled_date = fields.Date(string='Scheduled Date')
    done_date = fields.Date(string='Done Date')
    assigned_to = fields.Many2one('res.users', string='Technician')
    
    issue_type = fields.Selection([
        ('leakage', 'Water Leakage'),
        ('low_flow', 'Low Water Flow'),
        ('bad_taste', 'Bad Taste/Smell'),
        ('not_starting', 'Machine Not Starting'),
        ('filter_change', 'Filter Change Request'),
        ('other', 'Other')
    ], string="Issue Type")

    action_taken = fields.Selection([
        ('repair', 'Repair'),
        ('replace', 'Part Replacement'),
        ('service', 'General Service'),
        ('adjustment', 'Adjustment/Cleaning'),
        ('other', 'Other')
    ], string="Action Taken")

    diagnosis = fields.Text(string='Diagnosis')
    service_notes = fields.Text(string='Service Notes')
    parts_line_ids = fields.One2many('ro.service.part.line', 'service_order_id', string='Parts Used')
    warranty_coverage = fields.Selection(related='warranty_id.coverage', string="Warranty Coverage", readonly=True)
    
    state = fields.Selection([
        ('new', 'New'),
        ('assigned', 'Assigned'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('invoiced', 'Invoiced'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='new', tracking=True)
    
    chargeable = fields.Boolean(string='Chargeable', default=False, help="If True, create invoice")
        
    
    def action_complete(self):
        """ 
        Main Method:
        1. Deduct Stock from Technician's Van (if parts used).
        2. Mark Order as Done.
        3. Update AMC consumption.
        """
        _logger.info(f"--- STARTING STOCK MOVE FOR ORDER: {self.name} ---")

        # 1. Check & Move Stock
        if self.parts_line_ids:
            self._move_stock_from_technician_van()

        # 2. Update Status
        self.write({
            'state': 'done',
            'done_date': fields.Date.today()
        })

        # 3. Update AMC
        if self.contract_id:
            self.contract_id.update_consumption()
            
        _logger.info(f"--- ORDER {self.name} COMPLETED SUCCESSFULLY ---")
        return True

    def _move_stock_from_technician_van(self):
        """ 
        Creates a 'Direct' Transfer from Tech Location -> Customer 
        Forces the location at every level to prevent Odoo defaults.
        """
        self.ensure_one()

        # --- A. GET TECHNICIAN LOCATION ---
        if not self.assigned_to:
            raise UserError(_("No Technician assigned to this order."))

        van_config = self.env['ro.van.stock'].search([
            ('technician_id', '=', self.assigned_to.id)
        ], limit=1)

        if not van_config:
            raise UserError(_(f"Configuration Error: Technician '{self.assigned_to.name}' has no Van Stock configured."))
        
        tech_location = van_config.location_id
        customer_location = self.env.ref('stock.stock_location_customers')

        # --- B. GET PICKING TYPE ---
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'outgoing'),
            ('warehouse_id.company_id', 'in', [self.env.company.id, False])
        ], limit=1)
        
        if not picking_type:
            raise UserError("System Error: No 'Outgoing' picking type found.")

        # --- C. CREATE PICKING (HEADER) ---
        picking = self.env['stock.picking'].create({
            'partner_id': self.partner_id.id,
            'picking_type_id': picking_type.id,
            'location_id': tech_location.id,        # <--- FORCE LOCATION HERE
            'location_dest_id': customer_location.id,
            'origin': self.name,
            'move_type': 'direct', 
        })

        # --- D. CREATE MOVES (LINES) ---
        moves_created = False
        for line in self.parts_line_ids:
            if line.qty > 0:
                moves_created = True
                self.env['stock.move'].create({
                    'name': line.product_id.display_name,
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.qty,
                    'product_uom': line.product_id.uom_id.id,
                    'picking_id': picking.id,
                    'location_id': tech_location.id,        # <--- FORCE LOCATION HERE
                    'location_dest_id': customer_location.id,
                    'state': 'draft',
                })

        if not moves_created:
            return

        # --- E. CONFIRM ---
        picking.action_confirm()
        
        # --- F. FORCE "DONE" QUANTITIES & LOCATION ---
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty 
            
            # 1. Update the Move itself just in case
            move.write({'location_id': tech_location.id})

            # 2. Handle Move Lines (Physical movement)
            if not move.move_line_ids:
                self.env['stock.move.line'].create({
                    'move_id': move.id,
                    'product_id': move.product_id.id,
                    'product_uom_id': move.product_uom.id,
                    'quantity': move.product_uom_qty,
                    'location_id': tech_location.id,       # <--- FORCE LOCATION HERE
                    'location_dest_id': customer_location.id,
                    'picking_id': picking.id,
                })
            else:
                for move_line in move.move_line_ids:
                    move_line.write({
                        'location_id': tech_location.id,   # <--- FORCE UPDATE LOCATION
                        'quantity': move.product_uom_qty
                    })

        # --- G. VALIDATE ---
        picking.with_context(skip_immediate=True).button_validate()
    
    
    # working code , by grok
    # def action_complete(self):
    #     """ Deduct Inventory from TECHNICIAN LOCATION and Close Order """
    #     # 1. Validation: Technician is mandatory
    #     if not self.assigned_to:
    #         raise UserError(_("Please assign a Technician before marking as Done."))
    #     # 2. Find Technician's Location Config
    #     van_config = self.env['ro.van.stock'].search([
    #         ('technician_id', '=', self.assigned_to.id)
    #     ], limit=1)
    #     if not van_config:
    #         raise UserError(_(f"Configuration Missing!\n\n"
    #                         f"Technician '{self.assigned_to.name}' does not have a configured Stock Location.\n"
    #                         f"Please go to: Inventory > Technician Stock > New\n"
    #                         f"And assign a location (e.g., WH/Stock/Technician) to this user."))
    #     # This is the location we MUST use
    #     tech_location_id = van_config.location_id.id
    #     # 3. Get Picking Type
    #     picking_type = self.env['stock.picking.type'].search([
    #         ('code', '=', 'outgoing'),
    #         ('warehouse_id.company_id', 'in', [self.env.company.id, False])
    #     ], limit=1)
    #     if not picking_type:
    #         raise UserError("No 'Outgoing' picking type found for the current company.")
    #     # 4. Create Delivery Order Header (Force Location Here)
    #     picking = self.env['stock.picking'].create({
    #         'partner_id': self.partner_id.id,
    #         'picking_type_id': picking_type.id,
    #         'location_id': tech_location_id,  # <--- FORCE HEADER SOURCE
    #         'location_dest_id': self.env.ref('stock.stock_location_customers').id,
    #         'origin': self.name,
    #         'move_type': 'direct',
    #     })
    #     has_parts = False
    #     if self.parts_line_ids:
    #         for line in self.parts_line_ids.filtered(lambda l: l.qty > 0):
    #             has_parts = True
    #             # 5. Create Stock Move (Logical Request)
    #             self.env['stock.move'].create({
    #                 'name': line.product_id.display_name,
    #                 'product_id': line.product_id.id,
    #                 'product_uom_qty': line.qty,
    #                 'product_uom': line.product_id.uom_id.id,
    #                 'picking_id': picking.id,
    #                 'location_id': tech_location_id,  # <--- FORCE MOVE SOURCE
    #                 'location_dest_id': self.env.ref('stock.stock_location_customers').id,
    #                 'state': 'draft',
    #             })
    #         if has_parts:
    #             # 6. Confirm Picking (Generates moves, but we SKIP auto-reservation)
    #             picking.action_confirm()
    #             # DO NOT CALL action_assign()! It might revert to main warehouse.
    #             # 7. MANUALLY CREATE MOVE LINES (The Fix)
    #             for move in picking.move_ids:
    #                 move.quantity = move.product_uom_qty  # Set Done Qty
    #                 self.env['stock.move.line'].create({
    #                     'move_id': move.id,
    #                     'product_id': move.product_id.id,
    #                     'product_uom_id': move.product_uom.id,
    #                     'quantity': move.product_uom_qty,
    #                     'location_id': tech_location_id,  # <--- CRITICAL: Forces Tech Location
    #                     'location_dest_id': self.env.ref('stock.stock_location_customers').id,
    #                     'picking_id': picking.id,
    #                 })
    #             # 8. Validate
    #             picking.with_context(skip_immediate=True, skip_backorder=True).button_validate()
    #     # 9. Finalize Order
    #     self.write({'state': 'done', 'done_date': fields.Date.today()})
    #     if self.contract_id:
    #         self.contract_id.update_consumption()
    #     return True
        
    def _consume_parts_from_van(self):
        """ Creates Delivery Order from Technician Location -> Customer """
        self.ensure_one()
        
        # ERROR FIX: Use 'assigned_to', not 'technician_id'
        if not self.assigned_to:
            raise UserError(_("Please assign a Technician before marking as Done."))

        # 1. Find Van Stock Configuration
        van_config = self.env['ro.van.stock'].search([
            ('technician_id', '=', self.assigned_to.id)
        ], limit=1)

        if not van_config:
            raise UserError(_(f"No Stock Location configured for technician '{self.assigned_to.name}'.\nPlease go to Inventory > Technician Stock and configure it."))

        source_location = van_config.location_id.id
        customer_location = self.env.ref('stock.stock_location_customers').id 

        # 2. Create Picking Header
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_out').id, 
            'location_id': source_location,       
            'location_dest_id': customer_location, 
            'origin': self.name,
            'partner_id': self.partner_id.id,
            'move_type': 'direct',
        })

        # 3. Create Moves
        has_moves = False
        for part in self.parts_line_ids:
            if part.qty > 0:
                has_moves = True
                self.env['stock.move'].create({
                    'name': part.product_id.name,
                    'product_id': part.product_id.id,
                    'product_uom_qty': part.qty,  # Demand
                    'product_uom': part.product_id.uom_id.id,
                    'location_id': source_location,
                    'location_dest_id': customer_location,
                    'picking_id': picking.id
                })

        if not has_moves:
            return

        # 4. Confirm Picking
        picking.action_confirm()
        picking.action_assign() # Try to reserve stock

        # 5. FORCE VALIDATION (Fixes "Not Moving" issue)
        # Even if tech has 0 stock, we force the done quantity
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty # Set Done = Demand
            
            # If reservation failed (0 stock available), explicitly create the line
            if not move.move_line_ids:
                self.env['stock.move.line'].create({
                    'move_id': move.id,
                    'product_id': move.product_id.id,
                    'product_uom_id': move.product_uom.id,
                    'quantity': move.product_uom_qty,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                    'picking_id': picking.id,
                })

        # 6. Validate
        picking.button_validate()
    
    # def action_complete(self):
    #     """ Deduct Inventory from TECHNICIAN LOCATION and Close Order """
    #     if self.parts_line_ids:
    #         # Get the source location (technician's or main warehouse)
    #         source_location = self._get_source_location()
            
    #         # Get outgoing picking type
    #         picking_type = self.env['stock.picking.type'].search([
    #             ('code', '=', 'outgoing'),
    #             ('warehouse_id.company_id', 'in', [self.env.company.id, False])
    #         ], limit=1)
            
    #         if not picking_type:
    #             raise UserError(_("No outgoing picking type found for current company."))

    #         # Create Delivery Order
    #         picking = self.env['stock.picking'].create({
    #             'partner_id': self.partner_id.id,
    #             'picking_type_id': picking_type.id,
    #             'location_id': source_location,  # <--- Uses Technician Location
    #             'location_dest_id': self.env.ref('stock.stock_location_customers').id,
    #             'origin': self.name,
    #             'move_type': 'direct',
    #         })

    #         # Create stock moves
    #         moves_to_do = []
    #         for line in self.parts_line_ids.filtered(lambda l: l.qty > 0):
    #             move = self.env['stock.move'].create({
    #                 'name': line.product_id.display_name,
    #                 'product_id': line.product_id.id,
    #                 'product_uom_qty': line.qty,
    #                 'product_uom': line.product_id.uom_id.id,
    #                 'picking_id': picking.id,
    #                 'location_id': source_location,  # <--- Uses Technician Location
    #                 'location_dest_id': self.env.ref('stock.stock_location_customers').id,
    #                 'state': 'draft',
    #             })
    #             moves_to_do.append(move)

    #         if not moves_to_do:
    #             self.write({'state': 'done', 'done_date': fields.Date.today()})
    #             if self.contract_id:
    #                 self.contract_id.update_consumption()
    #             return

    #         # Confirm & Assign
    #         picking.action_confirm()
    #         picking.action_assign()

    #         # Force "DONE" QUANTITY
    #         for move in picking.move_ids:
    #             move.quantity = move.product_uom_qty
    #             # Also update move lines
    #             if not move.move_line_ids:
    #                 self.env['stock.move.line'].create({
    #                     'move_id': move.id,
    #                     'product_id': move.product_id.id,
    #                     'product_uom_id': move.product_uom.id,
    #                     'quantity': move.product_uom_qty,
    #                     'location_id': source_location,
    #                     'location_dest_id': self.env.ref('stock.stock_location_customers').id,
    #                     'picking_id': picking.id,
    #                 })
    #             else:
    #                 for move_line in move.move_line_ids:
    #                     move_line.quantity = move.product_uom_qty

    #         # Validate picking
    #         picking.with_context(skip_immediate=True).button_validate()

    #         # Log the technician location used
    #         _logger.info(f"Service Order {self.name}: Stock moved from location ID {source_location} (Technician: {self.assigned_to.name if self.assigned_to else 'Not Assigned'})")

    #     # Close Order
    #     self.write({'state': 'done', 'done_date': fields.Date.today()})
        
    #     # Update AMC Limits
    #     if self.contract_id:
    #         self.contract_id.update_consumption()
        
    #     return True
    
    # def _consume_parts_from_van(self):
    #     """ Creates Delivery Order from Technician Location -> Customer """
    #     self.ensure_one()
        
    #     if not self.assigned_to:
    #         raise UserError(_("Please assign a Technician before marking as Done."))

    #     # Get technician's van stock configuration
    #     van_config = self.env['ro.van.stock'].search([
    #         ('technician_id', '=', self.assigned_to.id)
    #     ], limit=1)

    #     if not van_config:
    #         raise UserError(_(f"No Stock Location configured for technician '{self.assigned_to.name}'.\nPlease go to Inventory > Technician Stock and configure it."))

    #     source_location = van_config.location_id.id
    #     customer_location = self.env.ref('stock.stock_location_customers').id 

    #     # Create Picking Header
    #     picking = self.env['stock.picking'].create({
    #         'picking_type_id': self.env.ref('stock.picking_type_out').id, 
    #         'location_id': source_location,       
    #         'location_dest_id': customer_location, 
    #         'origin': self.name,
    #         'partner_id': self.partner_id.id,
    #         'move_type': 'direct',
    #     })

    #     # Create Moves
    #     has_moves = False
    #     for part in self.parts_line_ids:
    #         if part.qty > 0:
    #             has_moves = True
    #             self.env['stock.move'].create({
    #                 'name': part.product_id.name,
    #                 'product_id': part.product_id.id,
    #                 'product_uom_qty': part.qty,
    #                 'product_uom': part.product_id.uom_id.id,
    #                 'location_id': source_location,
    #                 'location_dest_id': customer_location,
    #                 'picking_id': picking.id
    #             })

    #     if not has_moves:
    #         return

    #     # Confirm Picking
    #     picking.action_confirm()
    #     picking.action_assign()

    #     # Force Validation
    #     for move in picking.move_ids:
    #         move.quantity = move.product_uom_qty
            
    #         # If reservation failed (0 stock available), explicitly create the line
    #         if not move.move_line_ids:
    #             self.env['stock.move.line'].create({
    #                 'move_id': move.id,
    #                 'product_id': move.product_id.id,
    #                 'product_uom_id': move.product_uom.id,
    #                 'quantity': move.product_uom_qty,
    #                 'location_id': move.location_id.id,
    #                 'location_dest_id': move.location_dest_id.id,
    #                 'picking_id': picking.id,
    #             })

    #     # Validate
    #     picking.button_validate()
        
    @api.model
    def _cron_schedule_so_reminders(self):
        """
        Check for Service Orders scheduled for TOMORROW (Today + 1 Day)
        and assign an activity to the technician.
        """
        today = date.today()
        target_date = today + timedelta(days=1)  # Target is tomorrow

        # Find orders scheduled for tomorrow that are not yet Done/Cancelled
        # Adjust 'state' values based on your workflow (e.g., 'draft', 'confirmed', 'in_progress')
        orders_due_tomorrow = self.search([
            ('service_date', '=', target_date),
            ('state', 'not in', ['done', 'cancel']), 
        ])

        for order in orders_due_tomorrow:
            # Only create activity if a technician is assigned
            if order.technician_id:
                order.activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=order.technician_id.id,
                    note=f"Reminder: Service Order {order.name} is scheduled for tomorrow ({order.service_date}).",
                    summary="Upcoming Service Order"
                )
                
 
    # --- LOGIC TO POPULATE THE FILTER LIST ---
    @api.depends('partner_id')
    def _compute_allowed_products(self):
        for rec in self:
            if rec.partner_id:
                warranties = self.env['ro.warranty'].search([('partner_id', '=', rec.partner_id.id)])
                amcs = self.env['ro.amc'].search([('partner_id', '=', rec.partner_id.id)])
                owned_ids = warranties.mapped('product_id.id') + amcs.mapped('product_id.id')
                rec.allowed_product_ids = [(6, 0, list(set(owned_ids)))]
            else:
                rec.allowed_product_ids = [(5, 0, 0)]
    
    
    
    # --- AUTO-FILL LOGIC ---
    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        """ 
        1. Auto-fill Address (Editable)
        2. Auto-select Product if only one exists
        """
        if self.partner_id:
            # 1. Address
            self.partner_address = self.partner_id.contact_address
            
            # 2. Check how many products they own
            # Note: allowed_product_ids is computed, but inside onchange we might need to access the source directly
            warranties = self.env['ro.warranty'].search([('partner_id', '=', self.partner_id.id)])
            amcs = self.env['ro.amc'].search([('partner_id', '=', self.partner_id.id)])
            owned_ids = list(set(warranties.mapped('product_id.id') + amcs.mapped('product_id.id')))
            
            # 3. Auto-select if only one exists
            if len(owned_ids) == 1:
                self.product_id = owned_ids[0]
                self._onchange_product_id_auto_fill()
            else:
                self.product_id = False
                self.warranty_id = False
                self.contract_id = False
        else:
            self.product_id = False
            self.partner_address = False
    
    
    

    @api.onchange('product_id')
    def _onchange_product_id_auto_fill(self):
        """ 
        When Product is selected (manually or auto):
        Auto-select the Active Warranty OR Active AMC.
        """
        if self.partner_id and self.product_id:
            today = fields.Date.today()
            
            # 1. Look for Active Warranty
            warranty = self.env['ro.warranty'].search([
                ('partner_id', '=', self.partner_id.id),
                ('product_id', '=', self.product_id.id),
                ('state', '=', 'active'),
                ('start_date', '<=', today),
                ('end_date', '>=', today)
            ], limit=1, order='end_date desc')
            
            if warranty:
                self.warranty_id = warranty.id
                self.contract_id = False
                return # Stop here, Warranty takes priority

            # 2. Look for Active AMC (if no warranty)
            amc = self.env['ro.amc'].search([
                ('partner_id', '=', self.partner_id.id),
                ('product_id', '=', self.product_id.id),
                ('state', '=', 'active'),
                ('start_date', '<=', today),
                ('end_date', '>=', today)
            ], limit=1, order='end_date desc')
            
            if amc:
                self.contract_id = amc.id
                self.warranty_id = False
            else:
                # Reset if neither found
                self.warranty_id = False
                self.contract_id = False
    
    
    def update_amc_consumption(self):
        """Update AMC consumed quantities for this service order"""
        if not self.contract_id or self.state not in ['done', 'invoiced']:
            return
        
        for part_line in self.parts_line_ids:
            if not part_line.is_chargeable:
                # Find the coverage line for this part
                coverage = self.contract_id.coverage_ids.filtered(
                    lambda c: c.product_id == part_line.product_id
                )
                if coverage:
                    # Force update by triggering computation
                    coverage._compute_consumed()
        
        # Also recompute remaining quantities
        self.contract_id.coverage_ids._compute_remaining_qty()
    

    def action_reset_to_new(self):
        self.state = 'new'
    
    # --- THE BRAIN: LOGIC FOR WARRANTY & AMC ---
    # @api.onchange('parts_line_ids', 'warranty_id', 'contract_id' )
    # def _check_part_coverage(self):
    #     today = fields.Date.today()
    #     has_chargeable_part = False  # Add this flag

        
    #     for line in self.parts_line_ids:
    #         line.is_chargeable = False 
    #         line.qty_chargeable = 0.0 # Reset
    #         line.charge_reason = ""

    #         # 1. WARRANTY LOGIC ("No Reset" Rule)
    #         if self.warranty_id and self.warranty_id.state == 'active':
                
    #             install_date = self.warranty_id.start_date 
    #             warranty_rule = False   #added afterwards 
    #             # A. Check specific component warranty
    #             if self.product_id:
    #                 warranty_rule = self.product_id.product_tmpl_id.component_warranty_ids.filtered(
    #                     lambda r: r.component_id == line.product_id
    #                 )
                    
    #                 if warranty_rule:
    #                     part_months = warranty_rule[0].warranty_months
    #                     part_expiry = install_date + relativedelta(months=int(part_months))
                        
    #                     if today > part_expiry:
    #                         line.is_chargeable = True
    #                         line.qty_chargeable = line.qty
    #                         line.charge_reason = f"Part Warranty Expired on {part_expiry}"
    #                         has_chargeable_part = True  # Set flag

                
    #             # B. If no specific rule, check Main Machine Warranty
    #             elif self.warranty_id.end_date < today:
    #                 line.is_chargeable = True
    #                 line.qty_chargeable = line.qty
    #                 line.charge_reason = "Main Warranty Expired"
    #                 has_chargeable_part = True

    #         # 2. AMC LOGIC (Usage Limits)
    #         elif self.contract_id and self.contract_id.state == 'active':
    #             limit_rule = self.contract_id.coverage_ids.filtered(lambda r: r.product_id == line.product_id)
                
    #             if limit_rule:
    #                 remaining = limit_rule.allowed_qty - limit_rule.consumed_qty
    #                 if line.qty > max(0, remaining):
    #                     line.is_chargeable = True
    #                     # Calculate split: Free vs Paid
    #                     free_qty = max(0, remaining)
    #                     line.qty_chargeable = line.qty - free_qty
    #                     line.charge_reason = f"AMC Limit Reached. Allowed: {limit_rule.allowed_qty}. Paying for {line.qty_chargeable}."
    #                     has_chargeable_part = True
    #             else:
    #                 # Part not covered in AMC
    #                 line.is_chargeable = True
    #                 line.qty_chargeable = line.qty
    #                 line.charge_reason = "Part not covered in AMC"
    #                 has_chargeable_part = True

    #     if has_chargeable_part:
    #         self.chargeable = True
        
    #     # System Alert Popups
    #     if self.warranty_id:
    #         if self.warranty_id.state != 'active':
    #             self.chargeable = True
    #             return {'warning': {'title': "Invalid Warranty", 'message': "Warranty is NOT Active."}}
    #         if self.warranty_id.end_date < today:
    #             self.chargeable = True
    #             return {'warning': {'title': "Warranty Expired", 'message': "Warranty has expired."}}
    #         if self.warranty_id.coverage == 'labor' and self.parts_line_ids:
    #             self.chargeable = True 
    #             return {'warning': {'title': "Coverage Limit", 'message': "Warranty covers Labor Only. Parts are chargeable."}}

    
    
        # --- THE BRAIN: LOGIC FOR WARRANTY & AMC ---
    # @api.onchange('parts_line_ids', 'warranty_id', 'contract_id')
    # def _check_part_coverage(self):
    #     today = fields.Date.today()
    #     has_chargeable_part = False  # Add this flag

    #     for line in self.parts_line_ids:
    #         line.is_chargeable = False 
    #         line.qty_chargeable = 0.0  # Reset
    #         line.charge_reason = ""

    #         # 1. WARRANTY LOGIC ("No Reset" Rule)
    #         if self.warranty_id and self.warranty_id.state == 'active':
    #             install_date = self.warranty_id.start_date
    #             warranty_rule = False
                
    #             # A. Check if part is in component warranties
    #             if self.product_id:
    #                 warranty_rule = self.product_id.product_tmpl_id.component_warranty_ids.filtered(
    #                     lambda r: r.component_id == line.product_id
    #                 )
                
    #             if warranty_rule:
    #                 # Part IS in component warranty list
    #                 part_months = warranty_rule[0].warranty_months
    #                 part_expiry = install_date + relativedelta(months=int(part_months))
                    
    #                 if today <= part_expiry:
    #                     # Part is WITHIN warranty period
    #                     line.is_chargeable = False
    #                     line.qty_chargeable = 0.0
    #                     line.charge_reason = "This part is under warranty"
    #                 else:
    #                     # Part warranty has EXPIRED
    #                     line.is_chargeable = True
    #                     line.qty_chargeable = line.qty
    #                     line.charge_reason = f"This part is out of warranty (Expired on {part_expiry.strftime('%d/%m/%Y')})"
    #                     has_chargeable_part = True
                
    #             elif not warranty_rule and self.warranty_id.end_date < today:
    #                 line.is_chargeable = True
    #                 line.qty_chargeable = line.qty
    #                 line.charge_reason = "Main Warranty Expired"
    #                 has_chargeable_part = True

                
    #             else:
    #                 # Part is NOT in component warranty list at all
    #                 # Check main machine warranty instead
    #                 if today <= self.warranty_id.end_date:
    #                     # Main warranty is still active, but part is not in warranty list
    #                     line.is_chargeable = True
    #                     line.qty_chargeable = line.qty
    #                     line.charge_reason = "This part is not under warranty"
    #                     has_chargeable_part = True
    #                 else:
    #                     # Main warranty has also expired
    #                     line.is_chargeable = True
    #                     line.qty_chargeable = line.qty
    #                     line.charge_reason = "This part is not under warranty and main warranty has expired"
    #                     has_chargeable_part = True

    #             # B. If no specific rule and main warranty expired
            
    #         # 2. AMC LOGIC (Usage Limits)
    #         elif self.contract_id and self.contract_id.state == 'active':
    #             limit_rule = self.contract_id.coverage_ids.filtered(lambda r: r.product_id == line.product_id)
                
    #             if limit_rule:
    #                 remaining = limit_rule.allowed_qty - limit_rule.consumed_qty
    #                 if line.qty <= max(0, remaining):
    #                     # Within AMC limit
    #                     line.is_chargeable = False
    #                     line.qty_chargeable = 0.0
    #                     line.charge_reason = "Covered under AMC"
    #                 else:
    #                     # AMC limit exceeded
    #                     line.is_chargeable = True
    #                     free_qty = max(0, remaining)
    #                     line.qty_chargeable = line.qty - free_qty
    #                     line.charge_reason = f"AMC Limit Reached. Allowed: {limit_rule.allowed_qty}. Paying for {line.qty_chargeable}."
    #                     has_chargeable_part = True
    #             else:
    #                 # Part not covered in AMC
    #                 line.is_chargeable = True
    #                 line.qty_chargeable = line.qty
    #                 line.charge_reason = "Part not covered in AMC"
    #                 has_chargeable_part = True

    #     # Update main chargeable field based on parts
    #     if has_chargeable_part:
    #         self.chargeable = True
    #     elif self.parts_line_ids and self.warranty_id and self.warranty_id.state == 'active':
    #         # If all parts are free under warranty, uncheck chargeable
    #         self.chargeable = False
        
    #     # System Alert Popups
    #     if self.warranty_id:
    #         if self.warranty_id.state != 'active':
    #             self.chargeable = True
    #             return {'warning': {'title': "Invalid Warranty", 'message': "Warranty is NOT Active."}}
    #         if self.warranty_id.end_date < today:
    #             self.chargeable = True
    #             return {'warning': {'title': "Warranty Expired", 'message': "Warranty has expired."}}
    #         if self.warranty_id.coverage == 'labor' and self.parts_line_ids:
    #             self.chargeable = True 
    #             return {'warning': {'title': "Coverage Limit", 'message': "Warranty covers Labor Only. Parts are chargeable."}}        
        
    
        # --- THE BRAIN: LOGIC FOR WARRANTY & AMC ---
    @api.onchange('parts_line_ids', 'warranty_id', 'contract_id')
    def _check_part_coverage(self):
        today = fields.Date.today()
        
         # FIRST PASS: Calculate ALL remaining quantities BEFORE making decisions
        remaining_by_product = {}
        if self.contract_id and self.contract_id.state == 'active':
            for line in self.parts_line_ids:
                coverage = self.contract_id.coverage_ids.filtered(
                    lambda r: r.product_id == line.product_id
                )
                if coverage:
                    # Calculate initial remaining for each product
                    remaining = coverage.get_remaining_for_service(self)
                    remaining_by_product[line.product_id.id] = {
                        'coverage': coverage,
                        'remaining': remaining,
                        'used_in_this_order': 0.0  # Track free qty used in current order
                    }
        
        has_chargeable_part = False  # Add this flag

        for line in self.parts_line_ids:
            line.is_chargeable = False 
            line.qty_chargeable = 0.0  # Reset
            line.charge_reason = ""

            # 1. WARRANTY LOGIC ("No Reset" Rule)
            if self.warranty_id and self.warranty_id.state == 'active':
                install_date = self.warranty_id.start_date
                warranty_rule = False
                
                # A. Check if part is in component warranties
                if self.product_id:
                    warranty_rule = self.product_id.product_tmpl_id.component_warranty_ids.filtered(
                        lambda r: r.component_id == line.product_id
                    )
                
                if warranty_rule:
                    # Part IS in component warranty list
                    part_months = warranty_rule[0].warranty_months
                    part_expiry = install_date + relativedelta(months=int(part_months))
                    
                    if today <= part_expiry:
                        # Part is WITHIN warranty period
                        line.is_chargeable = False
                        line.qty_chargeable = 0.0
                        line.charge_reason = "This part is under warranty"
                    else:
                        # Part warranty has EXPIRED
                        line.is_chargeable = True
                        line.qty_chargeable = line.qty
                        line.charge_reason = f"This part is out of warranty (Expired on {part_expiry.strftime('%d/%m/%Y')})"
                        has_chargeable_part = True
                
                else:
                    # Part is NOT in component warranty list at all
                    # Check main machine warranty instead
                    if today <= self.warranty_id.end_date:
                        # Main warranty is still active, but part is not in warranty list
                        line.is_chargeable = True
                        line.qty_chargeable = line.qty
                        line.charge_reason = "This part is not under warranty"
                        has_chargeable_part = True
                    else:
                        # Main warranty has also expired
                        line.is_chargeable = True
                        line.qty_chargeable = line.qty
                        line.charge_reason = "This part is not under warranty and main warranty has expired"
                        has_chargeable_part = True

            # 2. AMC LOGIC (Usage Limits) - FIXED VERSION
            elif self.contract_id and self.contract_id.state == 'active':
                product_id = line.product_id.id
                
                if product_id in remaining_by_product:
                    coverage = remaining_by_product[product_id]['coverage']
                    remaining = remaining_by_product[product_id]['remaining']
                    already_used_in_order = remaining_by_product[product_id]['used_in_this_order']
                    
                    # Calculate ACTUALLY available for this specific line
                    actually_available = remaining - already_used_in_order
                    
                    _logger.info(f"[AMC CALC] Part: {line.product_id.name}")
                    _logger.info(f"  - Allowed: {coverage.allowed_qty}")
                    _logger.info(f"  - Remaining before this order: {remaining}")
                    _logger.info(f"  - Already used in this order: {already_used_in_order}")
                    _logger.info(f"  - Actually available: {actually_available}")
                    _logger.info(f"  - Qty needed: {line.qty}")
                    
                    if actually_available <= 0:
                        # No free quantity left - ALL are chargeable
                        line.is_chargeable = True
                        line.qty_chargeable = line.qty
                        line.charge_reason = f"AMC Limit Reached. Allowed: {coverage.allowed_qty}. Paying for all {line.qty} units."
                        has_chargeable_part = True
                        
                    elif line.qty <= actually_available:
                        # All units are within available limit - ALL are free
                        line.is_chargeable = False
                        line.qty_chargeable = 0.0
                        line.charge_reason = f"Covered under AMC (Remaining: {actually_available - line.qty})"
                        # Track that we've used this free quantity in current order
                        remaining_by_product[product_id]['used_in_this_order'] += line.qty
                        
                    else:
                        # Partial coverage: some free, some chargeable
                        line.is_chargeable = True
                        free_qty = actually_available
                        line.qty_chargeable = line.qty - free_qty
                        line.charge_reason = f"AMC Limit Reached. Allowed: {coverage.allowed_qty}. Free: {free_qty}, Paying for: {line.qty_chargeable}."
                        has_chargeable_part = True
                        # Track that we've used free quantity
                        if free_qty > 0:
                            remaining_by_product[product_id]['used_in_this_order'] += free_qty

                else:
                    # Part not covered in AMC
                    line.is_chargeable = True
                    line.qty_chargeable = line.qty
                    line.charge_reason = "Part not covered in AMC"
                    has_chargeable_part = True

            # 3. NO WARRANTY OR AMC (Direct Chargeable)
            elif not self.warranty_id and not self.contract_id:
                line.is_chargeable = True
                line.qty_chargeable = line.qty
                line.charge_reason = "No active warranty or AMC"
                has_chargeable_part = True

        # Update main chargeable checkbox
        if has_chargeable_part:
            self.chargeable = True
        else:
            self.chargeable = False
        
        # System Alert Popups
        if self.warranty_id:
            if self.warranty_id.state != 'active':
                self.chargeable = True
                return {'warning': {'title': "Invalid Warranty", 'message': "Warranty is NOT Active."}}
            if self.warranty_id.end_date < today:
                self.chargeable = True
                return {'warning': {'title': "Warranty Expired", 'message': "Warranty has expired."}}
            if self.warranty_id.coverage == 'labor' and self.parts_line_ids:
                self.chargeable = True 
                return {'warning': {'title': "Coverage Limit", 'message': "Warranty covers Labor Only. Parts are chargeable."}}
                


            # 2. AMC LOGIC (Usage Limits)
        #     elif self.contract_id and self.contract_id.state == 'active':
        #         limit_rule = self.contract_id.coverage_ids.filtered(lambda r: r.product_id == line.product_id)
                
        #         if limit_rule:
        #             remaining = limit_rule.get_remaining_qty(self)
        #             # if line.qty <= max(0, remaining):
        #             #     # Within AMC limit
        #             #     line.is_chargeable = False
        #             #     line.qty_chargeable = 0.0
        #             #     line.charge_reason = "Covered under AMC"
        #             # else:
        #             #     # AMC limit exceeded
        #             #     line.is_chargeable = True
        #             #     free_qty = max(0, remaining)
        #             #     line.qty_chargeable = line.qty - free_qty
        #             #     line.charge_reason = f"AMC Limit Reached. Allowed: {limit_rule.allowed_qty}. Paying for {line.qty_chargeable}."
        #             #     has_chargeable_part = True
        #             _logger.info(f"Part: {line.product_id.name}, Allowed: {limit_rule.allowed_qty}, "
        #                         f"Consumed: {limit_rule.consumed_qty}, Remaining: {remaining}, "
        #                         f"Qty needed: {line.qty}")
                    
        #             if remaining <= 0:
        #                 # No free quantity left - ALL are chargeable
        #                 line.is_chargeable = True
        #                 line.qty_chargeable = line.qty
        #                 line.charge_reason = f"AMC Limit Reached. Allowed: {limit_rule.allowed_qty}. Paying for all {line.qty} units."
        #                 has_chargeable_part = True
                        
        #             elif line.qty <= remaining:
        #                 # All units are within remaining limit - ALL are free
        #                 line.is_chargeable = False
        #                 line.qty_chargeable = 0.0
        #                 line.charge_reason = f"Covered under AMC (Remaining: {remaining - line.qty})"
                        
        #             else:
        #                 # Partial coverage: some free, some chargeable
        #                 line.is_chargeable = True
        #                 free_qty = remaining
        #                 line.qty_chargeable = line.qty - free_qty
        #                 line.charge_reason = f"AMC Limit Reached. Allowed: {limit_rule.allowed_qty}. Free: {free_qty}, Paying for: {line.qty_chargeable}."
        #                 has_chargeable_part = True
    
        #         else:
        #             # Part not covered in AMC
        #             line.is_chargeable = True
        #             line.qty_chargeable = line.qty
        #             line.charge_reason = "Part not covered in AMC"
        #             has_chargeable_part = True

        #     # 3. NO WARRANTY OR AMC (Direct Chargeable)
        #     elif not self.warranty_id and not self.contract_id:
        #         # No warranty or AMC at all
        #         line.is_chargeable = True
        #         line.qty_chargeable = line.qty
        #         line.charge_reason = "No active warranty or AMC"
        #         has_chargeable_part = True

        # # ===== CRITICAL FIX: Update main chargeable checkbox =====
        # # This should be OUTSIDE the for loop
        # if has_chargeable_part:
        #     self.chargeable = True
        # else:
        #     self.chargeable = False
        
        # # System Alert Popups
        # if self.warranty_id:
        #     if self.warranty_id.state != 'active':
        #         self.chargeable = True
        #         return {'warning': {'title': "Invalid Warranty", 'message': "Warranty is NOT Active."}}
        #     if self.warranty_id.end_date < today:
        #         self.chargeable = True
        #         return {'warning': {'title': "Warranty Expired", 'message': "Warranty has expired."}}
        #     if self.warranty_id.coverage == 'labor' and self.parts_line_ids:
        #         self.chargeable = True 
        #         return {'warning': {'title': "Coverage Limit", 'message': "Warranty covers Labor Only. Parts are chargeable."}}
    
        
    # @api.onchange('parts_line_ids')
    # def _onchange_parts_line_ids(self):
    #     """Ensure main chargeable checkbox updates when parts change"""
    #     # Check if any part is chargeable
    #     if self.parts_line_ids:
    #         any_chargeable = any(line.is_chargeable for line in self.parts_line_ids)
    #         if any_chargeable:
    #             self.chargeable = True
    #         elif self.warranty_id and self.warranty_id.state == 'active':
    #             # If all parts are under warranty, uncheck
    #             self.chargeable = False
    
    @api.onchange('parts_line_ids')
    def _onchange_parts_line_ids(self):
        """Handle when parts are added/removed - ensure proper recalculation"""
        # Trigger the main coverage check
        self._check_part_coverage()
                
                
    # System Alert Popups
    @api.onchange('warranty_id', 'parts_line_ids') 
    def _check_warranty_status(self):
        if self.warranty_id:
            if self.warranty_id.state != 'active':
                self.chargeable = True
                return {'warning': {'title': "Invalid Warranty", 'message': "Warranty is NOT Active."}}
            if self.warranty_id.end_date < fields.Date.today():
                self.chargeable = True
                return {'warning': {'title': "Warranty Expired", 'message': "Warranty has expired."}}
            if self.warranty_id.coverage == 'labor' and self.parts_line_ids:
                self.chargeable = True 
                return {'warning': {'title': "Coverage Limit", 'message': "Warranty covers Labor Only. Parts are chargeable."}}
            self.chargeable = False

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('ro.service.order') or 'New'
        return super(ROServiceOrder, self).create(vals)

    # def action_complete(self):
    #     """ Deduct Inventory and Close Order """
    #     if self.parts_line_ids:
    #         # 1. Create Picking
    #         picking_type = self.env['stock.picking.type'].search([('code', '=', 'outgoing')], limit=1)
    #         picking = self.env['stock.picking'].create({
    #             'partner_id': self.partner_id.id,
    #             'picking_type_id': picking_type.id,
    #             'location_id': picking_type.default_location_src_id.id,
    #             'location_dest_id': self.env.ref('stock.stock_location_customers').id,
    #             'origin': self.name,
    #         })
            
    #         # 2. Create Moves
    #         for line in self.parts_line_ids:
    #             self.env['stock.move'].create({
    #                 'name': line.product_id.name,
    #                 'product_id': line.product_id.id,
    #                 'product_uom_qty': line.qty,
    #                 'product_uom': line.product_id.uom_id.id,
    #                 'picking_id': picking.id,
    #                 'location_id': picking_type.default_location_src_id.id,
    #                 'location_dest_id': self.env.ref('stock.stock_location_customers').id,
    #             })

    #         # 3. Confirm and Assign
    #         picking.action_confirm()
    #         picking.action_assign()
            
    #         # 4. SET QUANTITIES (The Fix)
    #         for move in picking.move_ids:
    #             # If reserved, update the existing line
    #             if move.move_line_ids:
    #                 for move_line in move.move_line_ids:
    #                     move_line.quantity = move.product_uom_qty
    #             # If not reserved (e.g. forced), create the line
    #             else:
    #                 self.env['stock.move.line'].create({
    #                     'move_id': move.id,
    #                     'product_id': move.product_id.id,
    #                     'product_uom_id': move.product_uom.id,
    #                     'quantity': move.product_uom_qty,  # <--- 'quantity' is correct for Odoo 17
    #                     'location_id': move.location_id.id,
    #                     'location_dest_id': move.location_dest_id.id,
    #                     'picking_id': picking.id,
    #                 })
                
    #             move.picked = True # Important flag for Odoo 17
            
    #         # 5. Validate
    #         picking.button_validate()
            
    #     self.write({'state': 'done', 'done_date': fields.Date.today()})
    
    
    # def action_complete(self):
    #     """ Deduct Inventory and Close Order - FIXED FOR ODOO 17 """
    #     if self.parts_line_ids:
    #         # 1. Get outgoing picking type
    #         picking_type = self.env['stock.picking.type'].search([
    #             ('code', '=', 'outgoing'),
    #             ('warehouse_id.company_id', 'in', [self.env.company.id, False])
    #         ], limit=1)
    #         if not picking_type:
    #             raise UserError("No outgoing picking type found for current company.")

    #         # 2. Create Delivery Order
    #         picking = self.env['stock.picking'].create({
    #             'partner_id': self.partner_id.id,
    #             'picking_type_id': picking_type.id,
    #             'location_id': picking_type.default_location_src_id.id,
    #             'location_dest_id': self.env.ref('stock.stock_location_customers').id,
    #             'origin': self.name,
    #             'move_type': 'direct',  # Important for immediate transfer
    #         })

    #         # 3. Create stock moves
    #         moves_to_do = []
    #         for line in self.parts_line_ids.filtered(lambda l: l.qty > 0):
    #             move = self.env['stock.move'].create({
    #                 'name': line.product_id.display_name,
    #                 'product_id': line.product_id.id,
    #                 'product_uom_qty': line.qty,
    #                 'product_uom': line.product_id.uom_id.id,
    #                 'picking_id': picking.id,
    #                 'location_id': picking_type.default_location_src_id.id,
    #                 'location_dest_id': self.env.ref('stock.stock_location_customers').id,
    #                 'state': 'draft',
    #             })
    #             moves_to_do.append(move)

    #         if not moves_to_do:
    #             # No parts, just close
    #             self.write({'state': 'done', 'done_date': fields.Date.today()})
    #             return

    #         # 4. Confirm & Assign (reserve stock)
    #         picking.action_confirm()
    #         picking.action_assign()

    #         # THE HERO LINES - THIS IS WHAT MAKES IT "DONE" INSTANTLY
    #         for move in picking.move_ids_without_package:
    #             # Option A: Best & Cleanest (Odoo 17+ recommended)
    #             move.move_line_ids.write({'quantity': move.product_uom_qty})
                
    #             # Option B: Alternative (if no move lines exist, create them)
    #             if not move.move_line_ids:
    #                 self.env['stock.move.line'].create({
    #                     'move_id': move.id,
    #                     'product_id': move.product_id.id,
    #                     'product_uom_id': move.product_uom.id,
    #                     'quantity': move.product_uom_qty,
    #                     'location_id': move.location_id.id,
    #                     'location_dest_id': move.location_dest_id.id,
    #                     'picking_id': picking.id,
    #                 })
    #             else:
    #                 move.move_line_ids.write({'quantity': move.product_uom_qty})

    #         # 6. Validate picking - Stock will be deducted IMMEDIATELY
    #         picking.with_context(skip_immediate=True).button_validate()

    #     # 7. Mark service order as Done
    #     self.write({'state': 'done', 'done_date': fields.Date.today()})
        
    #     if self.contract_id:
    #     # Invalidate cache to force fresh computation
    #         self.contract_id.coverage_ids.invalidate_cache(['consumed_qty', 'remaining_qty'])
    #         # Trigger recomputation
    #         self.contract_id.coverage_ids._compute_consumed()
    #         self.contract_id.coverage_ids._compute_remaining_qty()
        
    #     return True
        

    
    # def action_complete(self):
    #     """ Deduct Inventory and Close Order - FIXED FOR ODOO 17 """
    #     # ... (Keep all existing Inventory/Stock Deduction Code here) ...
    #     if self.parts_line_ids:
    #         # 1. Get outgoing picking type
    #         picking_type = self.env['stock.picking.type'].search([
    #             ('code', '=', 'outgoing'),
    #             ('warehouse_id.company_id', 'in', [self.env.company.id, False])
    #         ], limit=1)
    #         if not picking_type:
    #             raise UserError("No outgoing picking type found for current company.")

    #         # 2. Create Delivery Order
    #         picking = self.env['stock.picking'].create({
    #             'partner_id': self.partner_id.id,
    #             'picking_type_id': picking_type.id,
    #             'location_id': picking_type.default_location_src_id.id,
    #             'location_dest_id': self.env.ref('stock.stock_location_customers').id,
    #             'origin': self.name,
    #             'move_type': 'direct',  # Important for immediate transfer
    #         })

    #         # 3. Create stock moves
    #         moves_to_do = []
    #         for line in self.parts_line_ids.filtered(lambda l: l.qty > 0):
    #             move = self.env['stock.move'].create({
    #                 'name': line.product_id.display_name,
    #                 'product_id': line.product_id.id,
    #                 'product_uom_qty': line.qty,
    #                 'product_uom': line.product_id.uom_id.id,
    #                 'picking_id': picking.id,
    #                 'location_id': picking_type.default_location_src_id.id,
    #                 'location_dest_id': self.env.ref('stock.stock_location_customers').id,
    #                 'state': 'draft',
    #             })
    #             moves_to_do.append(move)

    #         if not moves_to_do:
    #             # No parts, just close
    #             self.write({'state': 'done', 'done_date': fields.Date.today()})
    #             # Check for AMC update even if no parts were moved (e.g. labor only)
    #             if self.contract_id:
    #                 self.contract_id.update_consumption() 
    #             return

    #         # 4. Confirm & Assign (reserve stock)
    #         picking.action_confirm()
    #         picking.action_assign()

    #         # 5. Set Done Quantities and Validate
    #         for move in picking.move_ids_without_package:
    #             if not move.move_line_ids:
    #                 self.env['stock.move.line'].create({
    #                     'move_id': move.id,
    #                     'product_id': move.product_id.id,
    #                     'product_uom_id': move.product_uom.id,
    #                     'quantity': move.product_uom_qty,
    #                     'location_id': move.location_id.id,
    #                     'location_dest_id': move.location_dest_id.id,
    #                     'picking_id': picking.id,
    #                 })
    #             else:
    #                 # Update existing move lines
    #                 move.move_line_ids.write({'quantity': move.product_uom_qty})

    #         # 6. Validate picking
    #         picking.with_context(skip_immediate=True).button_validate()

    #     # 7. Mark service order as Done
    #     self.write({'state': 'done', 'done_date': fields.Date.today()})
        
    #     # --- CRITICAL FIX: Explicitly call the update method ---
    #     if self.contract_id:
    #         # This calls the method we defined in ro.amc to calculate consumed_qty
    #         self.contract_id.update_consumption() 
        
    #     return True
    
    def action_create_invoice(self):
        """ Create Invoice for Chargeable Services """
        # any_line_chargeable = any(line.is_chargeable for line in self.parts_line_ids)
        any_line_chargeable = any(
            line.is_chargeable and line.qty_chargeable > 0 
            for line in self.parts_line_ids
        )

        if not self.chargeable and not any_line_chargeable:
            raise UserError(_("No chargeable components found."))
        
        # Force chargeable to True if any part is chargeable
        if any_line_chargeable and not self.chargeable:
            self.chargeable = True
        
        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_origin': self.name,    
            'ro_technician_id': self.assigned_to.id,
            'invoice_line_ids': [],
        }
        
        has_lines = False
        for line in self.parts_line_ids:
            # Only invoice the chargeable quantity
            if line.is_chargeable and line.qty_chargeable > 0:
                has_lines = True
                invoice_vals['invoice_line_ids'].append((0, 0, {
                    'product_id': line.product_id.id,
                    'quantity': line.qty_chargeable, 
                    'price_unit': line.unit_price,
                    'name': f"{line.product_id.name} ({line.charge_reason})"
                }))
            
            elif line.qty_chargeable == 0:
                _logger.debug(f"Skipping {line.product_id.name}: qty_chargeable=0")
            elif not line.is_chargeable:
                _logger.debug(f"Skipping {line.product_id.name}: is_chargeable=False")
        
        if not has_lines and not self.chargeable:
             raise UserError("Nothing to invoice!")
        
        invoice = self.env['account.move'].create(invoice_vals)
        self.write({'state': 'invoiced'})
        return {
            'name': _('Invoice'),
            'view_mode': 'form',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'type': 'ir.actions.act_window',
        }

class ROServicePartLine(models.Model):
    _name = 'ro.service.part.line'
    _description = 'Service Order Parts'

    is_chargeable = fields.Boolean(string="Chargeable", default=False)
    charge_reason = fields.Char(string="Reason")
    qty_chargeable = fields.Float(string="Qty to Bill", default=0.0)
    
    service_order_id = fields.Many2one('ro.service.order', string='Service Order')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    qty = fields.Float(string='Quantity', default=1.0)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure') 
    unit_price = fields.Float(string='Unit Price')
    stock_move_id = fields.Many2one('stock.move', string='Stock Move')
    
    # Reporting fields
    technician_id = fields.Many2one(related='service_order_id.assigned_to', string="Technician", store=True)
    complaint_date = fields.Date(related='service_order_id.reported_date', string="Complaint Date", store=True)
    date_done = fields.Date(related='service_order_id.done_date', string="Completion Date", store=True)
    customer_id = fields.Many2one(related='service_order_id.partner_id', string="Customer", store=True)
    machine_id = fields.Many2one(related='service_order_id.product_id', string="Machine Model", store=True)
    part_amount = fields.Float(string="Part Amount", compute="_compute_part_amount", store=True)
    service_type = fields.Selection([('free', 'Free'),('chargeable', 'Chargeable')], string="Service Type", compute="_compute_service_type", store=True)
    comp_no = fields.Char(related='service_order_id.name', string="COMP NO.", store=True)
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.unit_price = self.product_id.list_price
            self.uom_id = self.product_id.uom_id
    
    @api.depends('qty', 'unit_price')
    def _compute_part_amount(self):
        for rec in self:
            rec.part_amount = rec.qty * rec.unit_price
            
    @api.depends('service_order_id.chargeable')
    def _compute_service_type(self):
        for rec in self:
            rec.service_type = 'chargeable' if rec.service_order_id.chargeable else 'free'