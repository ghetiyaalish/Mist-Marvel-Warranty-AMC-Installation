from odoo import models, fields, api
from dateutil.relativedelta import relativedelta

class ROWarranty(models.Model):
    _name = 'ro.warranty'
    _description = 'RO Warranty'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default='New')
    
    # Core Fields
    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    sale_id = fields.Many2one('sale.order', string='Sale Order')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    lot_id = fields.Many2one('stock.lot', string='Serial No', domain="[('product_id', '=', product_id)]")
    
    start_date = fields.Date(string='Start Date', default=fields.Date.context_today)
    end_date = fields.Date(string='End Date')
    coverage = fields.Selection([
        ('parts', 'Parts Only'),
        ('labor', 'Labor Only'),
        ('both', 'Parts & Labor')
    ], string='Coverage', default='both', tracking=True)
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', tracking=True)
    
    notes = fields.Text(string="Notes")
    
    # --- FIELDS REQUIRED BY DASHBOARD ---
    # These are stored here so the Dashboard can read them
    invoice_no = fields.Char(related='sale_id.name', string="Inv. No", store=True)
    sale_date = fields.Datetime(related='sale_id.date_order', string="Sale Date", store=True)
    partner_code = fields.Char(related='partner_id.ref', string="Code", store=True)
    partner_address = fields.Char(related='partner_id.contact_address', string="Address", store=True)
    partner_phone = fields.Char(related='partner_id.phone', string="Contact", store=True)
    partner_mobile = fields.Char(related='partner_id.mobile', string="Other Contact", store=True)
    
    # Contract Status (Stored)
    contract_status = fields.Char(compute='_compute_contract_status', string="Contract", store=True)
    
    # Fixed Type for Warranty
    contract_type = fields.Char(string="Contract Type", default="WARRANTY", readonly=True)

    @api.depends('state', 'end_date')
    def _compute_contract_status(self):
        today = fields.Date.today()
        for rec in self:
            if rec.state == 'active' and rec.end_date and rec.end_date >= today:
                rec.contract_status = 'IN-WARRANTY'
            else:
                rec.contract_status = 'OUT-WARRANTY'

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('ro.warranty') or 'New'
        return super(ROWarranty, self).create(vals)

    def _cron_send_warranty_expiry_reminders(self):
        """ Sends email for Warranties expiring in exactly 30 days """
        expiry_date = fields.Date.today() + relativedelta(days=30)
        expiring_warranties = self.search([('state', '=', 'active'), ('end_date', '=', expiry_date)])
        template_id = self.env.ref('sas_ro_service_management.email_template_warranty_expiry')
        for warranty in expiring_warranties:
            template_id.send_mail(warranty.id, force_send=True)

    # --- Button Actions ---
    def action_open_warranty_form(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'ro.warranty',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }

    def action_view_history(self):
        return {
            'name': 'Service History',
            'type': 'ir.actions.act_window',
            'res_model': 'ro.service.order',
            'view_mode': 'tree,form',
            'domain': [('warranty_id', '=', self.id)],
            'context': {'default_warranty_id': self.id},
        }