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
            services = rec.amc_id.service_ids.filtered(lambda s: s.state in ['done', 'invoiced'])
            
            for service in services:
                for part in service.parts_line_ids:
                    if (part.product_id == rec.product_id and 
                        not part.is_chargeable and
                        part.service_order_id.state in ['done', 'invoiced']):
                        total_free += part.qty
            
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
    
    def get_remaining_qty(self, service_order):
        """Get remaining free quantity for a specific service order"""
        self.ensure_one()
        
        # Calculate total already consumed in previous services
        previous_services = self.amc_id.service_ids.filtered(
            lambda s: s.state in ['done', 'invoiced'] and s.id != service_order.id
        )
        
        total_consumed = 0.0
        for service in previous_services:
            for part in service.parts_line_ids:
                if (part.product_id == self.product_id and 
                    not part.is_chargeable):
                    total_consumed += part.qty
        
        # Calculate remaining
        remaining = self.allowed_qty - total_consumed
        return max(0, remaining)