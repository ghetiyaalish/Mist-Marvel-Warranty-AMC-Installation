from odoo import models, fields, api

class CrmLead(models.Model):
    _inherit = 'crm.lead'

    ro_customer_category = fields.Selection([
        ('domestic', 'Domestic'),
        ('commercial', 'Commercial'),
        ('industrial', 'Industrial')
    ], string="Customer Category")

    ro_created_datetime = fields.Datetime(
        string="Opportunity Created On",
        readonly=True,
        default=lambda self: fields.Datetime.now()
    )
    
    # 1. Store the exact duration in hours for precise calculation
    hours_to_close = fields.Float(string="Hours to Close", compute='_compute_close_speed', store=True)

    # 2. Create the "Bucket" field for the Report grouping
    conversion_speed = fields.Selection([
        ('fast', 'Under 24 Hours'),
        ('medium', '24 - 48 Hours'),
        ('slow', '48 - 72 Hours'),
        ('week', 'Over 3 Days'),
        ('long', 'Over 1 Week')
    ], string="Conversion Speed", compute='_compute_close_speed', store=True)
    
    
    @api.depends('create_date', 'date_closed', 'stage_id')
    def _compute_close_speed(self):
        for lead in self:
            # Only calculate if the lead is Won/Closed
            if lead.date_closed and lead.create_date:
                # Calculate total seconds difference
                duration_seconds = (lead.date_closed - lead.create_date).total_seconds()
                hours = duration_seconds / 3600.0
                lead.hours_to_close = hours

                # Assign the "Bucket" based on hours
                if hours <= 24:
                    lead.conversion_speed = 'fast'
                elif 24 < hours <= 48:
                    lead.conversion_speed = 'medium'
                elif 48 < hours <= 72:
                    lead.conversion_speed = 'slow'
                elif 72 < hours <= 168:  # 168 hours = 7 days
                    lead.conversion_speed = 'week'
                else:
                    lead.conversion_speed = 'long'
            else:
                lead.hours_to_close = 0.0
                lead.conversion_speed = False
