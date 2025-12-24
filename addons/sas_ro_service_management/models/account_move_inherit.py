from odoo import models, api , fields
from dateutil.relativedelta import relativedelta
class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.model_create_multi
    def create(self, vals_list):
        """ Global Intercept: Force Journal based on GST Treatment for ALL invoices """
        for vals in vals_list:
            # 1. Only apply logic for Customer Invoices (out_invoice)
            if vals.get('move_type') == 'out_invoice':
                
                # 2. Get the Partner ID from the data being created
                partner_id = vals.get('partner_id')
                if partner_id:
                    partner = self.env['res.partner'].browse(partner_id)
                    gst_treatment = partner.l10n_in_gst_treatment
                    
                    # 3. Define Logic: Who is B2B?
                    # (Adjust this list if 'overseas' or others count as B2B for you)
                    b2b_types = ['regular', 'composition', 'special_economic_zone', 'deemed_export']
                    
                    target_code = 'B2B' if gst_treatment in b2b_types else 'B2C'
                    
                    # 4. Find the matching Journal
                    # We check 'company_id' to support multi-company, defaulting to current env
                    company_id = vals.get('company_id') or self.env.company.id
                    
                    journal = self.env['account.journal'].search([
                        ('code', '=', target_code), 
                        ('type', '=', 'sale'), 
                        ('company_id', '=', company_id)
                    ], limit=1)
                    
                    # 5. FORCE the Journal ID
                    if journal:
                        vals['journal_id'] = journal.id

        # 6. Proceed with standard Odoo creation using our modified values
        return super(AccountMove, self).create(vals_list)
    
    
    
    # 2. NEW LOGIC: Schedule Payment Reminders on Post
    def action_post(self):
        # Let Odoo do its standard posting work first
        res = super(AccountMove, self).action_post()
        
        for move in self:
            # Only run for Customer Invoices
            if move.move_type == 'out_invoice':
                
                # Find the separate installment lines Odoo created
                # (Odoo splits the debt into multiple lines if you use Payment Terms)
                installment_lines = move.line_ids.filtered(
                    lambda l: l.account_id.account_type == 'asset_receivable' and l.date_maturity
                )
                
                # Who should make the call? 
                # Priority: 1. Collection Technician (if set) -> 2. Salesperson -> 3. Current User
                # (You added 'ro_technician_id' in a previous step, so we use it here)
                assignee = move.ro_technician_id or move.invoice_user_id or self.env.user

                for line in installment_lines:
                    due_date = line.date_maturity
                    amount = line.amount_currency or line.balance
                    
                    # Calculate Reminder Date: 2 Days BEFORE the due date
                    reminder_date = due_date - relativedelta(days=2)
                    
                    # Only schedule if the reminder is for the future 
                    # (We don't need a reminder for the immediate 1st down payment if it's today)
                    if reminder_date >= fields.Date.today():
                        
                        self.env['mail.activity'].create({
                            'res_id': move.id,
                            'res_model_id': self.env['ir.model']._get('account.move').id,
                            'activity_type_id': self.env.ref('mail.mail_activity_data_call').id, # Creates a "Call" activity
                            'summary': f'Payment Follow-up: {amount:.2f}',
                            'note': f'Installment of {amount:.2f} is due on {due_date}. Please call customer for collection.',
                            'date_deadline': reminder_date, # This sets the activity date
                            'user_id': assignee.id,
                        })
        return res