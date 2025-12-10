# -*- coding: utf-8 -*-
{
    'name': "SAS Warranty & Installation",
    'summary': "Manage RO Sales, Warranties, AMC, and Service Orders",
    'description': """
        Complete RO Management System:
        - Auto-create Warranty from Sale
        - Installation Orders
        - AMC Contracts with Auto-Service Generation
        - Service Orders with Parts Consumption & Invoicing
    """,
    'author': "Peanut Square LLP",
    'website': "[http://www.peanutsquare.com](http://www.peanutsquare.com)",
    'category': 'Services',
    'version': '17.0.1.0.0',
    'depends': ['base', 'sale_management', 'stock', 'account'],
    'data': [
        'security/ro_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/ir_cron_data.xml',
        'data/mail_template_data.xml',
        'views/ro_warranty_views.xml',
        'views/ro_installation_views.xml',
        'views/ro_amc_views.xml',
        'views/ro_service_views.xml',
        'views/res_partner_views.xml',
        'views/product_views.xml',
        'views/sale_order_views.xml',
        'views/ro_menus.xml',
        'views/ro_reporting_views.xml',
        'wizard/fetch_orders_wizard_view.xml',
        'views/ro_legacy_dashboard.xml',
        'views/ro_van_stock_views.xml',
        
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}