{
    'name': 'SAS Product Warranty',
    'version': '17.0.1.0.0',
    'category': 'Sale',
    'summary': 'Warranty management used to manage warranty of product',
    'description': """The "Warranty Management" module enables businesses to 
    efficiently track product warranties, including expiration dates and 
    associated customer details. Seamlessly integrated with sales processes,
    it facilitates easy warranty claim creation from sales orders and enhances
    customer experience with website warranty registration.""",
    'author': 'Peanut Square LLP',
    'company': 'Peanut Square LLP',
    'maintainer': 'Peanut Square LLP',
    'website': "https://sas.peanutsquare.com",
    'depends': ['mail', 'sale_management', 'website'],
    'data': [
        'data/warranty_sequence.xml',
        'data/website_warranty_menu_data.xml',
        'security/ir.model.access.csv',
        'views/product_template_views.xml',
        'views/sale_order_views.xml',
        'views/website_registration_templates.xml',
        'views/warranty_claim_views.xml',
        'views/portal_templates.xml',
        'views/res_partner_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'sas_product_warranty/static/src/js'
            '/website_registration.js',
            'sas_product_warranty/static/src/css'
            '/sas_product_warranty.css',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
}
