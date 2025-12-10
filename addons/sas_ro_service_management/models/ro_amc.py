from odoo import models, fields, api , _
from odoo.exceptions import UserError # <--- Make sure to import UserError
from dateutil.relativedelta import relativedelta

class ROAMC(models.Model):
    _name = 'ro.amc'
    _description = 'AMC Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    technician_id = fields.Many2one('res.users', string="Technician (Sales)")
    invoice_id = fields.Many2one('account.move', string="Invoice", readonly=True)
    coverage_ids = fields.One2many('ro.amc.coverage', 'amc_id', string="Coverage Limits")
    service_ids = fields.One2many('ro.service.order', 'contract_id', string="Services")
    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default='New')
    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    sale_id = fields.Many2one('sale.order', string='Source Sale')
    product_id = fields.Many2one('product.product', string='Product')
    start_date = fields.Date(string='Start Date', required=True, default=fields.Date.context_today)
    end_date = fields.Date(string='End Date', required=True)
    frequency = fields.Selection([
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('halfyearly', 'Half-Yearly'),
        ('yearly', 'Yearly')
    ], string='Service Frequency', required=True)
    amount = fields.Monetary(string='Contract Amount', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    inclusions = fields.Text(string='Inclusions')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', tracking=True)
    auto_generate_service = fields.Boolean(string='Auto Generate Services', default=True)
    contract_type = fields.Selection([
    ('AMC-CAMC', 'AMC / CAMC'),
    ('AMC-Labor', 'Labor Only AMC'),
    ('AMC-Comp', 'Comprehensive AMC')
    ], string="Contract Type", required=True, default='AMC-CAMC')


    
    duration_years = fields.Selection([
        ('1', '1 Year'),
        ('2', '2 Years'),
        ('3', '3 Years'),
        ('4', '4 Years'),
        ('5', '5 Years')
    ], string="Duration", default='1', required=True)

    # Computed field to know exactly when the next one is due
    next_service_date = fields.Date(string="Next Service Date", compute="_compute_next_date", store=True)

    @api.depends('start_date', 'frequency')  # Removed 'last_service_date' dependency
    def _compute_next_date(self):
        today = fields.Date.today()
        
        for record in self:
            if not record.start_date or not record.frequency:
                record.next_service_date = False
                continue

            # 1. Determine the interval (delta) based on frequency
            delta = relativedelta(months=0)
            if record.frequency == 'monthly':
                delta = relativedelta(months=1)
            elif record.frequency == 'quarterly':
                delta = relativedelta(months=3)
            elif record.frequency == 'halfyearly':
                delta = relativedelta(months=6)
            elif record.frequency == 'yearly':
                delta = relativedelta(years=1)

            # 2. Calculate the next FUTURE date starting from Start Date
            # Example: Start=Dec 10. Today=Jan 5.
            # Loop 1: Dec 10 + 1 Month = Jan 10. (Is Jan 10 >= Today? Yes. Stop.)
            # Result: Jan 10.
            
            calculated_date = record.start_date + delta
            
            # If the calculated date is in the past, keep adding intervals until we reach the future
            while calculated_date < today:
                calculated_date += delta
            
            record.next_service_date = calculated_date

    def _cron_schedule_service_reminders(self):
        """ Checks for services due in 2 days and schedules a call activity. """
        
        # Calculate the target date (e.g., Today + 2 days)
        reminder_date = fields.Date.today() + relativedelta(days=2)
        
        # Find Active AMCs where next service is due on that specific date
        records_due = self.search([
            ('state', '=', 'active'),
            ('next_service_date', '=', reminder_date),
            ('technician_id', '!=', False) 
        ])

        for record in records_due:
            # Check if an activity is already scheduled to avoid duplicates
            existing_activity = self.env['mail.activity'].search_count([
                ('res_id', '=', record.id),
                ('res_model', '=', self._name),
                ('activity_type_id', '=', self.env.ref('mail.mail_activity_data_call').id),
                ('date_deadline', '=', record.next_service_date)
            ])
            
            if not existing_activity:
                formatted_date = record.next_service_date.strftime('%d-%m-%Y')
                record.activity_schedule(
                    'mail.mail_activity_data_call',
                    user_id=record.technician_id.id,
                    date_deadline=record.next_service_date,
                    summary=f"Service Due: {record.frequency.capitalize()}",
                    note=f"Please call the customer ({record.partner_id.name}). Service is due on {formatted_date}."
                )

    @api.onchange('start_date', 'duration_years')
    def _onchange_duration(self):
        """ 
        Calculate End Date: Start Date + X Years - 1 Day 
        Example: 
        Start: 01-Jan-2025, Duration: 1 Year
        End: 31-Dec-2025 (Not 01-Jan-2026)
        """
        if self.start_date and self.duration_years:
            years = int(self.duration_years)
            # Add years, then subtract 1 day
            self.end_date = self.start_date + relativedelta(years=years) - relativedelta(days=1)

    @api.onchange('product_id')
    def _onchange_product_load_amc_limits(self):
        """ Auto-load limits from Product Master """
        if self.product_id:
            # Clear old lines (Command 5)
            new_lines = [(5, 0, 0)]
            
            # Get master limits
            master_limits = self.product_id.product_tmpl_id.amc_part_limit_ids
            
            for limit in master_limits:
                new_lines.append((0, 0, {
                    'product_id': limit.part_id.id,
                    'allowed_qty': limit.allowed_qty,
                    'consumed_qty': 0.0,
                }))
            
            self.coverage_ids = new_lines
            
            # Trigger date logic too
            self._onchange_warranty_dates()
            
    
    def update_consumption(self):
        """ Recalculate consumed quantities based on done service orders """
        for contract in self:
            # Get all DONE orders
            done_orders = contract.service_ids.filtered(lambda s: s.state in ['done', 'invoiced'])
            
            for coverage in contract.coverage_ids:
                total_used = 0.0
                for order in done_orders:
                    for line in order.parts_line_ids:
                        if line.product_id == coverage.product_id:
                            # Total Qty - Chargeable Qty = Free Qty Used
                            free_qty_used = line.qty - line.qty_chargeable
                            total_used += max(0.0, free_qty_used)
                
                # Write the new total to the stored field
                coverage.consumed_qty = total_used
    
    def action_create_invoice(self):
        """ Generate Invoice for the AMC Contract Amount """
        if self.amount <= 0:
            raise UserError(_("Contract amount must be greater than 0 to create an invoice."))
        
        if self.invoice_id:
             raise UserError(_("An invoice has already been created for this contract."))

        # Create Invoice
        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_origin': self.name,
            'ro_technician_id': self.technician_id.id,  # Pass Technician to Invoice
            'invoice_line_ids': [(0, 0, {
                'name': f"AMC Contract: {self.name} ({self.product_id.name})",
                'quantity': 1,
                'price_unit': self.amount,
            })],
        }
        
        invoice = self.env['account.move'].create(invoice_vals)
        self.invoice_id = invoice.id
        
        return {
            'name': 'AMC Invoice',
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
        }
    
    
    def action_view_invoice(self):
        """ Open the linked Invoice """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Invoice',
            'view_mode': 'form',
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'target': 'current',
        }
    
    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('ro.amc') or 'New'
        return super(ROAMC, self).create(vals)

    @api.model
    def _cron_generate_service_orders(self):
        """ Cron to auto-create service orders based on frequency  """
        active_amcs = self.search([('state', '=', 'active'), ('auto_generate_service', '=', True)])
        for amc in active_amcs:
            # Simplified logic: Check if a service exists recently, if not create one
            # In a real scenario, you would calculate exact next dates based on start_date
            last_service = self.env['ro.service.order'].search([
                ('contract_id', '=', amc.id)
            ], order='scheduled_date desc', limit=1)
            
            next_date = False
            if not last_service:
                next_date = amc.start_date
            else:
                if amc.frequency == 'monthly':
                    next_date = last_service.scheduled_date + relativedelta(months=1)
                elif amc.frequency == 'quarterly':
                    next_date = last_service.scheduled_date + relativedelta(months=3)
                # ... Add other frequencies
            
            if next_date and next_date <= fields.Date.today():
                self.env['ro.service.order'].create({
                    'partner_id': amc.partner_id.id,
                    'contract_id': amc.id,
                    'product_id': amc.product_id.id,
                    'scheduled_date': next_date,
                    'state': 'new'
                })
    
    def _cron_send_amc_reminders(self):
        """ Sends email for AMCs expiring in exactly 30 days """
        expiry_date = fields.Date.today() + relativedelta(days=30)
        # Find AMCs expiring exactly 30 days from now
        expiring_amcs = self.search([
            ('state', '=', 'active'),
            ('end_date', '=', expiry_date)
        ])
        template_id = self.env.ref('sas_ro_service_management.email_template_amc_expiry')
        
        for amc in expiring_amcs:
            template_id.send_mail(amc.id, force_send=True)
            
    
    
    @api.onchange('partner_id', 'product_id')
    def _onchange_warranty_dates(self):
        """ 
        Auto-set AMC Start Date to be after Warranty Expires.
        """
        # Only run if both customer and product are selected
        if self.partner_id and self.product_id:
            
            # Find ANY active warranty for this customer & product
            warranty = self.env['ro.warranty'].search([
                ('partner_id', '=', self.partner_id.id),
                ('product_id', '=', self.product_id.id),
                ('state', '=', 'active')
            ], limit=1, order='end_date desc') # Get the latest one

            if warranty and warranty.end_date:
                # Calculate new dates
                new_start = warranty.end_date + relativedelta(days=1)
                new_end = new_start + relativedelta(years=1)
                
                # Force update the fields
                self.start_date = new_start
                self.end_date = new_end
                
                # Return a warning so you KNOW it happened
                return {
                    'warning': {
                        'title': "Date Adjusted",
                        'message': f"Found active warranty expiring on {warranty.end_date}. AMC start date aligned to {new_start}."
                    }
                }
    
    
    # 1. VALIDATION: Stop manual activation if date is in future
    @api.constrains('state', 'start_date')
    def _check_activation_date(self):
        for record in self:
            if record.state == 'active' and record.start_date > fields.Date.today():
                raise UserError(_("You cannot activate this contract yet! The Start Date is in the future."))

    # 2. AUTOMATION: Cron Job logic
    @api.model
    def _cron_auto_activate_amc(self):
        """ Finds Draft contracts where Start Date <= Today and activates them """
        today = fields.Date.today()
        
        # Search for contracts that are Draft AND ready to start
        contracts_to_activate = self.search([
            ('state', '=', 'draft'),
            ('start_date', '<=', today)
        ])
        
        # Bulk update them to Active
        if contracts_to_activate:
            contracts_to_activate.write({'state': 'active'})
            
            # Optional: Log it in the chatter
            for contract in contracts_to_activate:
                contract.message_post(body="Contract automatically activated by system based on Start Date.")
                
                
# class ROAMCCoverage(models.Model):
#     _name = 'ro.amc.coverage'
#     _description = 'AMC Part Coverage Limits'

#     amc_id = fields.Many2one('ro.amc', string="Contract")
#     product_id = fields.Many2one('product.product', string="Part", required=True)
#     allowed_qty = fields.Float(string="Allowed Qty", default=1.0, help="Max free replacements allowed per year")
#     consumed_qty = fields.Float(string="Consumed Qty", compute="_compute_consumed", store=True)
#     billed_qty = fields.Float(string="Billed Qty", compute="_compute_billed", store=True,
#                              help="Total quantity billed to customer (chargeable replacements)")
#     remaining_qty = fields.Float(string="Remaining Qty", compute='_compute_remaining_qty', store=True)

#     @api.depends('amc_id.service_ids.parts_line_ids.qty','amc_id.service_ids.parts_line_ids.is_chargeable', 'amc_id.service_ids.state')
#     def _compute_consumed(self):
#         """Compute total FREE quantity consumed"""
#         for rec in self:
#             total_free = 0.0
#             services = rec.amc_id.service_ids.filtered(lambda s: s.state in ['done', 'invoiced'])
            
#             for service in services:
#                 for part in service.parts_line_ids:
#                     if (part.product_id == rec.product_id and 
#                         not part.is_chargeable and  # Only count FREE parts
#                         part.service_order_id.state in ['done', 'invoiced']):
#                         total_free += part.qty
            
#             rec.consumed_qty = total_free
    
#     @api.depends('amc_id.service_ids.parts_line_ids.qty_chargeable',
#                  'amc_id.service_ids.state')
#     def _compute_billed(self):
#         """Compute total CHARGEABLE quantity billed"""
#         for rec in self:
#             total_billed = 0.0
#             services = rec.amc_id.service_ids.filtered(lambda s: s.state in ['done', 'invoiced'])
            
#             for service in services:
#                 for part in service.parts_line_ids:
#                     if (part.product_id == rec.product_id and 
#                         part.qty_chargeable > 0 and  # Only count billed quantity
#                         part.service_order_id.state in ['done', 'invoiced']):
#                         total_billed += part.qty_chargeable
            
#             rec.billed_qty = total_billed
    
#     def get_remaining_qty(self, service_order):
#         """Get remaining free quantity for a specific service order"""
#         self.ensure_one()
        
#         # Calculate total already consumed in previous services
#         previous_services = self.amc_id.service_ids.filtered(
#             lambda s: s.state in ['done', 'invoiced'] and s.id != service_order.id
#         )
        
#         total_consumed = 0.0
#         for service in previous_services:
#             for part in service.parts_line_ids:
#                 if (part.product_id == self.product_id and 
#                     not part.is_chargeable):
#                     total_consumed += part.qty
        
#         # Calculate remaining
#         remaining = self.allowed_qty - total_consumed
#         return max(0, remaining)



class ROAMCCoverage(models.Model):
    _name = 'ro.amc.coverage'
    _description = 'AMC Part Coverage Limits'

    amc_id = fields.Many2one('ro.amc', string="Contract")
    product_id = fields.Many2one('product.product', string="Part", required=True)
    allowed_qty = fields.Float(string="Allowed Qty", default=1.0, help="Max free replacements allowed per year")
    consumed_qty = fields.Float(string="Consumed Qty", compute="_compute_consumed", store=True, 
                               help="Total quantity used so far (free replacements)")
    # consumed_qty = fields.Float(string="Consumed Qty", default=0.0)
    
    billed_qty = fields.Float(string="Billed Qty", compute="_compute_billed", store=True,
                             help="Total quantity billed to customer (chargeable replacements)")
    remaining_qty = fields.Float(string="Remaining Qty", compute="_compute_remaining_qty", store=True,
                                help="Remaining free quantity available")

  
    
    @api.depends('allowed_qty', 'consumed_qty')
    def _compute_remaining_qty(self):  # FIXED METHOD NAME - REMOVED EXTRA UNDERSCORE
        """Compute remaining free quantity"""
        for rec in self:
            rec.remaining_qty = max(0, rec.allowed_qty - rec.consumed_qty)
    
    @api.depends('amc_id.service_ids.parts_line_ids.qty', 
                 'amc_id.service_ids.parts_line_ids.is_chargeable',
                 'amc_id.service_ids.state')
    def _compute_consumed(self):
        """Compute total FREE quantity consumed"""
        for rec in self:
            total_free = 0.0
            # Get ALL done services for this AMC
            services = rec.amc_id.service_ids.filtered(
                lambda s: s.state in ['done', 'invoiced']
            )
            
            for service in services:
                for part in service.parts_line_ids:
                    if (part.product_id == rec.product_id and 
                        part.service_order_id.state in ['done', 'invoiced']):
                        # Count the FREE portion (qty - qty_chargeable)
                        free_qty = part.qty - part.qty_chargeable
                        total_free += free_qty
            
            rec.consumed_qty = total_free
    
    @api.depends('amc_id.service_ids.parts_line_ids.qty_chargeable',
                 'amc_id.service_ids.state')
    def _compute_billed(self):
        """Compute total CHARGEABLE quantity billed"""
        for rec in self:
            total_billed = 0.0
            services = rec.amc_id.service_ids.filtered(lambda s: s.state in ['done', 'invoiced'])
            
            for service in services:
                for part in service.parts_line_ids:
                    if (part.product_id == rec.product_id and 
                        part.qty_chargeable > 0 and
                        part.service_order_id.state in ['done', 'invoiced']):
                        total_billed += part.qty_chargeable
            
            rec.billed_qty = total_billed
    
    # def get_remaining_qty(self, service_order):
    #     """Get remaining free quantity for a specific service order"""
    #     self.ensure_one()
        
    #     # Calculate total already consumed in previous services
    #     previous_services = self.amc_id.service_ids.filtered(
    #         lambda s: s.state in ['done', 'invoiced'] and s.id != service_order.id
    #     )
        
    #     total_consumed = 0.0
    #     # for service in previous_services:
    #     #     for part in service.parts_line_ids:
    #     #         if (part.product_id == self.product_id and 
    #     #             not part.is_chargeable):
    #     #             total_consumed += part.qty
        
    #     for service in previous_services:
    #         for part in service.parts_line_ids:
    #             if part.product_id == self.product_id:
    #                 # Count only FREE portion
    #                 free_qty = part.qty - part.qty_chargeable
    #                 total_consumed += free_qty
        
    #     # Calculate remaining
    #     remaining = self.allowed_qty - total_consumed
    #     return max(0, remaining)
    
    
    def get_remaining_for_service(self, service_order):
        """Get remaining free quantity for a specific service order"""
        self.ensure_one()
        
        # Calculate total already consumed in previous DONE services
        previous_services = self.amc_id.service_ids.filtered(
            lambda s: s.state in ['done', 'invoiced'] and s.id != service_order.id
        )
        
        total_consumed = 0.0
        for service in previous_services:
            for part in service.parts_line_ids:
                if part.product_id == self.product_id:
                    # Count only FREE portion
                    free_qty = part.qty - part.qty_chargeable
                    total_consumed += free_qty
        
        # Calculate remaining
        remaining = self.allowed_qty - total_consumed
        return max(0, remaining)