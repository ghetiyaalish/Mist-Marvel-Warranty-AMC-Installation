# from odoo import models, fields

# class SalesTarget(models.Model):
#     _name = 'ro.technician.target'
#     _description = 'Technician Monthly Targets'

#     user_id = fields.Many2one('res.users', string='Technician', required=True)
#     month = fields.Selection([
#         ('01', 'January'), ('02', 'February'), ('03', 'March'), ('04', 'April'),
#         ('05', 'May'), ('06', 'June'), ('07', 'July'), ('08', 'August'),
#         ('09', 'September'), ('10', 'October'), ('11', 'November'), ('12', 'December')
#     ], string='Month', required=True)
#     year = fields.Char(string='Year', required=True, default=lambda self: str(fields.Date.today().year))
    
#     target_revenue = fields.Float(string='Target Revenue')
#     target_calls = fields.Integer(string='Target Calls')