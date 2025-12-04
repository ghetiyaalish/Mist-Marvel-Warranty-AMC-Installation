from odoo import models, fields

class ProductComponentWarranty(models.Model):
    _name = 'product.component.warranty'
    _description = 'Specific Component Warranty'

    # Link back to the main product
    product_tmpl_id = fields.Many2one('product.template', string="RO Machine")
    
    # The actual component product (Membrane, Filter, Pump)
    component_id = fields.Many2one('product.product', string="Component", required=True)
    
    # The warranty duration for this component
    warranty_months = fields.Float(string="Warranty (Months)", required=True, default=12.0)
    
    _sql_constraints = [
        ('component_unique', 'unique(product_tmpl_id, component_id)', 'This component is already defined for this product template.'),
    ]


class ProductTemplate(models.Model):    
    _inherit = 'product.template'

    # 1. Main Warranty (for the machine)
    warranty_months = fields.Integer(string="Warranty (Months)", help="Duration of warranty in months")
    requires_installation = fields.Boolean(string="Requires Installation", default=True)
    
    
    # 2.  Component Warranty (For parts inside the machine)
    part_warranty_months = fields.Float(string="Part Warranty (Months)", 
        help="If this part is installed, how long is it covered? (e.g. 0.5 for 6 months)")
    
    #  One2Many field to hold the component list
    component_warranty_ids = fields.One2many(
        'product.component.warranty', 
        'product_tmpl_id', 
        string="Component Warranties"
    )