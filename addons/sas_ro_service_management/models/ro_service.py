from odoo import models, fields, api, _
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta
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
    contract_id = fields.Many2one('ro.amc', string='AMC Contract')
    warranty_id = fields.Many2one('ro.warranty', string='Warranty')
    product_id = fields.Many2one('product.product', string='Product')
    
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

            # 2. AMC LOGIC (Usage Limits)
            elif self.contract_id and self.contract_id.state == 'active':
                limit_rule = self.contract_id.coverage_ids.filtered(lambda r: r.product_id == line.product_id)
                
                if limit_rule:
                    remaining = limit_rule.allowed_qty - limit_rule.consumed_qty
                    # if line.qty <= max(0, remaining):
                    #     # Within AMC limit
                    #     line.is_chargeable = False
                    #     line.qty_chargeable = 0.0
                    #     line.charge_reason = "Covered under AMC"
                    # else:
                    #     # AMC limit exceeded
                    #     line.is_chargeable = True
                    #     free_qty = max(0, remaining)
                    #     line.qty_chargeable = line.qty - free_qty
                    #     line.charge_reason = f"AMC Limit Reached. Allowed: {limit_rule.allowed_qty}. Paying for {line.qty_chargeable}."
                    #     has_chargeable_part = True
                    _logger.info(f"Part: {line.product_id.name}, Allowed: {limit_rule.allowed_qty}, "
                                f"Consumed: {limit_rule.consumed_qty}, Remaining: {remaining}, "
                                f"Qty needed: {line.qty}")
                    
                    if remaining <= 0:
                        # No free quantity left - ALL are chargeable
                        line.is_chargeable = True
                        line.qty_chargeable = line.qty
                        line.charge_reason = f"AMC Limit Reached. Allowed: {limit_rule.allowed_qty}. Paying for all {line.qty} units."
                        has_chargeable_part = True
                        
                    elif line.qty <= remaining:
                        # All units are within remaining limit - ALL are free
                        line.is_chargeable = False
                        line.qty_chargeable = 0.0
                        line.charge_reason = f"Covered under AMC (Remaining: {remaining - line.qty})"
                        
                    else:
                        # Partial coverage: some free, some chargeable
                        line.is_chargeable = True
                        free_qty = remaining
                        line.qty_chargeable = line.qty - free_qty
                        line.charge_reason = f"AMC Limit Reached. Allowed: {limit_rule.allowed_qty}. Free: {free_qty}, Paying for: {line.qty_chargeable}."
                        has_chargeable_part = True
    
                else:
                    # Part not covered in AMC
                    line.is_chargeable = True
                    line.qty_chargeable = line.qty
                    line.charge_reason = "Part not covered in AMC"
                    has_chargeable_part = True

            # 3. NO WARRANTY OR AMC (Direct Chargeable)
            elif not self.warranty_id and not self.contract_id:
                # No warranty or AMC at all
                line.is_chargeable = True
                line.qty_chargeable = line.qty
                line.charge_reason = "No active warranty or AMC"
                has_chargeable_part = True

        # ===== CRITICAL FIX: Update main chargeable checkbox =====
        # This should be OUTSIDE the for loop
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
    
        
    @api.onchange('parts_line_ids')
    def _onchange_parts_line_ids(self):
        """Ensure main chargeable checkbox updates when parts change"""
        # Check if any part is chargeable
        if self.parts_line_ids:
            any_chargeable = any(line.is_chargeable for line in self.parts_line_ids)
            if any_chargeable:
                self.chargeable = True
            elif self.warranty_id and self.warranty_id.state == 'active':
                # If all parts are under warranty, uncheck
                self.chargeable = False
                
                
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
    
    
    def action_complete(self):
        """ Deduct Inventory and Close Order - FIXED FOR ODOO 17 """
        if self.parts_line_ids:
            # 1. Get outgoing picking type
            picking_type = self.env['stock.picking.type'].search([
                ('code', '=', 'outgoing'),
                ('warehouse_id.company_id', 'in', [self.env.company.id, False])
            ], limit=1)
            if not picking_type:
                raise UserError("No outgoing picking type found for current company.")

            # 2. Create Delivery Order
            picking = self.env['stock.picking'].create({
                'partner_id': self.partner_id.id,
                'picking_type_id': picking_type.id,
                'location_id': picking_type.default_location_src_id.id,
                'location_dest_id': self.env.ref('stock.stock_location_customers').id,
                'origin': self.name,
                'move_type': 'direct',  # Important for immediate transfer
            })

            # 3. Create stock moves
            moves_to_do = []
            for line in self.parts_line_ids.filtered(lambda l: l.qty > 0):
                move = self.env['stock.move'].create({
                    'name': line.product_id.display_name,
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.qty,
                    'product_uom': line.product_id.uom_id.id,
                    'picking_id': picking.id,
                    'location_id': picking_type.default_location_src_id.id,
                    'location_dest_id': self.env.ref('stock.stock_location_customers').id,
                    'state': 'draft',
                })
                moves_to_do.append(move)

            if not moves_to_do:
                # No parts, just close
                self.write({'state': 'done', 'done_date': fields.Date.today()})
                return

            # 4. Confirm & Assign (reserve stock)
            picking.action_confirm()
            picking.action_assign()

            # THE HERO LINES - THIS IS WHAT MAKES IT "DONE" INSTANTLY
            for move in picking.move_ids_without_package:
                # Option A: Best & Cleanest (Odoo 17+ recommended)
                move.move_line_ids.write({'quantity': move.product_uom_qty})
                
                # Option B: Alternative (if no move lines exist, create them)
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
                else:
                    move.move_line_ids.write({'quantity': move.product_uom_qty})

            # 6. Validate picking - Stock will be deducted IMMEDIATELY
            picking.with_context(skip_immediate=True).button_validate()

        # 7. Mark service order as Done
        self.write({'state': 'done', 'done_date': fields.Date.today()})

    
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