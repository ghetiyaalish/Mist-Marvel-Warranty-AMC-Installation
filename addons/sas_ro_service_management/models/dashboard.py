from odoo import models, fields, api, tools ,_
from odoo.exceptions import UserError

class ROMachineMaster(models.Model):
    _name = 'ro.machine.master'
    _description = 'Combined Machine Master (Warranty + AMC)'
    _auto = False  # SQL View
    _rec_name = 'product_id'
    _allow_sudo_commands = False

    
    @api.model
    def create(self, vals):
        raise UserError(_("Creating records in Machine Master view is not allowed. This is a read-only reporting view."))

    def write(self, vals):
        raise UserError(_("Editing records in Machine Master view is not allowed. This is a read-only reporting view."))

    def unlink(self):
        raise UserError(_("Deleting records from Machine Master view is not allowed. This is a read-only reporting view."))

    id = fields.Integer(string='ID')

    # --- Fields ---
    start_date = fields.Date(string="Date" , readonly=True )
    # sale_date = fields.Datetime(related='sale_id.date_order', string="Sale Date", store=True)
    sale_id = fields.Many2one('sale.order', string='Sale Order' , readonly=True)
    invoice_no = fields.Char(related='sale_id.name', string="Inv. No", store=True , readonly=True)   
    
    sale_date = fields.Datetime(related='sale_id.date_order', string="Sale Date", store=True , readonly=True)    
    # partner_code = fields.Char(related='partner_id.ref', string="Code", store=True)

    contract_type = fields.Char(string="Contract Type" , readonly=True)
    # Address & Contacts

    # partner_address = fields.Char(related='partner_id.contact_address', string="Address", store=True)

    # partner_phone = fields.Char(related='partner_id.phone', string="Contact", store=True)

    # partner_mobile = fields.Char(related='partner_id.mobile', string="Other Contact", store=True)
    partner_id = fields.Many2one('res.partner', string='Customer', required=True , readonly=True)
    partner_code = fields.Char(string="Code" , readonly=True)
    partner_address = fields.Char(string="Address" , readonly=True)
    partner_phone = fields.Char(string="Contact" , readonly=True)
    partner_mobile = fields.Char(string="Other Contact" , readonly=True)
    product_id = fields.Many2one('product.product', string='Product', required=True , readonly=True)    
    # lot_id = fields.Many2one('stock.lot', string="Serial No")
    contract_status = fields.Char(compute='_compute_contract_status', string="Contract" ,store=True , readonly=True)

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default='New' )

    end_date = fields.Date(string="End Date" , readonly=True)
    
    # --- NEW: State Field (Required for colors) ---
    state = fields.Char(string="Status" , readonly=True) 
    type_label = fields.Char(string="Type" , readonly=True)
    
    # Technical fields
    res_id = fields.Integer(string="Resource ID" , readonly=True )
    res_model = fields.Char(string="Resource Model" , readonly=True)

    # def init(self):
    #     tools.drop_view_if_exists(self.env.cr, self._table)
    #     self.env.cr.execute("""
    #         CREATE OR REPLACE VIEW ro_machine_master AS (
    #             SELECT
    #                 row_number() OVER() AS id,
    #                 sub.*
    #             FROM (
    #                 -- 1. WARRANTIES
    #                 SELECT
    #                     w.invoice_no,
    #                     w.sale_date as sale_date,
    #                     w.start_date as start_date,
    #                     w.partner_id,
    #                     p.ref as partner_code,
    #                     p.street as partner_address,
    #                     p.phone as partner_phone,
    #                     p.mobile as partner_mobile,
    #                     w.product_id,
    #                     w.lot_id,
    #                     w.end_date,
    #                     w.state as state,  -- <--- ADDED THIS
    #                     w.contract_status,
    #                     w.contract_type as type_label,
    #                     w.id as res_id,
    #                     'ro.warranty' as res_model
    #                 FROM ro_warranty w
    #                 JOIN res_partner p ON w.partner_id = p.id
                    
    #                 UNION ALL
                    
    #                 -- 2. AMCs
    #                 SELECT
    #                     a.name as invoice_no,
    #                     a.start_date as start_date,
    #                     a.partner_id,
    #                     p.ref as partner_code,
    #                     p.street as partner_address,
    #                     p.phone as partner_phone,
    #                     p.mobile as partner_mobile,
    #                     a.product_id,
    #                     NULL as lot_id,
    #                     a.end_date,
    #                     a.state as state, -- <--- ADDED THIS
    #                     CASE 
    #                         WHEN a.state = 'active' AND a.end_date >= CURRENT_DATE THEN 'FREE SERVICE' 
    #                         ELSE 'EXPIRED' 
    #                     END as contract_status,
    #                     a.contract_type as type_label,
    #                     a.id as res_id,
    #                     'ro.amc' as res_model
    #                 FROM ro_amc a
    #                 JOIN res_partner p ON a.partner_id = p.id
    #             ) sub
    #         )
    #     """)
    
    
    # def init(self):
    #     tools.drop_view_if_exists(self.env.cr, self._table)
    #     self.env.cr.execute("""
    #         CREATE OR REPLACE VIEW ro_machine_master AS (
    #             SELECT
    #                 row_number() OVER() AS id,
    #                 sub.*
    #             FROM (
    #                 -- 1. WARRANTIES
    #                 SELECT
    #                     w.sale_id as sale_id,  -- ADD THIS FIELD

    #                     w.invoice_no,
    #                     w.sale_date as sale_date,
    #                     w.start_date as start_date,
    #                     w.partner_id,
    #                     p.ref as partner_code,
    #                     p.street as partner_address,
    #                     p.phone as partner_phone,
    #                     p.mobile as partner_mobile,
    #                     w.product_id,
    #                     w.lot_id,
    #                     w.end_date,
    #                     w.state as state,
    #                     w.contract_status,
    #                     w.contract_type as type_label,
    #                     w.id as res_id,
    #                     'ro.warranty' as res_model
    #                 FROM ro_warranty w
    #                 JOIN res_partner p ON w.partner_id = p.id
                    
    #                 UNION ALL
                    
    #                 -- 2. AMCs
    #                 SELECT
    #                     a.sale_id as sale_id,
    #                     a.name as invoice_no,
    #                     a.start_date as sale_date,     
    #                     a.start_date as start_date,
    #                     a.partner_id,
    #                     p.ref as partner_code,
    #                     p.street as partner_address,
    #                     p.phone as partner_phone,
    #                     p.mobile as partner_mobile,
    #                     a.product_id,
    #                     NULL as lot_id,
    #                     a.end_date,
    #                     a.state as state,
    #                     CASE 
    #                         WHEN a.end_date >= CURRENT_DATE AND a.state != 'cancelled' THEN 'FREE SERVICE' 
    #                         ELSE 'EXPIRED' 
    #                     END as contract_status,
    #                     a.contract_type as type_label,
    #                     a.id as res_id,
    #                     'ro.amc' as res_model
    #                 FROM ro_amc a
    #                 JOIN res_partner p ON a.partner_id = p.id
    #             ) sub
    #         )
    #     """)
    
    
    
    
    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)

        self.env.cr.execute("""
            CREATE OR REPLACE VIEW ro_machine_master AS (
                SELECT
                    row_number() OVER() AS id,
                    sub.*
                FROM (
                    -- =======================
                    -- 1. WARRANTY RECORDS
                    -- =======================
                    SELECT
                        w.invoice_no                    AS invoice_no,
                        w.invoice_no                    AS name,
                        w.sale_date                     AS sale_date,
                        w.sale_id                       AS sale_id,
                        w.contract_type                 AS contract_type,
                        w.start_date                    AS start_date,
                        w.partner_id                    AS partner_id,
                        p.ref                           AS partner_code,
                        p.street                        AS partner_address,
                        p.phone                         AS partner_phone,
                        p.mobile                        AS partner_mobile,
                        w.product_id                    AS product_id,
                        w.lot_id                        AS lot_id,
                        w.end_date                      AS end_date,
                        w.state                         AS state,
                        w.contract_status               AS contract_status,
                        w.contract_type                 AS type_label,
                        w.id                            AS res_id,
                        'ro.warranty'                   AS res_model
                    FROM ro_warranty w
                    JOIN res_partner p ON w.partner_id = p.id

                    UNION ALL

                    -- =======================
                    -- 2. AMC RECORDS
                    -- =======================
                    SELECT
                        a.name                          AS invoice_no,
                        a.name                          AS name,
                        a.create_date                   AS sale_date,
                        a.sale_id                       AS sale_id,
                        a.contract_type                 AS contract_type,
                        a.start_date                    AS start_date,
                        a.partner_id                    AS partner_id,
                        p.ref                           AS partner_code,
                        p.street                        AS partner_address,
                        p.phone                         AS partner_phone,
                        p.mobile                        AS partner_mobile,
                        a.product_id                    AS product_id,
                        NULL::integer                   AS lot_id,
                        a.end_date                      AS end_date,
                        a.state                         AS state,
                        CASE 
                            WHEN a.end_date >= CURRENT_DATE 
                            AND a.state != 'cancelled' 
                            THEN 'FREE SERVICE'
                            ELSE 'EXPIRED'
                        END                             AS contract_status,
                        a.contract_type                 AS type_label,
                        a.id                            AS res_id,
                        'ro.amc'                        AS res_model
                    FROM ro_amc a
                    JOIN res_partner p ON a.partner_id = p.id
                ) sub
            )
        """)

        
        
    # --- Keep your Button Actions below (action_log_complaint, etc.) ---
    def action_log_complaint(self):
        vals = {
            'default_partner_id': self.partner_id.id,
            'default_product_id': self.product_id.id,
        }
        if self.res_model == 'ro.warranty':
            vals['default_warranty_id'] = self.res_id
        elif self.res_model == 'ro.amc':
            vals['default_contract_id'] = self.res_id
            
        return {
            'name': 'Log Complaint',
            'type': 'ir.actions.act_window',
            'res_model': 'ro.service.order',
            'view_mode': 'form',
            'context': vals,
            'target': 'current',
        }


    def action_open_source(self):
        """ 
        Smart Edit Button: Opens the real record (Warranty or AMC) 
        using the stored resource ID, not the dashboard row ID.
        """
        return {
            'name': 'Edit Record',
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,  # Dynamic: 'ro.warranty' or 'ro.amc'
            'res_id': self.res_id,        # The REAL ID of the record
            'view_mode': 'form',
            'target': 'current',
        }
        
    # def action_open_warranty_form(self):

    #     """ The 'Edit' Button Logic """
    #     return {
    #         'type': 'ir.actions.act_window',
    #         'res_model': 'ro.warranty',
    #         'view_mode': 'form',
    #         'res_id': self.id,
    #         'target': 'current',
    #     }
    
    def action_open_warranty_form(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,  # ro.warranty OR ro.amc
            'res_id': self.res_id,        # REAL Warranty/AMC ID
            'view_mode': 'form',
            'target': 'current',
        }



    # def action_view_history(self):
    #     """ The 'History' Button Logic (Shows past service orders) """
    #     return {
    #         'name': 'Service History',
    #         'type': 'ir.actions.act_window',
    #         'res_model': 'ro.service.order',
    #         'view_mode': 'tree,form',
    #         'domain': [('warranty_id', '=', self.id)],
    #         'context': {'default_warranty_id': self.id},
    #     }


    def action_view_history(self):
        """ 
        Smart History: Shows service orders for this specific contract 
        (Warranty or AMC) based on the record type.
        """
        domain = []
        
        # Build domain based on record type
        if self.res_model == 'ro.warranty':
            domain = [('warranty_id', '=', self.res_id)]
            context = {'default_warranty_id': self.res_id}
        elif self.res_model == 'ro.amc':
            domain = [('contract_id', '=', self.res_id)]
            context = {'default_contract_id': self.res_id}
        else:
            # Fallback: Filter by Customer AND Product
            domain = [
                ('partner_id', '=', self.partner_id.id),
                ('product_id', '=', self.product_id.id)
            ]
            context = {'default_partner_id': self.partner_id.id}
        
        return {
            'name': 'Service History',
            'type': 'ir.actions.act_window',
            'res_model': 'ro.service.order',
            'view_mode': 'tree,form',
            'domain': domain,
            'context': context
        }
    
