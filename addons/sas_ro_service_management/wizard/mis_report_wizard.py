# from odoo import models, fields, api
# from datetime import date, datetime, timedelta

# class MisReportWizard(models.TransientModel):
#     _name = 'ro.mis.report.wizard'
#     _description = 'MIS Report Wizard'

#     month = fields.Selection([
#         ('01', 'January'), ('02', 'February'), ('03', 'March'), ('04', 'April'),
#         ('05', 'May'), ('06', 'June'), ('07', 'July'), ('08', 'August'),
#         ('09', 'September'), ('10', 'October'), ('11', 'November'), ('12', 'December')
#     ], string='Month', required=True, default=lambda self: str(date.today().month).zfill(2))
    
#     year = fields.Char(string='Year', required=True, default=lambda self: str(date.today().year))

#     def action_print_report(self):
#         data = {
#             'month': self.month,
#             'year': self.year,
#             'month_label': dict(self._fields['month'].selection).get(self.month)
#         }
#         return self.env.ref('your_module_name.action_ro_mis_report').report_action(self, data=data)