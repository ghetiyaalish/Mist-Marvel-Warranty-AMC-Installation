from odoo import models, fields

class TechnicianTarget(models.Model):
    _name = 'ro.technician.target'
    _description = 'Technician Monthly Target'

    technician_id = fields.Many2one('res.users', string='Technician', required=True)
    month_date = fields.Date(string='Month', required=True, help="Select the first day of the month")
    target_revenue = fields.Float(string='Target Revenue')
    target_calls = fields.Integer(string='Target Calls (Install + Service)')