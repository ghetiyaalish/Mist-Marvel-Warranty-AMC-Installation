from odoo import models, fields, tools

class TechnicianPerformanceReport(models.Model):
    _name = 'ro.technician.report'
    _description = 'Technician Performance Analysis'
    _auto = False  # This creates a SQL View
    _rec_name = 'date'

    # Fields
    technician_id = fields.Many2one('res.users', string='Technician', readonly=True)
    order_type = fields.Selection([
        ('installation', 'Installation Order'),
        ('service', 'Service Order')
    ], string='Order Type', readonly=True)
    state = fields.Selection([
        ('draft', 'Pending/New'),
        ('new', 'New'),             # Added based on your service order states
        ('assigned', 'Assigned'),   # Added based on your service order states
        ('in_progress', 'In Progress'), # Added based on your service order states
        ('done', 'Completed'),
        ('invoiced', 'Invoiced'),
        ('cancel', 'Cancelled'),
        ('cancelled', 'Cancelled')
    ], string='Status', readonly=True)
    date = fields.Datetime(string='Date', readonly=True)
    nbr = fields.Integer(string='# Count', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW ro_technician_report AS (
                SELECT
                    ROW_NUMBER() OVER () as id,
                    sub.technician_id,
                    sub.order_type,
                    sub.state,
                    sub.date,
                    1 as nbr
                FROM (
                    -- 1. INSTALLATION ORDERS
                    -- (Assuming field is 'assigned_to' and status is 'status')
                    SELECT 
                        assigned_to as technician_id,
                        'installation' as order_type,
                        status as state,
                        create_date as date
                    FROM ro_installation
                    WHERE assigned_to IS NOT NULL
                    
                    UNION ALL
                    
                    -- 2. SERVICE ORDERS
                    -- (We found the field is 'assigned_to' in your code)
                    SELECT 
                        assigned_to as technician_id,  -- <--- FIXED HERE
                        'service' as order_type,
                        state,
                        create_date as date
                    FROM ro_service_order
                    WHERE assigned_to IS NOT NULL      -- <--- FIXED HERE
                ) sub
            )
        """)