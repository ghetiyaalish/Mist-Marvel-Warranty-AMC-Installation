/** @odoo-module */

import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart } from "@odoo/owl";

// --- 1. THE FILTER BAR COMPONENT ---
class RoFilterBar extends Component {
    setup() {
        this.orm = useService("orm");
        this.state = useState({
            date_from: '',
            date_to: '',
            technician_id: 'all',
            status: 'all',
            text_input: ''
        });

        this.technicians = [];
        this.filterConfig = this.getFilterConfig(this.props.resModel);

        onWillStart(async () => {
            try {
                // Fetch Technicians
                this.technicians = await this.orm.searchRead("res.users", [], ["id", "name"]);
            } catch (e) {
                console.error("Error fetching technicians:", e);
            }
        });
    }

    getFilterConfig(model) {
        // CONFIGURATION FOR EACH DASHBOARD
        if (model === 'ro.machine.master') {
            return {
                showDate: false,
                showTech: false, 
                statusOptions: [
                    { value: 'IN-WARRANTY', label: 'In Warranty' },
                    { value: 'OUT-WARRANTY', label: 'Out Warranty' },
                    { value: 'FREE SERVICE', label: 'Free Service' }
                ],
                textLabel: "Invoice / Customer"
            };
        } 
        else if (model === 'ro.service.part.line') {
            return {
                showDate: true,
                showTech: true,
                statusOptions: [], 
                textLabel: "Part Name / Customer"
            };
        } 
        else if (model === 'account.move') {
            return {
                showDate: true,
                showTech: true,
                statusOptions: [
                    { value: 'paid', label: 'Paid' },
                    { value: 'not_paid', label: 'Not Paid' },
                    { value: 'partial', label: 'Partial' }
                ],
                textLabel: "Voucher / Customer"
            };
        }
        return { showDate: false, showTech: false, statusOptions: [], textLabel: "Search..." };
    }

    async onSearchClick() {
        const domain = [];
        const model = this.props.resModel;
    
        // ---------------- DATE ----------------
        if (this.state.date_from) {
            const dateField = model === 'account.move' ? 'invoice_date' :
                              model === 'ro.service.part.line' ? 'date_done' : 'create_date';
            domain.push([dateField, '>=', this.state.date_from]);
        }
        if (this.state.date_to) {
            const dateField = model === 'account.move' ? 'invoice_date' :
                              model === 'ro.service.part.line' ? 'date_done' : 'create_date';
            domain.push([dateField, '<=', this.state.date_to]);
        }
    
        // ---------------- TECHNICIAN ----------------
        if (this.state.technician_id !== 'all' && model !== 'ro.machine.master') {
            domain.push(['technician_id', '=', parseInt(this.state.technician_id)]);
        }
    
        // ---------------- STATUS ----------------
        if (this.state.status !== 'all') {
            if (model === 'ro.machine.master') {
                domain.push(['contract_status', '=', this.state.status]);
            } else if (model === 'account.move') {
                domain.push(['payment_state', '=', this.state.status]);
            }
        }
    
        // ---------------- TEXT SEARCH ----------------
        if (this.state.text_input) {
            const val = this.state.text_input;
            if (model === 'ro.machine.master') {
                domain.push('|', ['invoice_no', 'ilike', val], ['partner_id.name', 'ilike', val]);
            } 
            else if (model === 'ro.service.part.line') {
                domain.push('|', ['product_id.name', 'ilike', val], ['customer_id.name', 'ilike', val]);
            } 
            else if (model === 'account.move') {
                domain.push('|', ['name', 'ilike', val], ['partner_id.name', 'ilike', val]);
            }
        }
    
        // ----- FINAL ODOO 17 FIX -----
        // const searchModel = this.env.searchModel;
        // await searchModel.setDomain(domain);  // <-- key line ✔
        

        const searchModel = this.env.searchModel;
        
        // 1. Clear previous search filters (Optional: keeps it clean)
        if (searchModel.clearQuery) {
            searchModel.clearQuery();
        }

        // 2. Apply the new domain
        if (domain.length > 0) {
            try {
                // splitAndAddDomain parses the domain and adds it as search facets
                await searchModel.splitAndAddDomain(domain);
            } catch (e) {
                console.error("Search Error:", e);
            }
        }

    }
        
    async onClearClick() {
        this.state.date_from = '';
        this.state.date_to = '';
        this.state.technician_id = 'all';
        this.state.status = 'all';
        this.state.text_input = '';
    
        const searchModel = this.env.searchModel;
        // await searchModel.setDomain([]);   // reset filters ✔
        // await searchModel.setDomainParts({ domain: [] });

    }
    
}

// Template registration
RoFilterBar.template = "sas_ro_service_management.RoFilterBar";


// --- 2. THE CONTROLLER (THIS WAS THE MISSING PART) ---
export class RoDashboardController extends ListController {
    // !!! THIS LINE FIXES YOUR ERROR !!!
    // It tells the controller: "I am using the RoFilterBar component in my XML"
    static components = { ...ListController.components, RoFilterBar }; 

    setup() {
        super.setup();
    }
}


// --- 3. VIEW REGISTRATION ---
export const RoDashboardView = {
    ...listView,
    Controller: RoDashboardController,
    buttonTemplate: "sas_ro_service_management.DashboardButtons",
    // template: "sas_ro_service_management.DashboardButtons",

};

registry.category("views").add("ro_dashboard_view", RoDashboardView);

