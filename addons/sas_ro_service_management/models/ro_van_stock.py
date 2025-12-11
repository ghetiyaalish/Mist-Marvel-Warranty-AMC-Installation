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
        Smart Replenishment:
        1. Calculate what is needed (Target - Current).
        2. Check what is available in Main Warehouse.
        3. Transfer the MINIMUM of those two numbers.
        """
        self.ensure_one()
        
        # Define Locations
        source_location = self.env.ref('stock.stock_location_stock') # Main Warehouse
        dest_location = self.location_id                             # Tech Location
        
        picking_vals = {
            'picking_type_id': self.env.ref('stock.picking_type_internal').id, 
            'location_id': source_location.id,
            'location_dest_id': dest_location.id,
            'origin': f"Replenishment for {self.technician_id.name}",
        }
        
        move_lines = []
        partial_stock_notes = [] # To notify user about shortages

        for line in self.line_ids:
            # 1. Calculate Need (Target - Tech Current)
            # We refresh the current qty just to be safe
            product_in_van = line.product_id.with_context(location=dest_location.id)
            current_van_qty = product_in_van.qty_available
            
            qty_needed = line.target_qty - current_van_qty
            
            if qty_needed > 0:
                # 2. Check Availability in Main Warehouse
                # We check 'qty_available' (On Hand) or 'free_qty' (Available to Promise)
                # Using 'qty_available' matches "Present Stock"
                product_in_wh = line.product_id.with_context(location=source_location.id)
                wh_available = product_in_wh.qty_available 
                
                # 3. The Logic: Take whichever is lower
                qty_to_transfer = min(qty_needed, wh_available)
                
                if qty_to_transfer > 0:
                    move_lines.append((0, 0, {
                        'name': line.product_id.name,
                        'product_id': line.product_id.id,
                        'product_uom': line.product_id.uom_id.id,
                        'product_uom_qty': qty_to_transfer,
                        'location_id': source_location.id,
                        'location_dest_id': dest_location.id,
                    }))
                    
                    # If we couldn't give them everything, add a note
                    if qty_to_transfer < qty_needed:
                        partial_stock_notes.append(
                            f"- {line.product_id.name}: Needed {qty_needed}, but Warehouse only had {wh_available}. Transferred {wh_available}."
                        )
                else:
                    # Warehouse is completely empty for this item
                    partial_stock_notes.append(
                        f"- {line.product_id.name}: Needed {qty_needed}, but Warehouse has 0 stock."
                    )

        if not move_lines:
            raise UserError(_("No stock available to transfer! either the technician has enough stock, or the Main Warehouse is empty."))

        # 4. Create the Picking
        picking_vals['move_ids_without_package'] = move_lines
        picking = self.env['stock.picking'].create(picking_vals)
        
        # 5. Log warnings in the chatter if we did a partial transfer
        if partial_stock_notes:
            note_body = "<b>Partial Replenishment Warning:</b><br/>" + "<br/>".join(partial_stock_notes)
            picking.message_post(body=note_body)

        # Confirm the picking
        picking.action_confirm()

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
    current_qty = fields.Float(string="Current Stock", compute="_compute_stock_levels")
    demand_qty = fields.Float(string="To Replenish", compute="_compute_stock_levels")

    @api.depends('product_id', 'target_qty', 'van_stock_id.location_id')
    def _compute_stock_levels(self):
        for line in self:
            if not line.van_stock_id.location_id or not line.product_id:
                line.current_qty = 0.0
                line.demand_qty = 0.0
                continue

            # 1. Get Stock in Technician's Location
            # We filter the product's available quantity by the specific location
            product_in_location = line.product_id.with_context(location=line.van_stock_id.location_id.id)
            line.current_qty = product_in_location.qty_available

            # 2. Calculate Demand (Target - Current)
            # If they have more than target, demand is 0 (we don't take back stock usually)
            line.demand_qty = max(0, line.target_qty - line.current_qty)