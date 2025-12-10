from odoo import models, fields, api, _
from odoo.exceptions import UserError

class RoVanStock(models.Model):
    _name = 'ro.van.stock'
    _description = 'Technician Standard Stock Configuration'
    _rec_name = 'technician_id'

    technician_id = fields.Many2one('res.users', string='Technician', required=True)
    # Link the technician to a specific stock location (e.g., WH/Stock/Tech A)
    location_id = fields.Many2one('stock.location', string='Technician Location', required=True)
    
    line_ids = fields.One2many('ro.van.stock.line', 'van_stock_id', string='Stock Lines')

    def action_replenish_stock(self):
        """
        Calculates difference between Target Qty and Current Qty.
        Creates an Internal Transfer for the missing items.
        """
        self.ensure_one()
        
        # 1. Prepare the Stock Picking (Transfer) Header
        picking_vals = {
            'picking_type_id': self.env.ref('stock.picking_type_internal').id, # Standard Internal Transfer
            'location_id': self.env.ref('stock.stock_location_stock').id,      # From Main Stock
            'location_dest_id': self.location_id.id,                           # To Tech Location
            'origin': f"Replenishment for {self.technician_id.name}",
        }
        
        move_lines = []
        
        # 2. Loop through the configured parts
        for line in self.line_ids:
            # Get current stock available in the Technician's Location
            product = line.product_id.with_context(location=self.location_id.id)
            current_qty = product.qty_available
            
            # Calculate what is missing
            qty_to_transfer = line.target_qty - current_qty
            
            if qty_to_transfer > 0:
                move_lines.append((0, 0, {
                    'name': line.product_id.name,
                    'product_id': line.product_id.id,
                    'product_uom': line.product_id.uom_id.id,
                    'product_uom_qty': qty_to_transfer, # Only transfer the missing amount
                    'location_id': picking_vals['location_id'],
                    'location_dest_id': picking_vals['location_dest_id'],
                }))

        if not move_lines:
            raise UserError(_("This technician is fully stocked! No items need replenishment."))

        # 3. Create the Picking and Moves
        picking_vals['move_ids_without_package'] = move_lines
        picking = self.env['stock.picking'].create(picking_vals)
        
        # Optional: Confirm the picking immediately so it's ready to validate
        picking.action_confirm()

        # Return the view of the created transfer
        return {
            'name': _('Replenishment Transfer'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': picking.id,
        }

class RoVanStockLine(models.Model):
    _name = 'ro.van.stock.line'
    _description = 'Van Stock Lines'

    van_stock_id = fields.Many2one('ro.van.stock', string='Van Stock')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    target_qty = fields.Integer(string='Target Quantity', default=5, help="Qty the tech should always have")