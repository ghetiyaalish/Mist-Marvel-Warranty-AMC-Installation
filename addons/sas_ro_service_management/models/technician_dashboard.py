from odoo import models, fields, tools

class TechnicianDashboard(models.Model):
    _name = 'ro.technician.dashboard'
    _description = 'Technician Excel-Style Dashboard'
    _auto = False
    
    technician_id = fields.Many2one('res.users', string='Technician', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    
    # 1. Targets (From Step 1)
    target_revenue = fields.Float(string='Target Revenue', readonly=True)
    target_calls = fields.Integer(string='Target Calls', readonly=True)

    # 2. Achieved (From Invoices & Operations)
    achieved_revenue = fields.Float(string='Achieved Revenue', readonly=True)
    achieved_calls = fields.Integer(string='Achieved Calls', readonly=True)
    
    # 3. Calculated Fields (For the Report)
    pending_revenue = fields.Float(string='Pending Revenue', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW ro_technician_dashboard AS (
                SELECT
                    ROW_NUMBER() OVER () as id,
                    sub.technician_id,
                    sub.date,
                    SUM(sub.target_revenue) as target_revenue,
                    SUM(sub.target_calls) as target_calls,
                    SUM(sub.achieved_revenue) as achieved_revenue,
                    SUM(sub.achieved_calls) as achieved_calls,
                    (SUM(sub.target_revenue) - SUM(sub.achieved_revenue)) as pending_revenue
                FROM (
                    -- A. TARGETS
                    SELECT 
                        technician_id,
                        month_date as date,
                        target_revenue,
                        target_calls,
                        0 as achieved_revenue,
                        0 as achieved_calls
                    FROM ro_technician_target
                    
                    UNION ALL
                    
                    -- B. ACTUAL REVENUE (From Invoices)
                    SELECT 
                        ro_technician_id as technician_id,
                        invoice_date as date,
                        0 as target_revenue,
                        0 as target_calls,
                        amount_untaxed_signed as achieved_revenue,
                        0 as achieved_calls
                    FROM account_move
                    WHERE move_type = 'out_invoice' AND state = 'posted' AND ro_technician_id IS NOT NULL

                    UNION ALL

                    -- C. ACTUAL CALLS (From Operations)
                    -- FIX: Ensure 'assigned_to' and 'status' match your actual field names
                    SELECT 
                        assigned_to as technician_id, 
                        create_date::date as date,
                        0 as target_revenue,
                        0 as target_calls,
                        0 as achieved_revenue,
                        1 as achieved_calls
                    FROM ro_installation
                    -- CHECK THIS LINE BELOW: Change 'state' to 'status' if that is your field name
                    WHERE status = 'done' AND assigned_to IS NOT NULL 

                ) sub
                GROUP BY sub.technician_id, sub.date
            )
        """)