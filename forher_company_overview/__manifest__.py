{
    'name': 'Forher Company Overview',
    'version': '1.0',
    'category': 'Company',
    'summary': 'Tổng quan công ty Forher',
    'description': '''
        Quản lý tổng quan công ty Forher:
        - Chi nhánh
        - Cấp phân quyền
        - Lĩnh vực kinh doanh: Thời trang công sở và áo dài
    ''',
    'author': 'Forher IT',
    'depends': ['base', 'mail','hr'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/company_overview_views.xml',
        'views/branch_views.xml',
        'views/permission_level_views.xml',
    ],
    'installable': True,
    'application': True,
}
