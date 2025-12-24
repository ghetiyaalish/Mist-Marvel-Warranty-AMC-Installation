# from odoo import models, api, fields
# from datetime import datetime, date
# import calendar

# class MisReportParser(models.AbstractModel):
#     _name = 'report.sas_ro_service_management.report_mis_template'
#     _description = 'MIS Report Logic'

#     @api.model
#     def _get_report_values(self, docids, data=None):
#         month = int(data.get('month'))
#         year = int(data.get('year'))
        
#         # 1. Get number of days in selected month (e.g., 28, 30, 31)
#         _, num_days = calendar.monthrange(year, month)
#         days_list = list(range(1, num_days + 1)) # [1, 2, 3... 31]

#         # 2. Find all Technicians who have targets or sales
#         technicians = self.env['res.users'].search([]) # Filter by group if needed
        
#         report_data = []
        
#         # Totals for the bottom row
#         total_row = {
#             'target_rev': 0, 'target_call': 0, 
#             'achieved_rev': 0, 'achieved_call': 0,
#             'daily_data': {d: {'rev': 0, 'call': 0} for d in days_list}
#         }

#         for tech in technicians:
#             # A. Get Target
#             target = self.env['ro.technician.target'].search([
#                 ('user_id', '=', tech.id), ('month', '=', data.get('month')), ('year', '=', str(year))
#             ], limit=1)
#             t_rev = target.target_revenue or 0.0
#             t_call = target.target_calls or 0

#             # B. Get Achieved (Actuals) - Example fetching from Invoices/Sales
#             # You must adjust this domain to match where your "Revenue" comes from (Sale Order vs Invoice)
#             start_date = date(year, month, 1)
#             end_date = date(year, month, num_days)
            
#             # Fetch Revenue (Example: Invoices)
#             invoices = self.env['account.move'].search([
#                 ('invoice_user_id', '=', tech.id),
#                 ('move_type', '=', 'out_invoice'),
#                 ('state', '=', 'posted'),
#                 ('invoice_date', '>=', start_date),
#                 ('invoice_date', '<=', end_date)
#             ])
#             achieved_rev = sum(invoices.mapped('amount_untaxed'))

#             # Fetch Calls (Example: CRM Activities)
#             calls = self.env['mail.activity'].search([
#                 ('user_id', '=', tech.id),
#                 ('activity_type_id.name', '=', 'Call'), # Adjust based on your activity name
#                 ('date_deadline', '>=', start_date),
#                 ('date_deadline', '<=', end_date)
#             ])
#             achieved_call = len(calls)

#             # C. Calculate Daily Breakdowns
#             daily_dict = {}
#             for day in days_list:
#                 day_date = date(year, month, day)
                
#                 # Daily Revenue
#                 day_rev = sum(invoices.filtered(lambda i: i.invoice_date == day_date).mapped('amount_untaxed'))
#                 # Daily Calls
#                 day_call = len(calls.filtered(lambda c: c.date_deadline == day_date))
                
#                 daily_dict[day] = {'rev': day_rev, 'call': day_call}
                
#                 # Add to Grand Total
#                 total_row['daily_data'][day]['rev'] += day_rev
#                 total_row['daily_data'][day]['call'] += day_call

#             # D. Calculate Pendings
#             pending_rev = t_rev - achieved_rev
#             # pending_days logic... (Simple version: remaining days in month)
#             today = date.today()
#             if today.month == month and today.year == year:
#                 pending_days = num_days - today.day
#             else:
#                 pending_days = 0 
            
#             req_per_day = pending_rev / pending_days if pending_days > 0 else 0

#             # E. Update Grand Totals
#             total_row['target_rev'] += t_rev
#             total_row['target_call'] += t_call
#             total_row['achieved_rev'] += achieved_rev
#             total_row['achieved_call'] += achieved_call

#             report_data.append({
#                 'name': tech.name,
#                 'target_rev': t_rev,
#                 'target_call': t_call,
#                 'achieved_rev': achieved_rev,
#                 'achieved_call': achieved_call,
#                 'pending_rev': pending_rev,
#                 'pending_days': pending_days,
#                 'req_per_day': req_per_day,
#                 'daily': daily_dict
#             })

#         return {
#             'doc_ids': docids,
#             'doc_model': 'ro.mis.report.wizard',
#             'data': data,
#             'days': days_list,
#             'lines': report_data,
#             'total': total_row,
#         }